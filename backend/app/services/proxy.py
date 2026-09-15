from __future__ import annotations

from urllib.parse import urlparse

from fastapi import Request
from sqlalchemy.orm import Session

from app.services.settings_service import get_setting_cached


def normalize_public_domain(raw: str) -> str:
    """Accept host or full URL; return bare hostname (lowercase, no port path)."""
    text = (raw or "").strip()
    if not text:
        return ""
    if "://" not in text:
        text = f"https://{text}"
    parsed = urlparse(text)
    host = (parsed.hostname or "").strip().lower()
    return host[:512]


def ssl_enabled(db: Session) -> bool:
    return bool(get_setting_cached(db, "ssl_enabled", False))


def public_domain(db: Session) -> str:
    return (get_setting_cached(db, "public_domain", None) or "").strip()


def cookie_domain_for_settings(db: Session) -> str | None:
    """Only set Domain= for real public hosts (skip localhost / bare IPs)."""
    host = public_domain(db)
    if not host:
        return None
    if host in {"localhost", "127.0.0.1", "::1"}:
        return None
    # Skip raw IPv4
    if host.replace(".", "").isdigit():
        return None
    return host


def request_is_https(request: Request, db: Session | None = None) -> bool:
    """True when behind Traefik HTTPS or ssl_enabled is on."""
    proto = (request.headers.get("x-forwarded-proto") or "").split(",")[0].strip().lower()
    if proto == "https":
        return True
    if request.url.scheme == "https":
        return True
    if db is not None and ssl_enabled(db):
        return True
    return False


def forwarded_host(request: Request, db: Session | None = None) -> str | None:
    xf = (request.headers.get("x-forwarded-host") or "").split(",")[0].strip()
    if xf:
        return xf.split(":")[0].lower()
    if db is not None:
        domain = public_domain(db)
        if domain:
            return domain
    if request.url.hostname:
        return request.url.hostname.lower()
    return None


def traefik_labels_snippet(domain: str, *, cert_resolver: str = "letsencrypt") -> str:
    host = normalize_public_domain(domain) or "music.example.com"
    return "\n".join(
        [
            f"traefik.enable=true",
            f"traefik.http.routers.musicarr.rule=Host(`{host}`)",
            f"traefik.http.routers.musicarr.entrypoints=websecure",
            f"traefik.http.routers.musicarr.tls=true",
            f"traefik.http.routers.musicarr.tls.certresolver={cert_resolver}",
            f"traefik.http.services.musicarr.loadbalancer.server.port=8787",
        ]
    )
