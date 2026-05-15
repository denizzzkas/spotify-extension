"""Spotify extension — Extension setup, lifecycle, and cache models."""
from __future__ import annotations

import logging

from pydantic import BaseModel

from imperal_sdk import Extension
from imperal_sdk.chat import ChatExtension
from imperal_sdk.types.health import HealthStatus

from spotify_config import (
    SP_API_BASE, SP_AUTH_URL, SP_TOKEN_URL, SP_SCOPES,
    CRED_COLLECTION, OAUTH_STATE_COLLECTION, DEMO_PLAYER_STATE, DEMO_PANEL_STATE,
    DEFAULT_SEARCH_LIMIT, DEFAULT_HISTORY_LIMIT, DEFAULT_LIKES_LIMIT, MAX_LIMIT,
)
from app_helpers import (
    _get_access_token, _get_stored_creds, _save_token, _refresh_access_token,
    _clear_all_credentials, _require_user_id, _require_auth, _get_auth_headers,
    _spotify_error,
)

log = logging.getLogger("spotify")

# ─── Extension ────────────────────────────────────────────────────────────── #

ext = Extension(
    "spotify-extension",
    display_name="Spotify",
    description="Full access to your Spotify music library. Search tracks, manage playlists, save songs, view play history, and more.",
    icon="icon.svg",
    version="2.0.0",
    capabilities=[],
    actions_explicit=True,
    system=False,
    config_defaults={},
)

ext.secret(
    name="spotify_client_id",
    description="Spotify OAuth Client ID from developer.spotify.com",
    required=True,
    write_mode="user",
    max_bytes=256,
)(lambda: None)

ext.secret(
    name="spotify_client_secret",
    description="Spotify OAuth Client Secret from developer.spotify.com",
    required=True,
    write_mode="user",
    max_bytes=512,
)(lambda: None)

ext.secret(
    name="genius_access_token",
    description="Genius API access token for lyrics lookup (optional)",
    required=False,
    write_mode="user",
    max_bytes=256,
)(lambda: None)

# ─── Cache models ─────────────────────────────────────────────────────────── #

@ext.cache_model("now_playing")
class NowPlayingModel(BaseModel):
    id: str = ""
    title: str = ""
    artist: str = ""
    url: str = ""
    duration: str = ""
    duration_ms: int = 0
    popularity: int = 0
    preview_url: str = ""
    album: str = ""
    album_art: str = ""
    is_playing: bool = False

@ext.cache_model("search")
class SearchModel(BaseModel):
    query: str = ""
    tracks: list[dict] = []

@ext.cache_model("detail")
class DetailModel(BaseModel):
    type: str = ""
    title: str = ""
    tracks: list[dict] = []
    profile: dict = {}

@ext.cache_model("playlists")
class PlaylistsModel(BaseModel):
    items: list[dict] = []

@ext.cache_model("queue")
class QueueModel(BaseModel):
    playlist_id: str = ""
    playlist_name: str = ""
    tracks: list[dict] = []
    index: int = 0

@ext.cache_model("demo_state")
class DemoStateModel(BaseModel):
    track_index: int = 0
    is_playing: bool = True
    shuffle: bool = False

# ─── ChatExtension ────────────────────────────────────────────────────────── #

chat = ChatExtension(
    ext,
    tool_name="spotify",
    description="Full access to your Spotify music library. Search tracks, manage playlists, save songs, view play history, and more.",
)

# ─── Emitted events ───────────────────────────────────────────────────────── #

@ext.emits("spotify-extension.connected")
@ext.emits("spotify-extension.disconnected")
@ext.emits("spotify-extension.track.liked")
@ext.emits("spotify-extension.track.unliked")
@ext.emits("spotify-extension.track.played")
@ext.emits("spotify-extension.track.added_to_playlist")
@ext.emits("spotify-extension.track.removed_from_playlist")
@ext.emits("spotify-extension.playlist.created")
@ext.emits("spotify-extension.playlist.played")
@ext.emits("spotify-extension.playback.paused")
@ext.emits("spotify-extension.playback.resumed")
@ext.emits("spotify-extension.playback.next")
@ext.emits("spotify-extension.playback.previous")
@ext.emits("spotify-extension.open_demo_playlist")
@ext.emits("spotify-extension.demo_play_track")
@ext.emits("spotify-extension.demo_next_track")
@ext.emits("spotify-extension.demo_prev_track")
@ext.emits("spotify-extension.demo_pause")
@ext.emits("spotify-extension.demo_shuffle")
async def _declare_events() -> None:
    pass

# ─── Lifecycle ────────────────────────────────────────────────────────────── #

@ext.health_check
async def health(ctx) -> HealthStatus:
    try:
        client_id = ctx.config.get("spotify_client_id")
        if not client_id:
            return HealthStatus.degraded("Spotify credentials not configured")

        token = await _get_access_token(ctx)
        connected = token is not None
        return HealthStatus.ok({"connected": connected})
    except Exception as exc:
        log.error("health check failed: %s", exc)
        return HealthStatus.degraded(str(exc))

@ext.on_install
async def on_install(ctx) -> None:
    user_id = ctx.user.imperal_id if hasattr(ctx, "user") and ctx.user else "system"
    log.info("Spotify extension installed for user %s", user_id)

@ext.on_uninstall
async def on_uninstall(ctx) -> None:
    try:
        await _clear_all_credentials(ctx)
    except Exception as e:
        log.error("cleanup on uninstall failed: %s", e)
