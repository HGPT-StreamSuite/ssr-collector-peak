"""Isolated real collector operations and in-memory handler tests. No sockets."""
import base64
import io
import json
import sqlite3
import tempfile
import unittest
from html.parser import HTMLParser
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from ssr_collector_peak.primitives import ContractError, digest
from tools.acceptance_demo import handler_for, main
from tools.collector_lab import CollectorLab, REPO, criteria, safe_test_summary

TEXT = 'Synthetic fictional Lunar Rope. SOURCE_COMMAND is inert text; no real PEAK source or permission.'


class MemoryConnection:
    def __init__(self, raw):
        self.input = io.BytesIO(raw)
        self.output = bytearray()

    def makefile(self, *_):
        return self.input

    def sendall(self, data):
        self.output.extend(data)


class CollectorLabTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.lab = CollectorLab(self.root / 'lab', version={'head': 'a'*40, 'branch': 'test', 'dirty': True})

    def tearDown(self):
        self.temp.cleanup()

    def payload(self, request_id='one', text=TEXT, **changes):
        return {'request_id': request_id, 'session_id': self.lab.session_id,
                'format': 'plain_text', 'text': text, 'synthetic': True, **changes}

    def test_actual_intake_bundle_and_new_connection_readback(self):
        result = self.lab.submit(self.payload())
        packet = result['bundle']
        self.assertEqual(base64.b64decode(packet['document']['raw_base64']), TEXT.encode())
        self.assertEqual(packet['document']['body'], TEXT)
        self.assertEqual(packet['document']['raw_sha256'], digest(TEXT))
        self.assertEqual(result['readback']['counts']['snapshots'], 1)
        self.assertEqual(result['readback']['documents'][0]['body_sha256'], digest(TEXT))
        db = sqlite3.connect(self.lab.stage / 'collector-stage.sqlite3')
        try:
            tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            self.assertNotIn('entries', tables)
            self.assertEqual(db.execute('SELECT body FROM snapshots').fetchone()[0], TEXT)
        finally:
            db.close()
        self.assertEqual(packet['document']['metadata']['http_requests'], 0)
        self.assertNotIn(str(self.root), json.dumps(result))

    def test_repeat_request_and_repeat_content_have_different_observation_semantics(self):
        first = self.lab.submit(self.payload())
        replay = self.lab.submit(self.payload())
        self.assertTrue(replay['request_replayed'])
        self.assertEqual(replay['readback']['counts']['observations'], 1)
        repeat = self.lab.submit(self.payload('two'))
        self.assertEqual(repeat['intake']['state'], 'unchanged')
        self.assertEqual(repeat['readback']['counts']['snapshots'], 1)
        self.assertEqual(repeat['readback']['counts']['observations'], 2)
        self.assertEqual(first['intake']['snapshot_id'], repeat['intake']['snapshot_id'])
        with self.assertRaises(ContractError):
            self.lab.submit(self.payload(text=TEXT+' changed'))

    def test_changed_content_keeps_previous_bundle(self):
        first = self.lab.submit(self.payload())
        original = self.lab.artifacts[first['artifact_key']].read_bytes()
        second = self.lab.submit(self.payload('two', TEXT+' Second synthetic version.'))
        self.assertNotEqual(first['intake']['snapshot_id'], second['intake']['snapshot_id'])
        self.assertEqual(second['readback']['counts']['snapshots'], 2)
        self.assertEqual(self.lab.artifacts[first['artifact_key']].read_bytes(), original)

    def test_html_raw_preserved_scripts_excluded(self):
        text = '<main>'+TEXT+'<script>NEVER_EXECUTE_SOURCE_TEXT</script></main>'
        packet = self.lab.submit(self.payload(text=text, format='html'))['bundle']['document']
        self.assertEqual(base64.b64decode(packet['raw_base64']), text.encode())
        self.assertNotIn('NEVER_EXECUTE_SOURCE_TEXT', packet['body'])

    def test_bad_inputs_leave_snapshot_and_observation_counts_unchanged(self):
        cases = [self.payload(text='short'), self.payload(text='x'*20001), self.payload(text=TEXT+'\x00'),
                 self.payload(format=[]), self.payload(synthetic=False), self.payload(session_id='stale'),
                 self.payload(path='private-file'), self.payload(request_id='../escape'),
                 self.payload(format='html', text='<div>'+TEXT+'</div>'),
                 self.payload(format='html', text='<main>'+TEXT+'</main><main>'+TEXT+'</main>')]
        for value in cases:
            with self.subTest(value=value), self.assertRaises(ContractError):
                self.lab.submit(value)
        self.assertEqual(self.lab.readback()['counts']['snapshots'], 0)
        self.assertEqual(self.lab.readback()['counts']['observations'], 0)

    def test_new_session_preserves_old_files_and_rejects_stale_requests(self):
        payload = self.payload()
        first = self.lab.submit(payload)
        old_db = self.lab.stage / 'collector-stage.sqlite3'
        old_bytes = old_db.read_bytes()
        self.lab.new_session()
        self.assertEqual(old_db.read_bytes(), old_bytes)
        self.assertEqual(self.lab.readback()['counts']['snapshots'], 0)
        self.assertNotIn(first['artifact_key'], self.lab.artifacts)
        with self.assertRaises(ContractError):
            self.lab.submit(payload)

    def test_reading_state_does_not_create_or_change_stage(self):
        self.lab.state()
        self.assertFalse(self.lab.stage.exists())
        self.lab.submit(self.payload())
        file = self.lab.stage / 'collector-stage.sqlite3'
        original = file.read_bytes()
        self.lab.state(); self.lab.state()
        self.assertEqual(file.read_bytes(), original)

    def test_checkout_and_knowledge_archive_output_are_refused(self):
        fake_repo = self.root / 'fake-repo'
        (fake_repo / '.git').mkdir(parents=True)
        archive = self.root / 'fake-archive'
        archive.mkdir()
        sentinel = archive / 'knowledge.sqlite3'
        sentinel.write_bytes(b'synthetic sentinel, preserve')
        for target in [fake_repo/'lab', archive, archive/'nested']:
            with self.subTest(target=target), self.assertRaises(ContractError):
                CollectorLab(target)
        self.assertEqual(sentinel.read_bytes(), b'synthetic sentinel, preserve')

    def test_test_summary_redacts_private_environment_and_does_not_claim_ui_success(self):
        path = self.root / 'test-summary.json'
        path.write_text(json.dumps({'tests_run': 12, 'passed': 12, 'private_path': str(self.root),
                                    'environment': {'secret': 'SYNTHETIC_SECRET'}, 'head': 'a'*40}), encoding='utf-8')
        summary = safe_test_summary(path)
        self.assertEqual(summary['passed'], 12)
        self.assertFalse(summary['http_ui_verified'])
        self.assertNotIn('SYNTHETIC_SECRET', json.dumps(summary))
        self.assertNotIn(str(self.root), json.dumps(summary))
        self.assertEqual(len(criteria()['criteria']), 6)

    def test_check_only_never_starts_server_or_requires_knowledge(self):
        args = ['acceptance_demo', '--collector-only', '--data-dir', str(self.root/'check'), '--check-only']
        output = io.StringIO()
        with patch('sys.argv', args), patch('tools.acceptance_demo.collector_version', return_value={'head':'a'*40}), \
             patch('tools.acceptance_demo.ThreadingHTTPServer', side_effect=AssertionError('No socket allowed')), redirect_stdout(output):
            main()
        self.assertEqual(json.loads(output.getvalue())['state'], 'collector_only_configured_not_http_verified')

    def request(self, method='GET', path='/api/state', value=None, **overrides):
        body = b'' if value is None else json.dumps(value).encode()
        headers = {'Host':'127.0.0.1:8766', 'Origin':'http://127.0.0.1:8766',
                   'X-Collector-Token':self.lab.token, 'Content-Type':'application/json', 'Content-Length':str(len(body)), **overrides}
        raw = (method+' '+path+' HTTP/1.0\r\n'+''.join(k+': '+v+'\r\n' for k,v in headers.items())+'\r\n').encode()+body
        connection = MemoryConnection(raw)
        handler_for(self.lab)(connection, ('127.0.0.1', 1), SimpleNamespace(server_port=8766))
        head, output = bytes(connection.output).split(b'\r\n\r\n', 1)
        return int(head.split()[1]), output, head

    def test_in_memory_get_post_and_bundle_allowlist(self):
        self.assertEqual(self.request()[0], 200)
        status, raw, _ = self.request('POST', '/api/collector/intake', self.payload())
        self.assertEqual(status, 200, raw)
        result = json.loads(raw)
        self.assertEqual(self.request(path='/artifact/'+result['artifact_key'])[1], json.dumps(result['bundle'], ensure_ascii=False, sort_keys=True, separators=(',',':')).encode())
        self.assertEqual(self.request(path='/artifact/../../knowledge.sqlite3')[0], 404)
        self.assertIn(b'data-collector-only="true"', self.request(path='/')[1])
        self.assertEqual(self.request(path='/collector-lab.js')[0], 200)

    def test_in_memory_host_origin_token_and_request_boundaries(self):
        for changes in [{'Host':'evil.test'}, {'Origin':'http://evil.test'}, {'X-Collector-Token':'bad'}]:
            self.assertEqual(self.request('POST', '/api/collector/intake', self.payload(), **changes)[0], 403)
        for value, changes in [(self.payload(text='short'), {}), ([], {}),
                               (self.payload(), {'Content-Type':'text/plain'}),
                               (self.payload(), {'Content-Length':'70000'}),
                               (self.payload(), {'Transfer-Encoding':'chunked'})]:
            self.assertEqual(self.request('POST', '/api/collector/intake', value, **changes)[0], 400)
        self.assertEqual(self.lab.readback()['counts']['snapshots'], 0)
        self.assertEqual(self.request('POST', '/api/collector/unknown', {})[0], 404)

    def test_in_memory_new_session_and_classic_viewer_remains_readonly(self):
        self.lab.submit(self.payload())
        old = self.lab.session_id
        self.assertEqual(self.request('POST', '/api/collector/new-session', {'session_id':old})[0], 200)
        self.assertNotEqual(self.lab.session_id, old)
        classic = MemoryConnection(b'POST /api/collector/intake HTTP/1.0\r\nHost: 127.0.0.1:8766\r\n\r\n')
        handler_for(SimpleNamespace())(classic, ('127.0.0.1',1), SimpleNamespace(server_port=8766))
        self.assertIn(b' 405 ', bytes(classic.output).split(b'\r\n')[0])

    def test_in_memory_read_error_redacts_local_path(self):
        with patch.object(self.lab, 'state', side_effect=OSError('SYNTHETIC_PRIVATE_PATH')):
            status, raw, _ = self.request()
        self.assertEqual(status, 503)
        self.assertNotIn(b'SYNTHETIC_PRIVATE_PATH', raw)

    def test_stale_session_reset_is_rejected_without_new_directory(self):
        current = self.lab.session_id
        self.assertEqual(self.request('POST', '/api/collector/new-session', {'session_id':'stale'})[0], 400)
        self.assertEqual(self.lab.session_id, current)

    def test_html_has_unique_ids_labelled_controls_and_existing_assets(self):
        class Page(HTMLParser):
            def __init__(self): super().__init__(); self.ids=[]; self.labels=[]; self.scripts=[]
            def handle_starttag(self, tag, attrs):
                attrs=dict(attrs)
                if 'id' in attrs: self.ids.append(attrs['id'])
                if tag=='label': self.labels.append(attrs.get('for'))
                if tag=='script' and 'src' in attrs: self.scripts.append(attrs['src'])
        page=Page();page.feed((REPO/'tools'/'acceptance.html').read_text(encoding='utf-8'))
        self.assertEqual(len(page.ids),len(set(page.ids)))
        self.assertTrue({'labText','labFormat','labConfirm'} <= set(page.labels))
        for asset in page.scripts: self.assertTrue((REPO/'tools'/asset).is_file())
        self.assertTrue((REPO/'tools'/'../docs/collector-independent-criteria.json').resolve().is_file())

    def test_common_default_browser_gate_stays_blocked_despite_program_passes(self):
        standard = criteria()
        gate = standard['common_gate']
        self.assertTrue(gate['required'])
        self.assertEqual(gate['status'], 'blocked')
        self.assertFalse(gate['default_browser_opened'])
        self.assertFalse(gate['interaction_verified'])
        self.assertEqual(gate['browser_evidence'], [])
        self.assertIsNone(gate['verified_url'])
        self.assertFalse(standard['actual_verified']['browser_pass'])
        self.assertEqual(standard['actual_verified']['program_tests'], 25)
        self.assertTrue(standard['not_applicable'])
        self.assertTrue(standard['unverified_blocked'])

    def test_page_has_all_five_acceptance_sections_without_claiming_browser_pass(self):
        status, body, _ = self.request(path='/')
        self.assertEqual(status, 200)
        for section in ['labCommonGate','labFunctionalCases','labVerified','labNotApplicable','labBlocked']:
            self.assertIn(('id="'+section+'"').encode(), body)
        self.assertIn('BLOCKED／未驗證'.encode(), body)
        self.assertIn('預設瀏覽器未開啟'.encode(), body)
