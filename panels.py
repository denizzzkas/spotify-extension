"""Spotify extension — UI panel registration."""
from imperal_sdk import ui

from app import ext
from spotify_config import SP_API_BASE, SP_REDIRECT_URI, DEMO_STATE_COLLECTION
from utils import format_playlist
from handlers.auth import get_access_token, get_auth_headers, build_auth_url, create_oauth_state
from cache_models import NowPlayingModel, SearchModel, DetailModel, PlaylistsModel, QueueModel
from demo_data import DEMO_TRACKS, DEMO_PLAYLIST_ID, DEMO_PLAYLIST_NAME


# ── Left panel ────────────────────────────────────────────────────────────────

@ext.panel(
    "spotify",
    slot="left",
    title="Spotify",
    icon="Music",
    default_width=280,
    min_width=220,
    max_width=400,
    refresh="on_event:spotify.connected,spotify.disconnected,track.liked,track.unliked,playlist.created,track.played,playlist.played",
)
async def panel_spotify(ctx, **kwargs):
    try:
        token = await get_access_token(ctx)
    except Exception:
        token = None

    if not token:
        try:
            client_id = ctx.config.get("spotify.client_id", "")
        except Exception:
            client_id = ""

        demo_now_playing = None
        is_demo_active = False
        try:
            demo_now_playing = await ctx.cache.get(key="now_playing", model=NowPlayingModel)
            demo_queue = await ctx.cache.get(key="queue", model=QueueModel)
            is_demo_active = bool(demo_queue and demo_queue.playlist_id == DEMO_PLAYLIST_ID)
        except Exception:
            pass

        if not is_demo_active:
            try:
                page = await ctx.store.query(DEMO_STATE_COLLECTION, where={"user_id": ctx.user.imperal_id})
                if page.data:
                    state = page.data[0].data
                    if state.get("active"):
                        track = DEMO_TRACKS[state.get("track_index", 0)]
                        demo_now_playing = NowPlayingModel(**track, is_playing=state.get("is_playing", True))
                        is_demo_active = True
            except Exception:
                pass

        now_playing = demo_now_playing.model_dump() if (demo_now_playing and is_demo_active) else None

        children = [ui.Header("Spotify", level=3)]

        if not client_id:
            children.append(ui.Alert(
                "Spotify credentials are not configured. Add client_id and client_secret in extension settings.",
                type="error",
            ))
        else:
            state = await create_oauth_state(ctx)
            auth_url = build_auth_url(client_id, SP_REDIRECT_URI, state)
            children += [
                ui.Alert("Not connected. Click below to link your Spotify account.", type="warn"),
                ui.Button("Connect Spotify", variant="primary", icon="Music",
                          on_click=ui.Open(auth_url)),
            ]

        children.append(
            ui.Accordion(sections=[{
                "id": "demo_playlists",
                "title": "My Playlists",
                "children": [ui.List(items=[
                    ui.ListItem(
                        id=DEMO_PLAYLIST_ID,
                        title=DEMO_PLAYLIST_NAME,
                        subtitle=f"{len(DEMO_TRACKS)} tracks",
                        avatar=ui.Avatar(src=DEMO_TRACKS[0]["album_art"], fallback="D"),
                        on_click=ui.Call("open_demo_playlist"),
                    ),
                ])],
            }])
        )

        if now_playing:
            is_playing = now_playing.get("is_playing", True)
            preview_url = now_playing.get("preview_url", "")
            children += [
                ui.Divider(),
                ui.Image(src=now_playing.get("album_art", ""), width="100%", object_fit="cover"),
                ui.Text(now_playing.get("title", ""), variant="heading"),
                ui.Text(now_playing.get("artist", ""), variant="caption"),
                ui.Stack([
                    ui.Button("", icon="SkipBack", variant="ghost", size="sm",
                              on_click=ui.Call("demo_prev_track")),
                    ui.Button("", icon="Pause" if is_playing else "Play", variant="ghost", size="sm",
                              on_click=ui.Call("demo_pause")),
                    ui.Button("", icon="SkipForward", variant="ghost", size="sm",
                              on_click=ui.Call("demo_next_track")),
                ], direction="h", gap=1, wrap=False),
            ]
            if preview_url:
                children.append(ui.Audio(src=preview_url, title="30s preview"))

        return ui.Stack(children, direction="v", gap=2)

    try:
        search_cache = await ctx.cache.get(key="search", model=SearchModel)
    except Exception:
        search_cache = None
    search_data = search_cache.model_dump() if search_cache else {}
    search_tracks = search_data.get("tracks", [])
    search_query = search_data.get("query", "")

    try:
        playlists_cache = await ctx.cache.get(key="playlists", model=PlaylistsModel)
    except Exception:
        playlists_cache = None
    playlists = playlists_cache.items if playlists_cache else []
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
                await ctx.cache.set(
                    key="playlists",
                    value=PlaylistsModel(items=playlists),
                    ttl_seconds=120,
                )
        except Exception:
            playlists = []

    # Build playlist list items for accordion
    playlist_items = [
        ui.ListItem(
            id=p["id"],
            title=p["title"],
            subtitle=f"{p['track_count']} tracks",
            avatar=ui.Avatar(src=p["image_url"], fallback=(p["title"] or "?")[0].upper()),
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
            avatar=ui.Avatar(src=t["album_art"], fallback=(t["title"] or "?")[0].upper()),
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
        children.append(ui.Text(f'Results for "{search_query}"', variant="caption"))
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

    try:
        now_playing_cache = await ctx.cache.get(key="now_playing", model=NowPlayingModel)
    except Exception:
        now_playing_cache = None
    now_playing = now_playing_cache.model_dump() if now_playing_cache else None
    children += [
        ui.Divider(),
        ui.Button("My Profile", variant="ghost", size="sm", icon="User",
                  on_click=ui.Call("open_profile")),
        ui.Button("Disconnect", variant="danger", size="sm", icon="LogOut",
                  on_click=ui.Call("disconnect_spotify")),
    ]

    if now_playing:
        is_playing = now_playing.get("is_playing", True)
        children += [
            ui.Divider(),
            ui.Image(src=now_playing.get("album_art", ""), width="100%", object_fit="cover"),
            ui.Text(now_playing.get("title", ""), variant="heading"),
            ui.Text(now_playing.get("artist", ""), variant="caption"),
            ui.Stack([
                ui.Button("", icon="SkipBack", variant="ghost", size="sm",
                          on_click=ui.Call("previous_track")),
                ui.Button("", icon="Pause" if is_playing else "Play", variant="ghost", size="sm",
                          on_click=ui.Call("pause_playback" if is_playing else "resume_playback")),
                ui.Button("", icon="SkipForward", variant="ghost", size="sm",
                          on_click=ui.Call("next_track")),
            ], direction="h", gap=1, wrap=False),
        ]

    return ui.Stack(children, direction="v", gap=2)
