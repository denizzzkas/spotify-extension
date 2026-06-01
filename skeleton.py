"""Spotify · Skeleton tools — library statistics and now playing for LLM classifier."""
import asyncio
import logging

from app import ext, NowPlayingModel
from spotify_config import SP_API_BASE
from app_helpers import _get_access_token, _refresh_access_token

log = logging.getLogger("spotify")

_STATS_EMPTY = {"response": {"connected": False, "liked_tracks": 0, "playlists": 0, "playlists_list": []}}


@ext.skeleton(
    "spotify_stats",
    ttl=300,
    alert=False,
    description="Spotify library stats: liked count, playlist count, first 5 playlist names and IDs",
)
async def skeleton_refresh_spotify(ctx) -> dict:
    """Fetch Spotify library statistics and return as skeleton state."""
    try:
        token = await _get_access_token(ctx)
        if not token:
            return _STATS_EMPTY

        fresh = await _refresh_access_token(ctx)
        headers = {"Authorization": f"Bearer {fresh or token}"}

        liked_resp, playlists_resp = await asyncio.gather(
            ctx.http.get(f"{SP_API_BASE}/me/tracks", headers=headers, params={"limit": 1}),
            ctx.http.get(f"{SP_API_BASE}/me/playlists", headers=headers, params={"limit": 5}),
        )

        liked_total = liked_resp.json().get("total", 0) if liked_resp.ok else 0

        playlists_data = playlists_resp.json() if playlists_resp.ok else {}
        playlists_total = playlists_data.get("total", 0)
        playlists_list = [
            {"id": p["id"], "name": p.get("name", "")}
            for p in (playlists_data.get("items") or [])
            if p.get("id")
        ]

        return {
            "response": {
                "connected": True,
                "liked_tracks": liked_total,
                "playlists": playlists_total,
                "playlists_list": playlists_list,
            }
        }

    except Exception as e:
        log.error("Spotify skeleton refresh failed: %s", e)
        return _STATS_EMPTY


@ext.skeleton(
    "spotify_now_playing",
    ttl=30,
    alert=False,
    description="Spotify current track being played by user",
)
async def skeleton_now_playing(ctx) -> dict:
    """Return current Spotify track from cache for LLM context."""
    try:
        now_playing = await ctx.cache.get(key="now_playing", model=NowPlayingModel)
        if not now_playing:
            return {"response": {"playing": False, "track_title": "", "track_artist": "", "track_album": "", "track_id": "", "is_liked": False}}

        track_data = now_playing.model_dump()
        return {
            "response": {
                "playing": track_data.get("is_playing", False),
                "track_title": track_data.get("title", ""),
                "track_artist": track_data.get("artist", ""),
                "track_album": track_data.get("album", ""),
                "track_id": track_data.get("id", ""),
                "is_liked": track_data.get("is_liked", False),
            }
        }
    except Exception as e:
        log.error("Spotify now_playing skeleton failed: %s", e)
        return {"response": {"playing": False, "track_title": "", "track_artist": "", "track_album": "", "track_id": "", "is_liked": False}}


