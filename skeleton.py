"""Spotify · Skeleton tool — background library statistics for the LLM classifier."""
import logging

from imperal_sdk import ActionResult

from app import ext
from handlers.auth import get_access_token, refresh_access_token
from spotify_config import SP_API_BASE

log = logging.getLogger("spotify")

SKELETON_STATS = "spotify_stats"


@ext.skeleton(
    "spotify_stats",
    ttl=300,
    alert=False,
    description="Spotify library stats: liked track count and playlist count for classifier",
)
async def skeleton_refresh_spotify(ctx) -> ActionResult:
    """Fetch Spotify library statistics and return as skeleton state."""
    try:
        token = await get_access_token(ctx)
        if not token:
            return ActionResult.success(
                data={"connected": False, "liked_tracks": 0, "playlists": 0},
                summary="Not connected",
            )

        fresh = await refresh_access_token(ctx)
        headers = {"Authorization": f"Bearer {fresh or token}"}

        liked_resp = await ctx.http.get(
            f"{SP_API_BASE}/me/tracks",
            headers=headers,
            params={"limit": 1},
        )
        liked_total = liked_resp.json().get("total", 0) if liked_resp.ok else 0

        playlists_resp = await ctx.http.get(
            f"{SP_API_BASE}/me/playlists",
            headers=headers,
            params={"limit": 1},
        )
        playlists_total = playlists_resp.json().get("total", 0) if playlists_resp.ok else 0

        return ActionResult.success(
            data={"connected": True, "liked_tracks": liked_total, "playlists": playlists_total},
            summary=f"{liked_total} liked tracks, {playlists_total} playlists",
        )

    except Exception as e:
        log.error("Spotify skeleton refresh failed: %s", e)
        return ActionResult.success(
            data={"connected": False, "liked_tracks": 0, "playlists": 0},
            summary="Refresh failed",
        )
