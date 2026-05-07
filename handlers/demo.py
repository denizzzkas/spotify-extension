"""Demo mode handlers — no Spotify auth required, uses ctx.store for state."""
from __future__ import annotations

import logging
import random

from pydantic import BaseModel, Field

from imperal_sdk import ActionResult

from app import chat, DEMO_PLAYER_STATE
from cache_models import DetailModel
from demo_data import DEMO_TRACKS, DEMO_PLAYLIST_ID, DEMO_PLAYLIST_NAME

log = logging.getLogger("spotify.demo")


async def _get_demo_state(ctx) -> dict:
    try:
        page = await ctx.store.query(DEMO_PLAYER_STATE, where={"user_id": ctx.user.imperal_id})
        return page.data[0].data if page.data else {}
    except Exception as e:
        log.error("_get_demo_state failed: %s", e)
        return {}


async def _save_demo_state(ctx, state: dict) -> None:
    try:
        record = {"user_id": ctx.user.imperal_id, **state}
        page = await ctx.store.query(DEMO_PLAYER_STATE, where={"user_id": ctx.user.imperal_id})
        if page.data:
            await ctx.store.update(DEMO_PLAYER_STATE, page.data[0].id, record)
        else:
            await ctx.store.create(DEMO_PLAYER_STATE, record)
    except Exception as e:
        log.error("_save_demo_state failed: %s", e)


async def _set_demo_track(ctx, index: int) -> None:
    index = index % len(DEMO_TRACKS)
    state = await _get_demo_state(ctx)
    await _save_demo_state(ctx, {**state, "track_index": index, "is_playing": True, "active": True})


class OpenDemoPlaylistParams(BaseModel):
    pass

class DemoPlayTrackParams(BaseModel):
    track_id: str = Field(..., description="Demo track ID to play")

class DemoNextTrackParams(BaseModel):
    pass

class DemoPrevTrackParams(BaseModel):
    pass

class DemoPauseParams(BaseModel):
    pass

class DemoShuffleParams(BaseModel):
    pass


@chat.function(
    "open_demo_playlist",
    action_type="write",
    effects=["demo:active"],
    description="Open demo playlist (no Spotify login required). Returns demo tracks for testing.",
)
async def fn_open_demo_playlist(ctx, params: OpenDemoPlaylistParams) -> ActionResult:
    try:
        await _set_demo_track(ctx, 0)
        await ctx.cache.set(
            key="detail",
            value=DetailModel(type="tracks", title=DEMO_PLAYLIST_NAME, tracks=DEMO_TRACKS),
            ttl_seconds=120,
        )
        return ActionResult.success(
            data={"count": len(DEMO_TRACKS), "tracks": DEMO_TRACKS},
            summary=f"Opened demo playlist ({len(DEMO_TRACKS)} tracks)",
            refresh_panels=["spotify"],
        )
    except Exception as e:
        log.error("open_demo_playlist failed: %s", e)
        return ActionResult.error(f"Failed to open demo: {str(e)}", retryable=True)


@chat.function(
    "demo_play_track",
    action_type="write",
    effects=["demo:play"],
    description="Play a specific track from demo playlist.",
)
async def fn_demo_play_track(ctx, params: DemoPlayTrackParams) -> ActionResult:
    try:
        index = next((i for i, t in enumerate(DEMO_TRACKS) if t["id"] == params.track_id), None)
        if index is None:
            return ActionResult.error("Track not found in demo playlist.")
        await _set_demo_track(ctx, index)
        return ActionResult.success(data={}, summary="Playing track", refresh_panels=["spotify"])
    except Exception as e:
        log.error("demo_play_track failed: %s", e)
        return ActionResult.error(f"Play failed: {str(e)}", retryable=True)


@chat.function(
    "demo_next_track",
    action_type="write",
    effects=["demo:next"],
    description="Skip to next track in demo playlist.",
)
async def fn_demo_next_track(ctx, params: DemoNextTrackParams) -> ActionResult:
    try:
        state = await _get_demo_state(ctx)
        if state.get("shuffle", False):
            current = state.get("track_index", 0)
            candidates = [i for i in range(len(DEMO_TRACKS)) if i != current]
            next_index = random.choice(candidates) if candidates else 0
        else:
            next_index = state.get("track_index", 0) + 1
        await _set_demo_track(ctx, next_index)
        return ActionResult.success(data={}, summary="Next track", refresh_panels=["spotify"])
    except Exception as e:
        log.error("demo_next_track failed: %s", e)
        return ActionResult.error(f"Skip failed: {str(e)}", retryable=True)


@chat.function(
    "demo_prev_track",
    action_type="write",
    effects=["demo:prev"],
    description="Go to previous track in demo playlist.",
)
async def fn_demo_prev_track(ctx, params: DemoPrevTrackParams) -> ActionResult:
    try:
        state = await _get_demo_state(ctx)
        await _set_demo_track(ctx, state.get("track_index", 0) - 1)
        return ActionResult.success(data={}, summary="Previous track", refresh_panels=["spotify"])
    except Exception as e:
        log.error("demo_prev_track failed: %s", e)
        return ActionResult.error(f"Previous failed: {str(e)}", retryable=True)


@chat.function(
    "demo_pause",
    action_type="write",
    effects=["demo:pause"],
    description="Toggle playback pause/resume in demo mode.",
)
async def fn_demo_pause(ctx, params: DemoPauseParams) -> ActionResult:
    try:
        state = await _get_demo_state(ctx)
        if not state.get("active"):
            return ActionResult.error("Click the demo playlist first to activate demo mode.")
        await _save_demo_state(ctx, {**state, "is_playing": not state.get("is_playing", True)})
        return ActionResult.success(data={}, summary="Toggled playback", refresh_panels=["spotify"])
    except Exception as e:
        log.error("demo_pause failed: %s", e)
        return ActionResult.error(f"Pause failed: {str(e)}", retryable=True)


@chat.function(
    "demo_shuffle",
    action_type="write",
    effects=["demo:shuffle"],
    description="Toggle shuffle mode in demo playlist.",
)
async def fn_demo_shuffle(ctx, params: DemoShuffleParams) -> ActionResult:
    try:
        state = await _get_demo_state(ctx)
        if not state.get("active"):
            return ActionResult.error("Click the demo playlist first to activate demo mode.")
        new_shuffle = not state.get("shuffle", False)
        await _save_demo_state(ctx, {**state, "shuffle": new_shuffle})
        label = "on" if new_shuffle else "off"
        return ActionResult.success(data={"shuffle": new_shuffle}, summary=f"Shuffle {label}", refresh_panels=["spotify"])
    except Exception as e:
        log.error("demo_shuffle failed: %s", e)
        return ActionResult.error(f"Shuffle failed: {str(e)}", retryable=True)
