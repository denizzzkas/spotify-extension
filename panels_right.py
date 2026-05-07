"""Spotify extension — right detail panel UI."""
import logging

from imperal_sdk import ui

from app import ext, SP_API_BASE, _get_access_token, _refresh_access_token
from cache_models import DetailModel
from demo_data import DEMO_TRACKS, DEMO_PLAYLIST_ID, DEMO_PLAYLIST_NAME
from utils import format_track

log = logging.getLogger("spotify.panels.right")


async def _get_auth_headers(ctx) -> dict | None:
    token = await _get_access_token(ctx)
    if not token:
        return None
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


async def _fetch_playlist_tracks(ctx, playlist_id: str) -> list[dict]:
    """Fetch playlist tracks from Spotify API, with token refresh on 401."""
    try:
        headers = await _get_auth_headers(ctx)
        if not headers:
            return []

        fields = "items(track(id,name,artists,album,duration_ms,preview_url,external_urls,popularity))"
        resp = await ctx.http.get(
            f"{SP_API_BASE}/playlists/{playlist_id}/tracks",
            headers=headers,
            params={"limit": 50, "fields": fields},
        )

        if resp.status_code == 401:
            token = await _refresh_access_token(ctx)
            if token:
                headers["Authorization"] = f"Bearer {token}"
                resp = await ctx.http.get(
                    f"{SP_API_BASE}/playlists/{playlist_id}/tracks",
                    headers=headers,
                    params={"limit": 50, "fields": fields},
                )

        if resp.ok:
            items = resp.json().get("items", [])
            return [format_track(item["track"]) for item in items if item.get("track")]

    except Exception as e:
        log.error("_fetch_playlist_tracks failed: %s", e)

    return []


@ext.panel(
    "spotify_detail",
    slot="right",
    title="Spotify",
    icon="Music",
    default_width=320,
    min_width=260,
    max_width=480,
)
async def panel_spotify_detail(ctx, detail_type: str = "", playlist_id: str = "", playlist_name: str = "", **kwargs):
    """Right panel: loads playlist/profile data from parameters, not from pre-populated cache."""

    if not detail_type:
        return ui.Empty("Select a playlist or profile from the sidebar.", icon="Music")

    if detail_type == "profile":
        return await _render_profile(ctx)

    # Demo mode — load directly from hardcoded demo data
    if playlist_id == DEMO_PLAYLIST_ID:
        return _render_tracks(DEMO_TRACKS, DEMO_PLAYLIST_NAME, play_fn="demo_play_track")

    # Authenticated mode — check cache first, then fetch from API
    if not playlist_id:
        return ui.Empty("No playlist selected.", icon="Music")

    title = playlist_name or "Playlist"

    try:
        cached = await ctx.cache.get(key="detail", model=DetailModel)
        if cached and cached.title == title and cached.tracks:
            return _render_tracks(cached.tracks, cached.title, play_fn="play_track")
    except Exception:
        pass

    tracks = await _fetch_playlist_tracks(ctx, playlist_id)

    if not tracks:
        return ui.Empty("No tracks found.", icon="Music")

    try:
        await ctx.cache.set(
            key="detail",
            value=DetailModel(type="tracks", title=title, tracks=tracks),
            ttl_seconds=120,
        )
    except Exception as e:
        log.error("Failed to cache playlist tracks: %s", e)

    return _render_tracks(tracks, title, play_fn="play_track")


async def _render_profile(ctx) -> ui.Stack:
    """Render profile detail — reads from cache (populated by open_profile handler)."""
    try:
        cached = await ctx.cache.get(key="detail", model=DetailModel)
        if cached and cached.type == "profile":
            profile = cached.profile or {}
            items = [
                ui.ListItem(id="name", title="Name", subtitle=profile.get("display_name", "")),
                ui.ListItem(id="email", title="Email", subtitle=profile.get("email", "")),
                ui.ListItem(id="plan", title="Plan", subtitle=profile.get("product", "free").capitalize()),
                ui.ListItem(id="followers", title="Followers", subtitle=str(profile.get("followers", 0))),
            ]
            return ui.Stack([
                ui.Header("My Profile", level=3),
                ui.List(items=items),
            ], direction="v", gap=2)
    except Exception as e:
        log.error("_render_profile failed: %s", e)

    return ui.Empty("Profile not loaded.", icon="User")


def _render_tracks(tracks: list[dict], title: str, play_fn: str = "play_track") -> ui.Stack:
    """Render track list with the correct play function for demo or authenticated mode."""
    track_items = [
        ui.ListItem(
            id=t["id"],
            title=t["title"],
            subtitle=t["artist"],
            meta=t["duration"],
            avatar=ui.Avatar(src=t["album_art"], fallback=(t["title"] or "?")[0].upper()),
            actions=[{"icon": "Play", "on_click": ui.Call(play_fn, track_id=t["id"])}],
        )
        for t in tracks
    ]

    return ui.Stack([
        ui.Header(title, level=3),
        ui.List(items=track_items) if track_items else ui.Empty("No tracks found."),
    ], direction="v", gap=2)
