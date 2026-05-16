"""Player control handlers — previous, next, play/pause, shuffle, like."""
from __future__ import annotations

import logging

from pydantic import BaseModel
from imperal_sdk import ActionResult

from app import chat, NowPlayingModel
from spotify_config import SP_API_BASE
from app_helpers import _spotify_call, _spotify_err

log = logging.getLogger("spotify.player_controls")


class EmptyParams(BaseModel):
    pass


@chat.function(
    "sp_prev", action_type="write",
    description="Skip to the previous track in the Spotify playback queue.",
    event="spotify-extension.player.previous",
    effects=["player:previous"],
)
async def fn_sp_prev(ctx, params: EmptyParams) -> ActionResult:
    """Skip to the previous track."""
    try:
        resp, err = await _spotify_call(ctx, "post", f"{SP_API_BASE}/me/player/previous")
        if err:
            return err
        if not resp.ok and resp.status_code != 204:
            return _spotify_err(resp)
        return ActionResult.success(data={}, summary="Previous track")
    except Exception as e:
        log.error("sp_prev failed: %s", e)
        return ActionResult.error(str(e))


@chat.function(
    "sp_next", action_type="write",
    description="Skip to the next track in the Spotify playback queue.",
    event="spotify-extension.player.next",
    effects=["player:next"],
)
async def fn_sp_next(ctx, params: EmptyParams) -> ActionResult:
    """Skip to the next track."""
    try:
        resp, err = await _spotify_call(ctx, "post", f"{SP_API_BASE}/me/player/next")
        if err:
            return err
        if not resp.ok and resp.status_code != 204:
            return _spotify_err(resp)
        return ActionResult.success(data={}, summary="Next track")
    except Exception as e:
        log.error("sp_next failed: %s", e)
        return ActionResult.error(str(e))


@chat.function(
    "sp_play_pause", action_type="write",
    description="Toggle Spotify playback between playing and paused states.",
    event="spotify-extension.player.play_pause",
    effects=["player:play_pause"],
)
async def fn_sp_play_pause(ctx, params: EmptyParams) -> ActionResult:
    """Toggle play or pause on the active Spotify device."""
    try:
        try:
            now_playing = await ctx.cache.get(key="now_playing", model=NowPlayingModel)
        except Exception:
            now_playing = None

        is_playing = now_playing.is_playing if now_playing else False
        endpoint = "pause" if is_playing else "play"

        resp, err = await _spotify_call(ctx, "put", f"{SP_API_BASE}/me/player/{endpoint}")
        if err:
            return err
        if not resp.ok and resp.status_code != 204:
            return _spotify_err(resp)
        return ActionResult.success(data={}, summary="Paused" if is_playing else "Resumed")
    except Exception as e:
        log.error("sp_play_pause failed: %s", e)
        return ActionResult.error(str(e))


@chat.function(
    "sp_shuffle", action_type="write",
    description="Toggle Spotify shuffle mode on or off for the current playback session.",
    event="spotify-extension.player.shuffle",
    effects=["player:shuffle"],
)
async def fn_sp_shuffle(ctx, params: EmptyParams) -> ActionResult:
    """Toggle shuffle mode on the active Spotify device."""
    try:
        resp, err = await _spotify_call(ctx, "get", f"{SP_API_BASE}/me/player")
        if err:
            return err
        if not resp.ok:
            return _spotify_err(resp)

        current = resp.json().get("shuffle_state", False)
        new_state = not current

        resp2, err = await _spotify_call(
            ctx, "put", f"{SP_API_BASE}/me/player/shuffle",
            params={"state": str(new_state).lower()},
        )
        if err:
            return err
        if not resp2.ok and resp2.status_code != 204:
            return _spotify_err(resp2)
        return ActionResult.success(data={"shuffle": new_state}, summary=f"Shuffle {'on' if new_state else 'off'}")
    except Exception as e:
        log.error("sp_shuffle failed: %s", e)
        return ActionResult.error(str(e))


@chat.function(
    "sp_like", action_type="write",
    description="Like or unlike the currently playing track in the user's Spotify library.",
    event="spotify-extension.track.liked",
    effects=["track:like"],
)
async def fn_sp_like(ctx, params: EmptyParams) -> ActionResult:
    """Like or unlike the currently playing track."""
    try:
        try:
            now_playing = await ctx.cache.get(key="now_playing", model=NowPlayingModel)
        except Exception:
            now_playing = None

        if not now_playing or not now_playing.id:
            return ActionResult.error("No track currently playing.")

        track_id = now_playing.id

        resp, err = await _spotify_call(
            ctx, "get", f"{SP_API_BASE}/me/tracks/contains",
            params={"ids": track_id},
        )
        if err:
            return err

        is_liked = resp.ok and bool(resp.json()) and resp.json()[0]
        method = "delete" if is_liked else "put"

        resp2, err = await _spotify_call(
            ctx, "delete" if is_liked else "put",
            f"{SP_API_BASE}/me/tracks",
            params={"ids": track_id},
        )
        if err:
            return err
        if not resp2.ok and resp2.status_code not in (200, 204):
            return _spotify_err(resp2)
        return ActionResult.success(data={"liked": not is_liked}, summary="Unliked" if is_liked else "Liked")
    except Exception as e:
        log.error("sp_like failed: %s", e)
        return ActionResult.error(str(e))
