from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware

from backend.app.api.routes import router
from backend.app.config import get_settings
from backend.app.container import build_container

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    settings.backend_runtime_path.mkdir(parents=True, exist_ok=True)
    container = build_container(settings)
    app.state.container = container

    try:
        container.retriever.load()
    except Exception as exc:
        # The API still starts so /api/health explains the missing/broken asset.
        logger.error("Backend started in unavailable mode: %s", exc)

    yield


settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description=(
        "FastAPI backend for the Persian University RAG system. "
        "Loads Notebook 02 retrieval artifacts and supports local runtime LLM settings."
    ),
    lifespan=lifespan,
)

app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=settings.allowed_hosts,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Accept"],
)


@app.middleware("http")
async def local_session_cookie(request: Request, call_next):
    manager = getattr(getattr(request.app.state, "container", None), "llm_settings", None)
    cookie_name = settings.session_cookie_name
    incoming = request.cookies.get(cookie_name)

    if manager is not None and manager.valid_session_id(incoming):
        session_id = incoming
        is_new = False
    elif manager is not None:
        session_id = manager.new_session_id()
        is_new = True
    else:
        # Lifespan has not completed yet; routes will not normally use this branch.
        session_id = incoming or "bootstrap-session"
        is_new = incoming is None

    request.state.session_id = session_id
    response = await call_next(request)

    if is_new and manager is not None:
        response.set_cookie(
            key=cookie_name,
            value=session_id,
            max_age=settings.session_cookie_max_age_seconds,
            httponly=True,
            secure=settings.session_cookie_secure,
            samesite=settings.session_cookie_samesite,
            path="/",
        )
    return response


app.include_router(router)


@app.get("/")
def root() -> dict[str, str]:
    return {
        "name": settings.app_name,
        "version": settings.app_version,
        "health": "/api/health",
        "docs": "/docs",
        "llm_settings": "/api/settings/llm",
    }
