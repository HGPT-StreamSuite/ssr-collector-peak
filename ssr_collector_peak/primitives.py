"""Local primitives. No import from another repository or shared package."""
from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SOURCE_TYPES = {"official", "wiki", "third_party_analysis", "player_test"}
USAGE_PURPOSES = {"local_cache", "search_index", "ai_input", "ai_train"}


class ContractError(ValueError):
    pass


def canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value: bytes | str) -> str:
    return hashlib.sha256(value.encode('utf-8') if isinstance(value,str) else value).hexdigest()


def identifier(value: Any) -> str:
    if not isinstance(value,str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,127}',value):
        raise ContractError('invalid identifier')
    return value


def required_text(value: Any, label: str, maximum: int = 4000) -> str:
    if not isinstance(value,str) or not value.strip() or len(value)>maximum:
        raise ContractError(f'{label}: nonempty bounded string required')
    return value


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def private_output(path: str | Path) -> Path:
    result=Path(path).expanduser().resolve()
    for parent in [result,*result.parents]:
        if (parent/'.git').exists(): raise ContractError('stage/output must be outside every Git checkout')
        if (parent/'knowledge.sqlite3').exists(): raise ContractError('collector cannot write in a knowledge archive directory')
    return result
