"""Meaningful viewer boundaries; no other repository import or real data."""
import http.client
import json
import sqlite3
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from http.server import ThreadingHTTPServer

from tools.acceptance_demo import file_hash, handler_for, read_database
from ssr_collector_peak.primitives import ContractError, digest


class AcceptanceViewerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.db = self.root / 'knowledge.sqlite3'
        connection = sqlite3.connect(self.db)
        connection.executescript('''CREATE TABLE sources(source_id TEXT,url TEXT,latest_snapshot TEXT);
            CREATE TABLE snapshots(snapshot_id TEXT,source_id TEXT,fetched_at TEXT,raw BLOB,raw_sha256 TEXT,body TEXT,body_sha256 TEXT,metadata_json TEXT);
            CREATE TABLE entries(entry_id TEXT,current_revision INTEGER);
            CREATE TABLE entry_revisions(revision_id INTEGER,entry_id TEXT,status TEXT,payload_json TEXT,review_json TEXT,published_at TEXT);
            CREATE TABLE collection_receipts(bundle_id TEXT,source_id TEXT,snapshot_id TEXT,observed_at TEXT);
            INSERT INTO sources VALUES('synthetic','approved-file:synthetic','snap');
            INSERT INTO entries VALUES('fictional',1);''')
        text = 'Synthetic fictional document, not PEAK.'
        connection.execute('INSERT INTO snapshots VALUES(?,?,?,?,?,?,?,?)',
            ('snap','synthetic','2026-01-01T00:00:00+00:00',text.encode(),digest(text),text,digest(text),'{}'))
        payload = {'name_en': 'Lunar Rope', 'name_zh': '月亮繩', 'aliases': ['月繩'], 'summary_zh': '<script>INERT_SOURCE_TEXT</script> 合成文字。'}
        connection.execute('INSERT INTO entry_revisions VALUES(?,?,?,?,NULL,NULL)', (1, 'fictional', 'pending_review', json.dumps(payload, ensure_ascii=False)))
        connection.commit()
        connection.close()

    def tearDown(self):
        self.temp.cleanup()

    def test_formal_preview_reads_actual_rows_and_is_byte_readonly(self):
        before = file_hash(self.db)
        for query in ['月', 'Lunar Rope', '月繩']:
            value = read_database(self.db, formal=True, query=query)
            self.assertEqual(value['samples'][0]['entry_id'], 'fictional')
            self.assertEqual(value['samples'][0]['status'], 'pending_review')
            self.assertEqual(value['counts']['entries'], 1)
            self.assertEqual(value['reviewed_or_published'], 0)
        self.assertEqual(read_database(self.db, formal=True, query='nonexistent')['samples'], [])
        self.assertEqual(before, file_hash(self.db))

    def test_reader_uses_mode_ro_query_only_and_no_write_statements(self):
        original = sqlite3.connect
        seen, statements = [], []
        def connect(*args, **kwargs):
            seen.append((args, kwargs))
            connection = original(*args, **kwargs)
            connection.set_trace_callback(statements.append)
            return connection
        with patch('tools.acceptance_demo.sqlite3.connect', side_effect=connect):
            read_database(self.db, formal=True)
        self.assertTrue(seen[0][0][0].endswith('?mode=ro'))
        self.assertTrue(seen[0][1]['uri'])
        self.assertIn('PRAGMA query_only=ON', statements)
        self.assertFalse(any(s.upper().startswith(('INSERT', 'UPDATE', 'DELETE', 'CREATE')) for s in statements))

    def test_viewer_requeries_database_instead_of_cached_success_report(self):
        first = read_database(self.db)
        connection = sqlite3.connect(self.db)
        connection.execute("INSERT INTO snapshots VALUES('second','synthetic','later',X'00','raw2','A second synthetic version.','hash2','{}')")
        connection.commit()
        connection.close()
        second = read_database(self.db)
        self.assertEqual(first['counts']['snapshots'], 1)
        self.assertEqual(second['counts']['snapshots'], 2)
        self.assertEqual(second['documents'][1]['body'], 'A second synthetic version.')

    def test_actual_body_tamper_is_detected_without_changing_row_count(self):
        first = read_database(self.db)
        self.assertTrue(first['documents'][0]['body_hash_matches'])
        self.assertTrue(first['documents'][0]['raw_hash_matches'])
        connection = sqlite3.connect(self.db)
        connection.execute("UPDATE snapshots SET body='Unexpected synthetic corruption'")
        connection.commit()
        connection.close()
        after = read_database(self.db)
        self.assertFalse(after['documents'][0]['body_hash_matches'])
        self.assertEqual(after['counts'], first['counts'])

    def test_missing_database_is_an_error_and_is_not_created(self):
        absent = self.root / 'not-present.sqlite3'
        with self.assertRaises(ContractError):
            read_database(absent, formal=True)
        self.assertFalse(absent.exists())

    def request(self, server, method, path, host=None):
        client = http.client.HTTPConnection('127.0.0.1', server.server_port)
        client.request(method, path, headers={'Host': host or '127.0.0.1:' + str(server.server_port)})
        response = client.getresponse()
        result = response.status, response.read(), dict(response.getheaders())
        client.close()
        return result

    def test_http_view_is_readonly_host_checked_and_artifacts_allowlisted(self):
        text = self.root / 'fixture.txt'
        text.write_text('Synthetic fixture only.', encoding='utf-8')
        run = SimpleNamespace(state=lambda query='': read_database(self.db, formal=True, query=query), artifacts={'input': text})
        server = ThreadingHTTPServer(('127.0.0.1', 0), handler_for(run))
        thread = threading.Thread(target=server.serve_forever)
        thread.start()
        before = file_hash(self.db)
        try:
            status, data, headers = self.request(server, 'GET', '/api/state')
            self.assertEqual(status, 200)
            self.assertEqual(json.loads(data)['counts']['entries'], 1)
            self.assertEqual(headers['Cache-Control'], 'no-store')
            self.assertEqual(self.request(server, 'POST', '/api/state')[0], 405)
            self.assertEqual(self.request(server, 'GET', '/api/state', 'evil.example')[0], 403)
            self.assertEqual(self.request(server, 'GET', '/artifact/../../knowledge.sqlite3')[0], 404)
            self.assertEqual(self.request(server, 'GET', '/artifact/input')[1], b'Synthetic fixture only.')
            self.assertEqual(self.request(server, 'GET', '/api/state?q=' + 'x' * 101)[0], 503)
            self.assertEqual(self.request(server, 'GET', '/')[0], 200)
        finally:
            server.shutdown()
            server.server_close()
            thread.join()
        self.assertEqual(file_hash(self.db), before)
