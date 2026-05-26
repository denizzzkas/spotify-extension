"""Web Playback SDK webhook — receives device_id from browser player."""
from __future__ import annotations

import json
import logging

from imperal_sdk.store.client import StoreClient

from app import ext
from spotify_config import SP_PLAYER_DEVICES

log = logging.getLogger("spotify.player_webhook")


@ext.webhook("player-ready", method="POST")
async def on_player_ready(ctx, headers, body, query_params):
    try:
        data = json.loads(body) if isinstance(body, (str, bytes)) else body
        device_id = data.get("device_id", "")
        user_id = data.get("user_id", "")

        if not device_id or not user_id:
            return {"status_code": 400, "error": "Missing device_id or user_id"}

        user_store = StoreClient(
            gateway_url=ctx.store._gateway_url,
            service_token=ctx.store._auth_token,
            extension_id=ctx.store._extension_id,
            user_id=user_id,
            tenant_id=ctx.store._tenant_id,
        )
        page = await user_store.query(SP_PLAYER_DEVICES, where={"user_id": user_id})
        if page.data:
            await user_store.update(
                SP_PLAYER_DEVICES, page.data[0].id,
                {"user_id": user_id, "device_id": device_id},
            )
        else:
            await user_store.create(SP_PLAYER_DEVICES, {"user_id": user_id, "device_id": device_id})

        log.info("Player ready: user=%s device=%s...", user_id[:8], device_id[:8])
        return {"status": "ok"}
    except Exception as e:
        log.error("on_player_ready failed: %s", e)
        return {"status_code": 500, "error": str(e)}
