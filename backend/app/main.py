"""FastAPI application and the Lambda entry point (``app.main.handler``)."""

from __future__ import annotations

import os

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from mangum import Mangum

from dueclaim.rates import BankRateUnavailableError

from .routes.invoices import router as invoices_router
from .routes.uploads import router as uploads_router

if os.environ.get("DEV_USER_SUB") and os.environ.get("ENVIRONMENT", "").lower() == "prod":
    # Fail at import (cold start) rather than at the first request.
    raise RuntimeError("DEV_USER_SUB is set while ENVIRONMENT=prod. Refusing to start.")

app = FastAPI(title="DueClaim API", version="0.1.0")
app.include_router(invoices_router)
app.include_router(uploads_router)


@app.exception_handler(BankRateUnavailableError)
def _bank_rate_unavailable(_: Request, exc: BankRateUnavailableError) -> JSONResponse:
    return JSONResponse(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, content={"detail": str(exc)})


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


handler = Mangum(app, lifespan="off")
