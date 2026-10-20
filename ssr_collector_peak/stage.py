"""Private acquisition spool. No entries, review, publication or knowledge query."""
from __future__ import annotations

import base64
import json
import shutil
import sqlite3
from pathlib import Path
from typing import Any

from .primitives import ContractError, canonical, digest, private_output, utc_now

APPLICATION_ID = 0x53534350


class StageLedger:
    def __init__(self, root: str | Path):
        self.root=private_output(root)
        self.root.mkdir(parents=True,exist_ok=True)
        if shutil.disk_usage(self.root).free<50*1024*1024: raise ContractError('stage requires 50 MiB free disk')
        file=self.root/'collector-stage.sqlite3'
        if file.exists():
            check=sqlite3.connect(file.resolve().as_uri()+'?mode=ro',uri=True)
            try:
                if check.execute('PRAGMA application_id').fetchone()[0]!=APPLICATION_ID:
                    raise ContractError('not a collector spool; refusing to initialize over another database')
            finally:
                check.close()
        self.db=sqlite3.connect(file)
        self.db.row_factory=sqlite3.Row
        self.db.executescript(f'''PRAGMA application_id={APPLICATION_ID};
            CREATE TABLE IF NOT EXISTS sources(source_id TEXT PRIMARY KEY,url TEXT UNIQUE NOT NULL,config_json TEXT NOT NULL,latest_snapshot TEXT);
            CREATE TABLE IF NOT EXISTS snapshots(snapshot_id TEXT PRIMARY KEY,source_id TEXT NOT NULL,captured_at TEXT NOT NULL,raw BLOB NOT NULL,body TEXT NOT NULL,config_json TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS observations(observation_id INTEGER PRIMARY KEY,snapshot_id TEXT NOT NULL,observed_at TEXT NOT NULL,metadata_json TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS events(event_id INTEGER PRIMARY KEY,at TEXT NOT NULL,source_id TEXT,event TEXT NOT NULL,details_json TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS throttles(origin TEXT PRIMARY KEY,next_at REAL NOT NULL);''')

    def close(self) -> None:
        self.db.close()

    def __enter__(self): return self
    def __exit__(self,*_): self.close()

    def event(self, source_id: str | None, event: str, details: dict[str,Any]) -> None:
        with self.db: self.db.execute('INSERT INTO events(at,source_id,event,details_json) VALUES(?,?,?,?)',(utc_now(),source_id,event,canonical(details)))

    def history(self,limit: int=100) -> list[dict[str,Any]]:
        return [{**dict(r),'details':json.loads(r['details_json'])} for r in self.db.execute('SELECT * FROM events ORDER BY event_id DESC LIMIT ?',(limit,))]

    def register_source(self, source: dict[str,Any]) -> None:
        old=self.db.execute('SELECT url FROM sources WHERE source_id=?',(source['source_id'],)).fetchone()
        if old and old[0]!=source['url']: raise ContractError('source_id URL cannot change')
        try:
            with self.db: self.db.execute('INSERT INTO sources(source_id,url,config_json) VALUES(?,?,?) ON CONFLICT(source_id) DO UPDATE SET config_json=excluded.config_json',
                (source['source_id'],source['url'],canonical(source)))
        except sqlite3.IntegrityError as exc: raise ContractError('URL already registered with another source_id') from exc

    def save_snapshot(self, source: dict[str,Any], raw: bytes, body: str, metadata: dict[str,Any]) -> dict[str,Any]:
        sid=digest(source['url']+'\0'+digest(raw)+'\0'+digest(canonical(source)))
        old=self.db.execute('SELECT latest_snapshot FROM sources WHERE source_id=?',(source['source_id'],)).fetchone()
        with self.db:
            self.db.execute('INSERT OR IGNORE INTO snapshots VALUES(?,?,?,?,?,?)',(sid,source['source_id'],utc_now(),raw,body,canonical(source)))
            self.db.execute('INSERT INTO observations(snapshot_id,observed_at,metadata_json) VALUES(?,?,?)',(sid,utc_now(),canonical(metadata)))
            self.db.execute('UPDATE sources SET latest_snapshot=? WHERE source_id=?',(sid,source['source_id']))
        return {'source_id':source['source_id'],'snapshot_id':sid,'state':'unchanged' if old and old[0]==sid else 'saved',
                'raw_sha256':digest(raw),'body_sha256':digest(body),'raw_bytes':len(raw),'body_characters':len(body)}

    def snapshot(self, sid: str, include_body: bool=False) -> dict[str,Any]:
        row=self.db.execute('SELECT * FROM snapshots WHERE snapshot_id=?',(sid,)).fetchone()
        if row is None: raise ContractError('staged document not found')
        observation=self.db.execute('SELECT * FROM observations WHERE snapshot_id=? ORDER BY observation_id DESC LIMIT 1',(sid,)).fetchone()
        meta=json.loads(observation['metadata_json']); source=json.loads(row['config_json'])
        result={'snapshot_id':sid,'source_id':row['source_id'],'source':source,'metadata':meta,
            'captured_at':row['captured_at'],'observed_at':observation['observed_at'],'raw_sha256':digest(row['raw']),'body_sha256':digest(row['body']),
            'provenance':{'canonical_url':meta.get('canonical_url',source['url']),'source_updated_at':meta.get('source_updated_at')}}
        if include_body: result['body']=row['body']
        return result

    def stats(self) -> dict[str,Any]:
        return {'kind':'acquisition_spool_only','counts':{t:self.db.execute('SELECT count(*) FROM '+t).fetchone()[0] for t in ['sources','snapshots','observations','events']},
                'knowledge_entries':0,'can_review_or_publish':False}

    def bundle(self, sid: str, output: str | Path) -> dict[str,Any]:
        doc=self.snapshot(sid,True)
        row=self.db.execute('SELECT raw FROM snapshots WHERE snapshot_id=?',(sid,)).fetchone()
        metadata={k:v for k,v in doc['metadata'].items() if k!='policy'}
        metadata.setdefault('acquisition_kind','http_collection')
        packet={'format':'ssr.collection.v1','producer':'ssr-collector-peak/0.1.0',
            'source_ref':{'source_id':doc['source_id'],'config_sha256':digest(canonical(doc['source']))},
            'document':{'url':doc['source']['url'],'captured_at':doc['captured_at'],'observed_at':doc['observed_at'],
                        'raw_base64':base64.b64encode(row['raw']).decode('ascii'),'raw_sha256':doc['raw_sha256'],
                        'body':doc['body'],'body_sha256':doc['body_sha256'],'metadata':metadata}}
        packet['bundle_id']=digest(canonical(packet))
        root=private_output(output); root.mkdir(parents=True,exist_ok=True)
        path=root/(packet['bundle_id']+'.collection.json'); data=canonical(packet).encode('utf-8')
        if path.exists() and path.read_bytes()!=data: raise ContractError('bundle collision; refusing overwrite')
        if not path.exists(): path.write_bytes(data)
        return {'bundle_id':packet['bundle_id'],'path':str(path),'format':packet['format'],'source_ref':packet['source_ref'],
                'authoritative_knowledge_saved':False}
