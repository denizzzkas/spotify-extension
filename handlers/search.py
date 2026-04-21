"""Track search and recommendations for the Spotify extension."""
from __future__ import annotations

from pydantic import BaseModel, Field

from imperal_sdk import ActionResult

from spotify_config import SP_API_BASE, DEFAULT_SEARCH_LIMIT, MAX_LIMIT
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


class GetRecommendationsParams(BaseModel):
    query: str = Field(..., description="Artist name, track title, or genre to base recommendations on")
    limit: int = Field(10, ge=1, le=50, description="Number of recommendations to return")


async def fn_get_recommendations(ctx, params: GetRecommendationsParams) -> ActionResult:
    """Get track recommendations based on an artist, track, or genre."""
    try:
        headers = await get_auth_headers(ctx)
    except ValueError as exc:
        return ActionResult.error(str(exc))

    # Search to resolve query → seed IDs
    search_resp = await ctx.http.get(
        f"{SP_API_BASE}/search",
        headers=headers,
        params={"q": params.query, "type": "track,artist", "limit": 1},
    )

    if search_resp.status_code == 401:
        try:
            headers = await get_auth_headers_refreshed(ctx)
        except ValueError as exc:
            return ActionResult.error(str(exc))
        search_resp = await ctx.http.get(
            f"{SP_API_BASE}/search",
            headers=headers,
            params={"q": params.query, "type": "track,artist", "limit": 1},
        )

    if not search_resp.ok:
        return ActionResult.error(sp_error(search_resp.status_code), retryable=(search_resp.status_code == 429))

    body = search_resp.json()
    seed_tracks = []
    seed_artists = []

    top_tracks = (body.get("tracks") or {}).get("items", [])
    top_artists = (body.get("artists") or {}).get("items", [])

    if top_tracks:
        seed_tracks = [top_tracks[0]["id"]]
        artist_ids = [a["id"] for a in (top_tracks[0].get("artists") or [])[:1]]
        seed_artists = artist_ids
    elif top_artists:
        seed_artists = [top_artists[0]["id"]]

    if not seed_tracks and not seed_artists:
        return ActionResult.error(f"Couldn't find '{params.query}' on Spotify to base recommendations on.", retryable=False)

    rec_params: dict = {"limit": params.limit}
    if seed_tracks:
        rec_params["seed_tracks"] = ",".join(seed_tracks)
    if seed_artists:
        rec_params["seed_artists"] = ",".join(seed_artists)

    rec_resp = await ctx.http.get(f"{SP_API_BASE}/recommendations", headers=headers, params=rec_params)

    if not rec_resp.ok:
        return ActionResult.error(sp_error(rec_resp.status_code), retryable=(rec_resp.status_code == 429))

    tracks = [format_track(t) for t in (rec_resp.json().get("tracks") or [])]

    return ActionResult.success(
        data={"tracks": tracks, "count": len(tracks), "based_on": params.query},
        summary=f"Here are {len(tracks)} tracks similar to '{params.query}'. Want me to create a playlist with these?",
    )
