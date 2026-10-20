"""Synthetic content-shape regressions; real DB comparison is a separate local check."""
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from tools.acceptance_demo import file_hash, read_database
from ssr_collector_peak.primitives import ContractError


class RealContentTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name)/'knowledge.sqlite3'
        db = sqlite3.connect(self.path)
        db.executescript('''CREATE TABLE sources(source_id TEXT,url TEXT,latest_snapshot TEXT,config_json TEXT);
            CREATE TABLE snapshots(snapshot_id TEXT,source_id TEXT,fetched_at TEXT,metadata_json TEXT);
            CREATE TABLE entries(entry_id TEXT,current_revision INTEGER);
            CREATE TABLE entry_revisions(revision_id INTEGER,entry_id TEXT,status TEXT,payload_json TEXT,review_json TEXT,published_at TEXT);''')
        for sid, url, kind in [('table','https://peak.wiki.gg/wiki/Synthetic_fixture','user_provided_text'),
                               ('official','https://store.steampowered.com/app/3527290/PEAK/','installed_game_text'),
                               ('overview','https://en.wikipedia.org/wiki/Synthetic_fixture','http_collection')]:
            cfg={'source_id':sid,'title':'Synthetic source only','language':'en','url':'local:'+sid,'original_url':url,
                 'declared_version':'synthetic-v1','acquisition':{'kind':kind}}
            db.execute('INSERT INTO sources VALUES(?,?,?,?)',(sid,'local:'+sid,sid,json.dumps(cfg)))
            db.execute('INSERT INTO snapshots VALUES(?,?,?,?)',(sid,sid,'2026-01-01T00:00:00+00:00',json.dumps({'acquisition_kind':kind,'original_url':url})))
        self.item={'entry_id':'synthetic-flask','category':'item','name_en':'Solar Flask','name_zh':'合成太陽瓶','aliases':['小瓶'],
            'summary_zh':'原表未附用途備註；已保存數值與出現區域。',
            'item_details':{'statistics':{'weight':{'state':'value','value':0,'raw':'Weight 0'},
                'hunger':{'state':'value','value':-7,'raw':'Hunger -7'},
                'poison':{'state':'source_na','value':None,'raw':'n/a'}},'biomes_en':['Any'],
                'notes_en':[],'notes_zh':[],'locations_en':[],'acquisition_en':[],'cooking_en':[]},
            'detail_page':{'url':'https://example.test/not-acquired'},
            'citations':[{'snapshot_id':'table','locator':'synthetic rows 1-2','evidence_quote':'Self-authored synthetic fixture.'}]}
        payloads=[self.item,{'entry_id':'concept','category':'achievement','name_en':'Badges concept','name_zh':'制度概覽',
            'aliases':['成就'],'summary_zh':'合成制度概述。','citations':[{'snapshot_id':'overview','locator':'Synthetic overview'}]}]
        for i in range(64):
            payloads.append({'entry_id':'badge-'+str(i),'category':'achievement','name_en':f'Fixture Badge {i:02}',
                'name_zh':f'合成徽章{i:02}','aliases':[], 'summary_zh':f'合成條件{i}，不是 PEAK 內容。',
                'badge_details':{'kind':'game_badge','condition_zh':f'合成條件{i}，不是 PEAK 內容。',
                    'condition_en':f'Fictional condition {i}.','english_citation':0},
                'citations':[{'snapshot_id':'official','locator':'SYNTHETIC_DESC_'+str(i)}]})
        for revision,payload in enumerate(payloads,1):
            db.execute('INSERT INTO entries VALUES(?,?)',(payload['entry_id'],revision))
            db.execute('INSERT INTO entry_revisions VALUES(?,?,?,?,NULL,NULL)',(revision,payload['entry_id'],'pending_review',json.dumps(payload,ensure_ascii=False)))
        db.commit();db.close()

    def tearDown(self): self.temp.cleanup()

    def test_category_keyword_returns_each_badge_and_all_pages_without_overview(self):
        seen=[]
        for page in range(1,7):
            data=read_database(self.path,formal=True,query='成就',page=page)
            self.assertEqual(data['total_matches'],64)
            self.assertEqual(data['pages'],6)
            self.assertEqual(data['category_counts']['achievement'],64)
            seen.extend(p['entry_id'] for p in data['samples'])
            self.assertTrue(all(p['condition_zh'] for p in data['samples']))
        self.assertEqual(len(seen),64)
        self.assertEqual(len(set(seen)),64)
        self.assertNotIn('concept',seen)
        self.assertEqual(read_database(self.path,formal=True,query='badges')['total_matches'],64)

    def test_item_values_zero_na_biome_sources_and_missing_detail_are_preserved(self):
        before=file_hash(self.path)
        data=read_database(self.path,formal=True,query='小瓶')['samples'][0]
        stats={s['key']:s for s in data['statistics']}
        self.assertEqual(stats['weight']['display'],'0')
        self.assertEqual(stats['hunger']['display'],'−7')
        self.assertIsNone(stats['poison']['value'])
        self.assertEqual(stats['poison']['display'],'n/a')
        self.assertEqual(data['biomes'],['Any'])
        self.assertEqual(data['summary_zh'],'')
        self.assertFalse(data['detail_page']['saved'])
        self.assertIn('具體取得位置／方式：原表未記載。',data['gaps'])
        source=data['sources'][0]
        self.assertEqual(source['site'],'PEAK Wiki')
        self.assertIn('非直接抓頁',source['acquisition'])
        self.assertEqual(source['locator'],'synthetic rows 1-2')
        self.assertEqual(file_hash(self.path),before)

    def test_official_game_resource_is_not_mislabeled_as_steam_page_evidence(self):
        badge=read_database(self.path,formal=True,query='Fixture Badge 00')['samples'][0]
        source=badge['sources'][0]
        self.assertIsNone(source['href'])
        self.assertEqual(source['site'],'PEAK 本機遊戲資源')
        self.assertIn('非本文來源',source['context_label'])
        self.assertEqual(badge['condition_en'],'Fictional condition 0.')

    def test_overview_keeps_its_actual_wikipedia_site(self):
        overview=read_database(self.path,formal=True,query='制度概覽')['samples'][0]
        self.assertTrue(overview['overview'])
        self.assertEqual(overview['sources'][0]['site'],'Wikipedia')
        self.assertIn('en.wikipedia.org',overview['sources'][0]['href'])

    def test_bad_pages_are_rejected_and_high_page_is_clamped(self):
        for options in [{'page':0},{'page_size':51},{'category':'invented'}]:
            with self.assertRaises(ContractError): read_database(self.path,formal=True,**options)
        last=read_database(self.path,formal=True,query='成就',page=999)
        self.assertEqual((last['page'],last['range_start'],last['range_end']),(6,61,64))
