"""Spotify · Skeleton tools — background library statistics."""
import logging

from app import ext
from handlers.auth import get_access_token
from spotify_config import SP_API_BASE

log = logging.getLogger("spotify")

SKELETON_STATS = "spotify_stats"


@ext.tool("skeleton_refresh_spotify", scopes=[], description="Background refresh: Spotify library statistics.")
async def skeleton_refresh_spotify(ctx, **kwargs) -> dict:
    """Fetch Spotify library statistics and update skeleton cache."""
    try:
        token = await get_access_token(ctx)
        if not token:
            stats = {"connected": False, "liked_tracks": 0, "playlists": 0}
            await ctx.skeleton.update(SKELETON_STATS, stats)
            return {"response": stats}

        headers = {"Authorization": f"Bearer {token}"}

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

        stats = {
            "connected": True,
            "liked_tracks": liked_total,
            "playlists": playlists_total,
        }
        await ctx.skeleton.update(SKELETON_STATS, stats)
        return {"response": stats}

    except Exception as e:
        log.error("Spotify skeleton refresh failed: %s", e)
        return {"response": {"connected": False, "liked_tracks": 0, "playlists": 0, "error": str(e)}}


@ext.tool("skeleton_alert_spotify", scopes=[], description="Alert on significant Spotify library changes.")
async def skeleton_alert_spotify(ctx, old: dict = None, new: dict = None, **kwargs) -> dict:
    """Check for notable changes and notify user if liked track count increased."""
    if not old or not new:
        return {"response": "No changes detected."}

    old_liked = old.get("liked_tracks", 0)
    new_liked = new.get("liked_tracks", 0)

    if isinstance(new_liked, int) and isinstance(old_liked, int) and new_liked > old_liked:
        diff = new_liked - old_liked
        msg = f"{diff} new track{'s' if diff > 1 else ''} added to your Spotify library."
        try:
            await ctx.notify.send(msg)
        except Exception:
            pass
        return {"response": msg}

    return {"response": "No significant Spotify library changes."}
