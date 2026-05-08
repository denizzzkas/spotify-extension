"""Spotify · Skeleton tools — library statistics and now playing for LLM classifier."""
import logging

from app import ext, _get_access_token, _refresh_access_token, SP_API_BASE, NowPlayingModel

log = logging.getLogger("spotify")


@ext.skeleton(
    "spotify_stats",
    ttl=300,
    alert=False,
    description="Spotify library stats: liked track count and playlist count for classifier",
)
async def skeleton_refresh_spotify(ctx) -> dict:
    """Fetch Spotify library statistics and return as skeleton state."""
    try:
        token = await _get_access_token(ctx)
        if not token:
            return {
                "response": {
                    "connected": False,
                    "liked_tracks": 0,
                    "playlists": 0,
                }
            }

        fresh = await _refresh_access_token(ctx)
        headers = {"Authorization": f"Bearer {fresh or token}"}

        liked_resp = await ctx.api.get(
            f"{SP_API_BASE}/me/tracks",
            headers=headers,
            params={"limit": 1},
        )
        liked_total = liked_resp.json().get("total", 0) if liked_resp.ok else 0

        playlists_resp = await ctx.api.get(
            f"{SP_API_BASE}/me/playlists",
            headers=headers,
            params={"limit": 1},
        )
        playlists_total = playlists_resp.json().get("total", 0) if playlists_resp.ok else 0

        return {
            "response": {
                "connected": True,
                "liked_tracks": liked_total,
                "playlists": playlists_total,
            }
        }

    except Exception as e:
        log.error("Spotify skeleton refresh failed: %s", e)
        return {
            "response": {
                "connected": False,
                "liked_tracks": 0,
                "playlists": 0,
            }
        }


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
            return {"response": {"playing": False, "track": None}}

        track_data = now_playing.model_dump()
        return {
            "response": {
                "playing": track_data.get("is_playing", False),
                "track": {
                    "title": track_data.get("title", ""),
                    "artist": track_data.get("artist", ""),
                    "album": track_data.get("album", ""),
                },
            }
        }
    except Exception as e:
        log.error("Spotify now_playing skeleton failed: %s", e)
        return {"response": {"playing": False, "track": None}}
