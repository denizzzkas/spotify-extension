"""Spotify search handlers."""
from __future__ import annotations

import logging

from pydantic import BaseModel, Field

from imperal_sdk import ActionResult

from app import (
    chat, SP_API_BASE, DEFAULT_SEARCH_LIMIT, MAX_LIMIT,
    _require_auth, _refresh_access_token, _spotify_error,
)
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
    description="Search Spotify catalogue for tracks by title or artist (requires Spotify login). Returns up to 50 matching tracks with id, title, artist, duration, preview_url, album_art.",
)
async def fn_search_tracks(ctx, params: SearchTracksParams) -> ActionResult:
    token = await _require_auth(ctx)
    if isinstance(token, ActionResult):
        return token

    try:
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        resp = await ctx.api.get(
            f"{SP_API_BASE}/search",
            headers=headers,
            params={"q": params.query, "type": "track", "limit": params.limit},
        )

        if resp.status_code == 401:
            token = await _refresh_access_token(ctx)
            if not token:
                return ActionResult.error("Spotify token expired. Please reconnect via connect_spotify().")
            headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
            resp = await ctx.api.get(
                f"{SP_API_BASE}/search",
                headers=headers,
                params={"q": params.query, "type": "track", "limit": params.limit},
            )

        if not resp.ok:
            return ActionResult.error(
                _spotify_error(resp.status_code),
                retryable=(resp.status_code == 429),
            )

        raw_list = (resp.json().get("tracks") or {}).get("items", [])
        tracks = [format_track(t) for t in raw_list]

        return ActionResult.success(
            data={"tracks": tracks, "count": len(tracks), "query": params.query},
            summary=f"Found {len(tracks)} track(s) for '{params.query}'",
        )
    except Exception as e:
        log.error("search_tracks failed: %s", e)
        return ActionResult.error(f"Search failed: {str(e)}", retryable=True)
