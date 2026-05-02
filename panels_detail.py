"""Spotify extension — right detail panel."""
from imperal_sdk import ui

from app import ext
from spotify_config import DEMO_STATE_COLLECTION
from cache_models import DetailModel


@ext.panel(
    "spotify_detail",
    slot="right",
    title="Spotify",
    icon="Music",
    min_width=260,
    max_width=480,
    refresh="on_event:panel.playlist_opened,panel.liked_tracks_opened,panel.recent_tracks_opened,panel.profile_opened",
)
async def panel_spotify_detail(ctx, **kwargs):
    """Right panel: shows playlist/profile details based on detail_type in store."""
    detail_type = ""
    try:
        page = await ctx.store.query(DEMO_STATE_COLLECTION, where={"user_id": ctx.user.imperal_id})
        if page.data:
            detail_type = page.data[0].data.get("detail_type", "")
    except Exception:
        pass

    if not detail_type:
        return ui.Empty("Select a playlist or profile from the sidebar.", icon="Music")

    detail = {}
    try:
        detail_cache = await ctx.cache.get(key="detail", model=DetailModel)
        if detail_cache:
            detail = detail_cache.model_dump()
    except Exception:
        pass

    if not detail:
        return ui.Empty("No data loaded.", icon="Music")

    detail_type_cached = detail.get("type")
    title = detail.get("title", "")

    if detail_type_cached == "profile":
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
        ui.List(items=track_items) if track_items else ui.Empty("No tracks found."),
    ], direction="v", gap=2)
