"""Spotify extension — Extension setup, lifecycle, and cache models."""
from __future__ import annotations

import logging
from pathlib import Path

from pydantic import BaseModel

from imperal_sdk import Extension
from imperal_sdk.chat import ChatExtension
from imperal_sdk.types.health import HealthStatus

from spotify_config import (
    SP_API_BASE, SP_AUTH_URL, SP_TOKEN_URL, SP_REDIRECT_URI, SP_SCOPES,
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

# ─── Secrets (SDK 4.2.2 EXT-SECRETS-V1) ────────────────────────────────────── #

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

SYSTEM_PROMPT = (Path(__file__).parent / "system_prompt.txt").read_text()

chat = ChatExtension(
    ext,
    tool_name="spotify",
    description="Full access to your Spotify music library. Search tracks, manage playlists, save songs, view play history, and more.",
    system_prompt=SYSTEM_PROMPT,
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
async def _declare_events() -> None:
    pass

# ─── Lifecycle ────────────────────────────────────────────────────────────── #

@ext.health_check
async def health(ctx) -> HealthStatus:
    try:
        client_id = await ctx.secrets.get("spotify_client_id")
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

# ─── Auth helpers (ctx-scoped, per-request) ────────────────────────────── #

async def _get_access_token(ctx) -> str | None:
    try:
        page = await ctx.store.query(CRED_COLLECTION, where={"user_id": ctx.user.imperal_id})
        if page.data:
            return page.data[0].data.get("access_token")
    except Exception as e:
        log.error("get_access_token failed: %s", e)
    return None

async def _get_stored_creds(ctx) -> dict | None:
    try:
        page = await ctx.store.query(CRED_COLLECTION, where={"user_id": ctx.user.imperal_id})
        return page.data[0].data if page.data else None
    except Exception as e:
        log.error("get_stored_creds failed: %s", e)
    return None

async def _save_token(ctx, user_id: str, token_data: dict) -> None:
    try:
        record = {
            "user_id": user_id,
            "access_token": token_data.get("access_token", ""),
            "refresh_token": token_data.get("refresh_token", ""),
            "scope": token_data.get("scope", ""),
            "token_type": token_data.get("token_type", "Bearer"),
        }
        page = await ctx.store.query(CRED_COLLECTION, where={"user_id": user_id})
        if page.data:
            await ctx.store.update(CRED_COLLECTION, page.data[0].id, record)
        else:
            await ctx.store.create(CRED_COLLECTION, record)
    except Exception as e:
        log.error("save_token failed: %s", e)

async def _refresh_access_token(ctx) -> str | None:
    try:
        creds = await _get_stored_creds(ctx)
        if not creds or not creds.get("refresh_token"):
            return None

        client_id = await ctx.secrets.get("spotify_client_id")
        client_secret = await ctx.secrets.get("spotify_client_secret")
        if not client_id or not client_secret:
            return None

        import base64
        credentials = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()

        resp = await ctx.api.post(
            SP_TOKEN_URL,
            headers={
                "Authorization": f"Basic {credentials}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            data={"grant_type": "refresh_token", "refresh_token": creds.get("refresh_token")},
        )

        if not resp.ok:
            return None

        new_token_data = resp.json()
        new_access = new_token_data.get("access_token")
        if new_access:
            updated = {**creds}
            updated["access_token"] = new_access
            if "refresh_token" in new_token_data:
                updated["refresh_token"] = new_token_data["refresh_token"]
            await _save_token(ctx, ctx.user.imperal_id, updated)
        return new_access
    except Exception as e:
        log.error("refresh_access_token failed: %s", e)
    return None

async def _clear_all_credentials(ctx) -> None:
    try:
        collections = [CRED_COLLECTION, OAUTH_STATE_COLLECTION, DEMO_PLAYER_STATE, DEMO_PANEL_STATE]
        for coll in collections:
            page = await ctx.store.query(coll, where={"user_id": ctx.user.imperal_id})
            for doc in page.data:
                await ctx.store.delete(coll, doc.id)
    except Exception as e:
        log.error("clear_all_credentials failed: %s", e)

async def _require_user_id(ctx) -> str | ActionResult:
    if not hasattr(ctx, "user") or not ctx.user:
        return ActionResult.error("No authenticated user on context.")
    return ctx.user.imperal_id

async def _require_auth(ctx) -> str | ActionResult:
    token = await _get_access_token(ctx)
    if not token:
        return ActionResult.error("Not connected to Spotify. Use connect_spotify() to authorise.")
    return token

async def _get_auth_headers(ctx) -> dict | None:
    token = await _get_access_token(ctx)
    if token:
        return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    return None

def _spotify_error(status_code: int) -> str:
    messages = {
        400: "Invalid request parameters.",
        401: "Not authorised — please reconnect via connect_spotify().",
        403: "You do not have permission. Some features require Spotify Premium.",
        404: "Resource not found on Spotify.",
        429: "Spotify rate limit reached. Please wait a moment and try again.",
        500: "Spotify server error. Please try again later.",
    }
    return messages.get(status_code, f"Unexpected Spotify error (HTTP {status_code}).")
