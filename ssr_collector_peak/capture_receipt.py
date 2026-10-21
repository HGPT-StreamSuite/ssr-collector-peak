"""Optional DOM observation record; never a permission grant or authentication."""
from datetime import datetime, timezone
from urllib.parse import urlsplit
from .primitives import ContractError, digest

FIELDS = {'format','requested_url','final_url','title','captured_at','raw_sha256','export_format',
          'selector','scope','page_updated','license_statement','license_links','method','http_status'}


def validate_capture_receipt(value, source, raw):
    if not isinstance(value,dict) or set(value) != FIELDS:
        raise ContractError('exact ssr.browser-export.v1 receipt required')
    if (value['format'] != 'ssr.browser-export.v1' or value['method'] not in {'local_chrome_computer_use','local_chrome_playwright'}
            or value['export_format'] not in {'rendered_dom_html','rendered_text_html'} or value['http_status'] is not None
            or value['raw_sha256'] != digest(raw)):
        raise ContractError('DOM export method/hash differs; unobserved HTTP status must be null')
    for field in ['requested_url','final_url']:
        if not isinstance(value[field],str) or len(value[field]) > 1000:raise ContractError('bounded capture URL required')
        url=urlsplit(value[field])
        if (url.scheme != 'https' or not url.hostname or url.username or url.password
                or value[field] != source['original_url']):
            raise ContractError('capture URL differs from exact central attribution URL')
    for field in ['title','selector','scope']:
        if not isinstance(value[field],str) or not 1 <= len(value[field]) <= 2000:
            raise ContractError('bounded capture observation fields required')
    for field in ['page_updated','license_statement']:
        if value[field] is not None and (not isinstance(value[field],str) or len(value[field]) > 2000):
            raise ContractError('unknown page date/license must remain null')
    try:
        at=datetime.fromisoformat(value['captured_at'])
        if at.tzinfo is None or (at-datetime.now(timezone.utc)).total_seconds() > 60:raise ValueError
    except (TypeError,ValueError) as error:
        raise ContractError('timezone-aware non-future capture time required') from error
    if not isinstance(value['license_links'],list) or len(value['license_links']) > 5:
        raise ContractError('bounded observed license links required')
    for link in value['license_links']:
        if not isinstance(link,dict) or set(link) != {'href','text'}:raise ContractError('invalid observed license link')
        if not isinstance(link['href'],str) or len(link['href']) > 1000:raise ContractError('bounded license URL required')
        url=urlsplit(link['href'])
        if url.scheme != 'https' or not url.hostname or url.username or url.password or not isinstance(link['text'],str) or len(link['text']) > 2000:
            raise ContractError('invalid observed license URL')
    return value
