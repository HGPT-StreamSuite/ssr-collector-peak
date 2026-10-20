"""Operator-run synthetic acceptance, separate CLI processes and a readonly viewer.

This tool is not an acquisition route, core dependency, or knowledge publisher.
The optional real archive is opened exclusively with SQLite mode=ro/query_only.
"""
from __future__ import annotations

import argparse
import hashlib
import http.client
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import threading
import unicodedata
import uuid
import webbrowser
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

from ssr_collector_peak.primitives import ContractError, canonical, digest, private_output

COLLECTOR = Path(__file__).resolve().parents[1]


def file_hash(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open('rb') as file:
        for block in iter(lambda: file.read(1024 * 1024), b''):
            hasher.update(block)
    return hasher.hexdigest()


def need(condition: Any, message: str) -> None:
    if not condition:
        raise ContractError(message)


def commit(repo: Path) -> str:
    result = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=repo, capture_output=True, text=True, encoding='utf-8')
    need(result.returncode == 0, '無法讀取 repo commit')
    return result.stdout.strip()


def worktree_status(repo: Path) -> str:
    result = subprocess.run(['git', 'status', '--porcelain'], cwd=repo, capture_output=True, text=True, encoding='utf-8')
    need(result.returncode == 0, '無法讀取工作樹狀態')
    return result.stdout.strip()


def read_database(path: Path, *, stage: bool = False, formal: bool = False, query: str = '') -> dict[str, Any]:
    """Every request reads current SQLite rows. Missing data never gets a demo substitute."""
    need(path.is_file(), '指定的資料庫不存在')
    db = sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True)
    db.row_factory = sqlite3.Row
    try:
        db.execute('PRAGMA query_only=ON')
        tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        names = ['sources', 'snapshots', 'observations', 'events'] if stage else ['sources', 'snapshots', 'entries', 'entry_revisions', 'collection_receipts']
        counts = {name: db.execute('SELECT count(*) FROM ' + name).fetchone()[0] if name in tables else 0 for name in names}
        need({'sources', 'snapshots'} <= tables, '不是可辨識的來源資料庫')
        sources = [dict(r) for r in db.execute('SELECT source_id,url,latest_snapshot FROM sources ORDER BY source_id')]
        if stage:
            docs = [dict(r) for r in db.execute('SELECT snapshot_id,source_id,captured_at,body,length(raw) AS raw_bytes FROM snapshots ORDER BY captured_at')]
            for doc in docs:
                row = db.execute('SELECT observed_at,metadata_json FROM observations WHERE snapshot_id=? ORDER BY observation_id DESC LIMIT 1', (doc['snapshot_id'],)).fetchone()
                doc.update(observed_at=row['observed_at'], metadata=json.loads(row['metadata_json']), body_sha256=digest(doc['body']))
            return {'role': 'collector 私有暫存（合成）', 'counts': counts, 'sources': sources, 'documents': docs, 'readonly': True}
        states = dict(db.execute('SELECT status,count(*) FROM entry_revisions GROUP BY status'))
        current_states = dict(db.execute('SELECT r.status,count(*) FROM entries e JOIN entry_revisions r ON e.current_revision=r.revision_id GROUP BY r.status'))
        reviewed = db.execute('SELECT count(*) FROM entry_revisions WHERE review_json IS NOT NULL OR published_at IS NOT NULL').fetchone()[0]
        if formal:
            needle = unicodedata.normalize('NFKC', query).casefold().strip()
            samples = []
            for row in db.execute('SELECT e.entry_id,r.status,r.revision_id,r.payload_json FROM entries e JOIN entry_revisions r ON e.current_revision=r.revision_id ORDER BY e.entry_id'):
                payload = json.loads(row['payload_json'])
                searchable = canonical([payload.get(k, '') for k in ['name_en', 'name_zh', 'aliases', 'summary_zh']])
                if not needle or needle in unicodedata.normalize('NFKC', searchable).casefold():
                    samples.append({'entry_id': row['entry_id'], 'revision_id': row['revision_id'], 'status': row['status'],
                                    **{k: payload.get(k) for k in ['name_en', 'name_zh', 'aliases', 'summary_zh']}})
                if len(samples) == 10:
                    break
            return {'role': '既有正式資料庫（唯讀待審預覽，並非正式發布查詢）', 'counts': counts, 'states': states,
                    'current_states': current_states, 'reviewed_or_published': reviewed, 'samples': samples,
                    'query': query, 'readonly': True, 'sha256': file_hash(path)}
        docs = [dict(r) for r in db.execute('SELECT snapshot_id,source_id,fetched_at,raw,raw_sha256,body,body_sha256,metadata_json FROM snapshots ORDER BY fetched_at')]
        for doc in docs:
            doc['metadata'] = json.loads(doc.pop('metadata_json'))
            doc['raw_hash_matches'] = digest(doc.pop('raw')) == doc['raw_sha256']
            doc['body_hash_matches'] = digest(doc['body']) == doc['body_sha256']
        receipts = [dict(r) for r in db.execute('SELECT * FROM collection_receipts ORDER BY observed_at')] if 'collection_receipts' in tables else []
        return {'role': '保存端測試 DB（合成）', 'counts': counts, 'states': states, 'current_states': current_states,
                'reviewed_or_published': reviewed, 'sources': sources, 'documents': docs, 'receipts': receipts, 'readonly': True}
    finally:
        db.close()


class AcceptanceRun:
    def __init__(self, knowledge: Path, root: Path, formal: Path | None):
        self.knowledge = knowledge.resolve()
        need((self.knowledge / 'ssr_knowledge' / 'catalog_cli.py').is_file(), '請指定 ssr-knowledge checkout')
        need((self.knowledge / '.venv' / 'Scripts' / 'python.exe').is_file(), '缺少既有本機 .venv；本工具不建立或安裝環境')
        self.root = private_output(root)
        self.formal = formal.resolve() if formal else None
        if self.formal:
            need(self.formal.is_file(), '指定的正式 DB 不存在；不會建立替代資料')
            need(self.formal.name == 'knowledge.sqlite3', '正式 DB 應為既有 knowledge.sqlite3')
            need(self.formal.parent != self.root and self.formal.parent not in self.root.parents, '測試資料不得放進正式 DB 目錄')
        self.root.mkdir(parents=True, exist_ok=True)
        need(shutil.disk_usage(self.root).free >= 100 * 1024 * 1024, '驗收至少需要 100 MiB 可用空間')
        self.run = self.root / ('run-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S') + '-' + uuid.uuid4().hex[:8])
        self.run.mkdir()
        self.archive = self.run / 'fixture-archive'
        self.stage = self.run / 'collector-stage'
        self.trace: list[dict[str, Any]] = []
        self.artifacts: dict[str, Path] = {}
        self.tests: list[dict[str, Any]] = []
        self.env = {**os.environ, 'PYTHONIOENCODING': 'utf-8', 'UV_PROJECT_ENVIRONMENT': str(self.knowledge / '.venv')}
        self.uv = ['uv', '--cache-dir', str(self.knowledge / '.uv-cache'), '--offline', 'run', '--no-sync']
        self.commits = {'collector': commit(COLLECTOR), 'knowledge': commit(self.knowledge)}
        self.working_trees = {'collector': worktree_status(COLLECTOR), 'knowledge': worktree_status(self.knowledge)}
        self.formal_before = file_hash(self.formal) if self.formal else None
        self.result: dict[str, Any] = {}

    def command(self, label: str, repo: Path, module: str, args: list[Any], expected: int = 0) -> dict[str, Any]:
        argv = [*self.uv, 'python', '-m', module, *map(str, args)]
        proc = subprocess.run(argv, cwd=repo, env=self.env, capture_output=True, text=True, encoding='utf-8', timeout=60)
        try:
            response = json.loads(proc.stdout)
        except ValueError:
            response = {'unparsed_stdout': proc.stdout}
        self.trace.append({'label': label, 'argv': argv, 'cwd': str(repo), 'exit_code': proc.returncode,
                           'expected_exit': expected, 'response': response, 'stderr': proc.stderr})
        need(proc.returncode == expected, label + ' 失敗，請看私有 trace：' + proc.stdout + proc.stderr)
        return response

    def old(self, label: str, *args: Any, expected: int = 0) -> dict[str, Any]:
        # Only the newly-created synthetic archive is ever passed to a writer CLI.
        return self.command(label, self.knowledge, 'ssr_knowledge', ['catalog', '--data-dir', self.archive, *args], expected)

    def new(self, label: str, *args: Any) -> dict[str, Any]:
        return self.command(label, COLLECTOR, 'ssr_collector_peak', list(args))

    def write_json(self, key: str, name: str, value: Any) -> Path:
        path = self.run / name
        path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
        self.artifacts[key] = path
        return path

    def unit_tests(self) -> None:
        for label, repo in [('collector', COLLECTOR), ('knowledge', self.knowledge)]:
            group = ['--group', 'extraction'] if label == 'knowledge' else []
            argv = [*self.uv, *group, 'python', '-m', 'unittest', 'discover', '-s', 'tests', '-v']
            print('執行獨立測試：' + label, flush=True)
            proc = subprocess.run(argv, cwd=repo, env=self.env, capture_output=True, text=True, encoding='utf-8', timeout=90)
            text = proc.stdout + proc.stderr
            path = self.run / (label + '-tests.private.log')
            path.write_text(text, encoding='utf-8')
            self.artifacts[label + '-tests'] = path
            match = re.search(r'Ran (\d+) tests?', text)
            self.tests.append({'repo': label, 'commit': self.commits[label], 'exit_code': proc.returncode,
                               'count': int(match[1]) if match else None, 'sha256': file_hash(path)})
            need(proc.returncode == 0, label + ' 單元測試失敗：' + str(path))

    def execute(self, run_tests: bool = True) -> None:
        try:
            if run_tests:
                self.unit_tests()
            fixture = COLLECTOR / 'fixtures' / 'permitted-source.synthetic.json'
            input_file = COLLECTOR / 'fixtures' / 'permitted-input.synthetic.txt'
            self.artifacts['input'] = input_file
            self.artifacts['source-config'] = fixture
            self.old('中央登記合成檔案來源', 'register-file-source', '--file', fixture)
            db = self.archive / 'knowledge.sqlite3'
            before = file_hash(db)
            plan = self.old('唯讀匯出來源計畫', 'export-source-plan')
            need(file_hash(db) == before, '來源計畫匯出改變了測試 DB')
            plan_file = self.write_json('source-plan', 'source-plan.private.json', plan)
            dry = self.new('可選 HTTP 僅 dry-run', 'http-collect', '--plan', plan_file, '--source-id', 'synthetic-export')
            need(dry['network_requests'] == 0, 'dry-run 不應有網路請求')
            common = ['--plan', plan_file, '--source-id', 'synthetic-export', '--stage-dir', self.stage, '--format', 'plain_text', '--origin', 'synthetic_fixture']
            first = self.new('暫存合成輸入', 'intake-file', *common, '--file', input_file)
            same = self.new('重複暫存同一輸入', 'intake-file', *common, '--file', input_file)
            need(same['state'] == 'unchanged' and same['snapshot_id'] == first['snapshot_id'], '暫存去重失敗')
            bundle = self.new('輸出資料包', 'bundle', '--stage-dir', self.stage, '--snapshot-id', first['snapshot_id'], '--output-dir', self.run / 'handoff')
            self.artifacts['bundle-v1'] = Path(bundle['path'])
            before = file_hash(db)
            checked = self.old('預設驗證不保存', 'ingest-collection', '--file', bundle['path'])
            need(checked['state'] == 'validated_only' and file_hash(db) == before, '預設驗證寫入了 DB')
            saved = self.old('明確保存文件', 'ingest-collection', '--file', bundle['path'], '--apply')
            duplicate = self.old('重複資料包不重存', 'ingest-collection', '--file', bundle['path'], '--apply')
            need(duplicate['state'] == 'unchanged' and not duplicate['archive_changed'], '保存端去重失敗')
            readback = self.old('新程序讀回正文', 'snapshot', '--snapshot-id', saved['snapshot_id'], '--body')
            original_text = input_file.read_bytes().decode('utf-8-sig')
            need(readback['body'] == original_text, '正文讀回不相同')
            queries = []
            for query in ['月', '月亮繩', 'Lunar Rope', '月繩', 'SOURCE_COMMAND']:
                answer = self.old('正式查詢：' + query, 'search', '--text', query)
                need(answer['status'] == 'no_data' and answer['matches'] == [], '文件不能冒充已發布知識')
                queries.append({'input': query, 'status': answer['status'], 'matches': answer['matches']})
            changed = self.run / 'updated.synthetic.txt'
            changed.write_bytes((original_text + '\n合成修訂二：只驗證文件更新與版本；不是 PEAK 知識。\n').encode('utf-8'))
            self.artifacts['updated-input'] = changed
            update = self.new('暫存更新輸入', 'intake-file', *common, '--file', changed)
            bundle2 = self.new('輸出更新資料包', 'bundle', '--stage-dir', self.stage, '--snapshot-id', update['snapshot_id'], '--output-dir', self.run / 'handoff')
            self.artifacts['bundle-v2'] = Path(bundle2['path'])
            updated = self.old('保存更新版本', 'ingest-collection', '--file', bundle2['path'], '--apply')
            self.old('重放舊包不倒退', 'ingest-collection', '--file', bundle['path'], '--apply')
            forged = json.loads(Path(bundle['path']).read_text(encoding='utf-8'))
            forged['document']['metadata']['policy'] = {'allow_fetch': True}
            forged['bundle_id'] = digest(canonical({k: v for k, v in forged.items() if k != 'bundle_id'}))
            bad = self.write_json('rejected', 'forged.collection.json', forged)
            before = file_hash(db)
            rejection = self.old('拒收資料包夾帶權限', 'ingest-collection', '--file', bad, expected=1)
            need(file_hash(db) == before, '拒收卻改變了 DB')
            need(not self.formal or file_hash(self.formal) == self.formal_before, '正式 DB 在驗收期間改變')
            self.result = {'commits': self.commits, 'working_trees': self.working_trees, 'tests': self.tests, 'queries': queries,
                           'v1_snapshot': saved['snapshot_id'], 'v2_snapshot': updated['snapshot_id'],
                           'v1_bundle': bundle['bundle_id'], 'v2_bundle': bundle2['bundle_id'],
                           'rejected_bundle': forged['bundle_id'], 'rejection': rejection,
                           'readonly_validation_byte_identical': True, 'rejected_byte_identical': True,
                           'website_documents_collected': 0, 'real_documents_imported': 0,
                           'formal_sha256_before': self.formal_before,
                           'real_site_to_database_verified': False, 'synthetic_only': True}
            self.write_json('trace', 'trace.private.json', self.trace)
            self.write_json('result', 'result.private.json', self.result)
            state = self.state()
            need(all(check['passed'] for check in state['checks']), '實際 DB 核對失敗')
            self.write_json('state-at-completion', 'state-at-completion.private.json', state)
        except Exception as error:
            self.write_json('trace', 'trace.private.json', self.trace)
            self.write_json('failure', 'failure.private.json', {'error': str(error), 'commits': self.commits})
            raise

    def state(self, query: str = '') -> dict[str, Any]:
        archive = read_database(self.archive / 'knowledge.sqlite3')
        stage = read_database(self.stage / 'collector-stage.sqlite3', stage=True)
        formal = read_database(self.formal, formal=True, query=query) if self.formal else None
        snapshots = {doc['snapshot_id']: doc for doc in archive['documents']}
        receipts = {row['bundle_id'] for row in archive['receipts']}
        source_heads = {row['latest_snapshot'] for row in archive['sources']}
        checks = [
            ('測試 DB 保存兩份文件版本', archive['counts']['snapshots'] == 2),
            ('collector 重複輸入沒有增加文件', stage['counts']['snapshots'] == 2 and stage['counts']['observations'] == 3),
            ('保存端資料包去重：兩份 receipt', archive['counts']['collection_receipts'] == 2),
            ('最新版本指向更新輸入', self.result.get('v2_snapshot') in source_heads),
            ('兩版文件可從 SQLite 讀回', {self.result.get('v1_snapshot'), self.result.get('v2_snapshot')} <= set(snapshots)),
            ('SQLite 原文與正文實算雜湊符合', len(snapshots) == 2 and all(d['raw_hash_matches'] and d['body_hash_matches'] for d in snapshots.values())),
            ('偽造權限包未進 receipt', self.result.get('rejected_bundle') not in receipts),
            ('文件沒有建立／批准知識', archive['counts']['entries'] == 0 and archive['counts']['entry_revisions'] == 0 and archive['reviewed_or_published'] == 0),
            ('正式 DB 與驗收前 SHA 相同', formal is None or formal['sha256'] == self.formal_before),
        ]
        return {'observed_at': datetime.now(timezone.utc).isoformat(), 'run': str(self.run), 'commits': self.commits,
                'current_commits': {'collector': commit(COLLECTOR), 'knowledge': commit(self.knowledge)},
                'working_trees_at_verification': self.working_trees,
                'current_working_trees': {'collector': worktree_status(COLLECTOR), 'knowledge': worktree_status(self.knowledge)},
                'archive': archive, 'stage': stage, 'formal': formal,
                'checks': [{'label': label, 'passed': bool(passed)} for label, passed in checks],
                'result': self.result, 'trace': self.trace, 'artifacts': list(self.artifacts),
                'limits': '合成檔案交接已實跑；本輪真實網站原文入庫 0，Chrome 真站取得至入庫尚未驗收。'}


def handler_for(run: AcceptanceRun):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_: Any) -> None:
            pass

        def reply(self, status: int, data: bytes, content_type: str = 'application/json; charset=utf-8') -> None:
            self.send_response(status)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(data)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'self'; frame-ancestors 'none'; object-src 'none'")
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self) -> None:
            allowed = {'127.0.0.1:' + str(self.server.server_port), 'localhost:' + str(self.server.server_port)}
            if self.headers.get('Host') not in allowed:
                self.reply(403, b'{"error":"host denied"}')
                return
            target = urlsplit(self.path)
            try:
                if target.path == '/':
                    self.reply(200, (COLLECTOR / 'tools' / 'acceptance.html').read_bytes(), 'text/html; charset=utf-8')
                elif target.path == '/api/state':
                    query = parse_qs(target.query).get('q', [''])[0]
                    need(len(query) <= 100, '查詢至多 100 字元')
                    self.reply(200, json.dumps(run.state(query), ensure_ascii=False).encode('utf-8'))
                elif target.path.startswith('/artifact/'):
                    key = target.path.removeprefix('/artifact/')
                    path = run.artifacts.get(key)
                    if path is None:
                        self.reply(404, b'{"error":"artifact not found"}')
                        return
                    self.reply(200, path.read_bytes(), 'text/plain; charset=utf-8')
                else:
                    self.reply(404, b'{"error":"not found"}')
            except (ContractError, OSError, sqlite3.Error, ValueError) as error:
                self.reply(503, json.dumps({'error': str(error)}, ensure_ascii=False).encode('utf-8'))

        def do_POST(self) -> None:
            self.reply(405, b'{"error":"read-only viewer"}')

    return Handler


def reuse_existing(args: argparse.Namespace) -> bool:
    """A second click opens the same verified viewer without replaying or killing it."""
    client = http.client.HTTPConnection('127.0.0.1', args.port, timeout=2)
    try:
        client.request('GET', '/api/state')
        response = client.getresponse()
    except ConnectionRefusedError:
        client.close()
        return False
    except (OSError, http.client.HTTPException) as error:
        client.close()
        raise ContractError('無法核對既有驗收 port，請改用 --port') from error
    try:
        need(response.status == 200, 'port 已被其他服務使用，請停止原服務或改用 --port')
        data = json.loads(response.read(6_000_001))
        expected = {'collector': commit(COLLECTOR), 'knowledge': commit(args.knowledge_repo.resolve())}
        expected_root = private_output(args.data_dir)
        need(Path(data['run']).resolve().parent == expected_root, '此 port 的驗收資料夾不同，請改用 --port')
        need(data['commits'] == data['current_commits'] == expected, '既有驗收版本不同，請停止原服務後重新啟動')
        need(all(not value for key in ['working_trees_at_verification', 'current_working_trees'] for value in data[key].values()), '既有驗收含未提交變更，請停止並重新驗收')
        need(all(item['passed'] for item in data['checks']), '既有驗收 DB 核對未通過')
        wanted_hash = file_hash(Path(args.formal_db)) if args.formal_db else None
        actual_hash = data['formal']['sha256'] if data['formal'] else None
        need(wanted_hash == actual_hash, '正式 DB 選擇不同，請改用 --port')
        print('既有同版驗收仍可訪問：http://127.0.0.1:' + str(args.port) + '/', flush=True)
        if not args.no_browser:
            webbrowser.open('http://127.0.0.1:' + str(args.port) + '/')
        return True
    except ContractError:
        raise
    except (KeyError, TypeError, ValueError) as error:
        raise ContractError('此 port 不是可辨識的驗收服務；不會停止它，請改用 --port') from error
    finally:
        client.close()


def main() -> None:
    parser = argparse.ArgumentParser(description='合成檔案交接驗收：既有環境、獨立 CLI、實際 DB 唯讀展示')
    parser.add_argument('--knowledge-repo', type=Path, required=True)
    parser.add_argument('--data-dir', type=Path, required=True)
    parser.add_argument('--formal-db', default='')
    parser.add_argument('--port', type=int, default=8766)
    parser.add_argument('--no-browser', action='store_true')
    parser.add_argument('--check-only', action='store_true')
    args = parser.parse_args()
    try:
        need(1 <= args.port <= 65535, 'port 需為 1–65535')
        if not args.check_only and reuse_existing(args):
            return
        run = AcceptanceRun(args.knowledge_repo, args.data_dir, Path(args.formal_db) if args.formal_db else None)
        run.execute()
        print(json.dumps({'state': 'verified_synthetic_handoff', 'run': str(run.run), 'commits': run.commits,
                          'tests': run.tests, 'new_real_documents': 0}, ensure_ascii=False), flush=True)
        if args.check_only:
            return
        server = ThreadingHTTPServer(('127.0.0.1', args.port), handler_for(run))
        url = 'http://127.0.0.1:' + str(server.server_port) + '/'
        print('本機驗收：' + url + ' ；Ctrl+C 停止，原有資料保留。', flush=True)
        if not args.no_browser:
            threading.Timer(0.3, lambda: webbrowser.open(url)).start()
        try:
            server.serve_forever()
        finally:
            server.server_close()
    except KeyboardInterrupt:
        pass
    except (ContractError, OSError, ValueError, subprocess.TimeoutExpired) as error:
        print('驗收未通過：' + str(error), file=sys.stderr)
        raise SystemExit(1) from error


if __name__ == '__main__':
    main()
