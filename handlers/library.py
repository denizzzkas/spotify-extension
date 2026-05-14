"""Spotify library handlers — likes, play history, profile."""
from __future__ import annotations

import logging

from pydantic import BaseModel, Field

from imperal_sdk import ActionResult

from app import chat
from spotify_config import SP_API_BASE, DEFAULT_HISTORY_LIMIT, DEFAULT_LIKES_LIMIT, MAX_LIMIT
from app_helpers import _require_auth, _refresh_access_token, _spotify_error
from utils import format_track

log = logging.getLogger("spotify.library")


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
    pass


# ─── Library handlers ─────────────────────────────────────────────────────── #

@chat.function(
    "get_recent_tracks",
    action_type="read",
    description="Get the user's recently played tracks (requires Spotify Premium). Returns list of tracks with full details.",
)
async def fn_get_recent_tracks(ctx, params: GetRecentTracksParams) -> ActionResult:
    """Get the user's recently played tracks (requires Spotify Premium). Returns list of tracks with full details."""
    token = await _require_auth(ctx)
    if isinstance(token, ActionResult):
        return token

    try:
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

        resp = await ctx.http.get(
            f"{SP_API_BASE}/me/player/recently-played",
            headers=headers,
            params={"limit": params.limit},
        )

        if resp.status_code == 401:
            token = await _refresh_access_token(ctx)
            if not token:
                return ActionResult.error("Spotify token expired. Please reconnect via connect_spotify().")
            headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
            resp = await ctx.http.get(
                f"{SP_API_BASE}/me/player/recently-played",
                headers=headers,
                params={"limit": params.limit},
            )

        if resp.status_code == 403:
            return ActionResult.error(
                "Play history requires Spotify Premium. Upgrade your account to access this feature.",
                retryable=False,
            )

        if not resp.ok:
            return ActionResult.error(_spotify_error(resp.status_code), retryable=(resp.status_code == 429))

        raw_list = resp.json().get("items") or []
        tracks = [format_track(item["track"]) for item in raw_list if item.get("track")]

        return ActionResult.success(
            data={"tracks": tracks, "count": len(tracks)},
            summary=f"Retrieved {len(tracks)} recently played track(s)",
        )
    except Exception as e:
        log.error("get_recent_tracks failed: %s", e)
        return ActionResult.error(f"Failed to get recent tracks: {str(e)}", retryable=True)


@chat.function(
    "get_liked_tracks",
    action_type="read",
    description="Get all tracks saved/liked in the user's Spotify library. Returns list of liked tracks with full details.",
)
async def fn_get_liked_tracks(ctx, params: GetLikedTracksParams) -> ActionResult:
    """Get all tracks saved/liked in the user's Spotify library. Returns list of liked tracks with full details."""
    token = await _require_auth(ctx)
    if isinstance(token, ActionResult):
        return token

    try:
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

        resp = await ctx.http.get(
            f"{SP_API_BASE}/me/tracks",
            headers=headers,
            params={"limit": params.limit},
        )

        if resp.status_code == 401:
            token = await _refresh_access_token(ctx)
            if not token:
                return ActionResult.error("Spotify token expired. Please reconnect via connect_spotify().")
            headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
            resp = await ctx.http.get(
                f"{SP_API_BASE}/me/tracks",
                headers=headers,
                params={"limit": params.limit},
            )

        if not resp.ok:
            return ActionResult.error(
                _spotify_error(resp.status_code),
                retryable=(resp.status_code == 429),
            )

        raw_list = resp.json().get("items") or []
        tracks = [format_track(item["track"]) for item in raw_list if item.get("track")]

        return ActionResult.success(
            data={"tracks": tracks, "count": len(tracks)},
            summary=f"Retrieved {len(tracks)} saved track(s)",
        )
    except Exception as e:
        log.error("get_liked_tracks failed: %s", e)
        return ActionResult.error(f"Failed to get liked tracks: {str(e)}", retryable=True)


@chat.function(
    "like_track",
    action_type="write",
    chain_callable=True,
    id_projection="track_id",
    effects=["library:like"],
    event="spotify-extension.track.liked",
    description="Save a track to the user's Spotify library (like it).",
)
async def fn_like_track(ctx, params: LikeTrackParams) -> ActionResult:
    """Save a track to the user's Spotify library (like it)."""
    token = await _require_auth(ctx)
    if isinstance(token, ActionResult):
        return token

    try:
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

        resp = await ctx.http.put(
            f"{SP_API_BASE}/me/tracks",
            headers=headers,
            params={"ids": params.track_id},
        )

        if resp.status_code == 401:
            token = await _refresh_access_token(ctx)
            if not token:
                return ActionResult.error("Spotify token expired. Please reconnect via connect_spotify().")
            headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
            resp = await ctx.http.put(
                f"{SP_API_BASE}/me/tracks",
                headers=headers,
                params={"ids": params.track_id},
            )

        if not resp.ok:
            try:
                detail = resp.json().get("error", {}).get("message", "")
            except Exception:
                detail = resp.text or ""
            msg = _spotify_error(resp.status_code)
            return ActionResult.error(f"{msg} Spotify says: {detail}" if detail else msg, retryable=False)

        return ActionResult.success(
            data={"track_id": params.track_id, "liked": True},
            summary=f"Track saved to your library",
            refresh_panels=["spotify"],
        )
    except Exception as e:
        log.error("like_track failed: %s", e)
        return ActionResult.error(f"Failed to like track: {str(e)}", retryable=False)


@chat.function(
    "unlike_track",
    action_type="write",
    chain_callable=True,
    id_projection="track_id",
    effects=["library:unlike"],
    event="spotify-extension.track.unliked",
    description="Remove a track from the user's Spotify library (unlike it).",
)
async def fn_unlike_track(ctx, params: UnlikeTrackParams) -> ActionResult:
    """Remove a track from the user's Spotify library (unlike it)."""
    token = await _require_auth(ctx)
    if isinstance(token, ActionResult):
        return token

    try:
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

        resp = await ctx.http.delete(
            f"{SP_API_BASE}/me/tracks",
            headers=headers,
            params={"ids": params.track_id},
        )

        if resp.status_code == 401:
            token = await _refresh_access_token(ctx)
            if not token:
                return ActionResult.error("Spotify token expired. Please reconnect via connect_spotify().")
            headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
            resp = await ctx.http.delete(
                f"{SP_API_BASE}/me/tracks",
                headers=headers,
                params={"ids": params.track_id},
            )

        if not resp.ok:
            try:
                detail = resp.json().get("error", {}).get("message", "")
            except Exception:
                detail = resp.text or ""
            msg = _spotify_error(resp.status_code)
            return ActionResult.error(f"{msg} Spotify says: {detail}" if detail else msg, retryable=False)

        return ActionResult.success(
            data={"track_id": params.track_id, "liked": False},
            summary=f"Track removed from your library",
            refresh_panels=["spotify"],
        )
    except Exception as e:
        log.error("unlike_track failed: %s", e)
        return ActionResult.error(f"Failed to unlike track: {str(e)}", retryable=False)


@chat.function(
    "get_user_profile",
    action_type="read",
    description="Get the authenticated user's Spotify profile information including username, followers, and subscription type.",
)
async def fn_get_user_profile(ctx, params: GetUserProfileParams) -> ActionResult:
    """Get the authenticated user's Spotify profile information including username, followers, and subscription type."""
    token = await _require_auth(ctx)
    if isinstance(token, ActionResult):
        return token

    try:
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

        resp = await ctx.http.get(f"{SP_API_BASE}/me", headers=headers)

        if resp.status_code == 401:
            token = await _refresh_access_token(ctx)
            if not token:
                return ActionResult.error("Spotify token expired. Please reconnect via connect_spotify().")
            headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
            resp = await ctx.http.get(f"{SP_API_BASE}/me", headers=headers)

        if not resp.ok:
            return ActionResult.error(
                _spotify_error(resp.status_code),
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
            "product": raw.get("product", "free"),
        }

        return ActionResult.success(
            data={"profile": profile},
            summary=f"Profile: {profile['display_name']} ({profile['product']})",
        )
    except Exception as e:
        log.error("get_user_profile failed: %s", e)
        return ActionResult.error(f"Failed to get profile: {str(e)}", retryable=True)
