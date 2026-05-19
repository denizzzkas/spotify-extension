# Spotify Extension — Full Audit Report
**Date:** 2026-05-13  
**Audited by:** Dmitrii (via Claude Code)  
**Extension version:** 2.0.0  
**SDK version:** 4.2.9 (imperal-sdk>=4.2.5)  
**Production path:** `/opt/extensions/spotify/` on whm-ai-worker

---

## Context for Claude working on this

This is the Imperal Cloud platform. Extensions are Python packages that run inside the Imperal kernel worker. They are developed locally, then deployed via the Imperal Developer Portal (panel.imperal.io/developer) — **you never edit files directly on the production server**. The workflow is:

1. Edit code locally
2. `python3 -m py_compile <file>` before every deploy
3. Bump version in `app.py` + add `CHANGELOG.md` entry
4. Upload zip via Developer Portal → it deploys to `/opt/extensions/<app_id>/`

The reference extension to follow is **Mail Client** (by SeeU) — it is the gold standard for OAuth-based extensions without a separate backend service.

---

## Critical Bug — Why Users See "Credentials Not Configured"

When any user opens the Spotify panel, they see:

```
Spotify credentials are not configured. Add client_id and client_secret in extension settings.
```

### Root cause

In `panels_left.py → _render_demo_state()`:

```python
client_id = await ctx.secrets.get("spotify_client_id") or ""
if not client_id:
    children.append(ui.Alert(
        "Spotify credentials are not configured. Add client_id and client_secret in extension settings.",
        type="error",
    ))
```

The extension requires every individual user to go to developer.spotify.com, register a Developer App, and enter their own `client_id` + `client_secret` via the Secrets panel. **This is architecturally wrong.**

### Why it's wrong

Spotify OAuth works like this:
- **One** Developer App is registered by the extension author (Denchik)
- That app's `client_id` + `client_secret` are platform-wide credentials
- Each user authenticates with **their own Spotify account** via OAuth — they never need developer credentials

Requiring users to register their own Developer App is impossible for normal users and breaks the entire onboarding flow.

### How Mail Client does it correctly

Mail Client stores platform OAuth credentials in **environment variables** on the worker:
```
GMAIL_CLIENT_ID=...
GMAIL_CLIENT_SECRET=...
MICROSOFT_CLIENT_ID=...
MICROSOFT_CLIENT_SECRET=...
```

Each user just clicks "Connect Google" → OAuth popup → done. Their personal `access_token` + `refresh_token` are stored in `ctx.store` (per-user). No developer credentials ever exposed to users.

---

## What Needs to Change

### 1. Remove all three `ctx.secrets` declarations

In `app.py`, remove these blocks entirely:

```python
# DELETE ALL OF THIS:
ext.secret(name="spotify_client_id", ...)(lambda: None)
ext.secret(name="spotify_client_secret", ...)(lambda: None)
ext.secret(name="genius_access_token", ...)(lambda: None)
```

**Why genius_access_token too?** Genius API is a platform feature — Denchik registers one Genius app, puts the token in env, all users get lyrics. Users should not need to register on genius.com.

### 2. Add env vars to worker `.env`

Ask the platform admin to add to `/home/imperal-platform-worker/.env`:

```
SPOTIFY_CLIENT_ID=your_spotify_app_client_id
SPOTIFY_CLIENT_SECRET=your_spotify_app_client_secret
GENIUS_ACCESS_TOKEN=your_genius_api_token
```

Denchik must first:
- Register a Spotify Developer App at developer.spotify.com
- Add the webhook callback URL as redirect URI: `https://<platform>/ext/spotify/webhook/callback`
- Register a Genius API app at genius.com/api-clients

### 3. Replace `ctx.secrets.get(...)` with `os.getenv(...)`

Every place `ctx.secrets.get("spotify_client_id")` or `ctx.secrets.get("spotify_client_secret")` appears, replace with:

```python
import os
client_id = os.getenv("SPOTIFY_CLIENT_ID", "")
client_secret = os.getenv("SPOTIFY_CLIENT_SECRET", "")
```

Files to update:
- `app.py` — health check and `_refresh_access_token`
- `app_helpers.py` — `_refresh_access_token`
- `handlers/auth.py` — `fn_connect_spotify` and `oauth_callback`

### 4. Fix the panel unauthenticated state

In `panels_left.py → _render_demo_state()`, replace the credential check with a simple connect button:

```python
# BEFORE (wrong):
client_id = await ctx.secrets.get("spotify_client_id") or ""
if not client_id:
    children.append(ui.Alert("Spotify credentials are not configured...", type="error"))
else:
    children += [
        ui.Alert("Not connected...", type="warn"),
        ui.Button("Connect Spotify", ...),
    ]

# AFTER (correct):
children += [
    ui.Alert("Connect your Spotify account to get started.", type="info"),
    ui.Button("Connect Spotify", variant="primary", icon="Music",
              on_click=ui.Call("connect_spotify")),
]
```

---

## Secondary Issues (fix after the main blocker)

### Duplicate functions between `app.py` and `app_helpers.py`

The following functions are defined **twice** — once in `app.py` and once in `app_helpers.py`:
- `_get_access_token`
- `_get_stored_creds`
- `_save_token`
- `_refresh_access_token`
- `_clear_all_credentials`
- `_require_user_id`
- `_require_auth`
- `_get_auth_headers`
- `_spotify_error`

**Fix:** Delete all of these from `app.py`. Keep only in `app_helpers.py`. All handlers already import from `app_helpers`, so nothing breaks.

### Private SDK API usage — `StoreClient` hack

In `handlers/auth.py`, the webhook callback does this:

```python
from imperal_sdk.store.client import StoreClient
webhook_store = StoreClient(
    gateway_url=ctx.store._gateway_url,
    service_token=ctx.store._auth_token,
    extension_id=ctx.store._extension_id,
    user_id="__webhook__",
    tenant_id=ctx.store._tenant_id,
)
```

This accesses private `_` attributes of the SDK store client. This will break on any SDK update that refactors internals. This was done to store the OAuth state record under `user_id="__webhook__"` so the callback can read it.

**Better approach:** Store the OAuth state under a neutral key that doesn't require user context — for example use `state` UUID as the doc ID and query without `user_id` filter. Or ask platform team if there's an official way to write cross-user store records from webhook context.

### No token expiry tracking

`_save_token` / `_save_token_to_store` save `access_token` and `refresh_token` but **no `expires_at` field**. Spotify access tokens expire after 1 hour. Currently the extension only refreshes when it gets a 401 back from Spotify (reactive). This means every hour the first request will fail with 401, then retry after refresh.

**Fix:** Save `expires_at` when storing tokens:

```python
import time
record = {
    "user_id": user_id,
    "access_token": token_data.get("access_token", ""),
    "refresh_token": token_data.get("refresh_token", ""),
    "expires_at": int(time.time()) + token_data.get("expires_in", 3600) - 60,
    "scope": token_data.get("scope", ""),
    "token_type": token_data.get("token_type", "Bearer"),
}
```

Then in `_get_access_token` or before each API call, check:
```python
if creds.get("expires_at", 0) < time.time():
    token = await _refresh_access_token(ctx)
```

### `_require_auth` returns `str | ActionResult` — fragile pattern

Every handler that calls `_require_auth` must do:
```python
token = await _require_auth(ctx)
if isinstance(token, ActionResult):
    return token
```

This is the same fragile union pattern used across all handlers. It works but is hard to read. Lower priority — fix when refactoring handlers.

### `import base64` inside function body

In `app.py → _refresh_access_token` (the duplicate version), there's a lazy `import base64` inside the function. Move to top of file. Minor but it's an anti-pattern.

---

## What is Good — Don't Touch

- `handlers/` split by domain (auth, search, playlists, library, playback, lyrics, demo) — correct structure
- `main.py` with sys.modules purge before imports — correct hot-reload safety pattern
- Demo mode with `DEMO_TRACKS` for unauthenticated state — good UX idea, keep it
- `@ext.skeleton("spotify_stats")` and `@ext.skeleton("spotify_now_playing")` — correct
- `@ext.emits(...)` declarations — correct
- `@ext.health_check` — correct structure (just fix the secrets check inside)
- Cache models with `@ext.cache_model` — correct
- `spotify_config.py` for constants — correct separation
- `format_track` / `format_playlist` in `utils.py` — correct
- OAuth webhook callback pattern (aside from the StoreClient hack) — correct approach

---

## File Change Summary

| File | Change |
|------|--------|
| `app.py` | Remove 3x `ext.secret(...)` blocks; remove duplicate helper functions; fix health check to use `os.getenv` |
| `app_helpers.py` | Add `expires_at` to `_save_token` / `_save_token_to_store`; add proactive refresh check; replace `ctx.secrets` with `os.getenv` in `_refresh_access_token` |
| `handlers/auth.py` | Replace `ctx.secrets.get(...)` with `os.getenv(...)` in `fn_connect_spotify` and `oauth_callback`; fix StoreClient hack if possible |
| `handlers/lyrics.py` | Replace `ctx.secrets.get("genius_access_token")` with `os.getenv("GENIUS_ACCESS_TOKEN", "")` |
| `panels_left.py` | Remove credential check from `_render_demo_state`; always show Connect button |
| `imperal.json` | Remove `"secrets": [...]` section entirely; bump `version` and `sdk_version` |
| `CHANGELOG.md` | Add entry for new version |

---

## Deploy Instructions (after all changes)

1. Run `python3 -m py_compile` on every changed `.py` file
2. Bump version in `app.py` (e.g. `2.0.0` → `2.1.0`)
3. Add `CHANGELOG.md` entry
4. Zip the extension folder
5. Upload via Developer Portal at panel.imperal.io/developer
6. Ask platform admin to add env vars to worker `.env` and restart workers
7. Test: open Spotify panel → should show "Connect Spotify" button → OAuth flow → connected

**Do not edit files directly on the server.** All changes go through Developer Portal.
