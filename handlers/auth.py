"""Spotify OAuth 2.0 authentication handlers."""
from __future__ import annotations

import base64
import logging
import uuid
from datetime import datetime, timezone

from pydantic import BaseModel

from imperal_sdk import ActionResult

from app import ext, chat
from return_models import SpotifyAuthRecord, SpotifyDisconnectRecord, SpotifyConnectionRecord
from spotify_config import (
    SP_AUTH_URL, SP_TOKEN_URL, SP_SCOPES,
    OAUTH_STATE_COLLECTION, CRED_COLLECTION,
)
from app_helpers import _get_access_token, _save_token_to_store, _require_user_id

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
    event="connected",
    data_model=SpotifyAuthRecord,
    description="Connect your Spotify account via OAuth 2.0. Returns an authorisation URL to visit.",
)
async def fn_connect_spotify(ctx, params: ConnectSpotifyParams) -> ActionResult:
    """Connect your Spotify account via OAuth 2.0. Returns an authorisation URL to visit."""
    user_id = await _require_user_id(ctx)
    if isinstance(user_id, ActionResult):
        return user_id

    try:
        client_id = await ctx.secrets.get("spotify_client_id")
        client_secret = await ctx.secrets.get("spotify_client_secret")
        if not client_id or not client_secret:
            return ActionResult.error(
                "Spotify credentials not configured. Set client_id and client_secret in extension settings."
            )

        state = str(uuid.uuid4())
        redirect_uri = ctx.webhook_url("callback")

        # Store OAuth state under __webhook__ user scope so the callback
        # (which runs as __webhook__ context) can query it directly via ctx.store.
        # SDK 4.2.16: ctx.as_user() requires __system__ context, not available in webhooks.
        from imperal_sdk.store.client import StoreClient
        webhook_store = StoreClient(
            gateway_url=ctx.store._gateway_url,
            service_token=ctx.store._auth_token,
            extension_id=ctx.store._extension_id,
            user_id="__webhook__",
            tenant_id=ctx.store._tenant_id,
        )
        await webhook_store.create(OAUTH_STATE_COLLECTION, {
            "user_id": user_id,
            "state": state,
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": redirect_uri,
            "created_at": datetime.now(timezone.utc).isoformat(),
        })

        import urllib.parse
        auth_url = SP_AUTH_URL + "?" + urllib.parse.urlencode({
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": SP_SCOPES,
            "state": state,
            "show_dialog": "true",
        })

        from imperal_sdk import ui
        return ActionResult.success(
            data={"auth_url": auth_url},
            summary="Click the link below to connect your Spotify account:",
            ui=ui.Link(label="Connect Spotify →", href=auth_url),
        )
    except Exception as e:
        log.error("connect_spotify failed: %s", e)
        return ActionResult.error(f"Connection failed: {str(e)}")


@chat.function(
    "disconnect_spotify",
    action_type="write",
    chain_callable=True,
    effects=["auth:disconnect"],
    event="disconnected",
    data_model=SpotifyDisconnectRecord,
    description="Disconnect your Spotify account and remove all stored credentials.",
)
async def fn_disconnect_spotify(ctx, params: DisconnectSpotifyParams) -> ActionResult:
    """Disconnect your Spotify account and remove all stored credentials."""
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
    data_model=SpotifyConnectionRecord,
    description="Check if you are connected to Spotify and get your profile info.",
)
async def fn_check_connection(ctx, params: CheckConnectionParams) -> ActionResult:
    """Check if you are connected to Spotify and get your profile info."""
    user_id = await _require_user_id(ctx)
    if isinstance(user_id, ActionResult):
        return user_id
    try:
        token = await _get_access_token(ctx)
        if not token:
            return ActionResult.success(data={"connected": False}, summary="Not connected to Spotify")
        page = await ctx.store.query(CRED_COLLECTION, where={"user_id": user_id})
        scope = page.data[0].data.get("scope", "NOT STORED") if page.data else "NO RECORD"
        return ActionResult.success(
            data={"connected": True, "token_scopes": scope},
            summary=f"Connected. Scopes: {scope}",
        )
    except Exception as e:
        log.error("check_connection failed: %s", e)
        return ActionResult.error(f"Status check failed: {str(e)}")


# ─── OAuth webhook callback ────────────────────────────────────────────────── #

@ext.webhook("callback", method="GET")
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

        # ctx.store in webhook context is scoped to __webhook__ user_id —
        # matches how connect_spotify stored the state record.
        page = await ctx.store.query(OAUTH_STATE_COLLECTION, where={"state": state})
        if not page.data:
            return WebhookResponse.error("Invalid or expired state — please try connect_spotify() again.", 400)

        record = page.data[0].data
        user_id = record.get("user_id")
        client_id = record.get("client_id")
        client_secret = record.get("client_secret")
        redirect_uri = record.get("redirect_uri")

        await ctx.store.delete(OAUTH_STATE_COLLECTION, page.data[0].id)

        if not client_id or not client_secret or not user_id:
            return WebhookResponse.error("Spotify credentials missing from state", 500)

        credentials = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()

        resp = await ctx.http.post(
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

        # Save token under the real user_id via a user-scoped StoreClient.
        from imperal_sdk.store.client import StoreClient
        user_store = StoreClient(
            gateway_url=ctx.store._gateway_url,
            service_token=ctx.store._auth_token,
            extension_id=ctx.store._extension_id,
            user_id=user_id,
            tenant_id=ctx.store._tenant_id,
        )
        await _save_token_to_store(user_store, user_id, token_data)

        try:
            await ctx.extensions.emit("spotify.connected", {"user_id": user_id})
        except Exception as e:
            log.warning("could not emit connected event: %s", e)

        html = """<!DOCTYPE html><html><head><title>Spotify Connected</title>
<style>body{font-family:sans-serif;display:flex;align-items:center;justify-content:center;height:100vh;margin:0;background:#191414;color:#1DB954;}
h1{font-size:24px;}p{color:#fff;margin-top:8px;}</style></head>
<body><div style="text-align:center"><h1>✓ Spotify Connected</h1>
<p>You can close this window and go back to the app.</p></div>
<script>setTimeout(()=>window.close(),2000);</script></body></html>"""
        return WebhookResponse(status_code=200, body=html, headers={"Content-Type": "text/html"})
    except Exception as e:
        log.error("oauth_callback failed: %s", e)
        return WebhookResponse.error(f"Callback failed: {str(e)}", 500)
