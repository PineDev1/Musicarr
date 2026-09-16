from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.core.database import get_db
from app.models import Album, Artist
from app.models.schemas import SearchResultsOut

router = APIRouter(prefix="/search", tags=["search"])


@router.get("", response_model=SearchResultsOut)
def search(q: str, db: Session = Depends(get_db)):
    term = (q or "").strip()
    if not term:
        return SearchResultsOut(artists=[], albums=[])

    pattern = f"%{term}%"
    artists = db.scalars(
        select(Artist).where(Artist.name.ilike(pattern)).order_by(Artist.name).limit(8)
    ).all()
    albums = db.scalars(
        select(Album)
        .options(joinedload(Album.artist))
        .where(Album.title.ilike(pattern))
        .order_by(Album.title)
        .limit(8)
    ).all()

    return SearchResultsOut(
        artists=[
            {"id": a.id, "name": a.name, "image_url": a.image_url} for a in artists
        ],
        albums=[
            {
                "id": a.id,
                "title": a.title,
                "artist_id": a.artist_id,
                "artist_name": a.artist.name if a.artist else "",
                "cover_url": a.cover_url,
            }
            for a in albums
        ],
    )
