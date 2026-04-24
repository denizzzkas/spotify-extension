"""Panel-specific handlers — write to skeleton, refresh panels."""
from __future__ import annotations

from pydantic import BaseModel, Field

from imperal_sdk import ActionResult

from spotify_config import SP_API_BASE, DEFAULT_SEARCH_LIMIT, MAX_LIMIT
from utils import format_track, sp_error
from handlers.auth import get_auth_headers, get_auth_headers_refreshed
from cache_models import SearchModel, DetailModel

SKELETON_DETAIL = "spotify_detail"  # kept for backwards compat with tests
SKELETON_SEARCH = "spotify_search"  # kept for backwards compat with tests


# ── Param models ──────────────────────────────────────────────────────────────

class PanelSearchParams(BaseModel):
    query: str = Field(..., description="Track title or artist to search for")
    limit: int = Field(DEFAULT_SEARCH_LIMIT, ge=1, le=MAX_LIMIT)


class OpenPlaylistParams(BaseModel):
    playlist_id: str = Field(..., description="Spotify playlist ID")
    playlist_name: str = Field("", description="Playlist display name")


class OpenLikedTracksParams(BaseModel):
    """No parameters."""


class OpenRecentTracksParams(BaseModel):
    """No parameters."""


class OpenProfileParams(BaseModel):
    """No parameters."""


# ── Functions ─────────────────────────────────────────────────────────────────

async def fn_panel_search(ctx, params: PanelSearchParams) -> ActionResult:
    """Search tracks and push results into the left panel below the search bar."""
    try:
        headers = await get_auth_headers(ctx)
    except ValueError as exc:
        return ActionResult.error(str(exc))

    resp = await ctx.http.get(
        f"{SP_API_BASE}/search",
        headers=headers,
        params={"q": params.query, "type": "track", "limit": params.limit},
    )

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
        return ActionResult.error(sp_error(resp.status_code), retryable=(resp.status_code == 429))

    raw_list = (resp.json().get("tracks") or {}).get("items", [])
    tracks = [format_track(t) for t in raw_list]

    await ctx.cache.set(
        key="search",
        value=SearchModel(query=params.query, tracks=tracks),
        ttl_seconds=60,
    )

    return ActionResult.success(
        data={"count": len(tracks), "query": params.query},
        summary=f"Found {len(tracks)} track(s) for '{params.query}'",
        refresh_panels=["spotify"],
    )


async def fn_open_playlist(ctx, params: OpenPlaylistParams) -> ActionResult:
    """Load playlist tracks into the right detail panel."""
    try:
        headers = await get_auth_headers(ctx)
    except ValueError as exc:
        return ActionResult.error(str(exc))

    resp = await ctx.http.get(
        f"{SP_API_BASE}/playlists/{params.playlist_id}/tracks",
        headers=headers,
    )

    if resp.status_code == 401:
        try:
            headers = await get_auth_headers_refreshed(ctx)
        except ValueError as exc:
            return ActionResult.error(str(exc))
        resp = await ctx.http.get(
            f"{SP_API_BASE}/playlists/{params.playlist_id}/tracks",
            headers=headers,
        )

    if not resp.ok:
        return ActionResult.error(sp_error(resp.status_code), retryable=(resp.status_code == 429))

    raw_list = resp.json().get("items") or []
    tracks = [format_track(item["track"]) for item in raw_list if item.get("track")]

    name = params.playlist_name or params.playlist_id
    await ctx.cache.set(
        key="detail",
        value=DetailModel(type="tracks", title=name, tracks=tracks),
        ttl_seconds=120,
    )

    return ActionResult.success(
        data={"count": len(tracks)},
        summary=f"Opened '{name}' ({len(tracks)} tracks)",
        refresh_panels=["spotify_detail"],
    )


async def fn_open_liked_tracks(ctx, params: OpenLikedTracksParams) -> ActionResult:
    """Load liked tracks into the right detail panel."""
    try:
        headers = await get_auth_headers(ctx)
    except ValueError as exc:
        return ActionResult.error(str(exc))

    resp = await ctx.http.get(
        f"{SP_API_BASE}/me/tracks",
        headers=headers,
        params={"limit": 50},
    )

    if resp.status_code == 401:
        try:
            headers = await get_auth_headers_refreshed(ctx)
        except ValueError as exc:
            return ActionResult.error(str(exc))
        resp = await ctx.http.get(f"{SP_API_BASE}/me/tracks", headers=headers, params={"limit": 50})

    if not resp.ok:
        return ActionResult.error(sp_error(resp.status_code), retryable=(resp.status_code == 429))

    raw_list = resp.json().get("items") or []
    tracks = [format_track(item["track"]) for item in raw_list if item.get("track")]

    await ctx.cache.set(
        key="detail",
        value=DetailModel(type="tracks", title="Liked Tracks", tracks=tracks),
        ttl_seconds=120,
    )

    return ActionResult.success(
        data={"count": len(tracks)},
        summary=f"Opened Liked Tracks ({len(tracks)} tracks)",
        refresh_panels=["spotify_detail"],
    )


async def fn_open_recent_tracks(ctx, params: OpenRecentTracksParams) -> ActionResult:
    """Load recently played tracks into the right detail panel."""
    try:
        headers = await get_auth_headers(ctx)
    except ValueError as exc:
        return ActionResult.error(str(exc))

    resp = await ctx.http.get(
        f"{SP_API_BASE}/me/player/recently-played",
        headers=headers,
        params={"limit": 50},
    )

    if resp.status_code == 401:
        try:
            headers = await get_auth_headers_refreshed(ctx)
        except ValueError as exc:
            return ActionResult.error(str(exc))
        resp = await ctx.http.get(
            f"{SP_API_BASE}/me/player/recently-played",
            headers=headers,
            params={"limit": 50},
        )

    if resp.status_code == 403:
        return ActionResult.error("Recent tracks require Spotify Premium.", retryable=False)

    if not resp.ok:
        return ActionResult.error(sp_error(resp.status_code), retryable=(resp.status_code == 429))

    raw_list = resp.json().get("items") or []
    tracks = [format_track(item["track"]) for item in raw_list if item.get("track")]

    await ctx.cache.set(
        key="detail",
        value=DetailModel(type="tracks", title="Recent Tracks", tracks=tracks),
        ttl_seconds=120,
    )

    return ActionResult.success(
        data={"count": len(tracks)},
        summary=f"Opened Recent Tracks ({len(tracks)} tracks)",
        refresh_panels=["spotify_detail"],
    )


async def fn_open_profile(ctx, params: OpenProfileParams) -> ActionResult:
    """Load user profile into the right detail panel."""
    try:
        headers = await get_auth_headers(ctx)
    except ValueError as exc:
        return ActionResult.error(str(exc))

    resp = await ctx.http.get(f"{SP_API_BASE}/me", headers=headers)

    if resp.status_code == 401:
        try:
            headers = await get_auth_headers_refreshed(ctx)
        except ValueError as exc:
            return ActionResult.error(str(exc))
        resp = await ctx.http.get(f"{SP_API_BASE}/me", headers=headers)

    if not resp.ok:
        return ActionResult.error(sp_error(resp.status_code), retryable=(resp.status_code == 429))

    raw = resp.json()
    images = raw.get("images") or []
    profile = {
        "display_name": raw.get("display_name") or raw.get("id", ""),
        "email": raw.get("email", ""),
        "avatar_url": images[0].get("url", "") if images else "",
        "followers": (raw.get("followers") or {}).get("total", 0),
        "product": raw.get("product", "free"),
        "url": (raw.get("external_urls") or {}).get("spotify", ""),
    }

    await ctx.cache.set(
        key="detail",
        value=DetailModel(type="profile", title=profile["display_name"], profile=profile),
        ttl_seconds=120,
    )

    return ActionResult.success(
        data={"profile": profile},
        summary=f"Opened profile: {profile['display_name']}",
        refresh_panels=["spotify_detail"],
    )
