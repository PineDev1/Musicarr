from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.core.database import get_db
from app.models import Album, DownloadClient, DownloadJob, Indexer, RemotePathMapping
from app.models.schemas import (
    AcquisitionStatusOut,
    DownloadClientCreate,
    DownloadClientOut,
    DownloadClientTestDraft,
    DownloadClientUpdate,
    IndexerCreate,
    IndexerOut,
    IndexerUpdate,
    ReleaseCandidateOut,
    ReleaseGrabRequest,
    RemotePathMappingCreate,
    RemotePathMappingOut,
    RemotePathMappingUpdate,
    TestResultOut,
)
from app.services.download_clients import (
    DownloadClientError,
    base_url,
    client_from_params,
    get_client,
    pick_client,
)
from app.services.history import add_history
from app.services.indexers.newznab import test_indexer
from app.services.indexers.search import parse_categories

router = APIRouter(prefix="/acquisition", tags=["acquisition"])


def _indexer_out(row: Indexer) -> IndexerOut:
    return IndexerOut(
        id=row.id,
        name=row.name or "",
        protocol=row.protocol or "usenet",
        implementation=row.implementation or "newznab",
        base_url=row.base_url or "",
        api_key_set=bool((row.api_key or "").strip()),
        categories=parse_categories(row.categories),
        enabled=bool(row.enabled),
        priority=int(row.priority or 25),
    )


def _client_out(row: DownloadClient) -> DownloadClientOut:
    host = row.host or ""
    port = int(row.port or 0)
    use_ssl = bool(row.use_ssl)
    try:
        constructed = base_url(host, port, use_ssl)
    except Exception:  # noqa: BLE001
        constructed = f"{'https' if use_ssl else 'http'}://{host}:{port}"
    return DownloadClientOut(
        id=row.id,
        name=row.name or "",
        protocol=row.protocol or "torrent",
        implementation=row.implementation or "qbittorrent",
        host=host,
        port=port,
        use_ssl=use_ssl,
        verify_ssl=bool(getattr(row, "verify_ssl", True)),
        username=row.username or "",
        password_set=bool((row.password or "").strip()),
        api_key_set=bool((row.api_key or "").strip()),
        category=row.category or "",
        enabled=bool(row.enabled),
        priority=int(row.priority or 1),
        base_url=constructed,
    )


def _mapping_out(row: RemotePathMapping) -> RemotePathMappingOut:
    return RemotePathMappingOut(
        id=row.id,
        host=row.host or "",
        remote_path=row.remote_path or "",
        local_path=row.local_path or "",
    )


def _path_mapping_note(db: Session) -> str:
    mappings = list(db.scalars(select(RemotePathMapping)).all())
    if not mappings:
        return (
            " Connected, but no remote path mappings are configured — "
            "completed downloads may not import until you map the client path "
            "to a folder Musicarr can see."
        )
    unread: list[str] = []
    for m in mappings:
        local = Path((m.local_path or "").strip())
        if local and not local.exists():
            unread.append(str(local))
    if unread:
        return (
            " Connected, but some mapped local paths are not visible here: "
            + ", ".join(unread[:3])
        )
    return ""


# -- status ----------------------------------------------------------------
@router.get("/status", response_model=AcquisitionStatusOut)
def acquisition_status(db: Session = Depends(get_db)):
    indexers = list(
        db.scalars(select(Indexer).where(Indexer.enabled.is_(True))).all()
    )
    clients = list(
        db.scalars(select(DownloadClient).where(DownloadClient.enabled.is_(True))).all()
    )
    mappings = list(db.scalars(select(RemotePathMapping)).all())
    torrent = any((c.protocol or "").lower() == "torrent" for c in clients)
    usenet = any((c.protocol or "").lower() == "usenet" for c in clients)
    messages: list[str] = []
    if not indexers:
        messages.append("No enabled indexers — add one under Settings → Indexers.")
    if not torrent and not usenet:
        messages.append("No enabled download clients — add qBittorrent or SABnzbd.")
    elif not torrent:
        messages.append("No torrent download client — torrent releases cannot be grabbed.")
    elif not usenet:
        messages.append("No Usenet download client — NZB releases cannot be grabbed.")
    if clients and not mappings:
        messages.append(
            "No remote path mappings — mount the same download volume and map "
            "client path → Musicarr path."
        )
    return AcquisitionStatusOut(
        indexers_enabled=len(indexers),
        torrent_client=torrent,
        usenet_client=usenet,
        path_mappings=len(mappings),
        messages=messages,
    )


# -- indexers --------------------------------------------------------------
@router.get("/indexers", response_model=list[IndexerOut])
def list_indexers(db: Session = Depends(get_db)):
    rows = db.scalars(
        select(Indexer).order_by(Indexer.priority.asc(), Indexer.id.asc())
    ).all()
    return [_indexer_out(r) for r in rows]


@router.post("/indexers", response_model=IndexerOut, status_code=201)
def create_indexer(payload: IndexerCreate, db: Session = Depends(get_db)):
    row = Indexer(
        name=payload.name.strip(),
        protocol=payload.protocol,
        implementation=payload.implementation,
        base_url=payload.base_url.strip().rstrip("/"),
        api_key=(payload.api_key or "").strip(),
        categories=json.dumps(payload.categories or []),
        enabled=payload.enabled,
        priority=payload.priority,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _indexer_out(row)


@router.get("/indexers/{indexer_id}", response_model=IndexerOut)
def get_indexer(indexer_id: int, db: Session = Depends(get_db)):
    row = db.get(Indexer, indexer_id)
    if not row:
        raise HTTPException(status_code=404, detail="Indexer not found")
    return _indexer_out(row)


@router.put("/indexers/{indexer_id}", response_model=IndexerOut)
def update_indexer(
    indexer_id: int,
    payload: IndexerUpdate,
    db: Session = Depends(get_db),
):
    row = db.get(Indexer, indexer_id)
    if not row:
        raise HTTPException(status_code=404, detail="Indexer not found")
    data = payload.model_dump(exclude_unset=True)
    if "categories" in data:
        row.categories = json.dumps(data.pop("categories") or [])
    if "api_key" in data:
        api_key = (data.pop("api_key") or "").strip()
        if api_key:
            row.api_key = api_key
    if "base_url" in data and data["base_url"]:
        row.base_url = data.pop("base_url").strip().rstrip("/")
    for key, value in data.items():
        setattr(row, key, value)
    db.commit()
    db.refresh(row)
    return _indexer_out(row)


@router.delete("/indexers/{indexer_id}")
def delete_indexer(indexer_id: int, db: Session = Depends(get_db)):
    row = db.get(Indexer, indexer_id)
    if not row:
        raise HTTPException(status_code=404, detail="Indexer not found")
    db.delete(row)
    db.commit()
    return {"ok": True}


@router.post("/indexers/{indexer_id}/test", response_model=TestResultOut)
def test_indexer_connection(indexer_id: int, db: Session = Depends(get_db)):
    row = db.get(Indexer, indexer_id)
    if not row:
        raise HTTPException(status_code=404, detail="Indexer not found")
    ok, message = test_indexer(row.base_url, row.api_key, row.protocol or "usenet")
    return TestResultOut(ok=ok, message=message)


# -- download clients ------------------------------------------------------
@router.get("/download-clients", response_model=list[DownloadClientOut])
def list_download_clients(db: Session = Depends(get_db)):
    rows = db.scalars(
        select(DownloadClient).order_by(DownloadClient.priority.asc(), DownloadClient.id.asc())
    ).all()
    return [_client_out(r) for r in rows]


@router.post("/download-clients", response_model=DownloadClientOut, status_code=201)
def create_download_client(payload: DownloadClientCreate, db: Session = Depends(get_db)):
    row = DownloadClient(
        name=payload.name.strip(),
        protocol=payload.protocol,
        implementation=payload.implementation,
        host=(payload.host or "localhost").strip(),
        port=payload.port,
        use_ssl=payload.use_ssl,
        verify_ssl=payload.verify_ssl,
        username=(payload.username or "").strip(),
        password=payload.password or "",
        api_key=(payload.api_key or "").strip(),
        category=(payload.category or "").strip(),
        enabled=payload.enabled,
        priority=payload.priority,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _client_out(row)


@router.get("/download-clients/{client_id}", response_model=DownloadClientOut)
def get_download_client(client_id: int, db: Session = Depends(get_db)):
    row = db.get(DownloadClient, client_id)
    if not row:
        raise HTTPException(status_code=404, detail="Download client not found")
    return _client_out(row)


@router.put("/download-clients/{client_id}", response_model=DownloadClientOut)
def update_download_client(
    client_id: int,
    payload: DownloadClientUpdate,
    db: Session = Depends(get_db),
):
    row = db.get(DownloadClient, client_id)
    if not row:
        raise HTTPException(status_code=404, detail="Download client not found")
    data = payload.model_dump(exclude_unset=True)
    for secret in ("password", "api_key"):
        if secret in data:
            value = (data.pop(secret) or "").strip()
            if value:
                setattr(row, secret, value)
    for key, value in data.items():
        setattr(row, key, value)
    db.commit()
    db.refresh(row)
    return _client_out(row)


@router.delete("/download-clients/{client_id}")
def delete_download_client(client_id: int, db: Session = Depends(get_db)):
    row = db.get(DownloadClient, client_id)
    if not row:
        raise HTTPException(status_code=404, detail="Download client not found")
    db.delete(row)
    db.commit()
    return {"ok": True}


@router.post("/download-clients/{client_id}/test", response_model=TestResultOut)
def test_download_client(client_id: int, db: Session = Depends(get_db)):
    row = db.get(DownloadClient, client_id)
    if not row:
        raise HTTPException(status_code=404, detail="Download client not found")
    try:
        ok, message = get_client(row).test()
    except DownloadClientError as exc:
        return TestResultOut(ok=False, message=str(exc))
    if ok:
        message = message + _path_mapping_note(db)
    return TestResultOut(ok=ok, message=message)


@router.post("/download-clients/test-draft", response_model=TestResultOut)
def test_download_client_draft(payload: DownloadClientTestDraft, db: Session = Depends(get_db)):
    """Test host/creds from the form without requiring a save."""
    password = payload.password or ""
    api_key = (payload.api_key or "").strip()
    username = (payload.username or "").strip()
    if payload.client_id:
        existing = db.get(DownloadClient, payload.client_id)
        if existing:
            if not password:
                password = existing.password or ""
            if not api_key:
                api_key = existing.api_key or ""
            if not username and existing.username:
                username = existing.username or ""
    try:
        client = client_from_params(
            implementation=payload.implementation,
            host=payload.host,
            port=payload.port,
            use_ssl=payload.use_ssl,
            verify_ssl=payload.verify_ssl,
            username=username,
            password=password,
            api_key=api_key,
        )
        ok, message = client.test()
    except DownloadClientError as exc:
        return TestResultOut(ok=False, message=str(exc))
    if ok:
        message = message + _path_mapping_note(db)
    return TestResultOut(ok=ok, message=message)


# -- remote path mappings --------------------------------------------------
@router.get("/path-mappings", response_model=list[RemotePathMappingOut])
def list_path_mappings(db: Session = Depends(get_db)):
    rows = db.scalars(select(RemotePathMapping).order_by(RemotePathMapping.id.asc())).all()
    return [_mapping_out(r) for r in rows]


@router.post("/path-mappings", response_model=RemotePathMappingOut, status_code=201)
def create_path_mapping(payload: RemotePathMappingCreate, db: Session = Depends(get_db)):
    row = RemotePathMapping(
        host=(payload.host or "").strip(),
        remote_path=payload.remote_path.strip(),
        local_path=payload.local_path.strip(),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _mapping_out(row)


@router.put("/path-mappings/{mapping_id}", response_model=RemotePathMappingOut)
def update_path_mapping(
    mapping_id: int,
    payload: RemotePathMappingUpdate,
    db: Session = Depends(get_db),
):
    row = db.get(RemotePathMapping, mapping_id)
    if not row:
        raise HTTPException(status_code=404, detail="Path mapping not found")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(row, key, (value or "").strip() if isinstance(value, str) else value)
    db.commit()
    db.refresh(row)
    return _mapping_out(row)


@router.delete("/path-mappings/{mapping_id}")
def delete_path_mapping(mapping_id: int, db: Session = Depends(get_db)):
    row = db.get(RemotePathMapping, mapping_id)
    if not row:
        raise HTTPException(status_code=404, detail="Path mapping not found")
    db.delete(row)
    db.commit()
    return {"ok": True}


# -- manual release search / grab -----------------------------------------
@router.get("/releases/search", response_model=list[ReleaseCandidateOut])
def search_releases(
    album_id: int = Query(...),
    db: Session = Depends(get_db),
):
    from app.services.indexers.search import search_album

    album = db.scalar(
        select(Album).options(joinedload(Album.artist)).where(Album.id == album_id)
    )
    if not album:
        raise HTTPException(status_code=404, detail="Album not found")
    artist_name = album.artist.name if album.artist else ""
    candidates = search_album(db, artist_name, album.title, year=album.release_date)
    return [
        ReleaseCandidateOut(
            title=c.title,
            size=c.size,
            seeders=c.seeders,
            protocol=c.protocol,
            download_url=c.download_url,
            magnet_url=c.magnet_url,
            grab_url=c.grab_url,
            indexer_id=c.indexer_id,
            indexer_name=c.indexer_name,
            score=c.score,
        )
        for c in candidates
    ]


@router.post("/releases/grab")
def grab_release(payload: ReleaseGrabRequest, db: Session = Depends(get_db)):
    """Send a user-selected release to the matching download client."""
    album = db.scalar(
        select(Album).options(joinedload(Album.artist), joinedload(Album.tracks)).where(
            Album.id == payload.album_id
        )
    )
    if not album:
        raise HTTPException(status_code=404, detail="Album not found")

    grab_url = (payload.grab_url or "").strip()
    if not grab_url:
        raise HTTPException(status_code=400, detail="grab_url is required")

    protocol = (payload.protocol or "torrent").lower()
    client_row = pick_client(db, protocol)
    if not client_row:
        label = "qBittorrent" if protocol == "torrent" else "SABnzbd"
        raise HTTPException(
            status_code=400,
            detail=f"No enabled {protocol} download client. Add {label} under Settings → Download clients.",
        )

    # Preflight: confirm the client still answers.
    try:
        ok, message = get_client(client_row).test()
    except DownloadClientError as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Download client '{client_row.name}' failed: {exc}",
        ) from exc
    if not ok:
        raise HTTPException(
            status_code=400,
            detail=f"Download client '{client_row.name}' failed: {message}",
        )

    artist = album.artist
    artist_name = artist.name if artist else ""

    # Avoid duplicate active indexer jobs for the same album.
    active = db.scalar(
        select(DownloadJob).where(
            DownloadJob.album_id == album.id,
            DownloadJob.source == "indexer",
            DownloadJob.state.in_(["grabbed", "downloading", "importing"]),
        )
    )
    if active:
        raise HTTPException(
            status_code=409,
            detail="An indexer download is already in progress for this album",
        )

    client = get_client(client_row)
    try:
        item_id = client.add_url(grab_url, client_row.category or "")
    except DownloadClientError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        closer = getattr(client, "close", None)
        if callable(closer):
            closer()

    try:
        from app.services.artists import sync_album_tracks

        if not album.tracks:
            sync_album_tracks(db, album)
    except Exception:  # noqa: BLE001
        pass

    job = DownloadJob(
        target_type="album",
        target_id=album.id,
        album_id=album.id,
        artist_name=artist_name,
        album_title=album.title,
        state="grabbed",
        source="indexer",
        indexer_id=payload.indexer_id,
        client_id=client_row.id,
        release_title=(payload.title or "").strip()[:1024],
        download_url=grab_url,
        client_item_id=item_id,
        progress=1.0,
        started_at=datetime.now(timezone.utc),
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    add_history(
        db,
        "grabbed",
        f"Grabbed '{job.release_title or 'release'}' for {artist_name} – {album.title} "
        f"(sent to {client_row.name})",
    )
    from app.services.download_queue import download_queue

    download_queue.wake()

    return {
        "ok": True,
        "job_id": job.id,
        "client": client_row.name,
        "client_item_id": item_id,
    }


@router.post("/completed/scan")
def scan_completed_downloads():
    """Poll download clients now instead of waiting for the next interval."""
    from app.services.completed_download_handler import completed_download_handler

    return completed_download_handler.run_once()
