from __future__ import annotations

from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import __version__
from . import jobs
from .config import Settings, get_settings
from .db import Base, init_engine
from .migrate import upgrade
from .routers import ai, aisettings, aitools, assets, cards, characters, collections, diagrams, encyclopedia, galgames, importer, library, lorebooks, notes, quicksearch, sd, sdtools, system
from .search import ensure_fts
from .routers import exports
from .routers import live2d
from .routers import chapterplans as chapterplans_router
from .routers import projectpreview as projectpreview_router

FRONTEND_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"
_hooks_installed = False


def create_app(settings: Settings | None = None) -> FastAPI:
    global _hooks_installed
    settings = settings or get_settings()
    for d in (settings.data_dir, settings.media_dir, settings.thumb_dir):
        d.mkdir(parents=True, exist_ok=True)
    job_manager = jobs.configure(settings.data_dir / "jobs.sqlite3")
    engine = init_engine(f"sqlite:///{settings.db_path}")
    Base.metadata.create_all(engine)
    upgrade(engine)
    ensure_fts(engine)
    if not _hooks_installed:
        assets.install_delete_hook()
        _hooks_installed = True

    @asynccontextmanager
    async def lifespan(app):
        yield
        job_manager.shutdown()

    app = FastAPI(
        lifespan=lifespan,
        title="Front API",
        version=__version__,
        description="Front · 自托管的创作素材库与百科数据库",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    for r in (
        system.router,
        exports.router,
        library.tag_extra, library.tags, library.works, library.worlds,
        encyclopedia.extra, encyclopedia.entries, encyclopedia.appearances,
        collections.extra, collections.crud,
        importer.router,
        chapterplans_router.router,
        projectpreview_router.router,
        live2d.router,
        assets.files, assets.router,
        characters.characters, characters.relations, characters.graph,
        sdtools.router, sdtools.snippets, sd.extra, sd.models, sd.prompts, sd.generations,
        cards.io_router, cards.router,
        aitools.router, aisettings.router, lorebooks.router, quicksearch.router, notes.extra, notes.crud, diagrams.extra, diagrams.crud, galgames.extra, galgames.crud,
        ai.router,
    ):
        app.include_router(r)

    if FRONTEND_DIST.is_dir():
        app.mount("/static", StaticFiles(directory=FRONTEND_DIST / "static"), name="static")

        @app.get("/{full_path:path}", include_in_schema=False)
        def spa(full_path: str) -> FileResponse:
            # Unknown API paths must not masquerade as successful HTML responses.
            if full_path == "api" or full_path.startswith("api/"):
                raise HTTPException(404, "API 不存在")
            if "\\" in full_path:
                raise HTTPException(404, "文件不存在")
            root = FRONTEND_DIST.resolve()
            candidate = (root / full_path).resolve()
            if not candidate.is_relative_to(root):
                raise HTTPException(404, "文件不存在")
            if full_path and candidate.is_file():
                return FileResponse(candidate)
            return FileResponse(root / "index.html")

    return app
