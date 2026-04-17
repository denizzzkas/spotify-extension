"""Spotify extension — Extension, ChatExtension, lifecycle and OAuth."""
from pydantic import BaseModel

from imperal_sdk import Extension, ChatExtension, ActionResult, WebhookResponse
from imperal_sdk.types.health import HealthStatus

from spotify_config import CRED_COLLECTION, OAUTH_STATE_COLLECTION, SP_REDIRECT_URI
from handlers.auth import (
    get_stored_creds, get_access_token, save_token, save_token_for_user, clear_token,
    build_auth_url, create_oauth_state, consume_oauth_state, exchange_code_for_token,
)
from pathlib import Path as _Path
from handlers import chat_registry

SYSTEM_PROMPT = (_Path(__file__).parent / "system_prompt.txt").read_text()

ext = Extension(
    "spotify-extension",
    version="1.0.0",
    capabilities=[],
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
    system_prompt=SYSTEM_PROMPT,
    model="claude-haiku-4-5-20251001",
)

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
    event="spotify.connected",
)
async def fn_connect_spotify(ctx, params: ConnectSpotifyParams) -> ActionResult:
    """Generate a Spotify OAuth 2.0 authorisation URL for the current user."""
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
    event="spotify.disconnected",
)
async def fn_disconnect_spotify(ctx, params: DisconnectSpotifyParams) -> ActionResult:
    """Remove all stored Spotify credentials for the current user."""
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
