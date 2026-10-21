"""Intake of an explicitly permitted local file; never opens a browser or HTTP."""
from pathlib import Path
from typing import Any

from .http_collection import BodyExtractor
from .primitives import ContractError, digest, utc_now
from .stage import StageLedger


def intake_file(stage: StageLedger, source: dict[str,Any], file: str, body_format: str, origin: str, capture_receipt: dict | None = None) -> dict[str,Any]:
    if source.get('acquisition',{}).get('kind')!='approved_local_file':
        raise ContractError('file intake requires a separately registered approved_local_file source')
    policy=source['policy']
    if policy.get('allow_import') is not True or policy['uses']['local_cache']['status']!='allowed':
        raise ContractError('local-file purpose is not explicitly allowed; unknown is not permission')
    if body_format not in {'plain_text','html'} or origin not in {'operator_file','synthetic_fixture'}:
        raise ContractError('explicit file format and acquisition origin required')
    path=Path(file)
    if not path.is_file() or not 40<=path.stat().st_size<=2_000_000:
        raise ContractError('local file must be 40 bytes to 2 MB')
    raw=path.read_bytes(); text=raw.decode('utf-8-sig',errors='strict')
    if capture_receipt is not None:
        from .capture_receipt import validate_capture_receipt
        if origin != 'operator_file' or body_format != 'html':raise ContractError('DOM receipt requires operator_file HTML input')
        validate_capture_receipt(capture_receipt,source,raw)
    if '\x00' in text: raise ContractError('expected UTF-8 text without NUL')
    if body_format=='html':
        parser=BodyExtractor(source['selector']); parser.feed(text); parser.close(); body=parser.body()
    else:
        body=text
    if not 40<=len(body)<=2_000_000:
        raise ContractError('extracted body must be 40 characters to 2 million characters')
    meta={'acquisition_kind':'approved_local_file','acquisition_method':origin,'body_format':body_format,
        'original_filename':path.name,'input_sha256':digest(raw),'purpose':'local_cache',
        'http_requests':0,'collector_called_llm':False,'requested_url':None,'original_url':source['original_url'],
        'canonical_url':source['original_url'],'canonical_basis':'Central attribution URL; local file, not an HTTP fetch',
        'source_updated_at':None,'source_updated_basis':'Unknown; file capture time is not the page update time',
        'body_locator':{'format':body_format},'imported_at':utc_now()}
    if capture_receipt is not None:
        meta.update(capture_receipt=capture_receipt,requested_url=capture_receipt['requested_url'],
                    canonical_url=capture_receipt['final_url'],canonical_basis='Observed selected Chrome tab URL; not an HTTP status',
                    source_updated_basis=str(capture_receipt['page_updated'])+'; page timezone unknown',browser_network_request_count=None)
    stage.register_source(source)
    result=stage.save_snapshot(source,raw,body,meta)
    stage.event(source['source_id'],'local_file_intake',{**result,'http_requests':0})
    return {**result,'acquisition_kind':'approved_local_file','origin':origin,'http_requests':0,'authoritative_knowledge_saved':False}
