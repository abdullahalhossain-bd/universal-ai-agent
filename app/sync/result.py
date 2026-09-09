"""Sync result reporting and deterministic data-quality summaries."""
from __future__ import annotations
from dataclasses import dataclass,field
from app.sync.quality import VALID_CURRENCIES,valid_http_url,normalize_name
QUALITY_FIELDS=("name","price","image_url","product_url")
@dataclass
class SyncResult:
 store_id:str;created:int=0;updated:int=0;unchanged:int=0;stock_zeroed:int=0;skipped:int=0
 errors:list[str]=field(default_factory=list);mapping_validation:dict|None=None;data_quality:dict=field(default_factory=dict);duplicate_ids:list[str]=field(default_factory=list);duplicate_skus:list[str]=field(default_factory=list);duplicate_names:list[str]=field(default_factory=list);duplicate_candidates:list[dict]=field(default_factory=list);invalid_data:dict=field(default_factory=dict);invalid_counts:dict=field(default_factory=dict);reconciliation:dict=field(default_factory=dict);stale:dict=field(default_factory=dict);schema_drift:dict=field(default_factory=dict);repair_suggestions:list[dict]=field(default_factory=list);price_changes:list[dict]=field(default_factory=list);stock_changes:list[dict]=field(default_factory=list)
 _seen_names:dict=field(default_factory=dict,repr=False);_seen_skus:set=field(default_factory=set,repr=False);_seen_ids:set=field(default_factory=set,repr=False);_duplicate_id_count:int=0;_duplicate_sku_count:int=0;_duplicate_name_count:int=0
 def __post_init__(self):
  if not self.data_quality:self.data_quality={"products":0,"source_rows":0,"skipped_rows":0,"fields":{f:{"present":0,"missing":0} for f in QUALITY_FIELDS}}
 def _invalid(self,k,p):
  self.invalid_counts[k]=self.invalid_counts.get(k,0)+1;b=self.invalid_data.setdefault(k,[])
  if len(b)<100:b.append({"id":str(p.get("id")),"name":p.get("name")})
 def record_quality(self,p,*,source_row=True):
  if source_row:self.data_quality["source_rows"]+=1
  if p is None:self.data_quality["skipped_rows"]+=1;return
  self.data_quality["products"]+=1;pid=str(p.get("id") or "").strip()
  if pid and pid in self._seen_ids:self._duplicate_id_count+=1
  if pid:self._seen_ids.add(pid)
  for f in QUALITY_FIELDS:
   v=p.get(f);self.data_quality["fields"][f]["present" if v is not None and v!="" else "missing"]+=1
  name=normalize_name(p.get("name"));attrs=p.get("attributes") if isinstance(p.get("attributes"),dict) else {};sku=p.get("sku") or attrs.get("sku")
  if sku:
   k=str(sku).strip().casefold();duplicate=k in self._seen_skus
   if duplicate:
    self._duplicate_sku_count+=1
    if k not in self.duplicate_skus and len(self.duplicate_skus)<1000:self.duplicate_skus.append(k)
   else:
    if len(self._seen_skus)<200000:self._seen_skus.add(k)
  if name:
   prior=self._seen_names.get(name)
   if prior is not None:
    self._duplicate_name_count+=1
    if name not in self.duplicate_names and len(self.duplicate_names)<1000:self.duplicate_names.append(name)
    if len(self.duplicate_candidates)<1000:
     same_price=p.get("price") is not None and prior.get("price")==p.get("price");same_cat=bool(p.get("category")) and normalize_name(p.get("category"))==normalize_name(prior.get("category"));confidence=95 if same_price and same_cat else(80 if same_price or same_cat else 60);self.duplicate_candidates.append({"id_a":prior.get("id"),"id_b":pid,"name":p.get("name"),"confidence_pct":confidence,"signals":["same_name"]+(["same_price"] if same_price else [])+(["same_category"] if same_cat else [])})
   self._seen_names[name]={"id":pid,"price":p.get("price"),"category":p.get("category")}
  if not str(p.get("name") or "").strip():self._invalid("empty_name",p)
  try:
   if p.get("price") is not None and float(p["price"])<0:self._invalid("negative_price",p)
  except(TypeError,ValueError):self._invalid("invalid_price",p)
  try:
   if p.get("stock") is not None and float(p["stock"])<0:self._invalid("invalid_stock",p)
  except(TypeError,ValueError):self._invalid("invalid_stock",p)
  if p.get("currency") and str(p["currency"]).upper() not in VALID_CURRENCIES:self._invalid("invalid_currency",p)
  if p.get("product_url") and not valid_http_url(p["product_url"]):self._invalid("malformed_url",p)
  if p.get("image_url") and not valid_http_url(p["image_url"]):self._invalid("invalid_image_url",p)
 def record_duplicate(self,pid):
  v=str(pid);self._duplicate_id_count+=1
  if v not in self.duplicate_ids and len(self.duplicate_ids)<1000:self.duplicate_ids.append(v)
 def record_price_change(self,pid,name,old,new):
  if len(self.price_changes)<1000:self.price_changes.append({"id":str(pid),"name":name,"old":old,"new":new,"direction":"increased" if new>old else "decreased"})
 def record_stock_change(self,pid,name,old,new):
  if len(self.stock_changes)<1000:
   o=float(old or 0);n=float(new or 0);state="became_out_of_stock" if o>0 and n<=0 else("came_back_in_stock" if o<=0 and n>0 else "changed");self.stock_changes.append({"id":str(pid),"name":name,"old":old,"new":new,"state":state})
 def data_quality_report(self):
  fields={}
  for f,c in self.data_quality["fields"].items():
   t=c["present"]+c["missing"];fields[f]={"present":c["present"],"missing":c["missing"],"coverage_pct":round(c["present"]/t*100,2) if t else 100.0}
  d={"duplicate_id_count":self._duplicate_id_count,"duplicate_sku_count":self._duplicate_sku_count,"possible_duplicate_name_count":self._duplicate_name_count,"possible_duplicate_count":len(self.duplicate_candidates),"sample_ids":self.duplicate_ids[:20],"sample_skus":self.duplicate_skus[:20],"sample_names":self.duplicate_names[:20],"candidates":self.duplicate_candidates[:20]}
  return {"products":self.data_quality["products"],"source_rows":self.data_quality["source_rows"],"skipped_rows":self.data_quality["skipped_rows"],"fields":fields,"duplicates":d,"invalid_data":self.invalid_data,"invalid_counts":self.invalid_counts,"broken_media":self.data_quality.get("broken_media",0)}
 def calculate_health_score(self):
  r=self.data_quality_report();f=r["fields"];base=f["name"]["coverage_pct"]*.30+f["price"]["coverage_pct"]*.25+f["image_url"]["coverage_pct"]*.20+f["product_url"]["coverage_pct"]*.25;invalid=sum(self.invalid_counts.values());penalty=min(10,invalid*.20)+min(8,self._duplicate_id_count*.5+self._duplicate_sku_count*.4)+min(5,self.skipped*.25)+min(10,float(r.get("broken_media",0))*.25);rec=self.reconciliation or {};penalty+=min(10,float(rec.get("unexplained",0) or 0)*.5) if rec and not rec.get("reconciled",False) else 0;return max(0,min(100,round(base-penalty)))
 def set_reconciliation(self,*,source_count,db_count,rejected=0,duplicates=0,known_stale=0):
  expected=max(0,source_count-rejected-duplicates);delta=db_count-expected;unexplained=max(0,abs(delta)-known_stale);self.reconciliation={"source_count":source_count,"db_count":db_count,"expected_db_count":expected,"difference":source_count-db_count,"missing_in_db":max(0,-delta),"stale_in_db":max(0,delta),"known_stale":known_stale,"rejected":rejected,"duplicates":duplicates,"unexplained":unexplained,"reconciled":unexplained==0}
 @property
 def seen_ids(self):return set(self._seen_ids)
 @property
 def success(self):return not self.errors or(self.created+self.updated+self.unchanged>0)
 def to_dict(self):
  return {"store_id":self.store_id,"created":self.created,"updated":self.updated,"unchanged":self.unchanged,"stock_zeroed":self.stock_zeroed,"skipped":self.skipped,"errors":list(self.errors),"mapping_validation":self.mapping_validation,"data_quality":self.data_quality_report(),"health_score":self.calculate_health_score(),"reconciliation":self.reconciliation,"stale":self.stale,"schema_drift":self.schema_drift,"repair_suggestions":self.repair_suggestions,"price_changes":{"total":len(self.price_changes),"increased":sum(x["direction"]=="increased" for x in self.price_changes),"decreased":sum(x["direction"]=="decreased" for x in self.price_changes),"items":self.price_changes[:100]},"stock_changes":{"total":len(self.stock_changes),"became_out_of_stock":sum(x["state"]=="became_out_of_stock" for x in self.stock_changes),"came_back_in_stock":sum(x["state"]=="came_back_in_stock" for x in self.stock_changes),"items":self.stock_changes[:100]},"success":self.success}
