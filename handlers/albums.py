"""Spotify album handlers — browse album tracks."""
from __future__ import annotations

import logging

from pydantic import BaseModel, Field

from imperal_sdk import ActionResult

from app import chat
from return_models import AlbumTracksRecord
from spotify_config import SP_API_BASE
from app_helpers import _spotify_call, _spotify_err
from utils import format_track

log = logging.getLogger("spotify.albums")


class GetAlbumTracksParams(BaseModel):
    album_name: str = Field(..., description="Album name to search for")
    artist_name: str = Field("", description="Artist name to narrow the search (optional but recommended)")


@chat.function(
    "get_album_tracks",
    action_type="read",
    data_model=AlbumTracksRecord,
    description="Get all tracks from an album by album name (and optionally artist name). Returns track list with ids, titles, durations. Use track ids to play individual tracks or add them to a playlist.",
)
async def fn_get_album_tracks(ctx, params: GetAlbumTracksParams) -> ActionResult:
    """Search for an album and return its track list."""
    try:
        query = f"{params.album_name} {params.artist_name}".strip()
        search_resp, err = await _spotify_call(
            ctx, "get", f"{SP_API_BASE}/search",
            params={"q": query, "type": "album", "limit": 1},
        )
        if err:
            return err
        if not search_resp.ok:
            return _spotify_err(search_resp)

        albums = search_resp.json().get("albums", {}).get("items", [])
        if not albums:
            return ActionResult.error(f"Album '{params.album_name}' not found on Spotify.", retryable=False)

        album = albums[0]
        album_id = album["id"]
        album_display = album["name"]
        artist_display = ", ".join(a["name"] for a in album.get("artists", []))

        tracks_resp, err = await _spotify_call(
            ctx, "get", f"{SP_API_BASE}/albums/{album_id}/tracks",
            params={"limit": 50},
        )
        if err:
            return err
        if not tracks_resp.ok:
            return _spotify_err(tracks_resp)

        raw_tracks = tracks_resp.json().get("items") or []
        tracks = []
        for t in raw_tracks:
            track = format_track(t)
            if not track["album"]:
                track["album"] = album_display
            if not track["album_art"]:
                images = album.get("images") or []
                track["album_art"] = images[0].get("url", "") if images else ""
            tracks.append(track)

        return ActionResult.success(
            data={"items": tracks, "total": len(tracks), "album": album_display, "artist": artist_display},
            summary=f"'{album_display}' by {artist_display} — {len(tracks)} tracks",
        )
    except Exception as e:
        log.error("get_album_tracks failed: %s", e)
        return ActionResult.error(f"Failed to get album tracks: {str(e)}", retryable=True)
