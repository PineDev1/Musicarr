from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from app.api import albums, artists, auth, backup, events, musicbrainz_catalog, ops, player, settings
from app.core.database import SessionLocal, ensure_dirs, init_db
from app.services import app_auth, player_auth
from app.services.cors_origins import LOCAL_CORS_ORIGINS, origin_is_allowed
from app.services.download_queue import download_queue
from app.services.monitor import release_monitor
from app.services.settings_service import ensure_settings
from sqlalchemy import select

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
    yield
    download_queue.stop()
    release_monitor.stop()


app = FastAPI(title="Musicarr", version="0.1.0", lifespan=lifespan)

# Static local origins at boot; DynamicCorsMiddleware also allows configured public_domain.
app.add_middleware(
    CORSMiddleware,
    allow_origins=sorted(LOCAL_CORS_ORIGINS),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class DynamicCorsMiddleware(BaseHTTPMiddleware):
    """Allow credentialed CORS from Settings → public_domain in addition to localhost."""

    async def dispatch(self, request: Request, call_next):
        origin = request.headers.get("origin")
        if request.method == "OPTIONS" and origin:
            db = SessionLocal()
            try:
                allowed = origin_is_allowed(origin, db)
            finally:
                db.close()
            if allowed:
                headers = {
                    "Access-Control-Allow-Origin": origin,
                    "Access-Control-Allow-Credentials": "true",
                    "Access-Control-Allow-Methods": "GET, POST, PUT, PATCH, DELETE, OPTIONS",
                    "Access-Control-Allow-Headers": request.headers.get(
                        "access-control-request-headers", "*"
                    ),
                    "Vary": "Origin",
                }
                return Response(status_code=200, headers=headers)

        response = await call_next(request)
        if origin:
            db = SessionLocal()
            try:
                allowed = origin_is_allowed(origin, db)
            finally:
                db.close()
            if allowed and "access-control-allow-origin" not in {
                k.lower() for k in response.headers.keys()
            }:
                response.headers["Access-Control-Allow-Origin"] = origin
                response.headers["Access-Control-Allow-Credentials"] = "true"
                response.headers["Vary"] = "Origin"
        return response


app.add_middleware(DynamicCorsMiddleware)


@app.middleware("http")
async def app_login_gate(request: Request, call_next):
    path = request.url.path.rstrip("/") or "/"
    if path == "/api":
        return await call_next(request)
    if not path.startswith("/api"):
        return await call_next(request)
    if path in PUBLIC_API_PATHS:
        return await call_next(request)

    # Player listener APIs use the player cookie. Admin player routes (/users, /admin)
    # fall through to the app login gate — never open without an admin session.
    if path.startswith("/api/player"):
        is_admin_player = path.startswith("/api/player/users") or path.startswith(
            "/api/player/admin"
        )
        if not is_admin_player:
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
            # Auth off: most APIs are open, but player admin handlers still 401 via _require_admin.
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
app.include_router(events.router, prefix="/api")
app.include_router(player.router, prefix="/api")
app.include_router(musicbrainz_catalog.router, prefix="/api")
app.include_router(backup.router, prefix="/api")


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


_OG_BOT_HINTS = (
    "bot",
    "crawl",
    "slurp",
    "spider",
    "facebookexternalhit",
    "discordbot",
    "slackbot",
    "twitterbot",
    "linkedinbot",
    "telegrambot",
    "whatsapp",
    "preview",
    "embedly",
    "quora link preview",
    "applebot",
)


def _is_link_preview_agent(request: Request) -> bool:
    ua = (request.headers.get("user-agent") or "").lower()
    return any(h in ua for h in _OG_BOT_HINTS)


@app.get("/s/{token}")
def share_landing(token: str, request: Request):
    """Serve Open Graph HTML for crawlers; SPA shell for browsers."""
    if not _is_link_preview_agent(request):
        index_file = STATIC_DIR / "index.html"
        if index_file.exists():
            return FileResponse(index_file)
        # Dev without static build — let Vite SPA handle it via proxy miss
        raise HTTPException(status_code=404, detail="Build frontend for share pages")

    from html import escape

    from app.models import Album, PlayerShareLink, Track
    from app.services import player_auth
    from sqlalchemy.orm import joinedload

    db = SessionLocal()
    try:
        if not player_auth.player_enabled(db):
            raise HTTPException(status_code=404, detail="Player is disabled")
        link = db.scalar(
            select(PlayerShareLink)
            .options(
                joinedload(PlayerShareLink.track)
                .joinedload(Track.album)
                .joinedload(Album.artist)
            )
            .where(PlayerShareLink.token == token)
        )
        if not link or getattr(link, "revoked", False):
            raise HTTPException(status_code=404, detail="Share not found")
        track = link.track
        if not track:
            raise HTTPException(status_code=404, detail="Track not found")
        album = track.album
        artist = album.artist if album else None
        title = escape(track.title or "Track")
        artist_name = escape(artist.name if artist else "Unknown artist")
        album_title = escape(album.title if album else "")
        cover = (album.cover_url if album else None) or ""
        desc = f"{artist_name} — {album_title}".strip(" —")
        page_url = str(request.url)
        html = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <title>{title} · Musicarr</title>
  <meta property="og:type" content="music.song" />
  <meta property="og:title" content="{title}" />
  <meta property="og:description" content="{escape(desc)}" />
  <meta property="og:url" content="{escape(page_url)}" />
  {"<meta property='og:image' content='" + escape(cover) + "' />" if cover else ""}
  <meta name="twitter:card" content="summary_large_image" />
  <meta name="twitter:title" content="{title}" />
  <meta name="twitter:description" content="{escape(desc)}" />
  {"<meta name='twitter:image' content='" + escape(cover) + "' />" if cover else ""}
</head>
<body>
  <p>{title} by {artist_name}</p>
  <p><a href="{escape(page_url)}">Open in Musicarr</a></p>
</body>
</html>"""
        return HTMLResponse(html)
    finally:
        db.close()


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
