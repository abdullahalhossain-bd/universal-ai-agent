"""Sync result reporting and deterministic data-quality summaries."""
from __future__ import annotations
from dataclasses import dataclass, field
from app.sync.quality import VALID_CURRENCIES, valid_http_url, normalize_name
QUALITY_FIELDS = ("name", "price", "image_url", "product_url")
@dataclass
class SyncResult:
    store_id: str
    created: int = 0; updated: int = 0; unchanged: int = 0; stock_zeroed: int = 0; skipped: int = 0
    errors: list[str] = field(default_factory=list); mapping_validation: dict | None = None; data_quality: dict = field(default_factory=dict)
    duplicate_ids: list[str] = field(default_factory=list); duplicate_skus: list[str] = field(default_factory=list); duplicate_names: list[str] = field(default_factory=list)
    invalid_data: dict = field(default_factory=dict); reconciliation: dict = field(default_factory=dict); stale: dict = field(default_factory=dict)
    schema_drift: dict = field(default_factory=dict); repair_suggestions: list[dict] = field(default_factory=list)
    _seen_names: set[str] = field(default_factory=set, repr=False); _seen_skus: set[str] = field(default_factory=set, repr=False); _seen_ids: set[str] = field(default_factory=set, repr=False)
    def __post_init__(self):
        if not self.data_quality: self.data_quality={"products":0,"source_rows":0,"skipped_rows":0,"fields":{f:{"present":0,"missing":0} for f in QUALITY_FIELDS}}
    def _invalid(self, kind, product):
        bucket=self.invalid_data.setdefault(kind,[])
        if len(bucket)<100: bucket.append({"id":str(product.get("id")),"name":product.get("name")})
    def record_quality(self, product: dict | None, *, source_row=True):
        if source_row: self.data_quality["source_rows"]+=1
        if product is None: self.data_quality["skipped_rows"]+=1; return
        self.data_quality["products"]+=1
        pid=str(product.get("id") or "").strip()
        if pid and len(self._seen_ids)<200000: self._seen_ids.add(pid)
        for f in QUALITY_FIELDS:
            value=product.get(f); self.data_quality["fields"][f]["present" if value is not None and value!="" else "missing"]+=1
        name=normalize_name(product.get("name"))
        if name and name in self._seen_names and len(self.duplicate_names)<1000 and name not in self.duplicate_names: self.duplicate_names.append(name)
        if name: self._seen_names.add(name)
        attrs=product.get("attributes") if isinstance(product.get("attributes"),dict) else {}; sku=product.get("sku") or attrs.get("sku")
        if sku:
            key=str(sku).strip().casefold()
            if key in self._seen_skus and len(self.duplicate_skus)<1000 and key not in self.duplicate_skus: self.duplicate_skus.append(key)
            self._seen_skus.add(key)
        if not str(product.get("name") or "").strip(): self._invalid("empty_name",product)
        try:
            if product.get("price") is not None and float(product["price"])<0: self._invalid("negative_price",product)
        except (TypeError,ValueError): self._invalid("invalid_price",product)
        try:
            if product.get("stock") is not None and float(product["stock"])<0: self._invalid("invalid_stock",product)
        except (TypeError,ValueError): self._invalid("invalid_stock",product)
        currency=product.get("currency")
        if currency and str(currency).upper() not in VALID_CURRENCIES: self._invalid("invalid_currency",product)
        if product.get("product_url") and not valid_http_url(product["product_url"]): self._invalid("malformed_url",product)
        if product.get("image_url") and not valid_http_url(product["image_url"]): self._invalid("invalid_image_url",product)
    def record_duplicate(self, product_id):
        value=str(product_id)
        if value not in self.duplicate_ids and len(self.duplicate_ids)<1000: self.duplicate_ids.append(value)
    def data_quality_report(self):
        report={"products":self.data_quality["products"],"source_rows":self.data_quality["source_rows"],"skipped_rows":self.data_quality["skipped_rows"],"fields":{},"duplicates":{"duplicate_id_count":len(self.duplicate_ids),"duplicate_sku_count":len(self.duplicate_skus),"possible_duplicate_name_count":len(self.duplicate_names),"sample_ids":self.duplicate_ids[:20],"sample_skus":self.duplicate_skus[:20],"sample_names":self.duplicate_names[:20]},"invalid_data":self.invalid_data}
        for f,c in self.data_quality["fields"].items():
            total=c["present"]+c["missing"]; report["fields"][f]={"present":c["present"],"missing":c["missing"],"coverage_pct":round(c["present"]/total*100,2) if total else 100.0}
        return report
    def calculate_health_score(self):
        f=self.data_quality_report()["fields"]; score=f["name"]["coverage_pct"]*.30+f["price"]["coverage_pct"]*.25+f["image_url"]["coverage_pct"]*.20+f["product_url"]["coverage_pct"]*.25
        penalty=min(len(self.duplicate_ids)+len(self.duplicate_skus),20)*.5+min(sum(len(v) for v in self.invalid_data.values() if isinstance(v,list)),40)*.25+min(self.data_quality["skipped_rows"],20)*.25
        return max(0,min(100,round(score-penalty)))
    def set_reconciliation(self, *, source_count, db_count, rejected=0, duplicates=0):
        difference=source_count-db_count; self.reconciliation={"source_count":source_count,"db_count":db_count,"difference":difference,"reconciled":difference==0,"reasons":{"rejected":rejected,"duplicates":duplicates,"unexplained":max(0,abs(difference)-rejected-duplicates)}}
    @property
    def seen_ids(self): return set(self._seen_ids)
    @property
    def success(self): return not self.errors or (self.created+self.updated+self.unchanged>0)
    def to_dict(self): return {"store_id":self.store_id,"created":self.created,"updated":self.updated,"unchanged":self.unchanged,"stock_zeroed":self.stock_zeroed,"skipped":self.skipped,"errors":list(self.errors),"mapping_validation":self.mapping_validation,"data_quality":self.data_quality_report(),"health_score":self.calculate_health_score(),"reconciliation":self.reconciliation,"stale":self.stale,"schema_drift":self.schema_drift,"repair_suggestions":self.repair_suggestions,"success":self.success}
