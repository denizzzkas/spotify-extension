"""Spotify extension — right detail panel UI."""
import logging

from imperal_sdk import ui

from pydantic import BaseModel

from app import ext
from spotify_config import SP_API_BASE
from app_helpers import _get_access_token, _refresh_access_token
from cache_models import DetailModel
from demo_data import DEMO_TRACKS, DEMO_PLAYLIST_ID, DEMO_PLAYLIST_NAME
from utils import format_track


@ext.cache_model("detail_params")
class _DetailParams(BaseModel):
    detail_type: str = ""
    playlist_id: str = ""
    playlist_name: str = ""

log = logging.getLogger("spotify.panels.right")


async def _get_auth_headers(ctx) -> dict | None:
    token = await _get_access_token(ctx)
    if not token:
        return None
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


async def _fetch_playlist_tracks(ctx, playlist_id: str) -> tuple[list[dict], str | None]:
    """Fetch playlist tracks. Returns (tracks, error_msg)."""
    try:
        headers = await _get_auth_headers(ctx)
        if not headers:
            return [], "Not authenticated"

        resp = await ctx.http.get(
            f"{SP_API_BASE}/playlists/{playlist_id}/items",
            headers=headers,
            params={"limit": 50},
        )

        if resp.status_code == 401:
            token = await _refresh_access_token(ctx)
            if token:
                headers["Authorization"] = f"Bearer {token}"
                resp = await ctx.http.get(
                    f"{SP_API_BASE}/playlists/{playlist_id}/items",
                    headers=headers,
                    params={"limit": 50},
                )

        if resp.ok:
            items = resp.json().get("items", [])
            tracks = [
                format_track(item.get("track") or item.get("item"))
                for item in items
                if item.get("track") or item.get("item")
            ]
            return tracks, None

        try:
            detail = resp.json().get("error", {}).get("message", "")
        except Exception:
            try:
                detail = resp.text
            except Exception:
                detail = ""

        if resp.status_code == 403:
            if detail and "not registered" in detail.lower():
                return [], "Account not registered as a test user. Add your email in Spotify Developer Dashboard → User Management."
            if detail and "premium" in detail.lower():
                return [], "This feature requires Spotify Premium."
            return [], "This playlist belongs to another user. Spotify restricts access to other users' playlists in development mode — only your own playlists are accessible."

        log.error("_fetch_playlist_tracks HTTP %s: %s", resp.status_code, detail)
        return [], f"HTTP {resp.status_code}{': ' + detail if detail else ''}"

    except Exception as e:
        log.error("_fetch_playlist_tracks failed: %s", e)
        return [], str(e)


@ext.panel(
    "spotify_detail",
    slot="center",
    center_overlay=True,
    title="Spotify",
    icon="Music",
)
async def panel_spotify_detail(ctx, detail_type: str = "", playlist_id: str = "", playlist_name: str = "", **kwargs):
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
        except Exception:
            pass

    if not detail_type:
        return ui.Empty("Select a playlist or profile from the sidebar.", icon="Music")

    # Persist current params so page refresh restores state
    try:
        await ctx.cache.set(
            key="detail_params",
            value=_DetailParams(detail_type=detail_type, playlist_id=playlist_id, playlist_name=playlist_name),
            ttl_seconds=300,
        )
    except Exception:
        pass

    if detail_type == "profile":
        return await _render_profile(ctx)

    if detail_type == "liked_tracks":
        return await _render_fetched_tracks(ctx, f"{SP_API_BASE}/me/tracks", "Liked Tracks", item_key="track", liked_context=True)

    if detail_type == "recent_tracks":
        return await _render_fetched_tracks(ctx, f"{SP_API_BASE}/me/player/recently-played", "Recent Tracks", item_key="track")

    # Demo mode — load directly from hardcoded demo data
    if playlist_id == DEMO_PLAYLIST_ID:
        return _render_tracks(DEMO_TRACKS, DEMO_PLAYLIST_NAME, play_fn="demo_play_track")

    # Regular playlist — check cache first, then fetch from API
    if not playlist_id:
        return ui.Empty("No playlist selected.", icon="Music")

    title = playlist_name or "Playlist"
    cache_key = f"detail_{playlist_id}"

    try:
        cached = await ctx.cache.get(key=cache_key, model=DetailModel)
        if cached and cached.tracks:
            return _render_tracks(cached.tracks, cached.title, play_fn="play_track", playlist_id=playlist_id)
    except Exception:
        pass

    tracks, err = await _fetch_playlist_tracks(ctx, playlist_id)

    if err:
        return ui.Stack([
            ui.Header(title, level=3),
            ui.Empty(err, icon="AlertCircle"),
        ], direction="v", gap=2)

    if not tracks:
        return ui.Empty("Playlist is empty.", icon="Music")

    try:
        await ctx.cache.set(
            key=cache_key,
            value=DetailModel(type="tracks", title=title, tracks=tracks),
            ttl_seconds=300,
        )
    except Exception as e:
        log.error("Failed to cache playlist tracks: %s", e)

    return _render_tracks(tracks, title, play_fn="play_track", playlist_id=playlist_id)


async def _render_fetched_tracks(ctx, url: str, title: str, item_key: str = "track", liked_context: bool = False, max_tracks: int = 200) -> ui.Stack:
    """Fetch tracks from a Spotify endpoint with pagination and render them."""
    try:
        token = await _get_access_token(ctx)
        if not token:
            return ui.Empty("Not connected to Spotify.", icon="Music")

        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        tracks = []
        next_url = url
        fetch_params = {"limit": 50}

        while next_url and len(tracks) < max_tracks:
            resp = await ctx.http.get(next_url, headers=headers, params=fetch_params)
            fetch_params = {}

            if resp.status_code == 401:
                token = await _refresh_access_token(ctx)
                if not token:
                    break
                headers["Authorization"] = f"Bearer {token}"
                resp = await ctx.http.get(next_url, headers=headers)

            if resp.status_code == 403:
                try:
                    body = resp.text
                except Exception:
                    body = ""
                if "not registered" in body.lower():
                    return ui.Empty("Account not registered for this app. Add it in Spotify Developer Dashboard → User Management.", icon="Lock")
                return ui.Empty("This feature requires Spotify Premium.", icon="Lock")

            if not resp.ok:
                return ui.Empty(f"Could not load tracks (HTTP {resp.status_code}).", icon="AlertCircle")

            data = resp.json()
            raw_list = data.get("items") or []
            tracks.extend(format_track(item[item_key]) for item in raw_list if item.get(item_key))
            next_url = data.get("next")

    except Exception as e:
        log.error("_render_fetched_tracks failed for %s: %s", url, e)
        return ui.Empty("Failed to load tracks.", icon="AlertCircle")

    return _render_tracks(tracks, title, play_fn="play_track", liked_context=liked_context)


async def _render_profile(ctx) -> ui.Stack:
    """Render profile by fetching from Spotify API directly."""
    try:
        token = await _get_access_token(ctx)
        if not token:
            return ui.Empty("Not connected to Spotify.", icon="User")

        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        resp = await ctx.http.get(f"{SP_API_BASE}/me", headers=headers)

        if resp.status_code == 401:
            token = await _refresh_access_token(ctx)
            if token:
                headers["Authorization"] = f"Bearer {token}"
                resp = await ctx.http.get(f"{SP_API_BASE}/me", headers=headers)

        if not resp.ok:
            return ui.Empty(f"Could not load profile (HTTP {resp.status_code}).", icon="User")

        raw = resp.json()
        items = [
            ui.ListItem(id="name", title="Name", subtitle=raw.get("display_name") or raw.get("id", "")),
            ui.ListItem(id="email", title="Email", subtitle=raw.get("email", "")),
            ui.ListItem(id="plan", title="Plan", subtitle=(raw.get("product") or "free").capitalize()),
            ui.ListItem(id="followers", title="Followers", subtitle=str((raw.get("followers") or {}).get("total", 0))),
        ]
        return ui.Stack([
            ui.Header("My Profile", level=3),
            ui.List(items=items),
            ui.Button("Disconnect Spotify", variant="danger", icon="LogOut", on_click=ui.Call("disconnect_spotify")),
        ], direction="v", gap=2)

    except Exception as e:
        log.error("_render_profile failed: %s", e)

    return ui.Empty("Profile not loaded.", icon="User")


def _render_tracks(tracks: list[dict], title: str, play_fn: str = "play_track", playlist_id: str = "", liked_context: bool = False) -> ui.Stack:
    """Render track list with the correct play function for demo or authenticated mode."""
    all_track_ids = [t["id"] for t in tracks if t.get("id")]

    def _play_action(track_id: str) -> ui.Call:
        if play_fn == "play_track" and playlist_id:
            return ui.Call(play_fn, track_id=track_id, playlist_id=playlist_id)
        if play_fn == "play_track" and len(all_track_ids) > 1:
            base = ui.Call(play_fn, track_id=track_id, track_ids_queue=all_track_ids)
            if liked_context:
                return ui.Call(play_fn, track_id=track_id, track_ids_queue=all_track_ids, is_liked=True)
            return base
        if play_fn == "play_track" and liked_context:
            return ui.Call(play_fn, track_id=track_id, is_liked=True)
        return ui.Call(play_fn, track_id=track_id)

    track_items = [
        ui.ListItem(
            id=t["id"],
            title=t["title"],
            subtitle=t["artist"],
            meta=t["duration"],
            avatar=ui.Avatar(src=t["album_art"], fallback=(t["title"] or "?")[0].upper()),
            actions=[{"icon": "Play", "on_click": _play_action(t["id"])}],
        )
        for t in tracks
    ]

    return ui.Stack([
        ui.Header(title, level=3),
        ui.List(items=track_items) if track_items else ui.Empty("No tracks found."),
    ], direction="v", gap=2)
