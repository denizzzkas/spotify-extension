"""Track search for the Spotify extension."""
from __future__ import annotations

from pydantic import BaseModel, Field

from imperal_sdk import ActionResult

from config import SP_API_BASE, DEFAULT_SEARCH_LIMIT, MAX_LIMIT
from utils import format_track, sp_error
from handlers.auth import get_auth_headers, get_auth_headers_refreshed


class SearchTracksParams(BaseModel):
    """Parameters for searching Spotify tracks."""
    query: str = Field(..., description="Track title or artist name to search for")
    limit: int = Field(DEFAULT_SEARCH_LIMIT, ge=1, le=MAX_LIMIT, description="Maximum results to return")


async def fn_search_tracks(ctx, params: SearchTracksParams) -> ActionResult:
    """Search Spotify for tracks matching the query."""
    try:
        headers = await get_auth_headers(ctx)
    except ValueError as exc:
        return ActionResult.error(str(exc))

    resp = await ctx.http.get(
        f"{SP_API_BASE}/search",
        headers=headers,
        params={"q": params.query, "type": "track", "limit": params.limit},
    )

    # Auto-refresh on 401
    if resp.status_code == 401:
        try:
            headers = await get_auth_headers_refreshed(ctx)
        except ValueError as exc:
            return ActionResult.error(str(exc))
        resp = await ctx.http.get(
            f"{SP_API_BASE}/search",
            headers=headers,
            params={"q": params.query, "type": "track", "limit": params.limit},
        )

    if not resp.ok:
        return ActionResult.error(
            sp_error(resp.status_code),
            retryable=(resp.status_code == 429),
        )

    body = resp.json()
    raw_list = (body.get("tracks") or {}).get("items", [])
    tracks = [format_track(t) for t in raw_list]

    return ActionResult.success(
        data={"tracks": tracks, "count": len(tracks), "query": params.query},
        summary=f"Found {len(tracks)} track(s) for '{params.query}'",
    )
