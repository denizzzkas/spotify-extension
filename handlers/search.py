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
    query: str = Field(..., description="Track title or artist name to search for")
    limit: int = Field(DEFAULT_SEARCH_LIMIT, ge=1, le=MAX_LIMIT, description="Maximum results to return")

# ─── Search handler ───────────────────────────────────────────────────────── #

@chat.function(
    "search_tracks",
    action_type="read",
    data_model=SearchResultRecord,
    description="Search Spotify catalogue for tracks by title or artist. Returns a list of matching tracks with id, title, artist, duration, album_art. Use the track id from results to play or add to playlist.",
)
async def fn_search_tracks(ctx, params: SearchTracksParams) -> ActionResult:
    """Search Spotify catalogue for tracks by title or artist. Returns list of tracks with id, title, artist, duration, album_art."""
    try:
        resp, err = await _spotify_call(
            ctx, "get", f"{SP_API_BASE}/search",
            params={"q": params.query, "type": "track", "limit": params.limit},
        )
        if err:
            return err
        if not resp.ok:
            return _spotify_err(resp)

        raw_list = (resp.json().get("tracks") or {}).get("items", [])
        tracks = [format_track(t) for t in raw_list]

        return ActionResult.success(
            data={"tracks": tracks, "count": len(tracks), "query": params.query},
            summary=f"Found {len(tracks)} track(s) for '{params.query}'",
        )
    except Exception as e:
        log.error("search_tracks failed: %s", e)
        return ActionResult.error(f"Search failed: {repr(e)}", retryable=True)
