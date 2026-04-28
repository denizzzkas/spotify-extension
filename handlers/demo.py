"""Demo mode handlers — no Spotify auth required, manipulate cache only."""
from __future__ import annotations

from pydantic import BaseModel, Field

from imperal_sdk import ActionResult

from cache_models import NowPlayingModel, QueueModel, DetailModel
from demo_data import DEMO_TRACKS, DEMO_PLAYLIST_ID, DEMO_PLAYLIST_NAME


async def _set_demo_track(ctx, index: int) -> None:
    index = index % len(DEMO_TRACKS)
    track = DEMO_TRACKS[index]
    queue = await ctx.cache.get(key="queue", model=QueueModel)
    await ctx.cache.set(
        key="queue",
        value=(queue.model_copy(update={"index": index}) if queue else QueueModel(
            playlist_id=DEMO_PLAYLIST_ID, playlist_name=DEMO_PLAYLIST_NAME,
            tracks=DEMO_TRACKS, index=index,
        )),
        ttl_seconds=300,
    )
    await ctx.cache.set(
        key="now_playing",
        value=NowPlayingModel(**track, is_playing=True),
        ttl_seconds=300,
    )


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
    """Load demo playlist into cache — no Spotify auth required."""
    await ctx.cache.set(
        key="detail",
        value=DetailModel(type="tracks", title=DEMO_PLAYLIST_NAME, tracks=DEMO_TRACKS),
        ttl_seconds=300,
    )
    await _set_demo_track(ctx, 0)
    return ActionResult.success(
        data={"count": len(DEMO_TRACKS)},
        refresh_panels=["spotify", "spotify_detail"],
    )


async def fn_demo_play_track(ctx, params: DemoPlayTrackParams) -> ActionResult:
    """Set a specific demo track as now playing."""
    index = next((i for i, t in enumerate(DEMO_TRACKS) if t["id"] == params.track_id), None)
    if index is None:
        return ActionResult.error("Track not found in demo playlist.", retryable=False)
    await _set_demo_track(ctx, index)
    return ActionResult.success(data={}, refresh_panels=["spotify"])


async def fn_demo_next_track(ctx, params: DemoNextTrackParams) -> ActionResult:
    """Advance to the next demo track."""
    queue = await ctx.cache.get(key="queue", model=QueueModel)
    await _set_demo_track(ctx, (queue.index + 1) if queue else 0)
    return ActionResult.success(data={}, refresh_panels=["spotify"])


async def fn_demo_prev_track(ctx, params: DemoPrevTrackParams) -> ActionResult:
    """Go back to the previous demo track."""
    queue = await ctx.cache.get(key="queue", model=QueueModel)
    await _set_demo_track(ctx, (queue.index - 1) if queue else 0)
    return ActionResult.success(data={}, refresh_panels=["spotify"])


async def fn_demo_pause(ctx, params: DemoPauseParams) -> ActionResult:
    """Toggle play/pause in demo mode."""
    cached = await ctx.cache.get(key="now_playing", model=NowPlayingModel)
    if not cached:
        return ActionResult.error("Click the demo playlist first.", retryable=False)
    await ctx.cache.set(
        key="now_playing",
        value=cached.model_copy(update={"is_playing": not cached.is_playing}),
        ttl_seconds=300,
    )
    return ActionResult.success(data={}, refresh_panels=["spotify"])
