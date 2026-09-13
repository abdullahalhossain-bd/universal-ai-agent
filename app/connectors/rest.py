from typing import Any
from urllib.parse import quote
import time
import httpx
from app.connectors.base.connector import Connector
from app.core.network_guard import assert_safe_http_url
from app.schemas.product import UniversalProduct
from app.discovery.models import ColumnInfo, DatabaseSchema, TableInfo
class RESTConnector(Connector):
 # A merchant feed can legitimately be large, but r.json() on an unbounded
 # response can OOM the sync worker (which would starve every other job).
 # 64 MB is far above any sane product page and matches the spirit of the
 # crawler's per-page byte cap.
 MAX_RESPONSE_BYTES = 64 * 1024 * 1024

 def __init__(self,base_url:str,api_key:str|None=None,options:dict|None=None):
  self.base_url=base_url.rstrip("/");self.api_key=api_key;self.options=options or {};assert_safe_http_url(self.base_url);self.supports_incremental_sync=bool(self.options.get("cursor_pagination"));self.last_test_error:str|None=None
 def _endpoint(self,name,default):
  value=self.options.get(name,default)
  if not isinstance(value,str) or not value.startswith("/"):raise ValueError(f"REST option {name} must be an absolute path")
  url=f"{self.base_url}{value}";assert_safe_http_url(url);return url
 def _headers(self):return {"Accept":"application/json",**({"Authorization":f"Bearer {self.api_key}"} if self.api_key else {})}
 async def test_connection(self):
  """Probe the merchant API.

  The base URL alone is often 404 (real APIs frequently serve nothing
  at '/'), so a base-URL failure falls back to the configured products
  endpoint before declaring the connection dead. The reason for a
  failure is recorded on ``last_test_error`` so the datasource test
  route can tell the merchant WHAT failed instead of a bare false.
  """
  try:
   async with httpx.AsyncClient(timeout=10,follow_redirects=False) as client:
    try:
     r=await client.get(self.base_url,headers=self._headers())
     if r.status_code<400:return True
     reason=f"base URL responded HTTP {r.status_code}"
    except httpx.HTTPError as exc:
     reason=f"base URL unreachable: {type(exc).__name__}"
    # Base URL failed/unreachable — probe the products endpoint
    # before giving up (it may 404 only on '/').
    try:
     r2=await client.get(self._endpoint("products_endpoint","/products"),headers=self._headers())
     if r2.status_code<400:return True
     self.last_test_error=f"{reason}; products endpoint responded HTTP {r2.status_code}"
    except httpx.HTTPError as exc2:
     self.last_test_error=f"{reason}; products endpoint unreachable: {type(exc2).__name__}"
    return False
  except Exception as exc:
   self.last_test_error=f"{type(exc).__name__}: {exc}";return False
 async def discover(self):
  payload=await self._request_json("GET",self._endpoint("schema_endpoint","/schema"));return DatabaseSchema(tables=[TableInfo(name=str(t["name"]),columns=[ColumnInfo(name=str(c["name"]),data_type=str(c.get("data_type","unknown")),nullable=bool(c.get("nullable",True))) for c in t.get("columns",[])]) for t in payload.get("tables",[])])
 async def get_products(self,limit=50,offset=0):
  payload=await self._request_json("GET",self._endpoint("products_endpoint","/products"),params={"limit":limit,"offset":offset});rows=payload.get("products",payload) if isinstance(payload,dict) else payload;return [self._normalize_product(r) for r in rows]
 async def get_product(self,product_id):
  try:payload=await self._request_json("GET",self._endpoint("product_endpoint","/products")+f"/{quote(str(product_id),safe='')}")
  except httpx.HTTPStatusError as exc:
   if exc.response.status_code==404:return None
   raise
  return self._normalize_product(payload)
 async def get_inventory(self,product_id):return await self._request_json("GET",self._endpoint("inventory_endpoint","/products")+f"/{quote(str(product_id),safe='')}/inventory")
 async def get_store_info(self):return await self._request_json("GET",self._endpoint("store_endpoint","/store"))
 def _fetch(self,params):
  url=self._endpoint("products_endpoint","/products");timeout=httpx.Timeout(60.0,connect=15.0);transient={502,503,504};last=None
  for attempt in range(4):
   try:
    with httpx.Client(timeout=timeout,follow_redirects=False) as client:
     with client.stream("GET",url,headers=self._headers(),params=params) as r:
      r.raise_for_status()
      declared=r.headers.get("content-length")
      if declared and declared.isdigit() and int(declared)>self.MAX_RESPONSE_BYTES:
       raise ValueError(f"REST response too large: {declared} bytes (limit {self.MAX_RESPONSE_BYTES})")
      body=r.read()
      if len(body)>self.MAX_RESPONSE_BYTES:
       raise ValueError(f"REST response too large: {len(body)} bytes (limit {self.MAX_RESPONSE_BYTES})")
    import json as _json
    payload=_json.loads(body)
    rows=payload.get("products",payload) if isinstance(payload,dict) else payload
    if not isinstance(rows,list):raise ValueError("REST products endpoint must return a list or an object with a 'products' list")
    return [x for x in rows if isinstance(x,dict)]
   except (httpx.ConnectError,httpx.ConnectTimeout,httpx.ReadTimeout) as exc:
    last=exc
    if attempt>=3:raise
    time.sleep(2*(attempt+1))
   except httpx.HTTPStatusError as exc:
    last=exc
    if exc.response.status_code not in transient or attempt>=3:raise
    time.sleep(2*(attempt+1))
  raise last or RuntimeError("REST product fetch failed")
 def fetch_product_rows(self,table_name,columns,*,limit=200,offset=0):return self._fetch({"limit":limit,"offset":offset})
 def fetch_product_rows_incremental(self,table_name,columns,*,updated_column=None,created_column=None,id_column=None,watermark_at=None,watermark_id=None,limit=200,upper_bound=None):
  if not self.supports_incremental_sync:raise RuntimeError("REST cursor pagination is not enabled")
  ts=updated_column or created_column;params={"limit":limit}
  if ts and watermark_at is not None:params[self.options.get("updated_after_param","updated_after")]=str(watermark_at)
  # Composite cursor is explicit: the API must order by timestamp,id and honor both bounds.
  if ts and id_column and watermark_id is not None:params[self.options.get("id_after_param","id_after")]=str(watermark_id)
  elif not ts and id_column and watermark_id is not None:params[self.options.get("id_after_param","id_after")]=str(watermark_id)
  if ts and upper_bound is not None:params[self.options.get("updated_before_param","updated_before")]=str(upper_bound)
  params[self.options.get("sort_param","sort")]=self.options.get("sort_value",f"{ts or id_column}:asc")
  return self._fetch(params)
 def get_sync_watermark(self,table_name,timestamp_column=None,id_column=None,*,upper_bound=None):
  if not self.supports_incremental_sync:return {}
  params={"limit":1,self.options.get("sort_param","sort"):self.options.get("sort_value",f"{timestamp_column or id_column}:desc")}
  if upper_bound is not None and timestamp_column:params[self.options.get("updated_before_param","updated_before")]=str(upper_bound)
  rows=self._fetch(params)
  if not rows:return {}
  row=rows[0];out={}
  if timestamp_column and row.get(timestamp_column) is not None:out["watermark_at"]=row[timestamp_column]
  if id_column and row.get(id_column) is not None:out["watermark_id"]=row[id_column]
  return out
 async def _request_json(self,method,url,**kwargs):
  assert_safe_http_url(url)
  async with httpx.AsyncClient(timeout=httpx.Timeout(10.0,connect=3.0),follow_redirects=False) as client:
   r=await client.request(method,url,headers=self._headers(),**kwargs);r.raise_for_status()
   if len(r.content)>self.MAX_RESPONSE_BYTES:raise ValueError(f"REST response too large: {len(r.content)} bytes (limit {self.MAX_RESPONSE_BYTES})")
   return r.json()
 @staticmethod
 def _normalize_product(row):return UniversalProduct(id=str(row.get("id",row.get("product_id",""))),name=str(row.get("name",row.get("product_name",""))),description=row.get("description"),price=row.get("price",row.get("selling_price")),currency=row.get("currency"),stock=row.get("stock",row.get("quantity")),sku=row.get("sku"),category=row.get("category"),brand=row.get("brand"),url=row.get("url",row.get("product_url")),source_metadata=dict(row))
