"""Spotify artist handlers — top tracks, albums."""
from __future__ import annotations

import logging

from pydantic import BaseModel, Field

from imperal_sdk import ActionResult

from app import chat
from return_models import SearchResultRecord, ArtistAlbumsRecord
from spotify_config import SP_API_BASE
from app_helpers import _spotify_call, _spotify_err
from utils import format_track, format_album

log = logging.getLogger("spotify.artists")

DEFAULT_ARTIST_ALBUMS_LIMIT = 20


class GetArtistTopTracksParams(BaseModel):
    artist_name: str = Field(..., description="Artist name to search for")


class GetArtistAlbumsParams(BaseModel):
    artist_name: str = Field(..., description="Artist name to search for")
    limit: int = Field(DEFAULT_ARTIST_ALBUMS_LIMIT, ge=1, le=50, description="Number of albums to return")


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
    "get_artist_top_tracks",
    action_type="read",
    data_model=SearchResultRecord,
    description="Get top tracks for an artist by name. Returns up to 10 most popular tracks with id, title, album, duration. Use track ids from results to play or add to playlist.",
)
async def fn_get_artist_top_tracks(ctx, params: GetArtistTopTracksParams) -> ActionResult:
    """Get top tracks for an artist. Returns list of up to 10 tracks."""
    try:
        artist_id, artist_display, err = await _find_artist_id(ctx, params.artist_name)
        if err:
            return err

        resp, err = await _spotify_call(
            ctx, "get", f"{SP_API_BASE}/artists/{artist_id}/top-tracks",
            params={"market": "from_token"},
        )
        if err:
            return err
        if not resp.ok:
            return _spotify_err(resp)

        tracks = [format_track(t) for t in (resp.json().get("tracks") or [])]
        return ActionResult.success(
            data={"tracks": tracks, "count": len(tracks), "query": artist_display},
            summary=f"Top {len(tracks)} tracks by {artist_display}",
        )
    except Exception as e:
        log.error("get_artist_top_tracks failed: %s", e)
        return ActionResult.error(f"Failed to get artist top tracks: {str(e)}", retryable=True)


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
            params={"include_groups": "album,single", "limit": params.limit, "market": "from_token"},
        )
        if err:
            return err
        if not resp.ok:
            return _spotify_err(resp)

        albums = [format_album(a) for a in (resp.json().get("items") or [])]
        return ActionResult.success(
            data={"albums": albums, "count": len(albums), "artist": artist_display},
            summary=f"Found {len(albums)} album(s) by {artist_display}",
        )
    except Exception as e:
        log.error("get_artist_albums failed: %s", e)
        return ActionResult.error(f"Failed to get artist albums: {str(e)}", retryable=True)
