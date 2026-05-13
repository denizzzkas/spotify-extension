"""Spotify OAuth 2.0 authentication handlers."""
from __future__ import annotations

import base64
import logging
import uuid
from datetime import datetime, timezone

from pydantic import BaseModel

from imperal_sdk import ActionResult

from app import ext, chat
from spotify_config import (
    SP_AUTH_URL, SP_TOKEN_URL, SP_SCOPES,
    OAUTH_STATE_COLLECTION, CRED_COLLECTION,
)
from app_helpers import _get_access_token, _save_token, _require_user_id

log = logging.getLogger("spotify.auth")

# ─── Param models ─────────────────────────────────────────────────────────── #

class ConnectSpotifyParams(BaseModel):
    pass

class DisconnectSpotifyParams(BaseModel):
    pass

class CheckConnectionParams(BaseModel):
    pass

# ─── Auth handlers ────────────────────────────────────────────────────────── #

@chat.function(
    "connect_spotify",
    action_type="write",
    chain_callable=True,
    effects=["auth:connect"],
    event="spotify-extension.connected",
    description="Connect your Spotify account via OAuth 2.0. Returns an authorisation URL to visit.",
)
async def fn_connect_spotify(ctx, params: ConnectSpotifyParams) -> ActionResult:
    user_id = await _require_user_id(ctx)
    if isinstance(user_id, ActionResult):
        return user_id

    try:
        client_id = await ctx.secrets.get("spotify_client_id")
        if not client_id:
            return ActionResult.error(
                "Spotify client_id not configured. Set it in extension settings."
            )

        state = str(uuid.uuid4())
        await ctx.store.create(OAUTH_STATE_COLLECTION, {
            "user_id": user_id,
            "state": state,
            "created_at": datetime.now(timezone.utc).isoformat(),
        })

        import urllib.parse
        redirect_uri = ctx.webhook_url("/callback")
        auth_url = SP_AUTH_URL + "?" + urllib.parse.urlencode({
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": SP_SCOPES,
            "state": state,
        })

        return ActionResult.success(
            data={"auth_url": auth_url},
            summary="Open the URL in your browser to authorise Spotify access",
        )
    except Exception as e:
        log.error("connect_spotify failed: %s", e)
        return ActionResult.error(f"Connection failed: {str(e)}")


@chat.function(
    "disconnect_spotify",
    action_type="write",
    chain_callable=True,
    effects=["auth:disconnect"],
    event="spotify-extension.disconnected",
    description="Disconnect your Spotify account and remove all stored credentials.",
)
async def fn_disconnect_spotify(ctx, params: DisconnectSpotifyParams) -> ActionResult:
    user_id = await _require_user_id(ctx)
    if isinstance(user_id, ActionResult):
        return user_id

    try:
        page = await ctx.store.query(CRED_COLLECTION, where={"user_id": user_id})
        if not page.data:
            return ActionResult.success(data={"disconnected": False}, summary="Spotify was not connected")

        for doc in page.data:
            await ctx.store.delete(CRED_COLLECTION, doc.id)

        return ActionResult.success(data={"disconnected": True}, summary="Spotify account disconnected")
    except Exception as e:
        log.error("disconnect_spotify failed: %s", e)
        return ActionResult.error(f"Disconnect failed: {str(e)}")


@chat.function(
    "check_spotify_connection",
    action_type="read",
    description="Check if you are connected to Spotify and get your profile info.",
)
async def fn_check_connection(ctx, params: CheckConnectionParams) -> ActionResult:
    user_id = await _require_user_id(ctx)
    if isinstance(user_id, ActionResult):
        return user_id

    try:
        token = await _get_access_token(ctx)
        if not token:
            return ActionResult.success(
                data={"connected": False},
                summary="Not connected to Spotify",
            )
        return ActionResult.success(
            data={"connected": True, "token_available": True},
            summary="Connected to Spotify",
        )
    except Exception as e:
        log.error("check_connection failed: %s", e)
        return ActionResult.error(f"Status check failed: {str(e)}")


# ─── OAuth webhook callback ────────────────────────────────────────────────── #

@ext.webhook("/callback", method="GET")
async def oauth_callback(ctx, headers, body, query_params) -> dict:
    from imperal_sdk import WebhookResponse

    try:
        error = query_params.get("error", "")
        code = query_params.get("code", "")
        state = query_params.get("state", "")

        if error:
            return WebhookResponse.error(f"Spotify authorisation denied: {error}", 400)
        if not code:
            return WebhookResponse.error("Missing authorisation code", 400)
        if not state:
            return WebhookResponse.error("Missing state parameter", 400)

        # Look up which user started this OAuth flow
        page = await ctx.store.query(OAUTH_STATE_COLLECTION, where={"state": state})
        if not page.data:
            return WebhookResponse.error("Invalid or expired state — please try connect_spotify() again.", 400)

        user_id = page.data[0].data.get("user_id")
        await ctx.store.delete(OAUTH_STATE_COLLECTION, page.data[0].id)

        # Get user-scoped context to access secrets and store tokens
        user_ctx = ctx.as_user(user_id)

        client_id = await user_ctx.secrets.get("spotify_client_id")
        client_secret = await user_ctx.secrets.get("spotify_client_secret")
        if not client_id or not client_secret:
            return WebhookResponse.error("Spotify credentials not configured", 500)

        credentials = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
        redirect_uri = user_ctx.webhook_url("/callback")

        resp = await user_ctx.http.post(
            SP_TOKEN_URL,
            headers={
                "Authorization": f"Basic {credentials}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": redirect_uri,
            },
        )

        if not resp.ok:
            log.error("oauth_callback token exchange failed: %s", resp.status_code)
            return WebhookResponse.error(f"Token exchange failed (HTTP {resp.status_code}).", 500)

        token_data = resp.json()
        await _save_token(user_ctx, user_id, token_data)

        return WebhookResponse.ok({"connected": True, "message": "Spotify connected. You can close this window."})
    except Exception as e:
        log.error("oauth_callback failed: %s", e)
        return WebhookResponse.error(f"Callback failed: {str(e)}", 500)
