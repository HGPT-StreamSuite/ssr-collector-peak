"""Public producer contract with real synthetic files/SQLite; never HTTP or subprocess."""
import base64
import copy
import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from ssr_collector_peak import cli
from ssr_collector_peak.capture_receipt import validate_capture_receipt
from ssr_collector_peak.file_intake import intake_file
from ssr_collector_peak.primitives import ContractError, canonical, digest, utc_now
from ssr_collector_peak.source_plan import source_from_plan
from ssr_collector_peak.stage import MAX_BUNDLE_JSON_BYTES, StageLedger

REPO = Path(__file__).resolve().parents[1]


class PublicContractTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.source = json.loads((REPO/'fixtures'/'permitted-source.synthetic.json').read_text(encoding='utf-8'))
        # Current review time applies only to this self-authored synthetic test config.
        self.source['policy']['reviewed_at'] = utc_now()
        self.input = self.root/'synthetic.txt'
        self.input.write_bytes(b'\xef\xbb\xbfSynthetic fictional Lunar Rope.\r\nOriginal CRLF and UTF-8 bytes are contract data.\r\n')

    def tearDown(self):
        self.temp.cleanup()

    def plan(self, sources=None, **updates):
        sources = [self.source] if sources is None else sources
        value = {'format':'ssr.source-plan.v1', 'game':'PEAK:3527290', 'created_at':utc_now(),
                 'selected_acquisition_route':'computer_use_or_permitted_local_file', 'http_is_optional':True,
                 'sources':sources, 'registry_sha256':digest(canonical(sources)), 'note':'Synthetic contract test only.', **updates}
        file = self.root/('plan-'+str(len(list(self.root.glob('plan-*'))))+'.json')
        file.write_text(canonical(value), encoding='utf-8-sig')
        return file

    def invoke(self, *args):
        output, errors, code = io.StringIO(), io.StringIO(), 0
        with patch('sys.argv',['ssr-collector-peak',*map(str,args)]), redirect_stdout(output), redirect_stderr(errors):
            try:
                cli.main()
            except SystemExit as error:
                code = error.code
        return code, json.loads(output.getvalue()) if output.getvalue() else None, errors.getvalue()

    def intake_args(self, plan, stage):
        return ['intake-file','--plan',plan,'--source-id',self.source['source_id'],'--file',self.input,
                '--stage-dir',stage,'--format','plain_text','--origin','synthetic_fixture']

    def test_full_plan_preserves_exact_source_and_unknown_uses(self):
        self.source['original_url'] = 'https://EXAMPLE.test/authorized-export'
        before = canonical(self.source)
        selected = source_from_plan(self.plan(), self.source['source_id'])
        self.assertEqual(canonical(selected), before)
        self.assertEqual(selected['policy']['uses']['ai_input']['status'], 'unknown')
        self.assertIs(cli.source_from_plan, source_from_plan)

    def test_minimal_legacy_plan_is_compatible(self):
        file = self.root/'minimal.json'
        file.write_text(canonical({'format':'ssr.source-plan.v1','sources':[self.source]}),encoding='utf-8')
        self.assertEqual(source_from_plan(file,self.source['source_id']),self.source)

    def test_malformed_records_are_contract_errors(self):
        missing = copy.deepcopy(self.source); missing.pop('policy')
        policy = copy.deepcopy(self.source); policy['policy'] = None
        uses = copy.deepcopy(self.source); uses['policy']['uses']['local_cache'] = []
        selector = copy.deepcopy(self.source); selector['selector']['tag'] = []
        kind = copy.deepcopy(self.source); kind['acquisition'] = {'kind':'unknown'}
        boolean = copy.deepcopy(self.source); boolean['policy']['allow_import'] = 1
        for sources in [[None],[[]],[missing],[policy],[uses],[selector],[kind],[boolean]]:
            with self.subTest(sources=sources), self.assertRaises(ContractError):
                source_from_plan(self.plan(sources),self.source['source_id'])

    def test_checksum_game_version_and_identity_boundaries(self):
        files = [self.plan(registry_sha256='0'*64), self.plan(game='OTHER:1'),
                 self.plan(format='ssr.source-plan.v2'), self.plan([self.source,self.source]), self.plan([])]
        for file in files:
            with self.subTest(file=file), self.assertRaises(ContractError):
                source_from_plan(file,self.source['source_id'])

    def test_checksum_binds_unselected_sources_too(self):
        second = copy.deepcopy(self.source)
        second.update(source_id='synthetic-second',url='approved-file:synthetic-second')
        file = self.plan([self.source,second])
        value = json.loads(file.read_text(encoding='utf-8-sig'))
        value['sources'][1]['title'] += ' tampered'
        file.write_text(canonical(value),encoding='utf-8')
        with self.assertRaises(ContractError):
            source_from_plan(file,self.source['source_id'])

    def test_nonfinite_malformed_or_non_utf8_json_is_rejected(self):
        file = self.root/'invalid.json'
        for raw in [b'{', b'\xff', b'{"format":"ssr.source-plan.v1","sources":[NaN]}']:
            file.write_bytes(raw)
            with self.subTest(raw=raw), self.assertRaises(ContractError):
                source_from_plan(file,self.source['source_id'])

    def test_bad_plan_cli_returns_json_exit_one_before_stage_creation(self):
        missing = copy.deepcopy(self.source); missing.pop('policy')
        stage = self.root/'not-created'
        code, value, errors = self.invoke(*self.intake_args(self.plan([missing]),stage))
        self.assertEqual((code,value['status'],errors),(1,'error',''))
        self.assertFalse(stage.exists())

    def test_corrupt_sqlite_error_is_json_and_original_is_preserved(self):
        stage = self.root/'corrupt'; stage.mkdir()
        file = stage/'collector-stage.sqlite3'; original = b'Synthetic invalid SQLite. Preserve these bytes.'*20
        file.write_bytes(original)
        code,value,errors = self.invoke('stats','--stage-dir',stage)
        self.assertEqual((code,value['status'],errors),(1,'error',''))
        self.assertEqual(file.read_bytes(),original)

    def test_native_intake_bundle_stats_and_envelope_contract(self):
        stage = self.root/'stage'
        code,intake,errors = self.invoke(*self.intake_args(self.plan(),stage))
        self.assertEqual((code,intake['state'],errors),(0,'saved',''))
        code,bundle,errors = self.invoke('bundle','--stage-dir',stage,'--snapshot-id',intake['snapshot_id'],'--output-dir',self.root/'handoff')
        self.assertEqual((code,errors),(0,''))
        packet = json.loads(Path(bundle['path']).read_text(encoding='utf-8'))
        contract = json.loads((REPO/'interfaces'/'collector.v1.json').read_text(encoding='utf-8'))['collection']
        self.assertEqual(set(packet),set(contract['root_fields']))
        self.assertEqual(set(packet['source_ref']),set(contract['source_ref_fields']))
        self.assertEqual(set(packet['document']),set(contract['document_fields']))
        self.assertEqual(packet['format'],'ssr.collection.v1')
        self.assertEqual(packet['producer'],'ssr-collector-peak/0.1.0')
        self.assertEqual(packet['source_ref']['config_sha256'],digest(canonical(self.source)))
        document = packet['document']; raw = self.input.read_bytes()
        self.assertEqual(base64.b64decode(document['raw_base64']),raw)
        self.assertEqual(document['raw_sha256'],digest(raw))
        self.assertEqual(document['body'],raw.decode('utf-8-sig'))
        self.assertEqual(document['body_sha256'],digest(document['body']))
        self.assertEqual(packet['bundle_id'],digest(canonical({k:v for k,v in packet.items() if k!='bundle_id'})))
        self.assertLessEqual(datetime.fromisoformat(document['captured_at']),datetime.fromisoformat(document['observed_at']))
        self.assertIsNotNone(datetime.fromisoformat(document['captured_at']).tzinfo)
        self.assertEqual(document['metadata']['purpose'],'local_cache')
        self.assertFalse(document['metadata']['collector_called_llm'])
        self.assertNotIn('policy',document['metadata'])
        code,stats,errors = self.invoke('stats','--stage-dir',stage)
        self.assertEqual((code,errors,stats['counts']['snapshots'],stats['counts']['observations']),(0,'',1,1))
        self.assertEqual(stats['knowledge_entries'],0)

    def test_unknown_prohibited_and_disabled_import_do_not_save_documents(self):
        cases = []
        for status in ['unknown','prohibited']:
            source = copy.deepcopy(self.source); source['policy']['uses']['local_cache']['status'] = status; cases.append(source)
        disabled = copy.deepcopy(self.source); disabled['policy']['allow_import'] = False; cases.append(disabled)
        for index,source in enumerate(cases):
            stage = self.root/('denied-'+str(index))
            code,value,errors = self.invoke(*self.intake_args(self.plan([source]),stage))
            self.assertEqual((code,value['status'],errors),(1,'error',''))
            with StageLedger(stage) as ledger:
                self.assertEqual(ledger.stats()['counts']['snapshots'],0)
                self.assertEqual(ledger.stats()['counts']['observations'],0)

    def test_empty_stats_and_unknown_snapshot_are_explicit(self):
        stage = self.root/'empty'
        code,stats,_ = self.invoke('stats','--stage-dir',stage)
        self.assertEqual(code,0)
        self.assertEqual(stats['counts']['snapshots'],0)
        output = self.root/'not-written'
        code,error,_ = self.invoke('bundle','--stage-dir',stage,'--snapshot-id','unknown','--output-dir',output)
        self.assertEqual((code,error['status']),(1,'error'))
        self.assertFalse(output.exists())

    def test_escaped_two_mb_input_cannot_export_over_six_mb(self):
        self.input.write_bytes(b'"'*2_000_000)
        stage = self.root/'large'
        code,intake,_ = self.invoke(*self.intake_args(self.plan(),stage))
        self.assertEqual(code,0)
        output = self.root/'no-partial-export'
        code,error,_ = self.invoke('bundle','--stage-dir',stage,'--snapshot-id',intake['snapshot_id'],'--output-dir',output)
        self.assertEqual((code,error['status']),(1,'error'))
        self.assertIn('6 MB',error['error'])
        self.assertFalse(output.exists())
        with StageLedger(stage) as ledger:
            self.assertEqual(ledger.stats()['counts']['snapshots'],1)
            self.assertEqual(ledger.db.execute('SELECT raw FROM snapshots').fetchone()[0],self.input.read_bytes())

    def test_escaped_packet_under_limit_roundtrips_without_truncation(self):
        raw = b'"'*1_000_000; self.input.write_bytes(raw)
        with StageLedger(self.root/'fits') as ledger:
            result = intake_file(ledger,self.source,str(self.input),'plain_text','synthetic_fixture')
            bundle = ledger.bundle(result['snapshot_id'],self.root/'fits-handoff')
        file = Path(bundle['path']); packet = json.loads(file.read_text(encoding='utf-8'))
        self.assertLessEqual(file.stat().st_size,MAX_BUNDLE_JSON_BYTES)
        self.assertEqual(base64.b64decode(packet['document']['raw_base64']),raw)
        self.assertEqual(packet['document']['body'],'"'*1_000_000)

    def test_receipt_enum_types_are_contract_errors(self):
        raw = b'<main>Synthetic receipt observation only, not a website fetch.</main>'
        receipt = {'format':'ssr.browser-export.v1','requested_url':self.source['original_url'],'final_url':self.source['original_url'],
                   'title':'Synthetic','captured_at':utc_now(),'raw_sha256':digest(raw),'export_format':'rendered_dom_html',
                   'selector':'main','scope':'Synthetic only','page_updated':None,'license_statement':None,'license_links':[],
                   'method':'local_chrome_computer_use','http_status':None}
        for field in ['method','export_format']:
            for wrong in [[],{},None]:
                value = copy.deepcopy(receipt); value[field] = wrong
                with self.subTest(field=field,wrong=wrong), self.assertRaises(ContractError):
                    validate_capture_receipt(value,self.source,raw)

    def test_bundle_collision_never_overwrites_existing_output(self):
        with StageLedger(self.root/'collision') as ledger:
            staged = intake_file(ledger,self.source,str(self.input),'plain_text','synthetic_fixture')
            bundle = ledger.bundle(staged['snapshot_id'],self.root/'collision-handoff')
            file = Path(bundle['path']); original = b'Synthetic collision sentinel, preserve.'; file.write_bytes(original)
            with self.assertRaises(ContractError):
                ledger.bundle(staged['snapshot_id'],file.parent)
            self.assertEqual(file.read_bytes(),original)

    def test_cli_usage_error_keeps_exit_two_and_stderr_contract(self):
        code,value,errors = self.invoke()
        self.assertEqual(code,2)
        self.assertIsNone(value)
        self.assertIn('usage:',errors)

    def receipt(self, raw, captured_at):
        return {'format':'ssr.browser-export.v1','requested_url':self.source['original_url'],'final_url':self.source['original_url'],
                'title':'Synthetic observation only','captured_at':captured_at,'raw_sha256':digest(raw),'export_format':'rendered_dom_html',
                'selector':'main','scope':'Self-authored synthetic receipt; no browser or real website','page_updated':None,
                'license_statement':None,'license_links':[],'method':'local_chrome_computer_use','http_status':None}

    def test_same_raw_new_receipt_exports_matching_observation_time_without_rewriting_history(self):
        raw = b'<main>Synthetic repeated receipt observation only; no real browser capture.</main>'
        self.input.write_bytes(raw)
        now = datetime.now(timezone.utc)
        first_at = (now-timedelta(minutes=2)).isoformat()
        second_at = (now-timedelta(minutes=1)).isoformat()
        with StageLedger(self.root/'receipt-replay') as ledger:
            first = intake_file(ledger,self.source,str(self.input),'html','operator_file',self.receipt(raw,first_at))
            first_bundle = ledger.bundle(first['snapshot_id'],self.root/'receipt-output')
            first_file = Path(first_bundle['path']); first_bytes = first_file.read_bytes()
            repeat = intake_file(ledger,self.source,str(self.input),'html','operator_file',self.receipt(raw,second_at))
            second_bundle = ledger.bundle(repeat['snapshot_id'],self.root/'receipt-output')
            packet = json.loads(Path(second_bundle['path']).read_text(encoding='utf-8'))
            self.assertEqual(ledger.stats()['counts']['snapshots'],1)
            self.assertEqual(ledger.stats()['counts']['observations'],2)
            self.assertEqual(ledger.db.execute('SELECT captured_at FROM snapshots').fetchone()[0],first_at)
        self.assertEqual(packet['document']['captured_at'],second_at)
        self.assertEqual(packet['document']['metadata']['capture_receipt']['captured_at'],second_at)
        self.assertNotEqual(first_bundle['bundle_id'],second_bundle['bundle_id'])
        self.assertEqual(first_file.read_bytes(),first_bytes)

    def test_capture_after_observation_is_not_exported_or_clamped(self):
        raw = b'<main>Synthetic clock boundary only; no real browser or website capture.</main>'
        self.input.write_bytes(raw)
        future = (datetime.now(timezone.utc)+timedelta(seconds=45)).isoformat()
        with StageLedger(self.root/'clock-boundary') as ledger:
            staged = intake_file(ledger,self.source,str(self.input),'html','operator_file',self.receipt(raw,future))
            output = self.root/'no-clock-export'
            with self.assertRaises(ContractError):
                ledger.bundle(staged['snapshot_id'],output)
            self.assertFalse(output.exists())
            self.assertEqual(ledger.stats()['counts']['snapshots'],1)
            self.assertEqual(ledger.snapshot(staged['snapshot_id'])['metadata']['capture_receipt']['captured_at'],future)
