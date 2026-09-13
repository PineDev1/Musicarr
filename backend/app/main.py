from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api import albums, artists, auth, events, ops, settings
from app.core.database import SessionLocal, ensure_dirs, init_db
from app.services.download_queue import download_queue
from app.services.monitor import release_monitor
from app.services.settings_service import ensure_settings

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


@asynccontextmanager
async def lifespan(_: FastAPI):
    ensure_dirs()
    init_db()
    db = SessionLocal()
    try:
        ensure_settings(db)
    finally:
        db.close()
    download_queue.start()
    release_monitor.start()
    yield
    download_queue.stop()
    release_monitor.stop()


app = FastAPI(title="Musicarr", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(settings.router, prefix="/api")
app.include_router(auth.router, prefix="/api")
app.include_router(artists.router, prefix="/api")
app.include_router(albums.router, prefix="/api")
app.include_router(ops.router, prefix="/api")
app.include_router(events.router, prefix="/api")


@app.get("/api")
def api_root():
    return {"name": "Musicarr", "docs": "/docs"}


if (STATIC_DIR / "assets").exists():
    app.mount("/assets", StaticFiles(directory=STATIC_DIR / "assets"), name="assets")


@app.get("/")
def index():
    index_file = STATIC_DIR / "index.html"
    if index_file.exists():
        return FileResponse(index_file)
    return {
        "name": "Musicarr",
        "message": "API running. Build the frontend into backend/static for the UI.",
        "docs": "/docs",
    }


@app.get("/favicon.svg")
def favicon():
    fav = STATIC_DIR / "favicon.svg"
    if fav.exists():
        return FileResponse(fav)
    raise HTTPException(status_code=404)


@app.get("/{full_path:path}")
def spa_fallback(full_path: str):
    if full_path.startswith(("api/", "docs", "openapi.json", "redoc", "assets/")):
        raise HTTPException(status_code=404)
    index_file = STATIC_DIR / "index.html"
    if not index_file.exists():
        raise HTTPException(status_code=404)
    candidate = STATIC_DIR / full_path
    if candidate.is_file():
        return FileResponse(candidate)
    return FileResponse(index_file)
