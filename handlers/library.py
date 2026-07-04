"""Spotify library handlers — likes, play history, profile."""
from __future__ import annotations

import logging

from pydantic import BaseModel, Field

from imperal_sdk import ActionResult

from app import chat
from return_models import RecentTracksRecord, LikedTracksRecord, TrackLikeRecord, UserProfileRecord
from spotify_config import SP_API_BASE, DEFAULT_HISTORY_LIMIT, DEFAULT_LIKES_LIMIT, MAX_LIMIT
from app_helpers import _spotify_call, _spotify_err
from utils import format_track, to_spotify_uri

log = logging.getLogger("spotify.library")


class GetRecentTracksParams(BaseModel):
    limit: int = Field(DEFAULT_HISTORY_LIMIT, ge=1, le=MAX_LIMIT,
                       description="Number of recently played tracks to return (requires Spotify Premium)")

class GetLikedTracksParams(BaseModel):
    limit: int = Field(DEFAULT_LIKES_LIMIT, ge=1, le=MAX_LIMIT,
                       description="Number of saved/liked tracks to return")

class LikeTrackParams(BaseModel):
    track_id: str = Field(..., description="Spotify track ID to save/like")

class UnlikeTrackParams(BaseModel):
    track_id: str = Field(..., description="Spotify track ID to unsave/unlike")

class GetUserProfileParams(BaseModel):
    pass


@chat.function(
    "get_recent_tracks",
    action_type="read",
    data_model=RecentTracksRecord,
    description="Get the user's recently played tracks (requires Spotify Premium). Returns list of tracks with full details.",
)
async def fn_get_recent_tracks(ctx, params: GetRecentTracksParams) -> ActionResult:
    """Get the user's recently played tracks (requires Spotify Premium). Returns list of tracks with full details."""
    try:
        resp, err = await _spotify_call(ctx, "get", f"{SP_API_BASE}/me/player/recently-played",
                                        params={"limit": params.limit})
        if err:
            return err
        if resp.status_code == 403:
            return ActionResult.error("Play history requires Spotify Premium.", retryable=False)
        if not resp.ok:
            return _spotify_err(resp)
        tracks = [format_track(item["track"]) for item in (resp.json().get("items") or []) if item.get("track")]
        return ActionResult.success(data={"items": tracks, "total": len(tracks)},
                                    summary=f"Retrieved {len(tracks)} recently played track(s)")
    except Exception as e:
        log.error("get_recent_tracks failed: %s", e)
        return ActionResult.error(f"Failed to get recent tracks: {str(e)}", retryable=True)


@chat.function(
    "get_liked_tracks",
    action_type="read",
    data_model=LikedTracksRecord,
    description="Get all tracks saved/liked in the user's Spotify library. Returns list of liked tracks with full details.",
)
async def fn_get_liked_tracks(ctx, params: GetLikedTracksParams) -> ActionResult:
    """Get all tracks saved/liked in the user's Spotify library. Returns list of liked tracks with full details."""
    try:
        resp, err = await _spotify_call(ctx, "get", f"{SP_API_BASE}/me/tracks",
                                        params={"limit": params.limit})
        if err:
            return err
        if not resp.ok:
            return _spotify_err(resp)
        tracks = [format_track(item["track"]) for item in (resp.json().get("items") or []) if item.get("track")]
        return ActionResult.success(data={"items": tracks, "total": len(tracks)},
                                    summary=f"Retrieved {len(tracks)} saved track(s)")
    except Exception as e:
        log.error("get_liked_tracks failed: %s", e)
        return ActionResult.error(f"Failed to get liked tracks: {str(e)}", retryable=True)


@chat.function(
    "like_track",
    action_type="write",
    chain_callable=True,
    id_projection="track_id",
    effects=["library:like"],
    event="spotify.track.liked",
    data_model=TrackLikeRecord,
    description="Like a specific track by track_id. Use in chains after search_tracks. To like the currently playing track without knowing its ID, use sp_like instead.",
)
async def fn_like_track(ctx, params: LikeTrackParams) -> ActionResult:
    """Save a track to the user's Spotify library (like it)."""
    try:
        resp, err = await _spotify_call(ctx, "put", f"{SP_API_BASE}/me/library",
                                        params={"uris": to_spotify_uri(params.track_id)})
        if err:
            return err
        if not resp.ok:
            return _spotify_err(resp)
        return ActionResult.success(data={"track_id": params.track_id, "liked": True},
                                    summary="Track saved to your library",
                                    refresh_panels=["spotify"])
    except Exception as e:
        log.error("like_track failed: %s", e)
        return ActionResult.error(f"Failed to like track: {str(e)}", retryable=False)


@chat.function(
    "unlike_track",
    action_type="write",
    chain_callable=True,
    id_projection="track_id",
    effects=["library:unlike"],
    event="spotify.track.unliked",
    data_model=TrackLikeRecord,
    description="Unlike a specific track by track_id. Use in chains after search_tracks. To unlike the currently playing track, use sp_like instead.",
)
async def fn_unlike_track(ctx, params: UnlikeTrackParams) -> ActionResult:
    """Remove a track from the user's Spotify library (unlike it)."""
    try:
        resp, err = await _spotify_call(ctx, "delete", f"{SP_API_BASE}/me/library",
                                        params={"uris": to_spotify_uri(params.track_id)})
        if err:
            return err
        if not resp.ok:
            return _spotify_err(resp)
        return ActionResult.success(data={"track_id": params.track_id, "liked": False},
                                    summary="Track removed from your library",
                                    refresh_panels=["spotify"])
    except Exception as e:
        log.error("unlike_track failed: %s", e)
        return ActionResult.error(f"Failed to unlike track: {str(e)}", retryable=False)


@chat.function(
    "get_user_profile",
    action_type="read",
    data_model=UserProfileRecord,
    description="Get the authenticated user's Spotify profile information including username, followers, and subscription type.",
)
async def fn_get_user_profile(ctx, params: GetUserProfileParams) -> ActionResult:
    """Get the authenticated user's Spotify profile information including username, followers, and subscription type."""
    try:
        resp, err = await _spotify_call(ctx, "get", f"{SP_API_BASE}/me")
        if err:
            return err
        if not resp.ok:
            return _spotify_err(resp)
        raw = resp.json()
        images = raw.get("images") or []
        display_name = raw.get("display_name") or raw.get("id", "")
        profile = {
            "id": raw.get("id", ""),
            "title": display_name,
            "username": raw.get("id", ""),
            "email": raw.get("email", ""),
            "url": (raw.get("external_urls") or {}).get("spotify", ""),
            "avatar_url": images[0].get("url", "") if images else "",
            "followers_count": (raw.get("followers") or {}).get("total", 0),
            "product": raw.get("product", "free"),
        }
        return ActionResult.success(data=profile,
                                    summary=f"Profile: {display_name} ({profile['product']})")
    except Exception as e:
        log.error("get_user_profile failed: %s", e)
        return ActionResult.error(f"Failed to get profile: {str(e)}", retryable=True)
