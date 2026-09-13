from pydantic import BaseModel


class CrawlJob(BaseModel):

    tenant_id: str
    url: str
    job_type: str = "website_crawl"
    max_pages: int = 100
    max_depth: int = 3
