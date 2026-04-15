"""User library functions: likes, play history, and profile for Spotify."""
from __future__ import annotations

from pydantic import BaseModel, Field

from imperal_sdk import ActionResult

from config import SP_API_BASE, DEFAULT_HISTORY_LIMIT, DEFAULT_LIKES_LIMIT, MAX_LIMIT
from utils import format_track, sp_error
from handlers.auth import get_auth_headers, get_auth_headers_refreshed


# ── Param models ──────────────────────────────────────────────────────────────

class GetRecentTracksParams(BaseModel):
    limit: int = Field(
        DEFAULT_HISTORY_LIMIT, ge=1, le=MAX_LIMIT,
        description="Number of recently played tracks to return (requires Spotify Premium)",
    )


class GetLikedTracksParams(BaseModel):
    limit: int = Field(
        DEFAULT_LIKES_LIMIT, ge=1, le=MAX_LIMIT,
        description="Number of saved/liked tracks to return",
    )


class LikeTrackParams(BaseModel):
    track_id: str = Field(..., description="Spotify track ID to save/like")


class UnlikeTrackParams(BaseModel):
    track_id: str = Field(..., description="Spotify track ID to unsave/unlike")


class GetUserProfileParams(BaseModel):
    """No parameters — returns the authenticated user's Spotify profile."""


# ── Functions ─────────────────────────────────────────────────────────────────

async def fn_get_recent_tracks(ctx, params: GetRecentTracksParams) -> ActionResult:
    """Get the user's recently played tracks.

    Note: Spotify requires Premium for the play history endpoint.
    A 403 response means the user needs to upgrade their Spotify account.
    """
    try:
        headers = await get_auth_headers(ctx)
    except ValueError as exc:
        return ActionResult.error(str(exc))

    resp = await ctx.http.get(
        f"{SP_API_BASE}/me/player/recently-played",
        headers=headers,
        params={"limit": params.limit},
    )

    if resp.status_code == 401:
        try:
            headers = await get_auth_headers_refreshed(ctx)
        except ValueError as exc:
            return ActionResult.error(str(exc))
        resp = await ctx.http.get(
            f"{SP_API_BASE}/me/player/recently-played",
            headers=headers,
            params={"limit": params.limit},
        )

    if resp.status_code == 403:
        return ActionResult.error(
            "Play history requires Spotify Premium. "
            "Upgrade your account to access this feature.",
            retryable=False,
        )

    if not resp.ok:
        return ActionResult.error(
            sp_error(resp.status_code),
            retryable=(resp.status_code == 429),
        )

    raw_list = resp.json().get("items") or []
    # Each item has a "track" key and a "played_at" timestamp
    tracks = [format_track(item["track"]) for item in raw_list if item.get("track")]

    return ActionResult.success(
        data={"tracks": tracks, "count": len(tracks)},
        summary=f"Retrieved {len(tracks)} recently played track(s)",
    )


async def fn_get_liked_tracks(ctx, params: GetLikedTracksParams) -> ActionResult:
    """Get all tracks the user has saved (liked) in their Spotify library."""
    try:
        headers = await get_auth_headers(ctx)
    except ValueError as exc:
        return ActionResult.error(str(exc))

    resp = await ctx.http.get(
        f"{SP_API_BASE}/me/tracks",
        headers=headers,
        params={"limit": params.limit},
    )

    if resp.status_code == 401:
        try:
            headers = await get_auth_headers_refreshed(ctx)
        except ValueError as exc:
            return ActionResult.error(str(exc))
        resp = await ctx.http.get(
            f"{SP_API_BASE}/me/tracks",
            headers=headers,
            params={"limit": params.limit},
        )

    if not resp.ok:
        return ActionResult.error(
            sp_error(resp.status_code),
            retryable=(resp.status_code == 429),
        )

    raw_list = resp.json().get("items") or []
    # Each item has a "track" key and an "added_at" timestamp
    tracks = [format_track(item["track"]) for item in raw_list if item.get("track")]

    return ActionResult.success(
        data={"tracks": tracks, "count": len(tracks)},
        summary=f"Retrieved {len(tracks)} saved track(s)",
    )


async def fn_like_track(ctx, params: LikeTrackParams) -> ActionResult:
    """Save a track to the user's Spotify library (like)."""
    try:
        headers = await get_auth_headers(ctx)
    except ValueError as exc:
        return ActionResult.error(str(exc))

    resp = await ctx.http.put(
        f"{SP_API_BASE}/me/tracks",
        headers=headers,
        params={"ids": params.track_id},
    )

    if not resp.ok:
        return ActionResult.error(sp_error(resp.status_code), retryable=False)

    return ActionResult.success(
        data={"track_id": params.track_id, "liked": True},
        summary=f"Track {params.track_id} saved to your library",
    )


async def fn_unlike_track(ctx, params: UnlikeTrackParams) -> ActionResult:
    """Remove a track from the user's Spotify library (unlike)."""
    try:
        headers = await get_auth_headers(ctx)
    except ValueError as exc:
        return ActionResult.error(str(exc))

    resp = await ctx.http.delete(
        f"{SP_API_BASE}/me/tracks",
        headers=headers,
        params={"ids": params.track_id},
    )

    if not resp.ok:
        return ActionResult.error(sp_error(resp.status_code), retryable=False)

    return ActionResult.success(
        data={"track_id": params.track_id, "liked": False},
        summary=f"Track {params.track_id} removed from your library",
    )


async def fn_get_user_profile(ctx, params: GetUserProfileParams) -> ActionResult:
    """Get the authenticated user's Spotify profile information."""
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
        return ActionResult.error(
            sp_error(resp.status_code),
            retryable=(resp.status_code == 429),
        )

    raw = resp.json()
    images = raw.get("images") or []
    profile = {
        "id": raw.get("id", ""),
        "username": raw.get("id", ""),
        "display_name": raw.get("display_name") or raw.get("id", ""),
        "email": raw.get("email", ""),
        "url": (raw.get("external_urls") or {}).get("spotify", ""),
        "avatar_url": images[0].get("url", "") if images else "",
        "followers_count": (raw.get("followers") or {}).get("total", 0),
        "product": raw.get("product", "free"),  # "free" or "premium"
    }

    return ActionResult.success(
        data={"profile": profile},
        summary=f"Profile: {profile['display_name']} ({profile['product']})",
    )
