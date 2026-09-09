"""Deterministic fingerprints for source-vs-local product change detection."""
from __future__ import annotations
import hashlib,json
from decimal import Decimal
from typing import Any
_FIELDS=("id","sku","name","description","category","price","currency","stock","image_url","product_url","attributes","rating","review_count","sales_count")
def _jsonable(value:Any):
    if isinstance(value,Decimal):return str(value)
    if isinstance(value,dict):return {str(k):_jsonable(value[k]) for k in sorted(value,key=lambda x:str(x))}
    if isinstance(value,(list,tuple)):return [_jsonable(v) for v in value]
    if isinstance(value,set):return sorted((_jsonable(v) for v in value),key=lambda x:repr(x))
    return value
def product_fingerprint(product:dict[str,Any])->str:
    payload={field:_jsonable(product.get(field)) for field in _FIELDS}
    encoded=json.dumps(payload,ensure_ascii=False,sort_keys=True,separators=(",",":"),default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
