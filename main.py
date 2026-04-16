"""Spotify extension for Imperal — full music library access via OAuth 2.0."""
from __future__ import annotations

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from pydantic import BaseModel

from imperal_sdk import Extension, ChatExtension, ActionResult, WebhookResponse
from imperal_sdk import ui
from imperal_sdk.types.health import HealthStatus

from spotify_config import CRED_COLLECTION, OAUTH_STATE_COLLECTION, SP_REDIRECT_URI
from handlers.auth import (
    get_stored_creds, get_access_token, save_token, save_token_for_user, clear_token,
    build_auth_url, create_oauth_state, consume_oauth_state, exchange_code_for_token,
)
from handlers import chat_registry


ext = Extension(
    "spotify-extension",
    version="1.0.0",
    capabilities=["inter-extension"],
    config_defaults={
        "spotify.client_id": "",
        "spotify.client_secret": "",
    },
)

chat = ChatExtension(
    ext,
    tool_name="spotify",
    description=(
        "Full access to your Spotify music library. "
        "Search tracks, manage playlists, save songs, view play history, and more."
    ),
)

# Register all chat functions
chat_registry.register(chat)


# ── Lifecycle ──────────────────────────────────────────────────────────────────

@ext.on_install
async def on_install(ctx):
    pass


@ext.on_uninstall
async def on_uninstall(ctx):
    await clear_token(ctx)
    state_page = await ctx.store.query(OAUTH_STATE_COLLECTION, where={"user_id": ctx.user.id})
    for doc in state_page.data:
        await ctx.store.delete(OAUTH_STATE_COLLECTION, doc.id)


@ext.health_check
async def health(ctx) -> HealthStatus:
    try:
        await ctx.store.count(CRED_COLLECTION)
        connected = (await get_access_token(ctx)) is not None
        return HealthStatus.ok({"connected": connected})
    except Exception as exc:
        return HealthStatus.degraded(str(exc))


# ── OAuth chat functions ───────────────────────────────────────────────────────

class ConnectSpotifyParams(BaseModel):
    """No parameters — generates the Spotify OAuth authorisation URL."""


class DisconnectSpotifyParams(BaseModel):
    """No parameters — removes stored Spotify credentials."""


@chat.function(
    "connect_spotify",
    description="Connect your Spotify account via OAuth 2.0. Returns an authorisation URL.",
    action_type="write",
)
async def fn_connect_spotify(ctx, params: ConnectSpotifyParams) -> ActionResult:
    client_id = ctx.config.get("spotify.client_id", "")
    if not client_id:
        return ActionResult.error(
            "spotify.client_id is not configured. Ask your administrator to add Spotify app credentials."
        )
    state = await create_oauth_state(ctx)
    auth_url = build_auth_url(client_id, SP_REDIRECT_URI, state)
    return ActionResult.success(
        data={"auth_url": auth_url},
        summary="Open the URL in your browser to authorise Spotify access",
    )


@chat.function(
    "disconnect_spotify",
    description="Disconnect your Spotify account and remove all stored credentials.",
    action_type="write",
)
async def fn_disconnect_spotify(ctx, params: DisconnectSpotifyParams) -> ActionResult:
    if (await get_stored_creds(ctx)) is None:
        return ActionResult.success(data={"disconnected": False}, summary="Spotify was not connected")
    await clear_token(ctx)
    return ActionResult.success(data={"disconnected": True}, summary="Spotify account disconnected")


# ── OAuth webhook ──────────────────────────────────────────────────────────────

@ext.webhook("/oauth/callback", method="GET")
async def oauth_callback(ctx, headers, body, query_params):
    error = query_params.get("error", "")
    code = query_params.get("code", "")
    state = query_params.get("state", "")
    if error:
        return WebhookResponse.error(f"Spotify authorisation denied: {error}", 400)
    if not code:
        return WebhookResponse.error("Missing authorisation code", 400)
    if not state:
        return WebhookResponse.error("Missing state parameter", 400)
    user_id = await consume_oauth_state(ctx, state)
    if user_id is None:
        return WebhookResponse.error("Invalid or expired state — please try connect_spotify() again.", 400)
    try:
        token_data = await exchange_code_for_token(ctx, code, SP_REDIRECT_URI)
    except ValueError as exc:
        return WebhookResponse.error(str(exc), 500)
    await save_token_for_user(ctx, user_id, token_data)
    return WebhookResponse.ok({"connected": True, "message": "Spotify connected. You can close this window."})


# ── UI panel ───────────────────────────────────────────────────────────────────

@ext.panel(
    "spotify", slot="left", title="Spotify", icon="Music",
    refresh="on_event:track.liked,track.unliked,playlist.created,track.added_to_playlist,track.removed_from_playlist",
)
async def panel_spotify(ctx, **kwargs):
    token = await get_access_token(ctx)
    if not token:
        return ui.Stack([
            ui.Header("Spotify", level=3),
            ui.Alert("Not connected. Click below to link your Spotify account.", variant="warning"),
            ui.Button("Connect Spotify", variant="primary", icon="Music",
                      on_click=ui.Send("Connect my Spotify account")),
        ], direction="v", gap=2)
    return ui.Stack([
        ui.Header("Spotify", level=3),
        ui.Alert("Connected", variant="success"),
        ui.Stack([
            ui.Button("Search Tracks", variant="secondary", size="sm",
                      on_click=ui.Send("Search Spotify tracks")),
            ui.Button("My Playlists", variant="secondary", size="sm",
                      on_click=ui.Send("Show my Spotify playlists")),
            ui.Button("Saved Tracks", variant="secondary", size="sm",
                      on_click=ui.Send("Show my saved tracks on Spotify")),
            ui.Button("Recent Tracks", variant="secondary", size="sm",
                      on_click=ui.Send("Show my recently played Spotify tracks")),
            ui.Button("My Profile", variant="secondary", size="sm",
                      on_click=ui.Send("Show my Spotify profile")),
        ], direction="v", gap=1),
        ui.Divider(),
        ui.Button("Disconnect", variant="danger", size="sm", icon="LogOut",
                  on_click=ui.Send("Disconnect Spotify"),
                  confirm="Disconnect your Spotify account and remove stored credentials?"),
    ], direction="v", gap=2)
