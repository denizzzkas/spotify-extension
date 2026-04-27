"""Track playback trigger for the Spotify extension."""
from __future__ import annotations

from pydantic import BaseModel, Field

from imperal_sdk import ActionResult

from spotify_config import SP_API_BASE
from utils import format_track, sp_error
from handlers.auth import get_auth_headers, get_auth_headers_refreshed
from cache_models import NowPlayingModel, QueueModel


async def _refresh_now_playing(ctx, headers) -> dict | None:
    """Fetch current player state from Spotify and write to cache. Returns track or None."""
    resp = await ctx.http.get(f"{SP_API_BASE}/me/player", headers=headers)
    if resp.status_code == 204 or not resp.ok:
        return None
    body = resp.json()
    item = body.get("item")
    if not item:
        return None
    track = format_track(item)
    track["is_playing"] = body.get("is_playing", False)
    await ctx.cache.set(key="now_playing", value=NowPlayingModel(**track), ttl_seconds=90)
    return track


class PlayTrackParams(BaseModel):
    track_id: str = Field(..., description="Spotify track ID to play")


class PlayTrackByNameParams(BaseModel):
    title: str = Field(..., description="Track title")
    artist: str = Field("", description="Artist name (optional but improves accuracy)")


class PlayPlaylistParams(BaseModel):
    playlist_id: str = Field(..., description="Spotify playlist ID")
    playlist_name: str = Field("", description="Playlist display name")


async def fn_play_track(ctx, params: PlayTrackParams) -> ActionResult:
    """Fetch track metadata and trigger a track.played event for platform playback.

    Returns track info including preview_url (30-second MP3, available on free accounts).
    Full playback via Imperal's player uses the Spotify track URL.
    """
    try:
        headers = await get_auth_headers(ctx)
    except ValueError as exc:
        return ActionResult.error(str(exc))

    resp = await ctx.http.get(
        f"{SP_API_BASE}/tracks/{params.track_id}",
        headers=headers,
    )

    if resp.status_code == 401:
        try:
            headers = await get_auth_headers_refreshed(ctx)
        except ValueError as exc:
            return ActionResult.error(str(exc))
        resp = await ctx.http.get(
            f"{SP_API_BASE}/tracks/{params.track_id}",
            headers=headers,
        )

    if not resp.ok:
        return ActionResult.error(sp_error(resp.status_code), retryable=False)

    track_data = format_track(resp.json())
    await ctx.cache.set(key="now_playing", value=NowPlayingModel(**track_data, is_playing=True), ttl_seconds=90)

    return ActionResult.success(
        data={
            "track_id": params.track_id,
            "track": track_data,
            "preview_url": track_data["preview_url"],
            "spotify_url": track_data["url"],
        },
        summary=f"▶ {track_data['artist']} — {track_data['title']} (system player coming soon)",
        refresh_panels=["spotify"],
    )


async def fn_play_track_by_name(ctx, params: PlayTrackByNameParams) -> ActionResult:
    """Search for a track by name and artist, then trigger playback."""
    try:
        headers = await get_auth_headers(ctx)
    except ValueError as exc:
        return ActionResult.error(str(exc))

    query = f"{params.title} {params.artist}".strip()
    resp = await ctx.http.get(
        f"{SP_API_BASE}/search",
        headers=headers,
        params={"q": query, "type": "track", "limit": 1},
    )

    if resp.status_code == 401:
        try:
            headers = await get_auth_headers_refreshed(ctx)
        except ValueError as exc:
            return ActionResult.error(str(exc))
        resp = await ctx.http.get(
            f"{SP_API_BASE}/search",
            headers=headers,
            params={"q": query, "type": "track", "limit": 1},
        )

    if not resp.ok:
        return ActionResult.error(sp_error(resp.status_code), retryable=(resp.status_code == 429))

    items = (resp.json().get("tracks") or {}).get("items", [])
    if not items:
        return ActionResult.error(f"Track '{query}' not found on Spotify.", retryable=False)

    track = format_track(items[0])
    await ctx.cache.set(key="now_playing", value=NowPlayingModel(**track, is_playing=True), ttl_seconds=90)

    return ActionResult.success(
        data={"track": track, "preview_url": track["preview_url"], "spotify_url": track["url"]},
        summary=f"▶ {track['artist']} — {track['title']} (system player coming soon)",
        refresh_panels=["spotify"],
    )


async def fn_play_playlist(ctx, params: PlayPlaylistParams) -> ActionResult:
    """Load full playlist into the playback queue and trigger playlist playback."""
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

    if not tracks:
        return ActionResult.error("Playlist is empty.", retryable=False)

    name = params.playlist_name or params.playlist_id
    await ctx.cache.set(
        key="queue",
        value=QueueModel(
            playlist_id=params.playlist_id,
            playlist_name=name,
            tracks=tracks[:30],  # cap at 30 to stay under 64 KB
            index=0,
        ),
        ttl_seconds=300,
    )
    await ctx.cache.set(key="now_playing", value=NowPlayingModel(**tracks[0], is_playing=True), ttl_seconds=90)

    return ActionResult.success(
        data={"playlist_name": name, "tracks": tracks, "count": len(tracks)},
        summary=f"▶ Playing '{name}' — {len(tracks)} tracks (system player coming soon)",
        refresh_panels=["spotify"],
    )


# ── Playback controls ─────────────────────────────────────────────────────────

class PausePlaybackParams(BaseModel):
    """No parameters needed."""

class ResumePlaybackParams(BaseModel):
    """No parameters needed."""

class NextTrackParams(BaseModel):
    """No parameters needed."""

class PrevTrackParams(BaseModel):
    """No parameters needed."""


async def fn_pause_playback(ctx, params: PausePlaybackParams) -> ActionResult:
    """Pause playback on the user's active Spotify device."""
    try:
        headers = await get_auth_headers(ctx)
    except ValueError as exc:
        return ActionResult.error(str(exc))
    resp = await ctx.http.put(f"{SP_API_BASE}/me/player/pause", headers=headers)
    if not resp.ok:
        return ActionResult.error(sp_error(resp.status_code), retryable=False)
    cached = await ctx.cache.get(key="now_playing", model=NowPlayingModel)
    if cached:
        await ctx.cache.set(
            key="now_playing",
            value=cached.model_copy(update={"is_playing": False}),
            ttl_seconds=90,
        )
    return ActionResult.success(data={"paused": True}, summary="Paused.", refresh_panels=["spotify"])


async def fn_resume_playback(ctx, params: ResumePlaybackParams) -> ActionResult:
    """Resume playback on the user's active Spotify device."""
    try:
        headers = await get_auth_headers(ctx)
    except ValueError as exc:
        return ActionResult.error(str(exc))
    resp = await ctx.http.put(f"{SP_API_BASE}/me/player/play", headers=headers)
    if not resp.ok:
        return ActionResult.error(sp_error(resp.status_code), retryable=False)
    cached = await ctx.cache.get(key="now_playing", model=NowPlayingModel)
    if cached:
        await ctx.cache.set(
            key="now_playing",
            value=cached.model_copy(update={"is_playing": True}),
            ttl_seconds=90,
        )
    return ActionResult.success(data={"playing": True}, summary="Resumed.", refresh_panels=["spotify"])


async def fn_next_track(ctx, params: NextTrackParams) -> ActionResult:
    """Skip to the next track on the user's active Spotify device."""
    try:
        headers = await get_auth_headers(ctx)
    except ValueError as exc:
        return ActionResult.error(str(exc))
    resp = await ctx.http.post(f"{SP_API_BASE}/me/player/next", headers=headers)
    if not resp.ok:
        return ActionResult.error(sp_error(resp.status_code), retryable=False)
    track = await _refresh_now_playing(ctx, headers)
    title = f"{track['artist']} — {track['title']}" if track else "next track"
    return ActionResult.success(data={"skipped": True}, summary=f"⏭ {title}", refresh_panels=["spotify"])


async def fn_prev_track(ctx, params: PrevTrackParams) -> ActionResult:
    """Skip to the previous track on the user's active Spotify device."""
    try:
        headers = await get_auth_headers(ctx)
    except ValueError as exc:
        return ActionResult.error(str(exc))
    resp = await ctx.http.post(f"{SP_API_BASE}/me/player/previous", headers=headers)
    if not resp.ok:
        return ActionResult.error(sp_error(resp.status_code), retryable=False)
    track = await _refresh_now_playing(ctx, headers)
    title = f"{track['artist']} — {track['title']}" if track else "previous track"
    return ActionResult.success(data={"skipped": True}, summary=f"⏮ {title}", refresh_panels=["spotify"])
