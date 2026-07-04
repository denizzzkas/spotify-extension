"""Web Playback SDK webhook — receives device_id from browser player."""
from __future__ import annotations

import json
import logging

from imperal_sdk import WebhookResponse

from app import ext
from spotify_config import SP_PLAYER_DEVICES, PLAYER_READY_TTL_SECONDS
from app_helpers import _state_is_fresh

log = logging.getLogger("spotify.player_webhook")


@ext.webhook("/player-ready", method="POST")
async def on_player_ready(ctx, headers, body, query_params):
    try:
        data = json.loads(body) if isinstance(body, (str, bytes)) else (body or {})
        device_id = data.get("device_id", "")
        token = data.get("player_token", "")

        if not device_id or not token:
            return WebhookResponse.error("Missing device_id or player_token", 400)

        page = await ctx.store.query(SP_PLAYER_DEVICES, where={"player_token": token})
        if not page.data:
            return WebhookResponse.error("Invalid player token", 403)

        record = page.data[0]
        user_id = record.data.get("user_id", "")
        created_at = record.data.get("created_at")
        if not user_id:
            await ctx.store.delete(SP_PLAYER_DEVICES, record.id)
            return WebhookResponse.error("Invalid player token", 403)

        if not _state_is_fresh(created_at, PLAYER_READY_TTL_SECONDS):
            await ctx.store.delete(SP_PLAYER_DEVICES, record.id)
            return WebhookResponse.error("Expired player token", 403)

        await ctx.store.update(
            SP_PLAYER_DEVICES,
            record.id,
            {
                "user_id": user_id,
                "player_token": token,
                "created_at": created_at,
                "device_id": device_id,
            },
        )

        log.info("Player ready verified: user=%s device=%s...", user_id[:8], device_id[:8])
        return WebhookResponse(status_code=200, body={"status": "ok"})
    except Exception as e:
        log.error("on_player_ready failed: %s", e)
        return WebhookResponse.error("Could not register Spotify player device", 500)
