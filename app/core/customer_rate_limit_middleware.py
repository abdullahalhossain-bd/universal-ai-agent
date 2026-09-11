from fastapi import Request
from app.core.customer_rate_limit import enforce_customer_rate_limit


class CustomerRateLimitMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return
        request = Request(scope, receive=receive)
        try:
            await enforce_customer_rate_limit(request)
        except Exception as exc:
            if getattr(exc, "status_code", None) == 429:
                from fastapi.responses import JSONResponse
                response = JSONResponse(status_code=429, content={"detail": str(exc.detail)})
                await response(scope, receive, send)
                return
            raise
        await self.app(scope, receive, send)
