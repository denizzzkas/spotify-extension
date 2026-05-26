"""Spotify playback handlers."""
from __future__ import annotations

import logging
import re

from pydantic import BaseModel, Field

from imperal_sdk import ActionResult

from app import chat, NowPlayingModel, QueueModel
from return_models import PlayTrackRecord, PlaylistPlayRecord, AlbumPlayRecord
from spotify_config import SP_API_BASE
from app_helpers import _spotify_call, _spotify_err, _require_auth, _refresh_access_token, _spotify_error
from utils import format_track

log = logging.getLogger("spotify.playback")


class PlayTrackParams(BaseModel):
    track_id: str = Field(..., description="Spotify track ID or track name/artist to search for and play")
    playlist_id: str = Field("", description="Optional playlist ID — if provided, plays track within playlist context so next/prev work through the playlist")


class PlayPlaylistParams(BaseModel):
    playlist_id: str = Field(..., description="Spotify playlist ID to play")
    playlist_name: str = Field("", description="Optional playlist name for display")


class PlayAlbumParams(BaseModel):
    album_name: str = Field(..., description="Album name to search for and play")
    artist_name: str = Field("", description="Artist name to narrow search (optional)")


@chat.function(
    "play_track",
    action_type="write",
    chain_callable=True,
    id_projection="track_id",
    effects=["playback:start"],
    event="track.played",
    data_model=PlayTrackRecord,
    description="Play a track on the user's active Spotify device. Pass a track ID or name/artist to search.",
)
async def fn_play_track(ctx, params: PlayTrackParams) -> ActionResult:
    """Play a track on the user's active Spotify device."""
    token = await _require_auth(ctx)
    if isinstance(token, ActionResult):
        return token

    try:
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        track_id = params.track_id

        # Search by name only if not a raw Spotify ID or URI
        _is_spotify_id = bool(re.match(r'^[A-Za-z0-9]{22}$', track_id))
        if not track_id.startswith(("spotify:", "http")) and not _is_spotify_id:
            search_resp, err = await _spotify_call(
                ctx, "get", f"{SP_API_BASE}/search",
                params={"q": track_id, "type": "track", "limit": 1},
            )
            if err:
                return err
            if not search_resp.ok:
                return _spotify_err(search_resp)
            items = search_resp.json().get("tracks", {}).get("items", [])
            if not items:
                return ActionResult.error(f"No tracks found matching '{params.track_id}'.", retryable=False)
            track_id = items[0]["id"]

        # Fetch track metadata
        track_resp, err = await _spotify_call(ctx, "get", f"{SP_API_BASE}/tracks/{track_id}")
        if err:
            return err
        if not track_resp.ok:
            return _spotify_err(track_resp)

        track_data = format_track(track_resp.json())
        await ctx.cache.set(
            key="now_playing",
            value=NowPlayingModel(**track_data, is_playing=True),
            ttl_seconds=90,
        )

        # Try playback via Spotify Connect — prefer the in-browser "Imperal Spotify" device
        played_full = False
        try:
            devices_resp, _ = await _spotify_call(ctx, "get", f"{SP_API_BASE}/me/player/devices")
            if devices_resp and devices_resp.ok:
                devices = devices_resp.json().get("devices", [])
                active = next((d for d in devices if d.get("name") == "Imperal Spotify"), None)
                if not active:
                    active = next((d for d in devices if not d.get("is_restricted")), None)
                if active:
                    if params.playlist_id:
                        play_body = {
                            "context_uri": f"spotify:playlist:{params.playlist_id}",
                            "offset": {"uri": f"spotify:track:{track_id}"},
                        }
                    else:
                        play_body = {"uris": [f"spotify:track:{track_id}"]}
                    play_resp, _ = await _spotify_call(
                        ctx, "put", f"{SP_API_BASE}/me/player/play",
                        params={"device_id": active["id"]},
                        json=play_body,
                    )
                    played_full = play_resp is not None and (play_resp.ok or play_resp.status_code == 204)
        except Exception as e:
            log.warning("Spotify Connect playback attempt failed: %s", e)

        summary = f"▶ {track_data['artist']} — {track_data['title']}"
        if not played_full:
            summary += " (preview only — open Spotify app on any device to enable full playback)"

        return ActionResult.success(
            data={
                "track_id": track_id,
                "track": track_data,
                "full_playback": played_full,
            },
            summary=summary,
            refresh_panels=["spotify"],
        )
    except Exception as e:
        log.error("play_track failed: %s", e)
        return ActionResult.error(f"Failed to get track: {str(e)}", retryable=True)


@chat.function(
    "play_playlist",
    action_type="write",
    chain_callable=True,
    id_projection="playlist_id",
    effects=["playback:start"],
    event="playlist.played",
    data_model=PlaylistPlayRecord,
    description="Get playlist tracks and trigger playback. Returns list of tracks in the playlist.",
)
async def fn_play_playlist(ctx, params: PlayPlaylistParams) -> ActionResult:
    """Get playlist tracks and trigger playback. Returns list of tracks in the playlist."""
    try:
        resp, err = await _spotify_call(ctx, "get", f"{SP_API_BASE}/playlists/{params.playlist_id}/items",
                                        params={"limit": 50})
        if err:
            return err
        if not resp.ok:
            return _spotify_err(resp)

        raw_list = resp.json().get("items") or []
        tracks = [
            format_track(item.get("track") or item.get("item"))
            for item in raw_list
            if item.get("track") or item.get("item")
        ]

        if not tracks:
            return ActionResult.error("Playlist is empty.", retryable=False)

        display_name = params.playlist_name or params.playlist_id
        await ctx.cache.set(
            key="queue",
            value=QueueModel(
                playlist_id=params.playlist_id,
                playlist_name=display_name,
                tracks=tracks[:30],
                index=0,
            ),
            ttl_seconds=300,
        )
        await ctx.cache.set(
            key="now_playing",
            value=NowPlayingModel(**tracks[0], is_playing=True),
            ttl_seconds=90,
        )

        # Start playback via Spotify Connect
        played_full = False
        try:
            devices_resp, _ = await _spotify_call(ctx, "get", f"{SP_API_BASE}/me/player/devices")
            if devices_resp and devices_resp.ok:
                devices = devices_resp.json().get("devices", [])
                active = next((d for d in devices if d.get("name") == "Imperal Spotify"), None)
                if not active:
                    active = next((d for d in devices if not d.get("is_restricted")), None)
                if active:
                    play_resp, _ = await _spotify_call(
                        ctx, "put", f"{SP_API_BASE}/me/player/play",
                        params={"device_id": active["id"]},
                        json={"context_uri": f"spotify:playlist:{params.playlist_id}"},
                    )
                    played_full = play_resp is not None and (play_resp.ok or play_resp.status_code == 204)
        except Exception as e:
            log.warning("Spotify Connect playlist playback failed: %s", e)

        summary = f"▶ Playing '{display_name}' — {len(tracks)} tracks"
        if not played_full:
            summary += " (open Spotify on any device to enable full playback)"

        return ActionResult.success(
            data={"playlist_id": params.playlist_id, "tracks": tracks, "count": len(tracks)},
            summary=summary,
            refresh_panels=["spotify"],
        )
    except Exception as e:
        log.error("play_playlist failed: %s", e)
        return ActionResult.error(f"Failed to load playlist: {str(e)}", retryable=True)


@chat.function(
    "play_album",
    action_type="write",
    chain_callable=True,
    data_model=AlbumPlayRecord,
    description="Search for an album by name and play it on the active Spotify device. Use this when the user wants to play a specific album.",
    event="spotify.album.played",
    effects=["playback:start"],
)
async def fn_play_album(ctx, params: PlayAlbumParams) -> ActionResult:
    """Search for an album and start playback."""
    try:
        auth_err = await _require_auth(ctx)
        if auth_err:
            return auth_err

        query = params.album_name
        if params.artist_name:
            query = f"{params.album_name} {params.artist_name}"

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
        album_name = album["name"]
        artist = ", ".join(a["name"] for a in album.get("artists", []))

        devices_resp, _ = await _spotify_call(ctx, "get", f"{SP_API_BASE}/me/player/devices")
        device_id = None
        if devices_resp and devices_resp.ok:
            devices = devices_resp.json().get("devices", [])
            active = next((d for d in devices if d.get("name") == "Imperal Spotify"), None)
            if not active:
                active = next((d for d in devices if not d.get("is_restricted")), None)
            if active:
                device_id = active["id"]

        play_body = {"context_uri": f"spotify:album:{album_id}"}
        play_url = f"{SP_API_BASE}/me/player/play"
        if device_id:
            play_url += f"?device_id={device_id}"

        play_resp, err = await _spotify_call(ctx, "put", play_url, json=play_body)
        if err:
            return err

        return ActionResult.success(
            data={"album_id": album_id, "album_name": album_name, "artist": artist},
            summary=f"▶ Playing album '{album_name}' by {artist}",
            refresh_panels=["spotify"],
        )
    except Exception as e:
        log.error("play_album failed: %s", e)
        return ActionResult.error(f"Failed to play album: {str(e)}", retryable=True)
