"""Spotify extension — UI panel registration."""
from imperal_sdk import ui

from app import ext
from spotify_config import SP_API_BASE
from utils import format_playlist
from handlers.auth import get_access_token, get_auth_headers


# ── Left panel ────────────────────────────────────────────────────────────────

@ext.panel(
    "spotify",
    slot="left",
    title="Spotify",
    icon="Music",
    default_width=280,
    min_width=220,
    max_width=400,
    refresh="on_event:spotify.connected,spotify.disconnected,track.liked,track.unliked,playlist.created",
)
async def panel_spotify(ctx, **kwargs):
    try:
        token = await get_access_token(ctx)
    except Exception:
        token = None

    if not token:
        return ui.Stack([
            ui.Header("Spotify", level=3),
            ui.Alert("Not connected. Click below to link your Spotify account.", type="warn"),
            ui.Button("Connect Spotify", variant="primary", icon="Music",
                      on_click=ui.Call("connect_spotify")),
        ], direction="v", gap=2)

    skeleton = getattr(ctx, "skeleton_data", None) or {}

    # Search results from skeleton
    search_data = skeleton.get("spotify_search") or {}
    search_tracks = search_data.get("tracks", [])
    search_query = search_data.get("query", "")

    # Load playlists — use skeleton cache, fetch if missing
    playlists = skeleton.get("spotify_playlists") or []
    if not playlists:
        try:
            headers = await get_auth_headers(ctx)
            resp = await ctx.http.get(
                f"{SP_API_BASE}/me/playlists",
                headers=headers,
                params={"limit": 50},
            )
            if resp.ok:
                playlists = [format_playlist(p) for p in (resp.json().get("items") or [])]
                await ctx.skeleton.update("spotify_playlists", playlists)
        except Exception:
            playlists = []

    # Build playlist list items for accordion
    playlist_items = [
        ui.ListItem(
            id=p["id"],
            title=p["title"],
            subtitle=f"{p['track_count']} tracks",
            avatar=p["image_url"],
            on_click=ui.Call("open_playlist", playlist_id=p["id"], playlist_name=p["title"]),
        )
        for p in playlists
    ]

    # Build search result items
    search_result_items = [
        ui.ListItem(
            id=t["id"],
            title=t["title"],
            subtitle=t["artist"],
            meta=t["duration"],
            avatar=t["album_art"],
            actions=[{"icon": "Play", "on_click": ui.Call("play_track", track_id=t["id"])}],
        )
        for t in search_tracks
    ]

    children = [
        ui.Header("Spotify", level=3),
        ui.Input(
            placeholder="Search tracks...",
            param_name="query",
            on_submit=ui.Call("panel_search_tracks"),
        ),
    ]

    if search_result_items:
        children.append(ui.Text(f'Results for "{search_query}"', variant="muted"))
        children.append(ui.List(items=search_result_items))
        children.append(ui.Divider())

    children.append(
        ui.Accordion(sections=[
            {
                "id": "playlists",
                "title": "My Playlists",
                "children": [ui.List(items=playlist_items)] if playlist_items else [ui.Empty("No playlists found.")],
            },
            {
                "id": "liked",
                "title": "Liked Tracks",
                "children": [
                    ui.Button("Open in panel", variant="secondary", size="sm",
                              on_click=ui.Call("open_liked_tracks")),
                ],
            },
            {
                "id": "recent",
                "title": "Recent Tracks",
                "children": [
                    ui.Button("Open in panel", variant="secondary", size="sm",
                              on_click=ui.Call("open_recent_tracks")),
                ],
            },
        ])
    )

    children += [
        ui.Divider(),
        ui.Button("My Profile", variant="ghost", size="sm", icon="User",
                  on_click=ui.Call("open_profile")),
        ui.Button("Disconnect", variant="danger", size="sm", icon="LogOut",
                  on_click=ui.Call("disconnect_spotify")),
    ]

    return ui.Stack(children, direction="v", gap=2)


# ── Right detail panel ────────────────────────────────────────────────────────

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
    detail = (getattr(ctx, "skeleton_data", None) or {}).get("spotify_detail") or {}
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

    # Track list (playlist / liked / recent)
    tracks = detail.get("tracks") or []
    track_items = [
        ui.ListItem(
            id=t["id"],
            title=t["title"],
            subtitle=t["artist"],
            meta=t["duration"],
            avatar=t["album_art"],
            actions=[{"icon": "Play", "on_click": ui.Call("play_track", track_id=t["id"])}],
        )
        for t in tracks
    ]

    return ui.Stack([
        ui.Header(title, level=3),
        ui.List(items=track_items) if track_items else ui.Empty("No tracks found."),
    ], direction="v", gap=2)
