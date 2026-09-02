PLAN_CRAWL_LIMITS = {
    "basic": {
        "max_pages": 100,
        "recrawl_hours": 24,
    },
    "standard": {
        "max_pages": 1000,
        "recrawl_hours": 6,
    },
    "premium": {
        "max_pages": 10000,
        "recrawl_hours": 1,
    },
}


def get_crawl_limits(plan: str):

    return PLAN_CRAWL_LIMITS.get(
        plan,
        PLAN_CRAWL_LIMITS["basic"],
    )
