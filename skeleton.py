"""Spotify · Skeleton tools — library statistics and now playing for LLM classifier."""
import logging

from app import ext
from spotify_config import SP_API_BASE
from app_helpers import _get_access_token, _refresh_access_token

log = logging.getLogger("spotify")

_STATS_EMPTY = {"response": {"connected": False, "liked_tracks": 0}}


@ext.skeleton(
    "spotify_stats",
    ttl=300,
    alert=False,
    description="Spotify library stats: liked track count",
)
async def skeleton_refresh_spotify(ctx) -> dict:
    """Fetch Spotify library statistics and return as skeleton state."""
    try:
        token = await _get_access_token(ctx)
        if not token:
            return _STATS_EMPTY

        fresh = await _refresh_access_token(ctx)
        headers = {"Authorization": f"Bearer {fresh or token}"}

        liked_resp = await ctx.http.get(
            f"{SP_API_BASE}/me/tracks", headers=headers, params={"limit": 1}
        )
        liked_total = liked_resp.json().get("total", 0) if liked_resp.ok else 0

        return {
            "response": {
                "connected": True,
                "liked_tracks": liked_total,
            }
        }

    except Exception as e:
        log.error("Spotify skeleton refresh failed: %s", e)
        return _STATS_EMPTY


_NOW_PLAYING_EMPTY = {"response": {"playing": False, "track_title": "", "track_artist": "", "track_album": "", "track_id": ""}}


@ext.skeleton(
    "spotify_now_playing",
    ttl=30,
    alert=False,
    description="Spotify current track being played by user",
)
async def skeleton_now_playing(ctx) -> dict:
    """Fetch current Spotify playback state directly from API."""
    try:
        token = await _get_access_token(ctx)
        if not token:
            return _NOW_PLAYING_EMPTY

        fresh = await _refresh_access_token(ctx)
        headers = {"Authorization": f"Bearer {fresh or token}"}

        resp = await ctx.http.get(f"{SP_API_BASE}/me/player", headers=headers)
        if not resp.ok or resp.status_code == 204:
            return _NOW_PLAYING_EMPTY

        data = resp.json()
        track = data.get("item") or {}
        artists = track.get("artists") or []
        artist_str = ", ".join(a.get("name", "") for a in artists)

        return {
            "response": {
                "playing": data.get("is_playing", False),
                "track_title": track.get("name", ""),
                "track_artist": artist_str,
                "track_album": (track.get("album") or {}).get("name", ""),
                "track_id": track.get("id", ""),
            }
        }
    except Exception as e:
        log.error("Spotify now_playing skeleton failed: %s", e)
        return _NOW_PLAYING_EMPTY


