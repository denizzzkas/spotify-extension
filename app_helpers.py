"""Auth helpers and utility functions for Spotify extension."""
import base64
import logging

from imperal_sdk import ActionResult

from spotify_config import SP_TOKEN_URL, CRED_COLLECTION

log = logging.getLogger("spotify")


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


async def _save_token_to_store(store, user_id: str, token_data: dict) -> None:
    """Save token using a provided store client (for webhook context)."""
    try:
        record = {
            "user_id": user_id,
            "access_token": token_data.get("access_token", ""),
            "refresh_token": token_data.get("refresh_token", ""),
            "scope": token_data.get("scope", ""),
            "token_type": token_data.get("token_type", "Bearer"),
        }
        page = await store.query(CRED_COLLECTION, where={"user_id": user_id})
        if page.data:
            await store.update(CRED_COLLECTION, page.data[0].id, record)
        else:
            await store.create(CRED_COLLECTION, record)
    except Exception as e:
        log.error("save_token_to_store failed: %s", e)


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

        credentials = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()

        resp = await ctx.http.post(
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
    from spotify_config import OAUTH_STATE_COLLECTION, DEMO_PLAYER_STATE, DEMO_PANEL_STATE
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


async def _spotify_call(ctx, method: str, url: str, **kwargs):
    """Authenticated Spotify API call with automatic 401 refresh-and-retry. Returns (resp, err)."""
    token = await _require_auth(ctx)
    if isinstance(token, ActionResult):
        return None, token
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    resp = await getattr(ctx.http, method)(url, headers=headers, **kwargs)
    if resp.status_code == 401:
        token = await _refresh_access_token(ctx)
        if not token:
            return None, ActionResult.error("Spotify token expired. Please reconnect via connect_spotify().")
        headers["Authorization"] = f"Bearer {token}"
        resp = await getattr(ctx.http, method)(url, headers=headers, **kwargs)
    return resp, None


def _spotify_err(resp) -> ActionResult:
    """Build ActionResult from a failed Spotify response, including Spotify's own message."""
    try:
        detail = resp.json().get("error", {}).get("message", "")
    except Exception:
        detail = resp.text or ""
    msg = _spotify_error(resp.status_code)
    return ActionResult.error(f"{msg} Spotify says: {detail}" if detail else msg, retryable=(resp.status_code == 429))


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
