"""Spotify artist handlers — top tracks, albums."""
from __future__ import annotations

import logging

from pydantic import BaseModel, Field

from imperal_sdk import ActionResult

from app import chat
from return_models import ArtistAlbumsRecord
from spotify_config import SP_API_BASE
from app_helpers import _spotify_call, _spotify_err
from utils import format_album

log = logging.getLogger("spotify.artists")


class GetArtistAlbumsParams(BaseModel):
    artist_name: str = Field(..., description="Artist name to search for")
    limit: int = Field(10, ge=1, le=10, description="Number of albums to return (max 10)")


async def _find_artist_id(ctx, artist_name: str):
    """Search for an artist by name, return (artist_id, artist_name, error)."""
    resp, err = await _spotify_call(
        ctx, "get", f"{SP_API_BASE}/search",
        params={"q": artist_name, "type": "artist", "limit": 1},
    )
    if err:
        return None, None, err
    if not resp.ok:
        return None, None, _spotify_err(resp)
    items = resp.json().get("artists", {}).get("items", [])
    if not items:
        return None, None, ActionResult.error(f"Artist '{artist_name}' not found on Spotify.", retryable=False)
    return items[0]["id"], items[0]["name"], None



@chat.function(
    "get_artist_albums",
    action_type="read",
    data_model=ArtistAlbumsRecord,
    description="Get albums and singles released by an artist. Returns list of albums with id, name, release_date, tracks_count. Use album id with get_album_tracks to browse an album's tracks.",
)
async def fn_get_artist_albums(ctx, params: GetArtistAlbumsParams) -> ActionResult:
    """Get albums for an artist by name."""
    try:
        artist_id, artist_display, err = await _find_artist_id(ctx, params.artist_name)
        if err:
            return err

        resp, err = await _spotify_call(
            ctx, "get", f"{SP_API_BASE}/artists/{artist_id}/albums",
            params={"include_groups": "album,single", "limit": params.limit},
        )
        if err:
            return err
        if not resp.ok:
            return _spotify_err(resp)

        albums = [format_album(a) for a in (resp.json().get("items") or [])]
        return ActionResult.success(
            data={"items": albums, "total": len(albums), "artist": artist_display},
            summary=f"Found {len(albums)} album(s) by {artist_display}",
        )
    except Exception as e:
        log.error("get_artist_albums failed: %s", e)
        return ActionResult.error(f"Failed to get artist albums: {str(e)}", retryable=True)
