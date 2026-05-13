"""Spotify playlist handlers."""
from __future__ import annotations

import logging
from typing import List

from pydantic import BaseModel, Field

from imperal_sdk import ActionResult

from app import chat
from spotify_config import SP_API_BASE, MAX_LIMIT
from app_helpers import _require_auth, _refresh_access_token, _spotify_error
from utils import format_track, format_playlist, to_spotify_uri

log = logging.getLogger("spotify.playlists")

# ─── Param models ─────────────────────────────────────────────────────────── #

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

# ─── Helpers ──────────────────────────────────────────────────────────────── #

async def _get_my_spotify_id(ctx, headers: dict) -> str | None:
    try:
        resp = await ctx.http.get(f"{SP_API_BASE}/me", headers=headers)
        if resp.ok:
            return resp.json().get("id")
    except Exception as e:
        log.error("_get_my_spotify_id failed: %s", e)
    return None

# ─── Playlist handlers ────────────────────────────────────────────────────── #

@chat.function(
    "get_playlists",
    action_type="read",
    description="Get all playlists owned or followed by the authenticated user. Returns list of playlists with id, title, track_count, image_url.",
)
async def fn_get_playlists(ctx, params: GetPlaylistsParams) -> ActionResult:
    token = await _require_auth(ctx)
    if isinstance(token, ActionResult):
        return token

    try:
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        resp = await ctx.http.get(
            f"{SP_API_BASE}/me/playlists",
            headers=headers,
            params={"limit": 50},
        )

        if resp.status_code == 401:
            token = await _refresh_access_token(ctx)
            if not token:
                return ActionResult.error("Spotify token expired. Please reconnect via connect_spotify().")
            headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
            resp = await ctx.http.get(f"{SP_API_BASE}/me/playlists", headers=headers, params={"limit": 50})

        if not resp.ok:
            return ActionResult.error(_spotify_error(resp.status_code), retryable=(resp.status_code == 429))

        raw_list = resp.json().get("items") or []
        playlists = [format_playlist(p) for p in raw_list]

        return ActionResult.success(
            data={"playlists": playlists, "count": len(playlists)},
            summary=f"Found {len(playlists)} playlist(s)",
        )
    except Exception as e:
        log.error("get_playlists failed: %s", e)
        return ActionResult.error(f"Failed to get playlists: {str(e)}", retryable=True)

@chat.function(
    "get_playlist_tracks",
    action_type="read",
    description="Get all tracks in a specific Spotify playlist. Returns list of tracks with full details.",
)
async def fn_get_playlist_tracks(ctx, params: GetPlaylistTracksParams) -> ActionResult:
    token = await _require_auth(ctx)
    if isinstance(token, ActionResult):
        return token

    try:
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        resp = await ctx.http.get(
            f"{SP_API_BASE}/playlists/{params.playlist_id}/tracks",
            headers=headers,
        )

        if resp.status_code == 401:
            token = await _refresh_access_token(ctx)
            if not token:
                return ActionResult.error("Spotify token expired. Please reconnect via connect_spotify().")
            headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
            resp = await ctx.http.get(f"{SP_API_BASE}/playlists/{params.playlist_id}/tracks", headers=headers)

        if not resp.ok:
            return ActionResult.error(_spotify_error(resp.status_code), retryable=(resp.status_code == 429))

        raw_list = resp.json().get("items") or []
        tracks = [format_track(item["track"]) for item in raw_list if item.get("track")]

        return ActionResult.success(
            data={"tracks": tracks, "count": len(tracks), "playlist_id": params.playlist_id},
            summary=f"Retrieved {len(tracks)} track(s) from playlist",
        )
    except Exception as e:
        log.error("get_playlist_tracks failed: %s", e)
        return ActionResult.error(f"Failed to get playlist tracks: {str(e)}", retryable=True)

@chat.function(
    "create_playlist",
    action_type="write",
    chain_callable=True,
    id_projection="playlist_id",
    effects=["playlist:create"],
    event="spotify-extension.playlist.created",
    description="Create a new playlist on the user's Spotify account. Returns playlist_id and playlist details.",
)
async def fn_create_playlist(ctx, params: CreatePlaylistParams) -> ActionResult:
    token = await _require_auth(ctx)
    if isinstance(token, ActionResult):
        return token

    try:
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

        my_id = await _get_my_spotify_id(ctx, headers)
        if not my_id:
            return ActionResult.error("Could not get Spotify user ID. Please reconnect via connect_spotify().")

        resp = await ctx.http.post(
            f"{SP_API_BASE}/users/{my_id}/playlists",
            headers=headers,
            json={
                "name": params.name,
                "description": params.description,
                "public": params.is_public,
            },
        )

        if resp.status_code == 401:
            token = await _refresh_access_token(ctx)
            if not token:
                return ActionResult.error("Spotify token expired. Please reconnect via connect_spotify().")
            headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
            resp = await ctx.http.post(
                f"{SP_API_BASE}/users/{my_id}/playlists",
                headers=headers,
                json={"name": params.name, "description": params.description, "public": params.is_public},
            )

        if not resp.ok:
            return ActionResult.error(_spotify_error(resp.status_code), retryable=False)

        playlist_data = resp.json()
        playlist_id = playlist_data.get("id")

        if params.tracks:
            uris = [to_spotify_uri(tid) for tid in params.tracks]
            await ctx.http.post(
                f"{SP_API_BASE}/playlists/{playlist_id}/tracks",
                headers=headers,
                json={"uris": uris},
            )

        return ActionResult.success(
            data={
                "playlist_id": playlist_id,
                "name": params.name,
                "url": (playlist_data.get("external_urls") or {}).get("spotify", ""),
                "tracks_added": len(params.tracks),
            },
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
    event="spotify-extension.track.added_to_playlist",
    description="Add a track to an existing Spotify playlist. Returns updated playlist info.",
)
async def fn_add_track_to_playlist(ctx, params: AddTrackToPlaylistParams) -> ActionResult:
    token = await _require_auth(ctx)
    if isinstance(token, ActionResult):
        return token

    try:
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        uri = to_spotify_uri(params.track_id)

        resp = await ctx.http.post(
            f"{SP_API_BASE}/playlists/{params.playlist_id}/tracks",
            headers=headers,
            json={"uris": [uri]},
        )

        if resp.status_code == 401:
            token = await _refresh_access_token(ctx)
            if not token:
                return ActionResult.error("Spotify token expired. Please reconnect via connect_spotify().")
            headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
            resp = await ctx.http.post(
                f"{SP_API_BASE}/playlists/{params.playlist_id}/tracks",
                headers=headers,
                json={"uris": [uri]},
            )

        if not resp.ok:
            return ActionResult.error(_spotify_error(resp.status_code), retryable=False)

        return ActionResult.success(
            data={"playlist_id": params.playlist_id, "track_id": params.track_id, "added": True},
            summary=f"Track added to playlist",
        )
    except Exception as e:
        log.error("add_track_to_playlist failed: %s", e)
        return ActionResult.error(f"Failed to add track: {str(e)}", retryable=False)

@chat.function(
    "remove_track_from_playlist",
    action_type="write",
    chain_callable=True,
    id_projection="playlist_id",
    effects=["playlist:remove_track"],
    event="spotify-extension.track.removed_from_playlist",
    description="Remove a track from a Spotify playlist. Returns updated playlist info.",
)
async def fn_remove_track_from_playlist(ctx, params: RemoveTrackFromPlaylistParams) -> ActionResult:
    token = await _require_auth(ctx)
    if isinstance(token, ActionResult):
        return token

    try:
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        uri = to_spotify_uri(params.track_id)

        resp = await ctx.http.delete(
            f"{SP_API_BASE}/playlists/{params.playlist_id}/tracks",
            headers=headers,
            json={"tracks": [{"uri": uri}]},
        )

        if resp.status_code == 401:
            token = await _refresh_access_token(ctx)
            if not token:
                return ActionResult.error("Spotify token expired. Please reconnect via connect_spotify().")
            headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
            resp = await ctx.http.delete(
                f"{SP_API_BASE}/playlists/{params.playlist_id}/tracks",
                headers=headers,
                json={"tracks": [{"uri": uri}]},
            )

        if not resp.ok:
            return ActionResult.error(_spotify_error(resp.status_code), retryable=False)

        return ActionResult.success(
            data={"playlist_id": params.playlist_id, "track_id": params.track_id, "removed": True},
            summary=f"Track removed from playlist",
        )
    except Exception as e:
        log.error("remove_track_from_playlist failed: %s", e)
        return ActionResult.error(f"Failed to remove track: {str(e)}", retryable=False)
