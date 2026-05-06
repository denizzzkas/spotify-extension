"""Spotify extension — right detail panel UI."""
import logging

from imperal_sdk import ui

from app import ext
from cache_models import DetailModel

log = logging.getLogger("spotify.panels.right")


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
    """Right panel: shows playlist/profile details based on parameters."""

    if not detail_type:
        return ui.Empty("Select a playlist or profile from the sidebar.", icon="Music")

    detail = {}
    try:
        detail_cache = await ctx.cache.get(key="detail", model=DetailModel)
        if detail_cache:
            detail = detail_cache.model_dump()
    except Exception as e:
        log.error("Failed to get detail cache: %s", e)

    if not detail:
        return ui.Empty("No data loaded.", icon="Music")

    detail_type_cached = detail.get("type")
    title = detail.get("title", "")

    if detail_type_cached == "profile":
        return _render_profile_detail(detail, title)

    return _render_tracks_detail(detail, title)


def _render_profile_detail(detail: dict, title: str) -> ui.Stack:
    """Render profile detail view."""
    profile = detail.get("profile") or {}
    items = [
        ui.ListItem(id="name", title="Name", subtitle=profile.get("display_name", "")),
        ui.ListItem(id="email", title="Email", subtitle=profile.get("email", "")),
        ui.ListItem(id="plan", title="Plan", subtitle=profile.get("product", "free").capitalize()),
        ui.ListItem(id="followers", title="Followers", subtitle=str(profile.get("followers", 0))),
    ]
    return ui.Stack([
        ui.Header(title, level=3),
        ui.List(items=items),
    ], direction="v", gap=2)


def _render_tracks_detail(detail: dict, title: str) -> ui.Stack:
    """Render tracks/playlist detail view."""
    tracks = detail.get("tracks") or []
    track_items = [
        ui.ListItem(
            id=t["id"],
            title=t["title"],
            subtitle=t["artist"],
            meta=t["duration"],
            avatar=ui.Avatar(src=t["album_art"], fallback=(t["title"] or "?")[0].upper()),
            actions=[{"icon": "Play", "on_click": ui.Call("play_track", track_id=t["id"])}],
        )
        for t in tracks
    ]

    return ui.Stack([
        ui.Header(title, level=3),
        ui.List(items=track_items) if track_items else ui.Empty("No tracks"),
    ], direction="v", gap=2)
