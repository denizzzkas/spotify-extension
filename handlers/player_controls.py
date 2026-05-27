"""Player control handlers — previous, next, play/pause, shuffle, like."""
from __future__ import annotations

import asyncio
import logging

from pydantic import BaseModel
from imperal_sdk import ActionResult

from app import chat, NowPlayingModel
from return_models import PlayerActionRecord, ShuffleRecord, TrackLikeRecord
from spotify_config import SP_API_BASE
from app_helpers import _spotify_call, _spotify_err
from utils import format_track

log = logging.getLogger("spotify.player_controls")


class EmptyParams(BaseModel):
    pass


async def _update_now_playing_cache(ctx) -> None:
    """Fetch current Spotify player state and update now_playing cache."""
    await asyncio.sleep(0.5)
    np_resp, _ = await _spotify_call(ctx, "get", f"{SP_API_BASE}/me/player")
    if np_resp and np_resp.ok and np_resp.status_code != 204:
        state = np_resp.json()
        item = state.get("item")
        if item:
            track_data = format_track(item)
            await ctx.cache.set(
                key="now_playing",
                value=NowPlayingModel(
                    **track_data,
                    is_playing=state.get("is_playing", True),
                    shuffle=state.get("shuffle_state", False),
                ),
                ttl_seconds=90,
            )


@chat.function(
    "sp_prev", action_type="write",
    chain_callable=True,
    data_model=PlayerActionRecord,
    description="Skip to the previous track in the Spotify playback queue.",
    event="player.previous",
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
        await _update_now_playing_cache(ctx)
        return ActionResult.success(data={}, summary="Previous track", refresh_panels=["spotify"])
    except Exception as e:
        log.error("sp_prev failed: %s", e)
        return ActionResult.error(str(e) or "Failed to skip to previous track.")


@chat.function(
    "sp_next", action_type="write",
    chain_callable=True,
    data_model=PlayerActionRecord,
    description="Skip to the next track in the Spotify playback queue.",
    event="player.next",
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
        await _update_now_playing_cache(ctx)
        return ActionResult.success(data={}, summary="Next track", refresh_panels=["spotify"])
    except Exception as e:
        log.error("sp_next failed: %s", e)
        return ActionResult.error(str(e) or "Failed to skip to next track.")


@chat.function(
    "sp_play_pause", action_type="write",
    chain_callable=True,
    data_model=PlayerActionRecord,
    description="Toggle Spotify playback between playing and paused states.",
    event="player.play_pause",
    effects=["player:play_pause"],
)
async def fn_sp_play_pause(ctx, params: EmptyParams) -> ActionResult:
    """Toggle play or pause on the active Spotify device."""
    try:
        resp, err = await _spotify_call(ctx, "get", f"{SP_API_BASE}/me/player")
        if err:
            return err
        if not resp.ok:
            return _spotify_err(resp)

        is_playing = resp.json().get("is_playing", False)
        endpoint = "pause" if is_playing else "play"

        resp2, err = await _spotify_call(ctx, "put", f"{SP_API_BASE}/me/player/{endpoint}")
        if err:
            return err
        if not resp2.ok and resp2.status_code != 204:
            return _spotify_err(resp2)
        return ActionResult.success(data={}, summary="Paused" if is_playing else "Resumed")
    except Exception as e:
        log.error("sp_play_pause failed: %s", e)
        return ActionResult.error(str(e) or "Failed to toggle playback.")


@chat.function(
    "sp_shuffle", action_type="write",
    chain_callable=True,
    data_model=ShuffleRecord,
    description="Toggle Spotify shuffle mode on or off for the current playback session.",
    event="player.shuffle",
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

        try:
            now_playing = await ctx.cache.get(key="now_playing", model=NowPlayingModel)
            if now_playing:
                now_playing.shuffle = new_state
                await ctx.cache.set(key="now_playing", value=now_playing, ttl_seconds=90)
        except Exception:
            pass

        return ActionResult.success(
            data={"shuffle": new_state},
            summary=f"Shuffle {'on' if new_state else 'off'}",
            refresh_panels=["spotify"],
        )
    except Exception as e:
        log.error("sp_shuffle failed: %s", e)
        return ActionResult.error(str(e) or "Failed to toggle shuffle.")


@chat.function(
    "sp_like", action_type="write",
    chain_callable=True,
    data_model=TrackLikeRecord,
    description="Toggle like/unlike on the currently playing track — no track_id needed. Use this when the user wants to like or save what's playing right now. To like a specific track by ID, use like_track instead.",
    event="track.liked",
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

        resp2, err = await _spotify_call(
            ctx, "delete" if is_liked else "put",
            f"{SP_API_BASE}/me/tracks",
            json={"ids": [track_id]},
        )
        if err:
            return err
        if not resp2.ok and resp2.status_code not in (200, 204):
            return _spotify_err(resp2)

        new_liked = not is_liked
        try:
            if now_playing:
                now_playing.is_liked = new_liked
                await ctx.cache.set(key="now_playing", value=now_playing, ttl_seconds=90)
        except Exception:
            pass

        return ActionResult.success(
            data={"track_id": track_id, "liked": new_liked},
            summary="Unliked" if is_liked else "Liked",
            refresh_panels=["spotify"],
        )
    except Exception as e:
        log.error("sp_like failed: %s", e)
        return ActionResult.error(str(e) or "Failed to like/unlike track.")
