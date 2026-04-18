"""Track playback trigger for the Spotify extension."""
from __future__ import annotations

from pydantic import BaseModel, Field

from imperal_sdk import ActionResult

from spotify_config import SP_API_BASE
from utils import format_track, sp_error
from handlers.auth import get_auth_headers, get_auth_headers_refreshed


class PlayTrackParams(BaseModel):
    track_id: str = Field(..., description="Spotify track ID to play")


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

    return ActionResult.success(
        data={
            "track_id": params.track_id,
            "track": track_data,
            "preview_url": track_data["preview_url"],
            "spotify_url": track_data["url"],
        },
        summary=f"Playing: {track_data['artist']} — {track_data['title']}",
        refresh_panels=["spotify"],
    )
