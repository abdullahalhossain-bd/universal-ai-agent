# ---------------------------------
# Monthly plan request quotas
# ---------------------------------
#
# Distinct from `app.core.rate_limit.PLAN_RATE_LIMITS`
# (a per-minute burst cap enforced in Redis). This is
# the plan-level "X requests / month" cap that billing
# actually sells — enforced against the same durable
# `usage_records` table (and inside the same row-locked
# transaction) as the per-request dollar budget in
# `UsageRepository.reserve_budget`, so a store can never
# burn past either limit due to a race between concurrent
# requests.
#
# `None` means unlimited (no monthly request cap).

PLAN_MONTHLY_REQUEST_QUOTAS: dict[str, int | None] = {
    "starter": 500,
    "growth": 5000,
    "pro": 50000,
}


def get_monthly_request_quota(
    plan: str | None,
) -> int | None:

    plan_name = (
        plan or "starter"
    ).lower().strip()

    return PLAN_MONTHLY_REQUEST_QUOTAS.get(
        plan_name,
        PLAN_MONTHLY_REQUEST_QUOTAS["starter"],
    )
