"""Demo mode handlers — no Spotify auth required, uses ctx.store for state."""
from __future__ import annotations

from pydantic import BaseModel, Field

from imperal_sdk import ActionResult

from cache_models import DetailModel, NowPlayingModel
from demo_data import DEMO_TRACKS, DEMO_PLAYLIST_ID, DEMO_PLAYLIST_NAME
from spotify_config import DEMO_STATE_COLLECTION


async def _get_demo_state(ctx) -> dict:
    try:
        page = await ctx.store.query(DEMO_STATE_COLLECTION, where={"user_id": ctx.user.imperal_id})
        return page.data[0].data if page.data else {}
    except Exception:
        return {}


async def _save_demo_state(ctx, state: dict) -> None:
    try:
        record = {"user_id": ctx.user.imperal_id, **state}
        page = await ctx.store.query(DEMO_STATE_COLLECTION, where={"user_id": ctx.user.imperal_id})
        if page.data:
            await ctx.store.update(DEMO_STATE_COLLECTION, page.data[0].id, record)
        else:
            await ctx.store.create(DEMO_STATE_COLLECTION, record)
    except Exception:
        pass


async def _set_demo_track(ctx, index: int) -> None:
    index = index % len(DEMO_TRACKS)
    await _save_demo_state(ctx, {"track_index": index, "is_playing": True, "active": True})


class OpenDemoPlaylistParams(BaseModel):
    """No parameters."""

class DemoPlayTrackParams(BaseModel):
    track_id: str = Field(..., description="Demo track ID to play")

class DemoNextTrackParams(BaseModel):
    """No parameters."""

class DemoPrevTrackParams(BaseModel):
    """No parameters."""

class DemoPauseParams(BaseModel):
    """No parameters."""


async def fn_open_demo_playlist(ctx, params: OpenDemoPlaylistParams) -> ActionResult:
    await _set_demo_track(ctx, 0)
    try:
        await ctx.cache.set(
            key="detail",
            value=DetailModel(type="tracks", title=DEMO_PLAYLIST_NAME, tracks=DEMO_TRACKS),
            ttl_seconds=300,
        )
    except Exception:
        pass
    return ActionResult.success(
        data={"count": len(DEMO_TRACKS)},
        refresh_panels=["spotify", "spotify_detail"],
    )


async def fn_demo_play_track(ctx, params: DemoPlayTrackParams) -> ActionResult:
    index = next((i for i, t in enumerate(DEMO_TRACKS) if t["id"] == params.track_id), None)
    if index is None:
        return ActionResult.error("Track not found in demo playlist.", retryable=False)
    await _set_demo_track(ctx, index)
    return ActionResult.success(data={}, refresh_panels=["spotify"])


async def fn_demo_next_track(ctx, params: DemoNextTrackParams) -> ActionResult:
    state = await _get_demo_state(ctx)
    await _set_demo_track(ctx, state.get("track_index", 0) + 1)
    return ActionResult.success(data={}, refresh_panels=["spotify"])


async def fn_demo_prev_track(ctx, params: DemoPrevTrackParams) -> ActionResult:
    state = await _get_demo_state(ctx)
    await _set_demo_track(ctx, state.get("track_index", 0) - 1)
    return ActionResult.success(data={}, refresh_panels=["spotify"])


async def fn_demo_pause(ctx, params: DemoPauseParams) -> ActionResult:
    state = await _get_demo_state(ctx)
    if not state.get("active"):
        return ActionResult.error("Click the demo playlist first.", retryable=False)
    await _save_demo_state(ctx, {**state, "is_playing": not state.get("is_playing", True)})
    return ActionResult.success(data={}, refresh_panels=["spotify"])
