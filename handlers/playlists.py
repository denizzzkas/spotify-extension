"""Spotify playlist handlers."""
from __future__ import annotations

import logging
from typing import List

from pydantic import BaseModel, Field

from imperal_sdk import ActionResult

from app import chat
from return_models import PlaylistRecord, TrackRecord, CreatePlaylistRecord, PlaylistTrackRecord, PlaylistRemoveRecord
from spotify_config import SP_API_BASE, MAX_LIMIT
from app_helpers import _spotify_call, _spotify_err
from cache_models import PlaylistsModel
from utils import format_track, format_playlist, to_spotify_uri

log = logging.getLogger("spotify.playlists")


class GetPlaylistsParams(BaseModel):
    pass

class GetPlaylistTracksParams(BaseModel):
    playlist_id: str = Field(..., description="Spotify playlist ID")

class CreatePlaylistParams(BaseModel):
    name: str = Field(..., description="Name of the new playlist")
    description: str = Field("", description="Optional playlist description")
    tracks: List[str] = Field(default_factory=list, description="Optional list of track IDs to add on creation")
    is_public: bool = Field(False, description="Set to true to make the playlist public")

class AddTrackToPlaylistParams(BaseModel):
    playlist_id: str = Field(..., description="Spotify playlist ID")
    track_id: str = Field(..., description="Spotify track ID to add")

class RemoveTrackFromPlaylistParams(BaseModel):
    playlist_id: str = Field(..., description="Spotify playlist ID")
    track_id: str = Field(..., description="Spotify track ID to remove")


@chat.function(
    "get_playlists",
    action_type="read",
    data_model=PlaylistRecord,
    description="Get all playlists owned or followed by the authenticated user. Returns list of playlists with id, title, track_count, image_url.",
)
async def fn_get_playlists(ctx, params: GetPlaylistsParams) -> ActionResult:
    """Get all playlists owned or followed by the authenticated user. Returns list of playlists with id, title, track_count, image_url."""
    try:
        playlists = []
        url = f"{SP_API_BASE}/me/playlists"
        fetch_params = {"limit": 50}
        while url:
            resp, err = await _spotify_call(ctx, "get", url, params=fetch_params)
            if err:
                return err
            if not resp.ok:
                return _spotify_err(resp)
            data = resp.json()
            playlists.extend([format_playlist(p) for p in (data.get("items") or [])])
            url = data.get("next")
            fetch_params = {}
        try:
            await ctx.cache.set(key="playlists", value=PlaylistsModel(items=playlists), ttl_seconds=300)
        except Exception as e:
            log.error("Failed to cache playlists: %s", e)
        return ActionResult.success(data={"playlists": playlists, "count": len(playlists)},
                                    summary=f"Found {len(playlists)} playlist(s)")
    except Exception as e:
        log.error("get_playlists failed: %s", e)
        return ActionResult.error(f"Failed to get playlists: {str(e)}", retryable=True)


@chat.function(
    "get_playlist_tracks",
    action_type="read",
    data_model=TrackRecord,
    description="Get all tracks in a specific Spotify playlist. Returns list of tracks with full details.",
)
async def fn_get_playlist_tracks(ctx, params: GetPlaylistTracksParams) -> ActionResult:
    """Get all tracks in a specific Spotify playlist. Returns list of tracks with full details."""
    try:
        tracks = []
        url = f"{SP_API_BASE}/playlists/{params.playlist_id}/tracks"
        fetch_params = {"limit": 50}
        while url:
            resp, err = await _spotify_call(ctx, "get", url, params=fetch_params)
            if err:
                return err
            if not resp.ok:
                return _spotify_err(resp)
            data = resp.json()
            for item in (data.get("items") or []):
                raw_track = item.get("track") or item.get("item")
                if raw_track:
                    tracks.append(format_track(raw_track))
            url = data.get("next")
            fetch_params = {}
        return ActionResult.success(data={"tracks": tracks, "count": len(tracks), "playlist_id": params.playlist_id},
                                    summary=f"Retrieved {len(tracks)} track(s) from playlist")
    except Exception as e:
        log.error("get_playlist_tracks failed: %s", e)
        return ActionResult.error(f"Failed to get playlist tracks: {str(e)}", retryable=True)


@chat.function(
    "create_playlist",
    action_type="write",
    chain_callable=True,
    id_projection="playlist_id",
    effects=["playlist:create"],
    event="playlist.created",
    data_model=CreatePlaylistRecord,
    description="Create a new playlist on the user's Spotify account. Returns playlist_id and playlist details.",
)
async def fn_create_playlist(ctx, params: CreatePlaylistParams) -> ActionResult:
    """Create a new playlist on the user's Spotify account. Returns playlist_id and playlist details."""
    try:
        me_resp, err = await _spotify_call(ctx, "get", f"{SP_API_BASE}/me")
        if err:
            return err
        if not me_resp.ok:
            return ActionResult.error("Could not get Spotify user ID. Please reconnect via connect_spotify().")
        my_id = me_resp.json().get("id")

        resp, err = await _spotify_call(
            ctx, "post", f"{SP_API_BASE}/users/{my_id}/playlists",
            json={"name": params.name, "description": params.description, "public": params.is_public},
        )
        if err:
            return err
        if not resp.ok:
            return _spotify_err(resp)

        playlist_data = resp.json()
        playlist_id = playlist_data.get("id")

        if params.tracks:
            uris = [to_spotify_uri(tid) for tid in params.tracks]
            await _spotify_call(ctx, "post", f"{SP_API_BASE}/playlists/{playlist_id}/tracks",
                                json={"uris": uris})

        return ActionResult.success(
            data={"playlist_id": playlist_id, "name": params.name,
                  "url": (playlist_data.get("external_urls") or {}).get("spotify", ""),
                  "tracks_added": len(params.tracks)},
            summary=f"Created playlist '{params.name}' with {len(params.tracks)} track(s)",
        )
    except Exception as e:
        log.error("create_playlist failed: %s", e)
        return ActionResult.error(f"Failed to create playlist: {str(e)}", retryable=False)


@chat.function(
    "add_track_to_playlist",
    action_type="write",
    chain_callable=True,
    id_projection="playlist_id",
    effects=["playlist:add_track"],
    event="track.added_to_playlist",
    data_model=PlaylistTrackRecord,
    description="Add a track to an existing Spotify playlist. Returns updated playlist info.",
)
async def fn_add_track_to_playlist(ctx, params: AddTrackToPlaylistParams) -> ActionResult:
    """Add a track to an existing Spotify playlist. Returns updated playlist info."""
    try:
        resp, err = await _spotify_call(
            ctx, "post", f"{SP_API_BASE}/playlists/{params.playlist_id}/tracks",
            json={"uris": [to_spotify_uri(params.track_id)]},
        )
        if err:
            return err
        if not resp.ok:
            return _spotify_err(resp)
        return ActionResult.success(data={"playlist_id": params.playlist_id, "track_id": params.track_id, "added": True},
                                    summary="Track added to playlist")
    except Exception as e:
        log.error("add_track_to_playlist failed: %s", e)
        return ActionResult.error(f"Failed to add track: {str(e)}", retryable=False)


@chat.function(
    "remove_track_from_playlist",
    action_type="write",
    chain_callable=True,
    id_projection="playlist_id",
    effects=["playlist:remove_track"],
    event="track.removed_from_playlist",
    data_model=PlaylistRemoveRecord,
    description="Remove a track from a Spotify playlist. Returns updated playlist info.",
)
async def fn_remove_track_from_playlist(ctx, params: RemoveTrackFromPlaylistParams) -> ActionResult:
    """Remove a track from a Spotify playlist. Returns updated playlist info."""
    try:
        resp, err = await _spotify_call(
            ctx, "delete", f"{SP_API_BASE}/playlists/{params.playlist_id}/tracks",
            json={"tracks": [{"uri": to_spotify_uri(params.track_id)}]},
        )
        if err:
            return err
        if not resp.ok:
            return _spotify_err(resp)
        return ActionResult.success(data={"playlist_id": params.playlist_id, "track_id": params.track_id, "removed": True},
                                    summary="Track removed from playlist")
    except Exception as e:
        log.error("remove_track_from_playlist failed: %s", e)
        return ActionResult.error(f"Failed to remove track: {str(e)}", retryable=False)
