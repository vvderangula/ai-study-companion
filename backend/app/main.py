"""Application entry point."""

from __future__ import annotations

import logging
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import admin, analytics, auth, health, learning, materials, quiz, tutor, workspace
from app.core.config import settings
from app.core.db import init_db
from app.core.errors import AppError
from app.core.logging import configure_logging, request_id_var

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging(settings.log_level)
    init_db()
    from app.services import workflows  # registers jobs + event handlers

    workflows.requeue_stale_materials()
    logger.info("%s started (%s); providers=%s; jobs=%s", settings.app_name, settings.environment, settings.ai_provider_order, settings.job_backend)
    yield


def create_app() -> FastAPI:
    app = FastAPI(title=settings.app_name, debug=settings.debug, lifespan=lifespan)
    app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        rid = request.headers.get("x-request-id") or uuid.uuid4().hex[:12]
        token = request_id_var.set(rid)
        started = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            logger.exception("unhandled error %s %s", request.method, request.url.path)
            response = JSONResponse({"detail": "Internal server error", "code": "internal_error", "request_id": rid}, status_code=500)
        finally:
            request_id_var.reset(token)
        latency = int((time.perf_counter() - started) * 1000)
        response.headers["x-request-id"] = rid
        if request.url.path != "/health":
            logger.info("%s %s -> %s", request.method, request.url.path, response.status_code, extra={"latency_ms": latency})
        return response

    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError):
        return JSONResponse({"detail": exc.message, "code": exc.code, "request_id": request_id_var.get()}, status_code=exc.status_code)

    @app.exception_handler(RequestValidationError)
    async def validation_handler(request: Request, exc: RequestValidationError):
        errors = [{"field": ".".join(str(p) for p in e.get("loc", [])[1:]), "message": e.get("msg")} for e in exc.errors()]
        return JSONResponse({"detail": errors[0]["message"] if errors else "Invalid request", "code": "validation_error", "errors": errors}, status_code=422)

    for module in (health, auth, workspace, materials, tutor, quiz, learning, analytics, admin):
        app.include_router(module.router)
    return app


app = create_app()
