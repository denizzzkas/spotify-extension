"""Demo mode handlers — no Spotify auth required, uses ctx.cache for session state."""
from __future__ import annotations

import logging
import random

from pydantic import BaseModel, Field

from imperal_sdk import ActionResult

from app import chat, NowPlayingModel, DemoStateModel
from return_models import DemoPlaylistRecord, DemoTrackRecord, PlayerActionRecord, ShuffleRecord
from demo_data import DEMO_TRACKS, DEMO_PLAYLIST_ID, DEMO_PLAYLIST_NAME

log = logging.getLogger("spotify.demo")


async def _get_demo_state(ctx) -> dict:
    try:
        cached = await ctx.cache.get(key="demo_state", model=DemoStateModel)
        return cached.model_dump() if cached else {}
    except Exception as e:
        log.error("_get_demo_state failed: %s", e)
        return {}


async def _save_demo_state(ctx, state: dict) -> None:
    try:
        await ctx.cache.set(
            key="demo_state",
            value=DemoStateModel(
                track_index=state.get("track_index", 0),
                is_playing=state.get("is_playing", True),
                shuffle=state.get("shuffle", False),
            ),
            ttl_seconds=300,
        )
    except Exception as e:
        log.error("_save_demo_state failed: %s", e)


async def _update_now_playing_cache(ctx, index: int, is_playing: bool) -> None:
    track = DEMO_TRACKS[index]
    try:
        await ctx.cache.set(
            key="now_playing",
            value=NowPlayingModel(**track, is_playing=is_playing),
            ttl_seconds=300,
        )
    except Exception as e:
        log.error("_update_now_playing_cache failed: %s", e)


async def _set_demo_track(ctx, index: int) -> None:
    index = index % len(DEMO_TRACKS)
    state = await _get_demo_state(ctx)
    await _save_demo_state(ctx, {**state, "track_index": index, "is_playing": True})
    await _update_now_playing_cache(ctx, index, is_playing=True)


class OpenDemoPlaylistParams(BaseModel):
    pass

class DemoPlayTrackParams(BaseModel):
    track_id: str = Field(..., description="Demo track ID or track name/artist to search for and play")

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
    chain_callable=True,
    effects=["demo:active"],
    event="open_demo_playlist",
    data_model=DemoPlaylistRecord,
    description="Open demo playlist (no Spotify login required). Returns demo tracks for testing.",
)
async def fn_open_demo_playlist(ctx, params: OpenDemoPlaylistParams) -> ActionResult:
    """Open demo playlist (no Spotify login required). Returns demo tracks for testing."""
    try:
        await _set_demo_track(ctx, 0)
        return ActionResult.success(
            data={"items": DEMO_TRACKS, "total": len(DEMO_TRACKS)},
            summary=f"Opened demo playlist ({len(DEMO_TRACKS)} tracks)",
            refresh_panels=["spotify"],
        )
    except Exception as e:
        log.error("open_demo_playlist failed: %s", e)
        return ActionResult.error(f"Failed to open demo: {str(e)}", retryable=True)


@chat.function(
    "demo_play_track",
    action_type="write",
    chain_callable=True,
    effects=["demo:play"],
    event="demo_play_track",
    data_model=DemoTrackRecord,
    description="Play a specific track from demo playlist.",
)
async def fn_demo_play_track(ctx, params: DemoPlayTrackParams) -> ActionResult:
    """Play a specific track from demo playlist."""
    try:
        index = None

        # Try exact ID match first (case-sensitive for Spotify IDs)
        index = next((i for i, t in enumerate(DEMO_TRACKS) if t["id"] == params.track_id), None)

        # If not found, search by title or artist (case-insensitive)
        if index is None:
            query = params.track_id.lower()
            index = next((i for i, t in enumerate(DEMO_TRACKS)
                         if query in t["title"].lower() or query in t["artist"].lower()), None)

        if index is None:
            return ActionResult.error(f"Track '{params.track_id}' not found in demo playlist.")

        await _set_demo_track(ctx, index)
        track = DEMO_TRACKS[index]
        return ActionResult.success(
            data={"track_id": track["id"], "title": track["title"], "artist": track["artist"]},
            summary=f"▶ {track['artist']} — {track['title']}",
            refresh_panels=["spotify"]
        )
    except Exception as e:
        log.error("demo_play_track failed: %s", e)
        return ActionResult.error(f"Play failed: {str(e)}", retryable=True)


@chat.function(
    "demo_next_track",
    action_type="write",
    chain_callable=True,
    effects=["demo:next"],
    event="demo_next_track",
    data_model=PlayerActionRecord,
    description="Skip to next track in demo playlist.",
)
async def fn_demo_next_track(ctx, params: DemoNextTrackParams) -> ActionResult:
    """Skip to next track in demo playlist."""
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
    chain_callable=True,
    effects=["demo:prev"],
    event="demo_prev_track",
    data_model=PlayerActionRecord,
    description="Go to previous track in demo playlist.",
)
async def fn_demo_prev_track(ctx, params: DemoPrevTrackParams) -> ActionResult:
    """Go to previous track in demo playlist."""
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
    chain_callable=True,
    effects=["demo:pause"],
    event="demo_pause",
    data_model=PlayerActionRecord,
    description="Toggle playback pause/resume in demo mode.",
)
async def fn_demo_pause(ctx, params: DemoPauseParams) -> ActionResult:
    """Toggle playback pause/resume in demo mode."""
    try:
        state = await _get_demo_state(ctx)
        new_is_playing = not state.get("is_playing", True)
        await _save_demo_state(ctx, {**state, "is_playing": new_is_playing})
        await _update_now_playing_cache(ctx, state.get("track_index", 0), is_playing=new_is_playing)
        return ActionResult.success(data={}, summary="Toggled playback", refresh_panels=["spotify"])
    except Exception as e:
        log.error("demo_pause failed: %s", e)
        return ActionResult.error(f"Pause failed: {str(e)}", retryable=True)


@chat.function(
    "demo_shuffle",
    action_type="write",
    chain_callable=True,
    effects=["demo:shuffle"],
    event="demo_shuffle",
    data_model=ShuffleRecord,
    description="Toggle shuffle mode in demo playlist.",
)
async def fn_demo_shuffle(ctx, params: DemoShuffleParams) -> ActionResult:
    """Toggle shuffle mode in demo playlist."""
    try:
        state = await _get_demo_state(ctx)
        new_shuffle = not state.get("shuffle", False)
        await _save_demo_state(ctx, {**state, "shuffle": new_shuffle})
        label = "on" if new_shuffle else "off"
        return ActionResult.success(data={"shuffle": new_shuffle}, summary=f"Shuffle {label}", refresh_panels=["spotify"])
    except Exception as e:
        log.error("demo_shuffle failed: %s", e)
        return ActionResult.error(f"Shuffle failed: {str(e)}", retryable=True)
