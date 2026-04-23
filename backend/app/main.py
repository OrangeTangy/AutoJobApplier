from __future__ import annotations

import sys
import time
from contextlib import asynccontextmanager
from pathlib import Path

import structlog
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from prometheus_client import Counter, Histogram, make_asgi_app

from app.config import get_settings
from app.database import enable_sqlite_fks, engine
from app.routers import admin, applications, auth, company_rules, import_batch, ingestion, jobs, profile, resumes

settings = get_settings()
logger = structlog.get_logger(__name__)

# ── Prometheus metrics ────────────────────────────────────────────────────────
REQUEST_COUNT = Counter("http_requests_total", "Total HTTP requests", ["method", "path", "status"])
REQUEST_LATENCY = Histogram("http_request_duration_seconds", "HTTP request latency", ["method", "path"])


def _run_migrations_if_needed() -> None:
    """Apply Alembic migrations to the configured database."""
    try:
        from alembic import command
        from alembic.config import Config as AlembicConfig

        base_dir = _find_alembic_dir()
        if base_dir is None:
            logger.warning("alembic_dir_not_found — skipping migrations")
            return
        ini_path = base_dir / "alembic.ini"
        cfg = AlembicConfig(str(ini_path)) if ini_path.exists() else AlembicConfig()
        cfg.set_main_option("script_location", str(base_dir / "alembic"))
        cfg.set_main_option("sqlalchemy.url", settings.database_url)
        command.upgrade(cfg, "head")
        logger.info("migrations_applied")
    except Exception as exc:
        logger.error("migrations_failed", error=str(exc))


def _find_alembic_dir() -> Path | None:
    """Locate the backend directory (with alembic/) whether running from
    source, a PyInstaller bundle, or an installed wheel."""
    here = Path(__file__).resolve()
    for candidate in (here.parent.parent, here.parent.parent.parent):
        if (candidate / "alembic").is_dir():
            return candidate
    # PyInstaller one-file bundle
    bundle_dir = getattr(sys, "_MEIPASS", None)
    if bundle_dir and (Path(bundle_dir) / "alembic").is_dir():
        return Path(bundle_dir)
    return None


def _register_periodic_tasks() -> None:
    """Attach periodic ingestion + cleanup jobs to the in-process scheduler."""
    from app.workers.celery_app import celery as queue
    from app.workers.tasks import cleanup_stale_drafts, poll_all_sources

    queue.register_periodic(poll_all_sources, interval_seconds=3600)  # hourly
    queue.register_periodic(cleanup_stale_drafts, interval_seconds=24 * 3600)
    queue.start_scheduler()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("startup", environment=settings.environment)
    await enable_sqlite_fks()
    _run_migrations_if_needed()
    _register_periodic_tasks()
    yield
    from app.workers.celery_app import celery as queue
    queue.shutdown()
    await engine.dispose()
    logger.info("shutdown")


def _frontend_dir() -> Path | None:
    """Return the Next.js static-export directory if present."""
    import os as _os

    env_override = _os.environ.get("FRONTEND_DIST_DIR")
    if env_override and Path(env_override).is_dir():
        return Path(env_override)
    if settings.frontend_dist_dir:
        path = Path(settings.frontend_dist_dir)
        if path.is_dir():
            return path
    here = Path(__file__).resolve()
    candidates = [
        here.parent.parent / "frontend_dist",                # bundled next to app/
        here.parent.parent.parent / "frontend" / "out",      # running from source tree
    ]
    bundle_dir = getattr(sys, "_MEIPASS", None)
    if bundle_dir:
        candidates.insert(0, Path(bundle_dir) / "frontend_dist")
    for c in candidates:
        if c.is_dir():
            return c
    return None


def create_app() -> FastAPI:
    app = FastAPI(
        title="AutoJobApplier API",
        description="Self-hosted job application assistant",
        version="1.0.0",
        docs_url="/api/docs" if not settings.is_production else None,
        redoc_url="/api/redoc" if not settings.is_production else None,
        lifespan=lifespan,
    )

    # ── CORS ──────────────────────────────────────────────────────────────────
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Request logging + metrics middleware ──────────────────────────────────
    @app.middleware("http")
    async def logging_middleware(request: Request, call_next):
        start = time.perf_counter()
        response = await call_next(request)
        duration = time.perf_counter() - start
        path = request.url.path

        REQUEST_COUNT.labels(request.method, path, response.status_code).inc()
        REQUEST_LATENCY.labels(request.method, path).observe(duration)

        logger.info(
            "http_request",
            method=request.method,
            path=path,
            status=response.status_code,
            duration_ms=round(duration * 1000, 1),
        )
        return response

    # ── API routers ───────────────────────────────────────────────────────────
    prefix = "/api/v1"
    app.include_router(auth.router, prefix=prefix)
    app.include_router(profile.router, prefix=prefix)
    app.include_router(jobs.router, prefix=prefix)
    app.include_router(resumes.router, prefix=prefix)
    app.include_router(applications.router, prefix=prefix)
    app.include_router(ingestion.router, prefix=prefix)
    app.include_router(company_rules.router, prefix=prefix)
    app.include_router(import_batch.router, prefix=prefix)
    app.include_router(admin.router, prefix=prefix)

    # ── Health endpoint ───────────────────────────────────────────────────────
    @app.get("/api/health", tags=["meta"])
    async def health():
        from sqlalchemy import text

        from app.database import AsyncSessionLocal

        db_ok = False
        try:
            async with AsyncSessionLocal() as db:
                await db.execute(text("SELECT 1"))
            db_ok = True
        except Exception:
            pass

        return {
            "status": "ok" if db_ok else "degraded",
            "database": "ok" if db_ok else "error",
            "environment": settings.environment,
        }

    # ── Prometheus metrics endpoint ───────────────────────────────────────────
    metrics_app = make_asgi_app()
    app.mount("/metrics", metrics_app)

    # ── Global error handler ──────────────────────────────────────────────────
    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        logger.error("unhandled_exception", path=request.url.path, error=str(exc))
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": "Internal server error"},
        )

    # ── Serve Next.js static export at root (desktop-mode UI) ────────────────
    frontend = _frontend_dir()
    if frontend is not None:
        app.mount(
            "/_next",
            StaticFiles(directory=str(frontend / "_next"), check_dir=False),
            name="next_static",
        )

        @app.get("/{full_path:path}", include_in_schema=False)
        async def serve_spa(full_path: str):
            # Let API & metrics routes win (FastAPI matches them first); this
            # handler only fires for paths that didn't match a router.
            path = full_path.strip("/")

            # 1) Exact file hit (e.g. _next assets, favicon, image).
            target = frontend / path
            if path and target.is_file():
                return FileResponse(str(target))

            # 2) Pre-exported page: "foo/bar" → "foo/bar/index.html" (trailingSlash=true)
            page_html = frontend / path / "index.html"
            if path and page_html.is_file():
                return FileResponse(str(page_html))

            # 3) Dynamic [id] fallback: "applications/<uuid>" → "applications/_/index.html".
            # Client reads the real id from window.location via useParams().
            parts = path.split("/")
            if len(parts) >= 2:
                placeholder = frontend / parts[0] / "_" / "index.html"
                if placeholder.is_file():
                    return FileResponse(str(placeholder))

            # 4) Root SPA shell.
            index = frontend / "index.html"
            if index.is_file():
                return FileResponse(str(index))

            return JSONResponse(
                status_code=404, content={"detail": "Frontend not bundled"}
            )
    else:
        logger.warning("frontend_dist_not_found — API-only mode")

    return app


app = create_app()
