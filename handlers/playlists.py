"""Playlist management for the Spotify extension."""
from __future__ import annotations

from typing import List

from pydantic import BaseModel, Field

from imperal_sdk import ActionResult

from spotify_config import SP_API_BASE
from utils import format_track, format_playlist, to_spotify_uri, sp_error
from handlers.auth import get_auth_headers, get_auth_headers_refreshed


# ── Param models ──────────────────────────────────────────────────────────────

class GetPlaylistsParams(BaseModel):
    """No parameters — returns all playlists for the authenticated user."""


class GetPlaylistTracksParams(BaseModel):
    playlist_id: str = Field(..., description="Spotify playlist ID")


class CreatePlaylistParams(BaseModel):
    name: str = Field(..., description="Name of the new playlist")
    description: str = Field("", description="Optional playlist description")
    tracks: List[str] = Field(
        default_factory=list,
        description="Optional list of track IDs to add on creation",
    )
    is_public: bool = Field(False, description="Set to true to make the playlist public")


class AddTrackToPlaylistParams(BaseModel):
    playlist_id: str = Field(..., description="Spotify playlist ID")
    track_id: str = Field(..., description="Spotify track ID to add")


class RemoveTrackFromPlaylistParams(BaseModel):
    playlist_id: str = Field(..., description="Spotify playlist ID")
    track_id: str = Field(..., description="Spotify track ID to remove")


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _get_my_spotify_id(ctx, headers: dict) -> str | None:
    """Fetch the current user's Spotify user ID (needed for playlist creation)."""
    resp = await ctx.http.get(f"{SP_API_BASE}/me", headers=headers)
    if resp.ok:
        return resp.json().get("id")
    return None


# ── Functions ─────────────────────────────────────────────────────────────────

async def fn_get_playlists(ctx, params: GetPlaylistsParams) -> ActionResult:
    """Retrieve all playlists owned or followed by the authenticated user."""
    try:
        headers = await get_auth_headers(ctx)
    except ValueError as exc:
        return ActionResult.error(str(exc))

    resp = await ctx.http.get(
        f"{SP_API_BASE}/me/playlists",
        headers=headers,
        params={"limit": 50},
    )

    if resp.status_code == 401:
        try:
            headers = await get_auth_headers_refreshed(ctx)
        except ValueError as exc:
            return ActionResult.error(str(exc))
        resp = await ctx.http.get(f"{SP_API_BASE}/me/playlists", headers=headers, params={"limit": 50})

    if not resp.ok:
        return ActionResult.error(
            sp_error(resp.status_code),
            retryable=(resp.status_code == 429),
        )

    raw_list = (resp.json().get("items") or [])
    playlists = [format_playlist(p) for p in raw_list]

    return ActionResult.success(
        data={"playlists": playlists, "count": len(playlists)},
        summary=f"Found {len(playlists)} playlist(s)",
    )


async def fn_get_playlist_tracks(ctx, params: GetPlaylistTracksParams) -> ActionResult:
    """Retrieve all tracks in a specific playlist."""
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
        return ActionResult.error(
            sp_error(resp.status_code),
            retryable=(resp.status_code == 429),
        )

    raw_list = resp.json().get("items") or []
    # Spotify wraps each track under a "track" key
    tracks = [format_track(item["track"]) for item in raw_list if item.get("track")]

    return ActionResult.success(
        data={"tracks": tracks, "count": len(tracks), "playlist_id": params.playlist_id},
        summary=f"Found {len(tracks)} track(s) in playlist {params.playlist_id}",
    )


async def fn_create_playlist(ctx, params: CreatePlaylistParams) -> ActionResult:
    """Create a new playlist on the user's Spotify account."""
    try:
        headers = await get_auth_headers(ctx)
    except ValueError as exc:
        return ActionResult.error(str(exc))

    # Spotify requires the user's Spotify ID to create a playlist
    user_id = await _get_my_spotify_id(ctx, headers)
    if not user_id:
        return ActionResult.error("Could not retrieve your Spotify user ID.")

    resp = await ctx.http.post(
        f"{SP_API_BASE}/users/{user_id}/playlists",
        headers=headers,
        json={
            "name": params.name,
            "description": params.description,
            "public": params.is_public,
        },
    )

    if not resp.ok:
        return ActionResult.error(sp_error(resp.status_code), retryable=False)

    playlist = format_playlist(resp.json())

    # Add initial tracks if provided
    if params.tracks:
        uris = [to_spotify_uri(tid) for tid in params.tracks if tid]
        tracks_resp = await ctx.http.post(
            f"{SP_API_BASE}/playlists/{playlist['id']}/tracks",
            headers=headers,
            json={"uris": uris},
        )
        if not tracks_resp.ok:
            return ActionResult.success(
                data={"playlist": playlist, "tracks_added": False},
                summary=f"Playlist '{params.name}' created but tracks could not be added: {sp_error(tracks_resp.status_code)}",
                refresh_panels=["spotify"],
            )

    return ActionResult.success(
        data={"playlist": playlist, "tracks_added": bool(params.tracks)},
        summary=f"Playlist '{params.name}' created (ID: {playlist['id']})",
        refresh_panels=["spotify"],
    )


async def fn_add_track_to_playlist(ctx, params: AddTrackToPlaylistParams) -> ActionResult:
    """Add a track to an existing playlist."""
    try:
        headers = await get_auth_headers(ctx)
    except ValueError as exc:
        return ActionResult.error(str(exc))

    resp = await ctx.http.post(
        f"{SP_API_BASE}/playlists/{params.playlist_id}/tracks",
        headers=headers,
        json={"uris": [to_spotify_uri(params.track_id)]},
    )

    if not resp.ok:
        return ActionResult.error(sp_error(resp.status_code), retryable=False)

    return ActionResult.success(
        data={"playlist_id": params.playlist_id, "track_id": params.track_id, "added": True},
        summary=f"Track {params.track_id} added to playlist {params.playlist_id}",
        refresh_panels=["spotify"],
    )


async def fn_remove_track_from_playlist(ctx, params: RemoveTrackFromPlaylistParams) -> ActionResult:
    """Remove a track from a playlist."""
    try:
        headers = await get_auth_headers(ctx)
    except ValueError as exc:
        return ActionResult.error(str(exc))

    resp = await ctx.http.delete(
        f"{SP_API_BASE}/playlists/{params.playlist_id}/tracks",
        headers=headers,
        json={"tracks": [{"uri": to_spotify_uri(params.track_id)}]},
    )

    if not resp.ok:
        return ActionResult.error(sp_error(resp.status_code), retryable=False)

    return ActionResult.success(
        data={"playlist_id": params.playlist_id, "track_id": params.track_id, "removed": True},
        summary=f"Track {params.track_id} removed from playlist {params.playlist_id}",
        refresh_panels=["spotify"],
    )
