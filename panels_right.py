"""Spotify extension — right detail panel UI."""
import logging

from imperal_sdk import ui

from pydantic import BaseModel

from app import ext
from spotify_config import SP_API_BASE
from app_helpers import _get_access_token, _spotify_call, _spotify_error
from cache_models import DetailModel
from demo_data import DEMO_TRACKS, DEMO_PLAYLIST_ID, DEMO_PLAYLIST_NAME
from utils import format_track
from panels_right_render import _render_fetched_tracks, _render_profile, _render_tracks


@ext.cache_model("detail_params")
class _DetailParams(BaseModel):
    detail_type: str = ""
    playlist_id: str = ""
    playlist_name: str = ""
    page: int = 0
    cursor: str = ""
    cursor_stack: str = ""

log = logging.getLogger("spotify.panels.right")


async def _get_auth_headers(ctx) -> dict | None:
    token = await _get_access_token(ctx)
    if not token:
        return None
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


async def _fetch_playlist_tracks(ctx, playlist_id: str, page: int = 0) -> tuple[list[dict], str | None, bool]:
    """Fetch one page of playlist tracks. Returns (tracks, error_msg, has_next)."""
    try:
        fetch_params = {"limit": 50, "offset": page * 50}
        resp, err = await _spotify_call(
            ctx,
            "get",
            f"{SP_API_BASE}/playlists/{playlist_id}/items",
            params=fetch_params,
        )
        if err:
            return [], err.error, False

        if resp.ok:
            data = resp.json()
            items = data.get("items", [])
            tracks = [
                format_track(item.get("item"))
                for item in items
                if item.get("item")
            ]
            return tracks, None, bool(data.get("next"))

        try:
            detail = resp.json().get("error", {}).get("message", "")
        except Exception:
            try:
                detail = resp.text
            except Exception:
                detail = ""

        if resp.status_code == 403:
            if detail and "not registered" in detail.lower():
                return [], "Account not registered as a test user. Add your email in Spotify Developer Dashboard → User Management.", False
            if detail and "premium" in detail.lower():
                return [], "This feature requires Spotify Premium.", False
            return [], "This playlist belongs to another user. Spotify restricts access to other users' playlists in development mode — only your own playlists are accessible.", False

        log.error("_fetch_playlist_tracks HTTP %s: %s", resp.status_code, detail)
        return [], f"HTTP {resp.status_code}{': ' + detail if detail else ''}", False

    except Exception as e:
        log.error("_fetch_playlist_tracks failed: %s", e)
        return [], str(e), False


@ext.panel(
    "spotify_detail",
    slot="center",
    center_overlay=True,
    title="Spotify",
    icon="Music",
)
async def panel_spotify_detail(ctx, detail_type: str = "", playlist_id: str = "", playlist_name: str = "", page: int = 0, cursor: str = "", cursor_stack: str = "", **kwargs):
    """Center overlay panel: loads playlist/liked/recent/profile data."""
    log.debug("panel_spotify_detail called: detail_type=%r playlist_id=%r", detail_type, playlist_id)

    # Restore params from cache on page refresh (when called with empty params)
    if not detail_type:
        try:
            saved = await ctx.cache.get(key="detail_params", model=_DetailParams)
            if saved and saved.detail_type:
                detail_type = saved.detail_type
                playlist_id = saved.playlist_id
                playlist_name = saved.playlist_name
                page = saved.page
                cursor = saved.cursor
                cursor_stack = saved.cursor_stack
        except Exception:
            pass

    if not detail_type:
        return ui.Empty("Select a playlist or profile from the sidebar.", icon="Music")

    # Persist current params so page refresh restores state
    try:
        await ctx.cache.set(
            key="detail_params",
            value=_DetailParams(detail_type=detail_type, playlist_id=playlist_id, playlist_name=playlist_name, page=page, cursor=cursor, cursor_stack=cursor_stack),
            ttl_seconds=300,
        )
    except Exception:
        pass

    if detail_type == "profile":
        return await _render_profile(ctx)

    if detail_type == "liked_tracks":
        return await _render_fetched_tracks(ctx, f"{SP_API_BASE}/me/tracks", "Liked Tracks", item_key="track", liked_context=True, page=page)

    if detail_type == "recent_tracks":
        return await _render_fetched_tracks(ctx, f"{SP_API_BASE}/me/player/recently-played", "Recent Tracks", item_key="track", cursor=cursor, cursor_stack=cursor_stack)

    # Demo mode — load directly from hardcoded demo data
    if playlist_id == DEMO_PLAYLIST_ID:
        return _render_tracks(DEMO_TRACKS, DEMO_PLAYLIST_NAME, play_fn="demo_play_track")

    # Regular playlist — check cache first, then fetch from API
    if not playlist_id:
        return ui.Empty("No playlist selected.", icon="Music")

    title = playlist_name or "Playlist"
    cache_key = f"detail_{playlist_id}"

    if page == 0:
        try:
            cached = await ctx.cache.get(key=cache_key, model=DetailModel)
            if cached and cached.tracks:
                return _render_tracks(cached.tracks, cached.title, play_fn="play_track", playlist_id=playlist_id, has_next=cached.has_next, page=0, playlist_name=playlist_name)
        except Exception:
            pass

    tracks, err, has_next = await _fetch_playlist_tracks(ctx, playlist_id, page=page)

    if err:
        return ui.Stack([
            ui.Header(title, level=3),
            ui.Empty(err, icon="AlertCircle"),
        ], direction="v", gap=2)

    if not tracks and page == 0:
        return ui.Empty("Playlist is empty.", icon="Music")

    if page == 0:
        try:
            await ctx.cache.set(
                key=cache_key,
                value=DetailModel(type="tracks", title=title, tracks=tracks, has_next=has_next),
                ttl_seconds=300,
            )
        except Exception as e:
            log.error("Failed to cache playlist tracks: %s", e)

    return _render_tracks(tracks, title, play_fn="play_track", playlist_id=playlist_id, has_next=has_next, page=page, playlist_name=playlist_name)


