from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api import acquisition, albums, artists, auth, events, ops, player, settings
from app.core.database import SessionLocal, ensure_dirs, init_db
from app.services import app_auth, player_auth
from app.services.completed_download_handler import completed_download_handler
from app.services.download_queue import download_queue
from app.services.monitor import release_monitor
from app.services.settings_service import ensure_settings

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"

PUBLIC_API_PATHS = {
    "/api",
    "/api/auth/status",
    "/api/auth/login",
    "/api/auth/logout-session",
    "/api/player/status",
    "/api/player/login",
    "/api/player/logout",
}


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
    completed_download_handler.start()
    yield
    download_queue.stop()
    release_monitor.stop()
    completed_download_handler.stop()


app = FastAPI(title="Musicarr", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def app_login_gate(request: Request, call_next):
    path = request.url.path.rstrip("/") or "/"
    if path == "/api":
        return await call_next(request)
    if not path.startswith("/api"):
        return await call_next(request)
    if path in PUBLIC_API_PATHS:
        return await call_next(request)

    # Player APIs authenticate themselves (player cookie). Never treat player
    # cookie as admin access. When player is disabled, return 404 for listener
    # routes; admin user CRUD stays available for Settings → Player.
    if path.startswith("/api/player"):
        if path.startswith("/api/player/users") or path.startswith("/api/player/admin"):
            return await call_next(request)
        db = SessionLocal()
        try:
            if not player_auth.player_enabled(db):
                return JSONResponse(status_code=404, content={"detail": "Player is disabled"})
        finally:
            db.close()
        return await call_next(request)

    db = SessionLocal()
    try:
        if not app_auth.auth_enabled(db):
            return await call_next(request)
        token = request.cookies.get(app_auth.COOKIE_NAME)
        if app_auth.parse_session_token(db, token):
            return await call_next(request)
    finally:
        db.close()

    return JSONResponse(status_code=401, content={"detail": "Authentication required"})


@app.middleware("http")
async def proxy_headers(request: Request, call_next):
    db = SessionLocal()
    try:
        from app.services.proxy import forwarded_host, request_is_https

        request.state.https = request_is_https(request, db)
        request.state.forwarded_host = forwarded_host(request, db)
    finally:
        db.close()
    return await call_next(request)


app.include_router(settings.router, prefix="/api")
app.include_router(auth.router, prefix="/api")
app.include_router(artists.router, prefix="/api")
app.include_router(albums.router, prefix="/api")
app.include_router(ops.router, prefix="/api")
app.include_router(acquisition.router, prefix="/api")
app.include_router(events.router, prefix="/api")
app.include_router(player.router, prefix="/api")


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


@app.api_route("/{full_path:path}", methods=["GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
def spa_fallback(full_path: str, request: Request):
    # Never let the SPA catch-all claim /api/* (avoids confusing 405s when a
    # method is missing or the process is running stale code).
    if full_path.startswith(("api/", "docs", "openapi.json", "redoc", "assets/")):
        raise HTTPException(status_code=404)
    if request.method not in ("GET", "HEAD"):
        raise HTTPException(status_code=405)
    index_file = STATIC_DIR / "index.html"
    if not index_file.exists():
        raise HTTPException(status_code=404)
    candidate = STATIC_DIR / full_path
    if candidate.is_file():
        return FileResponse(candidate)
    return FileResponse(index_file)
