"""Spotify search handlers."""
from __future__ import annotations

import logging

from pydantic import BaseModel, Field

from imperal_sdk import ActionResult

from app import chat
from return_models import SearchResultRecord
from spotify_config import SP_API_BASE, DEFAULT_SEARCH_LIMIT, MAX_LIMIT
from app_helpers import _spotify_call, _spotify_err
from utils import format_track

log = logging.getLogger("spotify.search")

# ─── Param models ─────────────────────────────────────────────────────────── #

class SearchTracksParams(BaseModel):
    query: str = Field("", description="Free-text search query — use when you only have a partial name or are unsure of the exact title/artist")
    track_name: str = Field("", description="Exact track title — use instead of query when you know the precise song name")
    artist_name: str = Field("", description="Exact artist name — combine with track_name or album_name for precise results")
    album_name: str = Field("", description="Exact album name — combine with artist_name to narrow results")
    limit: int = Field(DEFAULT_SEARCH_LIMIT, ge=1, le=MAX_LIMIT, description="Maximum results to return")

# ─── Search handler ───────────────────────────────────────────────────────── #

@chat.function(
    "search_tracks",
    action_type="read",
    data_model=SearchResultRecord,
    description="Search Spotify catalogue for tracks. Use track_name/artist_name/album_name for precise lookups (e.g. track_name='Rasputin' artist_name='Boney M'). Fall back to query for vague or partial searches. Returns a list of matching tracks with id, title, artist, duration, album_art. Use the track id from results to play or add to playlist.",
)
async def fn_search_tracks(ctx, params: SearchTracksParams) -> ActionResult:
    """Search Spotify catalogue for tracks. Builds a field-filtered query when specific fields are provided."""
    try:
        # Build a field-filtered query when specific fields are provided
        parts = []
        if params.track_name:
            parts.append(f"track:{params.track_name}")
        if params.artist_name:
            parts.append(f"artist:{params.artist_name}")
        if params.album_name:
            parts.append(f"album:{params.album_name}")
        q = " ".join(parts) if parts else params.query
        if not q:
            return ActionResult.error("Provide at least one of: query, track_name, artist_name, album_name.", retryable=False)

        resp, err = await _spotify_call(
            ctx, "get", f"{SP_API_BASE}/search",
            params={"q": q, "type": "track", "limit": params.limit},
        )
        if err:
            return err
        if not resp.ok:
            return _spotify_err(resp)

        raw_list = (resp.json().get("tracks") or {}).get("items", [])
        tracks = [format_track(t) for t in raw_list]

        return ActionResult.success(
            data={"tracks": tracks, "count": len(tracks), "query": q},
            summary=f"Found {len(tracks)} track(s) for '{q}'",
        )
    except Exception as e:
        log.error("search_tracks failed: %s", e)
        return ActionResult.error(f"Search failed: {str(e)}", retryable=True)
