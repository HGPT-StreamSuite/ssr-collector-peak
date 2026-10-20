"""Read-only presentation of saved knowledge; never acquires or invents content."""
from __future__ import annotations

import json
import math
import sqlite3
import unicodedata
from typing import Any
from urllib.parse import urlsplit

from ssr_collector_peak.primitives import ContractError

CATEGORIES = {'item':'道具','achievement':'成就／遊戲徽章','mechanic':'機制','status':'狀態','location':'地點',
              'creature':'生物','guide':'攻略','lore':'世界觀','update':'更新','other':'其他'}
CATEGORY_QUERIES = {'成就':'achievement','徽章':'achievement','勳章':'achievement','成就勳章':'achievement',
                    'badges':'achievement','achievements':'achievement','道具':'item','物品':'item',
                    'items':'item','機制':'mechanic','狀態':'status','地點':'location','攻略':'guide','世界觀':'lore'}
STAT_LABELS = {'weight':'重量','hunger':'飢餓','bonus_stamina':'額外體力','poison':'中毒','heat':'炎熱',
               'cold':'寒冷','injury':'受傷','spores':'孢子','curse':'詛咒','drowsiness':'嗜睡','stamina':'體力'}
TOPICS = {'effects':'效果／用途','acquisition':'取得方式','cooking':'烹調','conditions':'條件',
          'badge_hints':'徽章提示','location':'地點','prerequisites':'前置條件','steps':'步驟',
          'constraints':'限制','tips':'技巧','recipients':'獲得對象','reward':'獎勵'}
ACQUISITIONS = {'user_provided_text':'使用者提供的頁面文字（已保存，非直接抓頁）',
                'installed_game_text':'本機官方遊戲文字（已保存）',
                'web_search_excerpt':'搜尋索引摘錄（已保存，並非詳細頁全文）',
                'local_name_reference':'名稱參考資料（已保存）','http_collection':'頁面快照（已保存）',
                'approved_local_file':'獲准的本機檔案（已保存）'}


def normalized(value: str) -> str:
    return unicodedata.normalize('NFKC', value).casefold().strip()


def safe_href(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    parsed = urlsplit(value)
    return value if parsed.scheme == 'https' and parsed.hostname and not parsed.username and not parsed.password else None


def strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, list):
        return list(dict.fromkeys(item for item in value if isinstance(item, str) and item.strip()))
    return []


def saved_sources(db: sqlite3.Connection, payload: dict[str, Any]) -> list[dict[str, Any]]:
    result = []
    for index, citation in enumerate(payload.get('citations', [])):
        snapshot = db.execute('SELECT * FROM snapshots WHERE snapshot_id=?', (citation['snapshot_id'],)).fetchone()
        if snapshot is None:
            result.append({'index':index+1,'title':'引用快照不存在','acquisition':'未能讀回來源','locator':citation.get('locator',''),'href':None})
            continue
        source = db.execute('SELECT * FROM sources WHERE source_id=?', (snapshot['source_id'],)).fetchone()
        config = json.loads(source['config_json']) if source and 'config_json' in source.keys() else {}
        meta = json.loads(snapshot['metadata_json'])
        kind = meta.get('acquisition_kind', config.get('acquisition',{}).get('kind','http_collection'))
        original = meta.get('original_url') or config.get('original_url') or config.get('url','')
        host = urlsplit(original).hostname or ''
        site = 'PEAK Wiki' if host == 'peak.wiki.gg' else 'Wikipedia' if host.endswith('.wikipedia.org') else host
        installed = kind == 'installed_game_text'
        result.append({'index':index+1,'source_id':snapshot['source_id'],
            'title':('PEAK 官方遊戲文字 · '+str(config.get('language',''))) if installed else config.get('title', meta.get('title', '已保存來源')),
            'site':'PEAK 本機遊戲資源' if installed else site,
            'href':None if installed else safe_href(original),
            'context_href':safe_href(original) if installed else None,
            'context_label':'遊戲歸屬連結，非本文來源' if installed else None,
            'acquisition':ACQUISITIONS.get(kind, kind), 'acquisition_kind':kind,
            'locator':citation.get('locator','未記錄段落'), 'captured_at':snapshot['fetched_at'],
            'source_updated_at':meta.get('source_updated_at'), 'updated_basis':meta.get('source_updated_basis'),
            'version':config.get('declared_version'), 'quote':citation.get('evidence_quote',''),
            'license_url':safe_href(meta.get('license_url')), 'license_statement':meta.get('license_statement')})
    return result


def present(db: sqlite3.Connection, row: sqlite3.Row, payload: dict[str, Any]) -> dict[str, Any]:
    item = payload.get('item_details', {})
    badge = payload.get('badge_details', {})
    guide = payload.get('guide_details', {})
    summary = payload.get('summary_zh','')
    if summary == '原表未附用途備註；已保存數值與出現區域。':
        summary = ''
    overview = payload.get('category') == 'achievement' and badge.get('kind') != 'game_badge'
    if overview:
        summary = summary.split('本稿')[0].strip()
    stats = []
    for key, value in item.get('statistics', {}).items():
        state = value.get('state')
        actual = value.get('value')
        display = 'n/a（來源原值）' if state == 'source_na' else str(actual).replace('-', '−') if actual is not None else '未記載'
        stats.append({'key':key,'label':STAT_LABELS.get(key,key),'value':actual,'display':display,
                      'source_raw':value.get('raw'),'state':state,'source_refs':[1] if payload.get('citations') else []})
    sections = []
    for key, label in [('notes_zh','用途／備註'),('notes_en','原文備註'),('acquisition_en','取得方式'),
                       ('locations_en','具體位置'),('cooking_en','烹調'),('restrictions_en','限制')]:
        values = strings(item.get(key))
        if values:
            sections.append({'title':label,'lines':values,'source_refs':[1]})
    gaps = [g['reason'] for g in guide.get('gaps',[]) if isinstance(g,dict) and g.get('reason')]
    if item:
        if not item.get('locations_en') and not item.get('acquisition_en'):
            gaps.append('具體取得位置／方式：原表未記載。')
        if not item.get('notes_en') and not item.get('notes_zh'):
            gaps.append('詳細使用方法：原表未附備註。')
        if not item.get('cooking_en'):
            gaps.append('烹調效果：原表未記載。')
    detail = payload.get('detail_page', {})
    sources = saved_sources(db,payload)
    detail_href = safe_href(detail.get('url'))
    detail_saved = bool(detail_href and any(s.get('href') == detail_href and s.get('acquisition_kind') != 'web_search_excerpt' for s in sources))
    if detail_href and not detail_saved:
        gaps.append('個別詳細頁正文尚未保存。')
    if badge and not guide:
        gaps.append('詳細攻略、獎勵與實際解鎖邏輯尚未保存。')
    claims = []
    for claim in guide.get('claims', []):
        claims.append({'title':TOPICS.get(claim.get('topic'),claim.get('topic','補充')),
            'text':claim.get('text_zh',''),'source_class':claim.get('source_class'),
            'source_refs':sorted({e['citation']+1 for e in claim.get('evidence',[]) if isinstance(e.get('citation'),int)})})
    for source in sources:
        source['role'] = ('名稱／官方條件' if badge else '名稱') if source.get('acquisition_kind') == 'installed_game_text' else '數值／表格備註' if item and source['index'] == 1 else '攻略補充' if guide else '內容'
    return {'entry_id':row['entry_id'],'revision_id':row['revision_id'],'status':row['status'],
        'category':payload.get('category','other'),'category_label':CATEGORIES.get(payload.get('category'),'其他'),
        'name_en':payload.get('name_en',''),'name_zh':payload.get('name_zh',''),'aliases':payload.get('aliases',[]),
        'summary_zh':summary,'overview':overview,'statistics':stats,'biomes':strings(item.get('biomes_en')),
        'sections':sections,'condition_zh':badge.get('condition_zh'),'condition_en':badge.get('condition_en'),
        'condition_refs':[badge[k]+1 for k in ['english_citation','traditional_citation'] if isinstance(badge.get(k),int)],
        'guide_claims':claims,'gaps':list(dict.fromkeys(gaps)), 'sources':sources,
        'detail_page':{'href':detail_href,'saved':detail_saved} if detail_href else None,
        'game_version':payload.get('game_version','unknown')}


def browse(db: sqlite3.Connection, query: str = '', category: str = 'all', page: int = 1, page_size: int = 12) -> dict[str, Any]:
    if category not in {'all',*CATEGORIES} or page < 1 or not 1 <= page_size <= 50:
        raise ContractError('invalid content category or page')
    needle = normalized(query)
    inferred = CATEGORY_QUERIES.get(needle)
    if inferred:
        category, needle = inferred, ''
    rows = [(row,json.loads(row['payload_json'])) for row in db.execute('SELECT e.entry_id,r.status,r.revision_id,r.payload_json FROM entries e JOIN entry_revisions r ON e.current_revision=r.revision_id')]
    counts = {key:0 for key in CATEGORIES}
    for _, payload in rows:
        kind = payload.get('category','other')
        if kind == 'achievement' and payload.get('badge_details',{}).get('kind') != 'game_badge':
            continue
        counts[kind if kind in counts else 'other'] += 1
    selected = []
    for row, payload in rows:
        if category != 'all' and payload.get('category') != category:
            continue
        if category == 'achievement' and payload.get('badge_details',{}).get('kind') != 'game_badge':
            continue
        searchable = [payload.get(key,'') for key in ['name_en','name_zh','aliases','summary_zh']]
        searchable += [payload.get('item_details',{}),payload.get('badge_details',{}),
                       [c.get('text_zh','') for c in payload.get('guide_details',{}).get('claims',[])]]
        if needle and needle not in normalized(json.dumps(searchable,ensure_ascii=False)):
            continue
        selected.append((row,payload))
    selected.sort(key=lambda pair:(normalized(pair[1].get('name_en','')),pair[0]['entry_id']))
    total = len(selected); pages = max(1, math.ceil(total/page_size)); page = min(page,pages)
    entries = [present(db,row,payload) for row,payload in selected[(page-1)*page_size:page*page_size]]
    return {'samples':entries,'total_matches':total,'page':page,'page_size':page_size,'pages':pages,
            'category':category,'category_inferred':bool(inferred),'query':query,'category_counts':counts,
            'range_start':(page-1)*page_size+1 if total else 0,'range_end':min(page*page_size,total),
            'content_scope':'已保存內容瀏覽；缺欄依現存資料列出，並非內容完整性通過判定。'}
