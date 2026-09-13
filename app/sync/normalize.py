"""Normalize raw merchant rows into the local Product field shape."""
from __future__ import annotations
import json,re
from typing import Any
REQUIRED_FIELDS=("id","name")
_CURRENCY_AND_GROUPING=re.compile(r"[^0-9+\-.,]")
_KEY_RE=re.compile(r"[^a-z0-9]+")
_FIELD_ALIASES={
 "id":("id","productid","product_id","itemid","item_id","code","productcode","product_code"),
 "sku":("sku","productsku","product_sku","itemsku","item_sku","stockkeepingunit","stock_keeping_unit","itemcode","item_code","productcode","product_code"),
 "name":("name","productname","product_name","title","producttitle","product_title","itemname","item_name"),
 "description":("description","productdescription","product_description","details","summary","shortdescription"),
 "price":("price","saleprice","sale_price","sellingprice","selling_price","regularprice","regular_price","amount","cost"),
 "stock":("stock","quantity","qty","inventory","inventoryquantity","inventory_quantity","stockquantity","stock_quantity","availablequantity","available_quantity"),
 "category":("category","categoryname","category_name","productcategory","product_category","type","producttype","product_type"),
 "brand":("brand","brandname","brand_name","manufacturer","vendor","make"),
 "currency":("currency","currencycode","currency_code","pricecurrency","price_currency"),
 "image_url":("image_url","image","images","main_image","mainimage","image_src","imagesource","image_source","imageurl","image_url_1","thumbnail","thumbnail_url","thumbnailurl","featured_image","featuredimage","photo","picture","productimage","product_image","productphoto","product_photo","primaryimage","primary_image","coverimage","cover_image"),
 "product_url":("product_url","producturl","url","link","product_link","productlink","permalink","product_page","productpage","product_page_url","productpageurl","web_url","weburl","shop_url","shopurl","href","product_href","producthref"),
}
_IMAGE_EXCLUDE={"alt","alttext","alt_text","caption","name","title","id"}
def _key(value:Any)->str:return _KEY_RE.sub("",str(value or "").casefold())
def _mapping_column(mapping:dict,key:str)->str|None:
 entry=mapping.get(key)
 if entry is None:return None
 if isinstance(entry,dict):
  column=entry.get("column");aliases=entry.get("aliases") or []
  if isinstance(column,str) and column.strip():return column.strip()
  if isinstance(aliases,str) and aliases.strip():return aliases.strip()
  if isinstance(aliases,(list,tuple)):
   for alias in aliases:
    if isinstance(alias,str) and alias.strip():return alias.strip()
  return None
 return entry.strip() if isinstance(entry,str) and entry.strip() else None
def _available_columns(raw:dict)->list[str]:return [str(c) for c in raw.keys() if c is not None]
def _looks_like_url(value:Any)->bool:
 if not isinstance(value,str):return False
 text=value.strip();return bool(re.match(r"^(?:https?://|//|/|[A-Za-z0-9._~-]+/)",text,re.I)) or ("." in text and " " not in text and len(text)>=5)
def _looks_like_image(value:Any)->bool:
 if isinstance(value,(list,tuple,dict)):return True
 if not isinstance(value,str):return False
 text=value.strip().casefold()
 return bool(text) and (any(ext in text for ext in (".jpg",".jpeg",".png",".webp",".gif",".avif",".svg")) or "image" in text or "images" in text)
def _resolve_column(mapping:dict,raw:dict,field:str)->str|None:
 explicit=_mapping_column(mapping,field)
 if explicit and explicit in raw:return explicit
 columns=_available_columns(raw)
 if not columns:return explicit
 normalized={_key(c):c for c in columns}
 for alias in _FIELD_ALIASES.get(field,(field,)):
  match=normalized.get(_key(alias))
  if match:return match
 entry=mapping.get(field)
 if isinstance(entry,dict):
  aliases=entry.get("aliases") or []
  if isinstance(aliases,str):aliases=[aliases]
  for alias in aliases:
   match=normalized.get(_key(alias))
   if match:return match
 for column in columns:
  nk=_key(column)
  if not nk:continue
  if field=="image_url":
   if any(t in nk for t in ("alt","caption")):continue
   if any(t in nk for t in ("image","photo","picture","thumbnail","featured","cover")) and ("url" in nk or _looks_like_image(raw.get(column))):return column
  elif field=="product_url":
   if any(t in nk for t in ("image","photo","thumbnail","avatar","logo")):continue
   if any(t in nk for t in ("product","item","page","permalink","link","url","href","shop")) and _looks_like_url(raw.get(column)):return column
  elif field in ("id","sku","name","price","stock","category","currency"):
   aliases=_FIELD_ALIASES[field]
   if any(_key(alias) in nk or nk in _key(alias) for alias in aliases):return column
 return explicit
def _get(raw,mapping,field):
 column=_resolve_column(mapping,raw,field);return raw.get(column) if column else None
def _as_float(value):
 if value is None or value=="":return None
 if isinstance(value,bool):return float(value)
 if isinstance(value,(int,float)):return float(value)
 text=str(value).strip();text=_CURRENCY_AND_GROUPING.sub("",text).replace(" ","")
 if not text:return None
 if "." in text and "," in text:text=text.replace(".","").replace(",",".") if text.rfind(",")>text.rfind(".") else text.replace(",","")
 elif text.count(",")==1 and len(text.rsplit(",",1)[1])!=3:text=text.replace(",",".")
 else:text=text.replace(",","")
 try:return float(text)
 except(ValueError,TypeError):return None
def _as_str(value):
 if value is None:return None
 text=str(value).strip();return text or None
def _as_currency(value):
 text=_as_str(value)
 if not text:return None
 text=text.upper();return text if text.isalpha() and 2<=len(text)<=10 else None
def _first_image_url(value):
 if value is None:return None
 if isinstance(value,(list,tuple)):
  for item in value:
   found=_first_image_url(item)
   if found:return found
  return None
 if isinstance(value,dict):
  for key in ("url","src","image_url","image","thumbnail","thumbnail_url","original","original_url"):
   if key in value:
    found=_first_image_url(value[key])
    if found:return found
  return None
 text=_as_str(value)
 if not text:return None
 if text[:1] in "[{":
  try:parsed=json.loads(text)
  except(TypeError,ValueError,json.JSONDecodeError):parsed=None
  if parsed is not None:return _first_image_url(parsed)
 return text
def _first_product_url(value):
 if value is None:return None
 if isinstance(value,(list,tuple)):
  for item in value:
   found=_first_product_url(item)
   if found:return found
  return None
 if isinstance(value,dict):
  for key in ("url","product_url","link","product_link","permalink","product_page","product_page_url","web_url","href"):
   if key in value:
    found=_first_product_url(value[key])
    if found:return found
  return None
 text=_as_str(value)
 if not text:return None
 if text[:1] in "[{":
  try:parsed=json.loads(text)
  except(TypeError,ValueError,json.JSONDecodeError):parsed=None
  if parsed is not None:return _first_product_url(parsed)
 return text
def _normalize_attribute_value(value):
 if value is None:return None
 if isinstance(value,str):return value.strip() or None
 if isinstance(value,(int,float,bool,list,dict)):return value
 return str(value).strip() or None
def _extract_attributes(raw,mapping):
 result={};attribute_mapping=mapping.get("attributes") or {}
 if isinstance(attribute_mapping,dict):
  for semantic_name,entry in attribute_mapping.items():
   key=str(semantic_name).strip().lower();column=entry.get("column") if isinstance(entry,dict) else entry
   if key and isinstance(column,str) and column.strip():
    value=_normalize_attribute_value(raw.get(column))
    if value is not None:result[key]=value
 return result
def discover_mapping(raw:dict,mapping:dict|None=None)->dict:
 mapping=mapping if isinstance(mapping,dict) else {}
 return {field:_resolve_column(mapping,raw,field) for field in _FIELD_ALIASES}
def validate_mapping(raw:dict,mapping:dict|None=None)->dict:
 effective=discover_mapping(raw,mapping);missing_required=[f for f in REQUIRED_FIELDS if not effective.get(f)]
 return {"ok":not missing_required,"mapping":effective,"missing_required":missing_required,"mapped_fields":[f for f,c in effective.items() if c]}
def normalize_row(raw:dict,mapping:dict)->dict|None:
 if not isinstance(raw,dict):return None
 raw_id=_get(raw,mapping,"id");raw_name=_get(raw,mapping,"name")
 if raw_id is None or raw_name is None:return None
 product_id,name=str(raw_id).strip(),str(raw_name).strip()
 if not product_id or not name:return None
 attrs=_extract_attributes(raw,mapping);sku=_as_str(_get(raw,mapping,"sku"))
 if sku:attrs.setdefault("sku",sku)
 return {"id":product_id,"sku":sku,"name":name,"description":_as_str(_get(raw,mapping,"description")),"price":_as_float(_get(raw,mapping,"price")),"stock":_as_float(_get(raw,mapping,"stock")),"category":_as_str(_get(raw,mapping,"category")),"brand":_as_str(_get(raw,mapping,"brand")),"image_url":_first_image_url(_get(raw,mapping,"image_url")),"product_url":_first_product_url(_get(raw,mapping,"product_url")),"currency":_as_currency(_get(raw,mapping,"currency")),"attributes":attrs}
