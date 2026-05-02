"""Spotify extension — right detail panel."""
from imperal_sdk import ui

from app import ext
from spotify_config import DEMO_STATE_COLLECTION
from cache_models import DetailModel
from demo_data import DEMO_TRACKS, DEMO_PLAYLIST_NAME


@ext.panel(
    "spotify_detail",
    slot="right",
    title="Spotify",
    icon="Music",
    default_width=320,
    min_width=260,
    max_width=480,
    refresh="manual",
)
async def panel_spotify_detail(ctx, **kwargs):
    detail = {}
    try:
        page = await ctx.store.query(DEMO_STATE_COLLECTION, where={"user_id": ctx.user.imperal_id})
        if page.data and page.data[0].data.get("active") and page.data[0].data.get("detail_open"):
            try:
                detail_cache = await ctx.cache.get(key="detail", model=DetailModel)
                if detail_cache:
                    detail = detail_cache.model_dump()
                else:
                    detail = {"type": "tracks", "title": DEMO_PLAYLIST_NAME, "tracks": DEMO_TRACKS}
            except Exception:
                detail = {"type": "tracks", "title": DEMO_PLAYLIST_NAME, "tracks": DEMO_TRACKS}
    except Exception:
        pass
    detail_type = detail.get("type")
    title = detail.get("title", "")

    if not detail_type:
        return ui.Empty("Select a playlist or profile from the sidebar.", icon="Music")

    if detail_type == "profile":
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
    is_demo = title == DEMO_PLAYLIST_NAME
    track_items = [
        ui.ListItem(
            id=t["id"],
            title=t["title"],
            subtitle=t["artist"],
            meta=t["duration"],
            avatar=ui.Avatar(src=t["album_art"], fallback=(t["title"] or "?")[0].upper()),
            actions=[{"icon": "Play", "on_click": ui.Call(
                "demo_play_track" if is_demo else "play_track", track_id=t["id"],
            )}],
        )
        for t in tracks
    ]

    return ui.Stack([
        ui.Header(title, level=3),
        ui.List(items=track_items) if track_items else ui.Empty("No tracks found."),
    ], direction="v", gap=2)
