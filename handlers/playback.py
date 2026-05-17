"""Spotify playback handlers."""
from __future__ import annotations

import logging
import re

from pydantic import BaseModel, Field

from imperal_sdk import ActionResult

from app import chat, NowPlayingModel, QueueModel
from return_models import PlayTrackRecord, PlaylistPlayRecord
from spotify_config import SP_API_BASE
from app_helpers import _spotify_call, _spotify_err, _require_auth, _refresh_access_token, _spotify_error
from utils import format_track

log = logging.getLogger("spotify.playback")


class PlayTrackParams(BaseModel):
    track_id: str = Field(..., description="Spotify track ID or track name/artist to search for and play")


class PlayPlaylistParams(BaseModel):
    playlist_id: str = Field(..., description="Spotify playlist ID to play")


@chat.function(
    "play_track",
    action_type="write",
    chain_callable=True,
    id_projection="track_id",
    effects=["playback:start"],
    event="track.played",
    data_model=PlayTrackRecord,
    description="Get track info and trigger playback. Returns track metadata with preview URL.",
)
async def fn_play_track(ctx, params: PlayTrackParams) -> ActionResult:
    """Get track info and trigger playback. Returns track metadata with preview URL."""
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
                    play_resp, _ = await _spotify_call(
                        ctx, "put", f"{SP_API_BASE}/me/player/play",
                        params={"device_id": active["id"]},
                        json={"uris": [f"spotify:track:{track_id}"]},
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
                "preview_url": track_data["preview_url"],
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
        resp, err = await _spotify_call(ctx, "get", f"{SP_API_BASE}/playlists/{params.playlist_id}/tracks")
        if err:
            return err
        if not resp.ok:
            return _spotify_err(resp)

        raw_list = resp.json().get("items") or []
        tracks = [format_track(item["track"]) for item in raw_list if item.get("track")]

        if not tracks:
            return ActionResult.error("Playlist is empty.", retryable=False)

        await ctx.cache.set(
            key="queue",
            value=QueueModel(
                playlist_id=params.playlist_id,
                playlist_name=params.playlist_id,
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

        return ActionResult.success(
            data={"playlist_id": params.playlist_id, "tracks": tracks, "count": len(tracks)},
            summary=f"▶ Playing playlist — {len(tracks)} tracks",
            refresh_panels=["spotify"],
        )
    except Exception as e:
        log.error("play_playlist failed: %s", e)
        return ActionResult.error(f"Failed to load playlist: {str(e)}", retryable=True)
