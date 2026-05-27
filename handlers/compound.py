"""Compound handlers — multi-step Spotify operations in a single function call."""
from __future__ import annotations

import logging

from pydantic import BaseModel, Field

from imperal_sdk import ActionResult

from app import chat
from return_models import BulkAddTracksRecord
from spotify_config import SP_API_BASE
from app_helpers import _spotify_call, _spotify_err
from utils import to_spotify_uri

log = logging.getLogger("spotify.compound")


class AddArtistTopTracksToPlaylistParams(BaseModel):
    artist_name: str = Field(..., description="Artist name to search for")
    playlist_id: str = Field(..., description="Spotify playlist ID to add tracks to")
    limit: int = Field(10, ge=1, le=10, description="Number of top tracks to add (max 10)")


class AddAlbumTracksToPlaylistParams(BaseModel):
    album_name: str = Field(..., description="Album name to search for")
    artist_name: str = Field("", description="Artist name to narrow the album search (optional)")
    playlist_id: str = Field(..., description="Spotify playlist ID to add tracks to")
    limit: int = Field(50, ge=1, le=50, description="Maximum number of tracks to add from the album")


@chat.function(
    "add_artist_top_tracks_to_playlist",
    action_type="write",
    chain_callable=True,
    id_projection="playlist_id",
    effects=["playlist:add_track"],
    event="track.added_to_playlist",
    data_model=BulkAddTracksRecord,
    description="Find an artist by name and add their top tracks to a playlist in one step. Use when the user says 'add top tracks from [artist] to [playlist]' or 'add N tracks by [artist] to [playlist]'.",
)
async def fn_add_artist_top_tracks_to_playlist(ctx, params: AddArtistTopTracksToPlaylistParams) -> ActionResult:
    """Search artist → get top tracks → add to playlist in one operation."""
    try:
        tracks_resp, err = await _spotify_call(
            ctx, "get", f"{SP_API_BASE}/search",
            params={"q": f"artist:{params.artist_name}", "type": "track", "limit": 50},
        )
        if err:
            return err
        if not tracks_resp.ok:
            return _spotify_err(tracks_resp)

        raw_tracks = tracks_resp.json().get("tracks", {}).get("items") or []
        raw_tracks.sort(key=lambda t: t.get("popularity", 0), reverse=True)
        artist_display = raw_tracks[0]["artists"][0]["name"] if raw_tracks else params.artist_name
        uris = [to_spotify_uri(t["id"]) for t in raw_tracks[:params.limit] if t.get("id")]
        if not uris:
            return ActionResult.error(f"No tracks found for '{params.artist_name}'.", retryable=False)

        add_resp, err = await _spotify_call(
            ctx, "post", f"{SP_API_BASE}/playlists/{params.playlist_id}/items",
            json={"uris": uris},
        )
        if err:
            return err
        if not add_resp.ok:
            return _spotify_err(add_resp)

        return ActionResult.success(
            data={"playlist_id": params.playlist_id, "tracks_added": len(uris)},
            summary=f"Added {len(uris)} top tracks by {artist_display} to playlist",
        )
    except Exception as e:
        log.error("add_artist_top_tracks_to_playlist failed: %s", e)
        return ActionResult.error(f"Failed: {str(e)}", retryable=False)


@chat.function(
    "add_album_tracks_to_playlist",
    action_type="write",
    chain_callable=True,
    id_projection="playlist_id",
    effects=["playlist:add_track"],
    event="track.added_to_playlist",
    data_model=BulkAddTracksRecord,
    description="Find an album by name and add its tracks to a playlist in one step. Use when the user says 'add tracks from [album] to [playlist]' or 'add first N tracks from [album] to [playlist]'.",
)
async def fn_add_album_tracks_to_playlist(ctx, params: AddAlbumTracksToPlaylistParams) -> ActionResult:
    """Search album → get tracks → add to playlist in one operation."""
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

        tracks_resp, err = await _spotify_call(
            ctx, "get", f"{SP_API_BASE}/albums/{album_id}/tracks",
            params={"limit": 50},
        )
        if err:
            return err
        if not tracks_resp.ok:
            return _spotify_err(tracks_resp)

        raw_tracks = tracks_resp.json().get("items") or []
        uris = [to_spotify_uri(t["id"]) for t in raw_tracks[:params.limit] if t.get("id")]
        if not uris:
            return ActionResult.error(f"No tracks found in album '{album_display}'.", retryable=False)

        add_resp, err = await _spotify_call(
            ctx, "post", f"{SP_API_BASE}/playlists/{params.playlist_id}/items",
            json={"uris": uris},
        )
        if err:
            return err
        if not add_resp.ok:
            return _spotify_err(add_resp)

        return ActionResult.success(
            data={"playlist_id": params.playlist_id, "tracks_added": len(uris)},
            summary=f"Added {len(uris)} tracks from '{album_display}' to playlist",
        )
    except Exception as e:
        log.error("add_album_tracks_to_playlist failed: %s", e)
        return ActionResult.error(f"Failed: {str(e)}", retryable=False)
