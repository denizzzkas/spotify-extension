"""OAuth 2.0 token management for the Spotify extension.

Tokens are stored in the Imperal document store (CRED_COLLECTION), keyed by
user_id. Spotify tokens expire after 1 hour — this module handles automatic
refresh via the stored refresh_token.
"""
from __future__ import annotations

import base64
import urllib.parse
import uuid
from datetime import datetime, timezone

from spotify_config import (
    CRED_COLLECTION,
    OAUTH_STATE_COLLECTION,
    SP_AUTH_URL,
    SP_TOKEN_URL,
    SP_SCOPES,
    SP_REDIRECT_URI,
)


# ── Token storage ─────────────────────────────────────────────────────────────

async def get_stored_creds(ctx):
    """Return the credential Document for the current user, or None."""
    page = await ctx.store.query(CRED_COLLECTION, where={"user_id": ctx.user.id})
    return page.data[0] if page.data else None


async def get_access_token(ctx) -> str | None:
    """Return the stored access token, or None if the user has not connected."""
    doc = await get_stored_creds(ctx)
    if doc is None:
        return None
    return doc.data.get("access_token")


async def save_token(ctx, token_data: dict) -> None:
    """Persist or overwrite OAuth credentials for the current user."""
    await save_token_for_user(ctx, ctx.user.id, token_data)


async def save_token_for_user(ctx, user_id: str, token_data: dict) -> None:
    """Persist or overwrite OAuth credentials for an explicit user_id.

    Used in the OAuth webhook callback where ctx.user may not reflect
    the user who initiated the OAuth flow.
    """
    record = {
        "user_id": user_id,
        "access_token": token_data.get("access_token", ""),
        "refresh_token": token_data.get("refresh_token", ""),
        "scope": token_data.get("scope", ""),
        "token_type": token_data.get("token_type", "Bearer"),
    }
    page = await ctx.store.query(CRED_COLLECTION, where={"user_id": user_id})
    existing = page.data[0] if page.data else None
    if existing is None:
        await ctx.store.create(CRED_COLLECTION, record)
    else:
        await ctx.store.update(CRED_COLLECTION, existing.id, record)


async def clear_token(ctx) -> None:
    """Delete all stored credentials for the current user."""
    page = await ctx.store.query(CRED_COLLECTION, where={"user_id": ctx.user.id})
    for doc in page.data:
        await ctx.store.delete(CRED_COLLECTION, doc.id)


async def refresh_access_token(ctx) -> str | None:
    """Use the stored refresh_token to obtain a new access_token.

    Returns the new access token, or None if refresh failed.
    Spotify tokens expire after 1 hour — this is called automatically on 401.
    """
    doc = await get_stored_creds(ctx)
    if doc is None:
        return None

    refresh_token = doc.data.get("refresh_token", "")
    if not refresh_token:
        return None

    client_id = ctx.config.get("spotify.client_id", "")
    client_secret = ctx.config.get("spotify.client_secret", "")
    if not client_id or not client_secret:
        return None

    credentials = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()

    resp = await ctx.http.post(
        SP_TOKEN_URL,
        headers={
            "Authorization": f"Basic {credentials}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        data={"grant_type": "refresh_token", "refresh_token": refresh_token},
    )

    if not resp.ok:
        return None

    new_token = resp.json().get("access_token")
    if new_token:
        await ctx.store.update(CRED_COLLECTION, doc.id, {"access_token": new_token})
    return new_token


async def get_auth_headers(ctx) -> dict:
    """Return Authorization headers, or raise ValueError if not connected."""
    token = await get_access_token(ctx)
    if not token:
        raise ValueError(
            "Not connected to Spotify. Use connect_spotify() to authorise."
        )
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }


async def get_auth_headers_refreshed(ctx) -> dict:
    """Same as get_auth_headers but attempts token refresh first.

    Use this after receiving a 401 to get fresh headers.
    Raises ValueError if refresh also fails.
    """
    new_token = await refresh_access_token(ctx)
    if not new_token:
        raise ValueError(
            "Spotify token expired and refresh failed. Please reconnect via connect_spotify()."
        )
    return {
        "Authorization": f"Bearer {new_token}",
        "Content-Type": "application/json",
    }


# ── OAuth helpers ─────────────────────────────────────────────────────────────

def build_auth_url(client_id: str, redirect_uri: str, state: str) -> str:
    """Construct the Spotify OAuth 2.0 authorisation URL."""
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": SP_SCOPES,
        "state": state,
    }
    return SP_AUTH_URL + "?" + urllib.parse.urlencode(params)


async def create_oauth_state(ctx) -> str:
    """Generate a random state token and persist it for CSRF verification."""
    state = str(uuid.uuid4())
    await ctx.store.create(OAUTH_STATE_COLLECTION, {
        "user_id": ctx.user.id,
        "state": state,
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    return state


async def consume_oauth_state(ctx, state: str) -> str | None:
    """Verify and delete the state token. Returns the user_id or None if invalid.

    Queries by state only — ctx.user may not be the initiating user in
    the OAuth webhook callback (request comes from Spotify's servers).
    """
    page = await ctx.store.query(OAUTH_STATE_COLLECTION, where={"state": state})
    if not page.data:
        return None
    doc = page.data[0]
    await ctx.store.delete(OAUTH_STATE_COLLECTION, doc.id)
    return doc.data.get("user_id")


async def exchange_code_for_token(ctx, code: str, redirect_uri: str) -> dict:
    """Exchange an authorisation code for access + refresh tokens from Spotify."""
    client_id = ctx.config.get("spotify.client_id", "")
    client_secret = ctx.config.get("spotify.client_secret", "")

    if not client_id or not client_secret:
        raise ValueError(
            "spotify.client_id and spotify.client_secret must be configured."
        )

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
        raise ValueError(f"Token exchange failed (HTTP {resp.status_code}).")

    return resp.json()
