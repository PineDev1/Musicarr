from __future__ import annotations

import asyncio
from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse
from sqlalchemy import select

from app.core.database import SessionLocal
from app.models import DownloadJob

router = APIRouter(tags=["events"])


def _queue_snapshot() -> list[dict]:
    db = SessionLocal()
    try:
        jobs = db.scalars(
            select(DownloadJob)
            .where(
                DownloadJob.state.in_(
                    [
                        "queued",
                        "running",
                        "searching",
                        "grabbed",
                        "downloading",
                        "importing",
                        "failed",
                    ]
                )
            )
            .order_by(DownloadJob.created_at.desc())
            .limit(100)
        ).all()
        return [
            {
                "id": j.id,
                "album_id": j.album_id,
                "artist_name": j.artist_name,
                "album_title": j.album_title,
                "state": j.state,
                "progress": j.progress,
                "error": j.error,
                "error_category": getattr(j, "error_category", "") or "",
                "retries": j.retries,
                "source": getattr(j, "source", None) or "streaming",
                "release_title": getattr(j, "release_title", None) or "",
                "client_id": getattr(j, "client_id", None),
                "client_item_id": getattr(j, "client_item_id", None) or "",
            }
            for j in jobs
        ]
    finally:
        db.close()


@router.get("/events/queue")
async def queue_sse(request: Request):
    async def event_stream():
        last = None
        while True:
            if await request.is_disconnected():
                break
            snap = _queue_snapshot()
            payload = str(snap)
            if payload != last:
                last = payload
                import json

                yield f"data: {json.dumps(snap)}\n\n"
            await asyncio.sleep(1.0)

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.websocket("/ws/queue")
async def queue_ws(websocket: WebSocket):
    await websocket.accept()
    try:
        last = None
        while True:
            import json

            snap = _queue_snapshot()
            payload = json.dumps(snap)
            if payload != last:
                last = payload
                await websocket.send_text(payload)
            await asyncio.sleep(1.0)
    except WebSocketDisconnect:
        return
