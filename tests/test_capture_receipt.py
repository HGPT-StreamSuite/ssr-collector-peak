"""Synthetic receipt observations only; no browser or real-source permission."""
import copy
import tempfile
import unittest
from pathlib import Path
from test_boundary import file_source
from ssr_collector_peak.capture_receipt import validate_capture_receipt
from ssr_collector_peak.file_intake import intake_file
from ssr_collector_peak.primitives import ContractError,digest
from ssr_collector_peak.stage import StageLedger

RAW=b'<main><h1>Fictional Lunar Flask</h1><p>Weight 2. Synthetic fixture only, no real game content.</p></main>'

def receipt(source):
    return {'format':'ssr.browser-export.v1','requested_url':source['original_url'],'final_url':source['original_url'],
        'title':'Synthetic observation only','captured_at':'2026-01-01T00:00:00+00:00','raw_sha256':digest(RAW),
        'export_format':'rendered_dom_html','selector':'main','scope':'Synthetic selected article',
        'page_updated':None,'license_statement':None,'license_links':[],
        'method':'local_chrome_computer_use','http_status':None}

class CaptureReceiptTests(unittest.TestCase):
    def test_observation_is_bound_to_exact_file_url_and_unknown_http(self):
        source=file_source(); value=receipt(source)
        validate_capture_receipt(value,source,RAW)
        for field,changed in [('raw_sha256','0'*64),('final_url','https://example.test/other'),
                              ('http_status',200),('captured_at','2026-01-01T00:00:00')]:
            bad=copy.deepcopy(value);bad[field]=changed
            with self.subTest(field=field),self.assertRaises(ContractError):validate_capture_receipt(bad,source,RAW)

    def test_html_receipt_is_preserved_without_knowledge_access(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);file=root/'input.html';file.write_bytes(RAW);source=file_source()
            with StageLedger(root/'spool') as stage:
                result=intake_file(stage,source,str(file),'html','operator_file',receipt(source))
                saved=stage.snapshot(result['snapshot_id'],True)
                self.assertEqual(saved['captured_at'],receipt(source)['captured_at'])
                self.assertEqual(saved['metadata']['capture_receipt']['raw_sha256'],digest(RAW))
                self.assertIn('Weight 2.',saved['body'])
                self.assertEqual(stage.stats()['knowledge_entries'],0)
                denied=copy.deepcopy(source);denied['policy']['uses']['local_cache']['status']='prohibited'
                with self.assertRaises(ContractError):intake_file(stage,denied,str(file),'html','operator_file',receipt(source))
