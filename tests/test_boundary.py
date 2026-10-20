"""Synthetic permitted files. No browser export or real website collection."""
import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from fixture_helpers import source
from ssr_collector_peak.file_intake import intake_file
from ssr_collector_peak.primitives import ContractError, canonical, digest
from ssr_collector_peak.stage import StageLedger


def file_source():
    value=source(); value.update(source_id='synthetic-export',url='approved-file:synthetic-export',
        original_url='https://example.test/authorized-export',acquisition={'kind':'approved_local_file'})
    value['policy'].update(allow_fetch=False,allow_import=True)
    return value


class BoundaryTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.root=Path(self.temp.name)
        self.source=file_source(); self.file=self.root/'synthetic.txt'
        self.file.write_text('Synthetic fictional Lunar Rope. SOURCE_COMMAND is inert text; no real PEAK source or permissions.',encoding='utf-8')

    def tearDown(self): self.temp.cleanup()

    def test_local_file_to_data_only_bundle_and_reopen(self):
        data=self.root/'spool'; output=self.root/'handoff'
        with StageLedger(data) as stage:
            first=intake_file(stage,self.source,str(self.file),'plain_text','synthetic_fixture')
            again=intake_file(stage,self.source,str(self.file),'plain_text','synthetic_fixture')
            self.assertEqual(again['state'],'unchanged')
            self.assertEqual(stage.stats()['counts']['snapshots'],1)
            bundle=stage.bundle(first['snapshot_id'],output)
            names={r[0] for r in stage.db.execute("select name from sqlite_master where type='table'")}
            self.assertFalse(names & {'entries','entry_revisions','citations','collection_receipts'})
        with StageLedger(data) as stage:
            repeat=stage.bundle(first['snapshot_id'],output)
            self.assertEqual(bundle,repeat)
        packet=json.loads(Path(bundle['path']).read_text(encoding='utf-8'))
        self.assertNotIn('policy',packet['document']['metadata'])
        self.assertEqual(packet['source_ref']['config_sha256'],digest(canonical(self.source)))
        self.assertEqual(packet['document']['metadata']['http_requests'],0)
        self.assertEqual(packet['document']['metadata']['acquisition_method'],'synthetic_fixture')
        self.assertFalse(bundle['authoritative_knowledge_saved'])

    def test_collector_refuses_archive_or_git_output_without_touching_it(self):
        archive=self.root/'archive'; archive.mkdir(); sentinel=archive/'knowledge.sqlite3'; sentinel.write_bytes(b'preserve-this-original-file')
        with self.assertRaises(ContractError): StageLedger(archive)
        with self.assertRaises(ContractError): StageLedger(archive/'nested')
        self.assertEqual(sentinel.read_bytes(),b'preserve-this-original-file')
        repo=self.root/'repo'; (repo/'.git').mkdir(parents=True)
        with self.assertRaises(ContractError): StageLedger(repo/'stage')
        with StageLedger(self.root/'stage') as stage:
            snap=intake_file(stage,self.source,str(self.file),'plain_text','synthetic_fixture')
            with self.assertRaises(ContractError): stage.bundle(snap['snapshot_id'],repo/'packets')

    def test_unknown_or_prohibited_is_not_file_permission(self):
        for status in ['unknown','prohibited']:
            cfg=copy.deepcopy(self.source); cfg['policy']['uses']['local_cache']['status']=status
            with StageLedger(self.root/status) as stage, self.assertRaises(ContractError):
                intake_file(stage,cfg,str(self.file),'plain_text','synthetic_fixture')

    def test_short_multibyte_body_is_rejected_before_staging(self):
        self.file.write_text('虛構測試資料'*4,encoding='utf-8')
        with StageLedger(self.root/'stage') as stage, self.assertRaises(ContractError):
            intake_file(stage,self.source,str(self.file),'plain_text','synthetic_fixture')
        with StageLedger(self.root/'stage') as stage:
            self.assertEqual(stage.stats()['counts']['snapshots'],0)

    def test_local_file_preserves_windows_crlf_bytes_and_body(self):
        raw=b'Synthetic fictional Lunar Rope.\r\nOriginal Windows newlines must survive.\r\n'
        self.file.write_bytes(raw)
        with StageLedger(self.root/'stage') as stage:
            result=intake_file(stage,self.source,str(self.file),'plain_text','synthetic_fixture')
            snapshot=stage.snapshot(result['snapshot_id'],True)
            self.assertEqual(snapshot['body'],raw.decode('utf-8'))
            self.assertEqual(snapshot['raw_sha256'],digest(raw))

    def test_html_file_is_parsed_without_running_script_or_claiming_http(self):
        self.source['selector']={'tag':'main'}
        self.file.write_text('<title>Synthetic</title><main>Synthetic fictional Lunar Rope creates a fictional blue platform.<script>RUN_SOURCE_COMMAND</script></main>',encoding='utf-8')
        with StageLedger(self.root/'stage') as stage:
            snap=intake_file(stage,self.source,str(self.file),'html','synthetic_fixture')
            body=stage.snapshot(snap['snapshot_id'],True)
            self.assertNotIn('RUN_SOURCE_COMMAND',body['body'])
            self.assertEqual(body['metadata']['http_requests'],0)
            self.assertIsNone(body['metadata']['requested_url'])

    def test_cli_optional_http_is_dry_run_and_does_not_create_stage(self):
        plan=self.root/'plan.json'; plan.write_text(json.dumps({'format':'ssr.source-plan.v1','sources':[self.source]}),encoding='utf-8')
        stage=self.root/'not-created'
        result=subprocess.run([sys.executable,'-m','ssr_collector_peak','http-collect','--plan',str(plan),'--source-id',self.source['source_id'],'--stage-dir',str(stage)],capture_output=True,text=True,encoding='utf-8')
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        value=json.loads(result.stdout)
        self.assertEqual(value['network_requests'],0)
        self.assertEqual(value['mode'],'optional_http_dry_run')
        self.assertFalse(stage.exists())
