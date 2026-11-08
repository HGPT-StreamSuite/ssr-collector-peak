"""Validate central plan data without fetching, normalizing, or granting policy."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .http_collection import validate_manifest
from .primitives import ContractError, canonical, digest, identifier


def _finite_json(value: str) -> None:
    raise ContractError('source plan requires finite JSON numbers: ' + value)


def _validate_source(source: dict[str, Any]) -> None:
    """Use the receiver's existing file/HTTP profiles; keep the original bytes' meaning."""
    try:
        if 'acquisition' not in source:
            validate_manifest({'manifest_version': 1, 'game': 'PEAK:3527290', 'sources': [source]})
            return
        fields = {'source_id', 'url', 'original_url', 'source_type', 'title', 'language',
                  'declared_version', 'selector', 'policy', 'interval_seconds', 'acquisition'}
        if set(source) != fields:
            raise ContractError('file source requires exactly the documented central fields')
        identifier(source['source_id'])
        if source['url'] != 'approved-file:' + source['source_id'] or source['acquisition'] != {'kind': 'approved_local_file'}:
            raise ContractError('file permission must remain a separate approved_local_file source')
        policy = source['policy']
        if not isinstance(policy, dict) or type(policy.get('allow_import')) is not bool or policy.get('allow_fetch') is not False:
            raise ContractError('file source needs explicit allow_import and allow_fetch=false')
        # Same structural policy check as ssr-knowledge's file-source validator.
        # The normalized validation copy is discarded; config_sha256 binds the original.
        network_form = {key: value for key, value in source.items() if key != 'acquisition'}
        network_form['url'] = source['original_url']
        network_form['policy'] = {key: value for key, value in policy.items() if key != 'allow_import'}
        validate_manifest({'manifest_version': 1, 'game': 'PEAK:3527290', 'sources': [network_form]})
    except (KeyError, TypeError, AttributeError, OverflowError) as error:
        raise ContractError('malformed central source record') from error


def source_from_plan(file: str | Path, source_id: str) -> dict[str, Any]:
    identifier(source_id)
    try:
        value = json.loads(Path(file).read_text(encoding='utf-8-sig'), parse_constant=_finite_json)
    except (json.JSONDecodeError, UnicodeError) as error:
        raise ContractError('source plan must be valid UTF-8 JSON') from error
    if (not isinstance(value, dict) or value.get('format') != 'ssr.source-plan.v1'
            or not isinstance(value.get('sources'), list)):
        raise ContractError('expected central ssr.source-plan.v1; no policy inferred from a URL')
    if 'game' in value and value['game'] != 'PEAK:3527290':
        raise ContractError('source plan game differs from PEAK:3527290')
    if any(not isinstance(source, dict) for source in value['sources']):
        raise ContractError('source plan records must be JSON objects')
    if 'registry_sha256' in value:
        supplied = value['registry_sha256']
        if (not isinstance(supplied, str) or not re.fullmatch('[0-9a-f]{64}', supplied)
                or supplied != digest(canonical(value['sources']))):
            raise ContractError('source plan registry_sha256 differs; obtain a fresh central export')
    matches = [source for source in value['sources'] if source.get('source_id') == source_id]
    if len(matches) != 1:
        raise ContractError('source-id must resolve to one central source record')
    source = matches[0]
    _validate_source(source)
    return source
