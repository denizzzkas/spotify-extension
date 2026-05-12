"""Spotify playback handlers."""
from __future__ import annotations

import logging

from pydantic import BaseModel, Field

from imperal_sdk import ActionResult

from app import (
    chat, SP_API_BASE, NowPlayingModel, QueueModel,
    _require_auth, _refresh_access_token, _spotify_error,
)
from utils import format_track

log = logging.getLogger("spotify.playback")


# ── Param models ──────────────────────────────────────────────────────────────

class PlayTrackParams(BaseModel):
    track_id: str = Field(..., description="Spotify track ID or track name/artist to search for and play")


class PlayPlaylistParams(BaseModel):
    playlist_id: str = Field(..., description="Spotify playlist ID to play")


# ─── Playback handlers ────────────────────────────────────────────────────── #

@chat.function(
    "play_track",
    action_type="write",
    chain_callable=True,
    id_projection="track_id",
    effects=["playback:start"],
    event="spotify-extension.track.played",
    description="Get track info and trigger playback. Returns track metadata with preview URL.",
)
async def fn_play_track(ctx, params: PlayTrackParams) -> ActionResult:
    token = await _require_auth(ctx)
    if isinstance(token, ActionResult):
        return token

    try:
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        track_id = params.track_id

        # If track_id looks like a Spotify ID (starts with number), use it directly
        # Otherwise, search for the track by name/artist
        if not track_id.startswith(("spotify:", "http")):
            search_resp = await ctx.api.get(
                f"{SP_API_BASE}/search",
                headers=headers,
                params={"q": track_id, "type": "track", "limit": 1},
            )

            if search_resp.status_code == 401:
                token = await _refresh_access_token(ctx)
                if not token:
                    return ActionResult.error("Spotify token expired. Please reconnect via connect_spotify().")
                headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
                search_resp = await ctx.api.get(
                    f"{SP_API_BASE}/search",
                    headers=headers,
                    params={"q": track_id, "type": "track", "limit": 1},
                )

            if search_resp.ok:
                tracks = search_resp.json().get("tracks", {}).get("items", [])
                if tracks:
                    track_id = tracks[0]["id"]
                else:
                    return ActionResult.error(f"No tracks found matching '{params.track_id}'.", retryable=False)
            else:
                return ActionResult.error(_spotify_error(search_resp.status_code), retryable=False)

        resp = await ctx.api.get(
            f"{SP_API_BASE}/tracks/{track_id}",
            headers=headers,
        )

        if resp.status_code == 401:
            token = await _refresh_access_token(ctx)
            if not token:
                return ActionResult.error("Spotify token expired. Please reconnect via connect_spotify().")
            headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
            resp = await ctx.api.get(
                f"{SP_API_BASE}/tracks/{track_id}",
                headers=headers,
            )

        if not resp.ok:
            return ActionResult.error(_spotify_error(resp.status_code), retryable=False)

        track_data = format_track(resp.json())
        await ctx.cache.set(
            key="now_playing",
            value=NowPlayingModel(**track_data, is_playing=True),
            ttl_seconds=90,
        )

        return ActionResult.success(
            data={
                "track_id": track_id,
                "track": track_data,
                "preview_url": track_data["preview_url"],
            },
            summary=f"▶ {track_data['artist']} — {track_data['title']}",
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
    event="spotify-extension.playlist.played",
    description="Get playlist tracks and trigger playback. Returns list of tracks in the playlist.",
)
async def fn_play_playlist(ctx, params: PlayPlaylistParams) -> ActionResult:
    token = await _require_auth(ctx)
    if isinstance(token, ActionResult):
        return token

    try:
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

        resp = await ctx.api.get(
            f"{SP_API_BASE}/playlists/{params.playlist_id}/tracks",
            headers=headers,
        )

        if resp.status_code == 401:
            token = await _refresh_access_token(ctx)
            if not token:
                return ActionResult.error("Spotify token expired. Please reconnect via connect_spotify().")
            headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
            resp = await ctx.api.get(
                f"{SP_API_BASE}/playlists/{params.playlist_id}/tracks",
                headers=headers,
            )

        if not resp.ok:
            return ActionResult.error(_spotify_error(resp.status_code), retryable=(resp.status_code == 429))

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
