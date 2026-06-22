"""Spotify playlist handlers."""
from __future__ import annotations

import logging
from pydantic import BaseModel, Field
from imperal_sdk import ActionResult
from app import chat
from return_models import UserPlaylistsRecord, PlaylistTracksRecord, CreatePlaylistRecord, PlaylistTrackRecord, PlaylistRemoveRecord, DeletePlaylistRecord, BulkAddTracksRecord, RenamePlaylistRecord
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
    tracks: list[str] = Field(default=[], description="Optional list of track IDs to add on creation")
    is_public: bool = Field(False, description="Set to true to make the playlist public")

class AddTrackToPlaylistParams(BaseModel):
    playlist_id: str = Field(..., description="Spotify playlist ID")
    track_id: str = Field(..., description="Spotify track ID to add")

class RemoveTrackFromPlaylistParams(BaseModel):
    playlist_id: str = Field(..., description="Spotify playlist ID")
    track_id: str = Field(..., description="Spotify track ID to remove")

class RenamePlaylistParams(BaseModel):
    playlist_id: str = Field(..., description="Spotify playlist ID to rename")
    name: str = Field(..., description="New playlist name")

class DeletePlaylistParams(BaseModel):
    playlist_id: str = Field(..., description="Spotify playlist ID to delete")

class AddTracksToPlaylistParams(BaseModel):
    playlist_id: str = Field(..., description="Spotify playlist ID")
    track_ids: list[str] = Field(..., description="List of Spotify track IDs to add")

@chat.function(
    "get_playlists",
    action_type="read",
    data_model=UserPlaylistsRecord,
    description="List all playlists owned or followed by the user. Use this to browse or find a playlist before playing or editing it. Returns id, title, track_count, image_url.",
)
async def fn_get_playlists(ctx, params: GetPlaylistsParams) -> ActionResult:
    """Return all playlists owned or followed by the authenticated user."""
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
            url, fetch_params = data.get("next"), {}
        try:
            await ctx.cache.set(key="playlists", value=PlaylistsModel(items=playlists), ttl_seconds=300)
        except Exception as e:
            log.error("Failed to cache playlists: %s", e)
        return ActionResult.success(data={"items": playlists, "total": len(playlists)},
                                    summary=f"Found {len(playlists)} playlist(s)")
    except Exception as e:
        log.error("get_playlists failed: %s", e)
        return ActionResult.error(f"Failed to get playlists: {str(e)}", retryable=True)


@chat.function(
    "get_playlist_tracks",
    action_type="read",
    data_model=PlaylistTracksRecord,
    description="List tracks in a playlist WITHOUT playing it. Use this to browse contents. To actually play the playlist, use play_playlist instead. Accepts playlist_id or playlist name.",
)
async def fn_get_playlist_tracks(ctx, params: GetPlaylistTracksParams) -> ActionResult:
    """Return all tracks in a playlist without starting playback."""
    try:
        tracks = []
        url = f"{SP_API_BASE}/playlists/{params.playlist_id}/items"
        fetch_params = {"limit": 50}
        while url:
            resp, err = await _spotify_call(ctx, "get", url, params=fetch_params)
            if err:
                return err
            if not resp.ok:
                return _spotify_err(resp)
            data = resp.json()
            for item in (data.get("items") or []):
                raw_track = item.get("item")
                if raw_track:
                    tracks.append(format_track(raw_track))
            url, fetch_params = data.get("next"), {}
        return ActionResult.success(data={"items": tracks, "total": len(tracks), "playlist_id": params.playlist_id},
                                    summary=f"Retrieved {len(tracks)} track(s) from playlist")
    except Exception as e:
        log.error("get_playlist_tracks failed: %s", e)
        return ActionResult.error(f"Failed to get playlist tracks: {str(e)}", retryable=True)


@chat.function(
    "create_playlist",
    action_type="write",
    chain_callable=True,
    effects=["playlist:create"],
    event="playlist.created",
    data_model=CreatePlaylistRecord,
    description="Create a NEW empty playlist. Call this ONLY when the user explicitly asks to create a playlist — NOT for viewing existing ones (use get_playlists) or playing one (use play_playlist).",
)
async def fn_create_playlist(ctx, params: CreatePlaylistParams) -> ActionResult:
    """Create a new empty playlist, optionally seeded with track IDs."""
    try:
        resp, err = await _spotify_call(
            ctx, "post", f"{SP_API_BASE}/me/playlists",
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
            await _spotify_call(ctx, "post", f"{SP_API_BASE}/playlists/{playlist_id}/items",
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
    description="Add a track to an existing playlist. Accepts track name/artist or track_id. In chains after search_tracks, pass the track_id from results. Accepts playlist name or playlist_id.",
)
async def fn_add_track_to_playlist(ctx, params: AddTrackToPlaylistParams) -> ActionResult:
    """Add a single track to a playlist by track ID."""
    try:
        resp, err = await _spotify_call(
            ctx, "post", f"{SP_API_BASE}/playlists/{params.playlist_id}/items",
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
    description="Remove a track from a playlist. Accepts track name/artist or track_id, and playlist name or playlist_id.",
)
async def fn_remove_track_from_playlist(ctx, params: RemoveTrackFromPlaylistParams) -> ActionResult:
    """Remove a track from a Spotify playlist. Returns updated playlist info."""
    try:
        resp, err = await _spotify_call(
            ctx, "delete", f"{SP_API_BASE}/playlists/{params.playlist_id}/items",
            json={"items": [{"uri": to_spotify_uri(params.track_id)}]},
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


@chat.function(
    "rename_playlist",
    action_type="write",
    chain_callable=True,
    id_projection="playlist_id",
    effects=["playlist:update"],
    event="playlist.renamed",
    data_model=RenamePlaylistRecord,
    description="Rename an existing playlist. Accepts playlist_id (use get_playlists to find it if you only have the name) and the new name.",
)
async def fn_rename_playlist(ctx, params: RenamePlaylistParams) -> ActionResult:
    """Rename a playlist via PUT /playlists/{id}."""
    try:
        resp, err = await _spotify_call(
            ctx, "put", f"{SP_API_BASE}/playlists/{params.playlist_id}",
            json={"name": params.name},
        )
        if err:
            return err
        if not resp.ok and resp.status_code != 200:
            return _spotify_err(resp)
        return ActionResult.success(
            data={"playlist_id": params.playlist_id, "name": params.name},
            summary=f"Playlist renamed to '{params.name}'",
            refresh_panels=["spotify"],
        )
    except Exception as e:
        log.error("rename_playlist failed: %s", e)
        return ActionResult.error(f"Failed to rename playlist: {str(e)}", retryable=False)


@chat.function(
    "delete_playlist",
    action_type="write",
    chain_callable=True,
    id_projection="playlist_id",
    effects=["playlist:delete"],
    event="playlist.deleted",
    data_model=DeletePlaylistRecord,
    description="Delete (unfollow) a playlist from the user's library by playlist_id. Use get_playlists first to find the playlist_id if you only have the name.",
)
async def fn_delete_playlist(ctx, params: DeletePlaylistParams) -> ActionResult:
    """Delete a playlist by unfollowing it via Spotify API."""
    try:
        resp, err = await _spotify_call(
            ctx, "delete", f"{SP_API_BASE}/playlists/{params.playlist_id}/followers",
        )
        if err:
            return err
        if not resp.ok and resp.status_code != 200:
            return _spotify_err(resp)
        return ActionResult.success(
            data={"playlist_id": params.playlist_id, "deleted": True},
            summary="Playlist deleted",
            refresh_panels=["spotify"],
        )
    except Exception as e:
        log.error("delete_playlist failed: %s", e)
        return ActionResult.error(f"Failed to delete playlist: {str(e)}", retryable=False)


@chat.function(
    "add_tracks_to_playlist",
    action_type="write",
    chain_callable=True,
    id_projection="playlist_id",
    effects=["playlist:add_track"],
    event="track.added_to_playlist",
    data_model=BulkAddTracksRecord,
    description="Add multiple tracks to a playlist in one operation. Pass a list of track_ids. Use this after get_artist_top_tracks, get_album_tracks, or search_tracks to bulk-add results to a playlist.",
)
async def fn_add_tracks_to_playlist(ctx, params: AddTracksToPlaylistParams) -> ActionResult:
    """Add a list of tracks to a Spotify playlist in one API call."""
    try:
        if not params.track_ids:
            return ActionResult.error("No track IDs provided.", retryable=False)
        uris = [to_spotify_uri(tid) for tid in params.track_ids[:100]]
        resp, err = await _spotify_call(
            ctx, "post", f"{SP_API_BASE}/playlists/{params.playlist_id}/items",
            json={"uris": uris},
        )
        if err:
            return err
        if not resp.ok:
            return _spotify_err(resp)
        return ActionResult.success(
            data={"playlist_id": params.playlist_id, "tracks_added": len(uris)},
            summary=f"Added {len(uris)} track(s) to playlist",
        )
    except Exception as e:
        log.error("add_tracks_to_playlist failed: %s", e)
        return ActionResult.error(f"Failed to add tracks: {str(e)}", retryable=False)
