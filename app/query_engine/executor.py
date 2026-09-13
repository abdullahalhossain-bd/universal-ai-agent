from __future__ import annotations

from sqlalchemy.orm import Session

from app.query_engine.registry import TOOLS


class PlanExecutor:

    async def run(
        self,
        tenant_id: str,
        plan,
        db: Session | None = None,
    ):

        results = {}

        for step in plan.steps:

            tool = TOOLS.get(step.tool)

            if not tool:

                results[step.tool] = {
                    "error": "unknown tool"
                }

                continue

            # DB-backed tools (StockTool, ProductSearchTool) need a
            # request-scoped session — the registry only holds
            # process-lifetime singletons, so bind it here, per call,
            # rather than baking a session into a shared instance.
            if db is not None and hasattr(tool, "bind_db"):
                tool.bind_db(db)

            try:

                output = await tool.execute(
                    tenant_id=tenant_id,
                    filters=step.filters,
                    query=step.query,
                )

                results[step.tool] = output

            except NotImplementedError as exc:

                results[step.tool] = {
                    "error": str(exc)
                }

        return results
