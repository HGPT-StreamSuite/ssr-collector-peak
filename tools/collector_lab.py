"""Synthetic-only adapter for the existing acceptance viewer; no other repo or HTTP."""
from __future__ import annotations

import json
import re
import secrets
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ssr_collector_peak.file_intake import intake_file
from ssr_collector_peak.http_collection import BodyExtractor
from ssr_collector_peak.primitives import ContractError, canonical, digest, private_output
from ssr_collector_peak.stage import StageLedger

REPO = Path(__file__).resolve().parents[1]
MAX_INPUT = 20_000


def criteria() -> dict[str, Any]:
    return json.loads((REPO / 'docs' / 'collector-independent-criteria.json').read_text(encoding='utf-8'))


def safe_test_summary(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {'status': '未載入程式測試證據', 'http_ui_verified': False}
    if path.stat().st_size > 1_000_000:
        raise ContractError('測試摘要檔過大')
    value = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(value, dict):
        raise ContractError('測試摘要需為 JSON object')
    result: dict[str, Any] = {'http_ui_verified': False}
    for key in ['new_tests_run', 'new_tests_passed', 'assertion_failures', 'test_errors',
                'prior_same_version_passes_reused', 'combined_passes', 'tests_run', 'passed', 'failures', 'errors']:
        if type(value.get(key)) is int and value[key] >= 0:
            result[key] = value[key]
    for key, size in [('head_at_execution', 40), ('head', 40), ('file_manifest_sha256', 64)]:
        if isinstance(value.get(key), str) and re.fullmatch('[0-9a-f]{' + str(size) + '}', value[key]):
            result[key] = value[key]
    result['status'] = '已載入程式測試摘要；需對照 HEAD 與工作檔 hash，HTTP／瀏覽器未驗證'
    return result


class CollectorLab:
    collector_only = True

    def __init__(self, root: Path, *, evidence_summary: Path | None = None, version: dict | None = None):
        base = private_output(root)
        self.test_summary = safe_test_summary(evidence_summary)
        self.source = json.loads((REPO / 'fixtures' / 'permitted-source.synthetic.json').read_text(encoding='utf-8'))
        self.token = secrets.token_urlsafe(32)
        self.version = version or {'head': 'unknown', 'branch': 'unknown', 'dirty': True}
        self.lock = threading.RLock()
        self.run = base / ('collector-lab-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S') + '-' + uuid.uuid4().hex)
        self.run.mkdir(parents=True, exist_ok=False)
        self.artifacts: dict[str, Path] = {'criteria': REPO / 'docs' / 'collector-independent-criteria.json'}
        self.results: dict[str, tuple[str, dict[str, Any]]] = {}
        self.history: list[dict[str, Any]] = []
        self.new_session()

    def new_session(self, expected_session: str | None = None) -> dict[str, Any]:
        with self.lock:
            if expected_session is not None and expected_session != self.session_id:
                raise ContractError('工作階段已變更；請先重新讀取')
            self.session_id = uuid.uuid4().hex
            self.session = self.run / self.session_id
            self.session.mkdir(exist_ok=False)
            self.stage = self.session / 'stage'
            self.results = {}
            self.artifacts = {'criteria': REPO / 'docs' / 'collector-independent-criteria.json'}
            self.history = []
            self._record({'event': 'session_created', 'session_id': self.session_id})
            return self.state()

    def _record(self, value: dict[str, Any]) -> None:
        row = {'at': datetime.now(timezone.utc).isoformat(), **value}
        with (self.session / 'events.jsonl').open('a', encoding='utf-8') as file:
            file.write(canonical(row) + '\n')
        self.history.append(row)

    def record_error(self, message: str) -> None:
        with self.lock:
            self._record({'event': 'request_rejected', 'error': message})

    def readback(self) -> dict[str, Any]:
        file = self.stage / 'collector-stage.sqlite3'
        if not file.is_file():
            return {'counts': {'sources': 0, 'snapshots': 0, 'observations': 0, 'events': 0}, 'documents': []}
        db = sqlite3.connect(file.resolve().as_uri() + '?mode=ro', uri=True)
        db.row_factory = sqlite3.Row
        try:
            db.execute('PRAGMA query_only=ON')
            counts = {name: db.execute('SELECT count(*) FROM ' + name).fetchone()[0]
                      for name in ['sources', 'snapshots', 'observations', 'events']}
            docs = [dict(row) for row in db.execute('SELECT snapshot_id,body,length(raw) AS raw_bytes FROM snapshots ORDER BY rowid')]
            for doc in docs:
                doc['body_sha256'] = digest(doc['body'])
            return {'counts': counts, 'documents': docs}
        finally:
            db.close()

    def state(self, *_: Any, **__: Any) -> dict[str, Any]:
        with self.lock:
            return {'mode': 'collector_only', 'session_id': self.session_id, 'csrf_token': self.token, 'version': self.version,
                    'stage': self.readback(), 'criteria': criteria(), 'test_evidence': self.test_summary,
                    'operations': list(self.history), 'artifacts': list(self.artifacts),
                    'http_ui_verified': False,
                    'limits': '只處理合成資料；HTTP／瀏覽器尚未驗證；不取得網站、不寫正式知識。'}

    def submit(self, value: Any) -> dict[str, Any]:
        with self.lock:
            if not isinstance(value, dict) or set(value) != {'request_id', 'session_id', 'format', 'text', 'synthetic'}:
                raise ContractError('僅接受 request_id、session_id、format、text、synthetic')
            if value['session_id'] != self.session_id:
                raise ContractError('工作階段已變更；請先重新讀取，再確認輸入')
            request_id = value['request_id']
            if not isinstance(request_id, str) or not re.fullmatch('[a-zA-Z0-9_-]{1,80}', request_id):
                raise ContractError('request_id 格式不符')
            if value['synthetic'] is not True:
                raise ContractError('請確認輸入為合成資料，不含真實或私人資料')
            text, body_format = value['text'], value['format']
            if not isinstance(text, str) or '\x00' in text or not 40 <= len(text.encode('utf-8')) <= MAX_INPUT:
                raise ContractError('合成 UTF-8 輸入需為 40–20,000 bytes，且不含 NUL')
            if not isinstance(body_format, str) or body_format not in {'plain_text', 'html'}:
                raise ContractError('格式需為 plain_text 或 html')
            body = text
            if body_format == 'html':
                parser = BodyExtractor(self.source['selector'])
                parser.feed(text)
                parser.close()
                body = parser.body()
            if not 40 <= len(body) <= MAX_INPUT:
                raise ContractError('擷取後正文需為 40–20,000 字元')
            input_hash = digest(canonical(value))
            if request_id in self.results:
                previous_hash, previous_result = self.results[request_id]
                if input_hash != previous_hash:
                    raise ContractError('同一 request_id 不可變更內容；請建立新請求')
                return {**previous_result, 'request_replayed': True, 'readback': self.readback(), 'operations': list(self.history), 'artifacts': list(self.artifacts)}
            if len(self.results) >= 100:
                raise ContractError('本合成工作階段已達 100 次操作；請建立新工作階段')
            operation = self.session / request_id
            operation.mkdir(exist_ok=False)
            raw = operation / 'synthetic-input.txt'
            raw.write_bytes(text.encode('utf-8'))
            (operation / 'request.json').write_text(canonical(value), encoding='utf-8')
            with StageLedger(self.stage) as stage:
                intake = intake_file(stage, self.source, str(raw), body_format, 'synthetic_fixture')
                bundle = stage.bundle(intake['snapshot_id'], self.session / 'bundles')
            packet = json.loads(Path(bundle['path']).read_text(encoding='utf-8'))
            key = 'bundle-' + packet['bundle_id']
            self.artifacts[key] = Path(bundle['path'])
            result = {'request_id': request_id, 'session_id': self.session_id, 'request_replayed': False,
                      'intake': intake, 'bundle': packet, 'artifact_key': key, 'readback': self.readback()}
            self._record({'event': 'intake_bundle', 'request_id': request_id, 'state': intake['state'],
                          'snapshot_id': intake['snapshot_id'], 'bundle_id': packet['bundle_id'],
                          'raw_sha256': intake['raw_sha256'], 'counts': result['readback']['counts']})
            result.update(operations=list(self.history), artifacts=list(self.artifacts))
            (operation / 'result.json').write_text(canonical(result), encoding='utf-8')
            self.results[request_id] = (input_hash, result)
            return result
