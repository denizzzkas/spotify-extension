"""Spotify extension — left panel UI."""
import logging

from imperal_sdk import ui

from app import ext, NowPlayingModel, DemoStateModel
from spotify_config import SP_API_BASE
from app_helpers import _get_access_token, _refresh_access_token
from utils import format_playlist, format_track
from cache_models import SearchModel, PlaylistsModel
from demo_data import DEMO_TRACKS, DEMO_PLAYLIST_ID, DEMO_PLAYLIST_NAME

log = logging.getLogger("spotify.panels.left")


async def _get_auth_headers(ctx) -> dict | None:
    """Get auth headers with token refresh if needed."""
    token = await _get_access_token(ctx)
    if not token:
        return None
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


async def panel_search_tracks(ctx, query: str = "", limit: int = 20) -> dict:
    """Search tracks via HTTP for panel display."""
    if not query:
        return {}

    try:
        headers = await _get_auth_headers(ctx)
        if not headers:
            return {}

        resp = await ctx.http.get(
            f"{SP_API_BASE}/search",
            headers=headers,
            params={"q": query, "type": "track", "limit": limit},
        )

        if resp.status_code == 401:
            token = await _refresh_access_token(ctx)
            if token:
                headers["Authorization"] = f"Bearer {token}"
                resp = await ctx.http.get(
                    f"{SP_API_BASE}/search",
                    headers=headers,
                    params={"q": query, "type": "track", "limit": limit},
                )

        if resp.ok:
            raw_list = (resp.json().get("tracks") or {}).get("items", [])
            tracks = [format_track(t) for t in raw_list]
            await ctx.cache.set(
                key="search",
                value=SearchModel(query=query, tracks=tracks),
                ttl_seconds=60,
            )
            return {"count": len(tracks)}

    except Exception as e:
        log.error("panel_search_tracks failed: %s", e)

    return {}


@ext.panel(
    "spotify",
    slot="left",
    title="Spotify",
    icon="Music",
    default_width=280,
    min_width=220,
    max_width=400,
    refresh="on_event:spotify-extension.connected,spotify-extension.disconnected,spotify-extension.track.liked,spotify-extension.track.unliked,spotify-extension.playlist.created,spotify-extension.track.played,spotify-extension.playlist.played",
)
async def panel_spotify(ctx, **kwargs):
    """Left sidebar panel showing authentication state, playlists, and search."""
    try:
        token = await _get_access_token(ctx)
    except Exception:
        token = None

    if not token:
        return await _render_demo_state(ctx)

    # Authenticated state: load cached search and playlists
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
            headers = await _get_auth_headers(ctx)
            if headers:
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
        except Exception as e:
            log.error("Failed to fetch playlists: %s", e)

    # Build UI components
    playlist_items = [
        ui.ListItem(
            id=p["id"],
            title=p["title"],
            subtitle=f"{p['track_count']} tracks",
            avatar=ui.Avatar(src=p["image_url"], fallback=(p["title"] or "?")[0].upper()),
            on_click=ui.Call("__panel__spotify_detail", detail_type="tracks", playlist_id=p["id"], playlist_name=p["title"]),
        )
        for p in playlists
    ]

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
                "id": "my_playlists",
                "title": "My Playlists",
                "children": [ui.List(items=playlist_items)] if playlist_items else [ui.Empty("No playlists")],
            },
            {
                "id": "liked_tracks",
                "title": "Liked Tracks",
                "children": [ui.Button("Open", size="sm", on_click=ui.Call("open_liked_tracks"))],
            },
            {
                "id": "recent_tracks",
                "title": "Recent Tracks",
                "children": [ui.Button("Open", size="sm", on_click=ui.Call("open_recent_tracks"))],
            },
            {
                "id": "profile",
                "title": "My Profile",
                "children": [ui.Button("Open", size="sm", on_click=ui.Call("open_profile"))],
            },
        ])
    )

    return ui.Stack(children, direction="v", gap=2)


async def _render_demo_state(ctx) -> ui.Stack:
    """Render demo/unauthenticated state with demo player."""
    client_id = ""
    _secrets_error = ""
    try:
        secret = await ctx.secrets.get("spotify_client_id")
        if secret:
            client_id = secret
    except Exception as e:
        _secrets_error = f"{type(e).__name__}: {e}"
        log.error("ctx.secrets.get failed: %s", _secrets_error)

    children = [ui.Header("Spotify", level=3)]

    if not client_id:
        msg = "Spotify credentials are not configured. Add client_id and client_secret in extension settings."
        if _secrets_error:
            msg += f" [debug: {_secrets_error}]"
        children.append(ui.Alert(msg, type="error"))
    else:
        children += [
            ui.Alert("Not connected. Click below to link your Spotify account.", type="warn"),
            ui.Button("Connect Spotify", variant="primary", icon="Music",
                      on_click=ui.Call("connect_spotify")),
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
                    on_click=ui.Call("__panel__spotify_detail", detail_type="tracks", playlist_id=DEMO_PLAYLIST_ID, playlist_name=DEMO_PLAYLIST_NAME),
                ),
            ])],
        }])
    )

    # Load demo player state from cache only (session-scoped with TTL)
    demo_now_playing = None
    demo_shuffle = False

    try:
        demo_now_playing = await ctx.cache.get(key="now_playing", model=NowPlayingModel)
    except Exception:
        pass

    # Read shuffle state from demo_state cache
    if demo_now_playing:
        try:
            demo_state_cached = await ctx.cache.get(key="demo_state", model=DemoStateModel)
            if demo_state_cached:
                demo_shuffle = demo_state_cached.shuffle
        except Exception:
            pass

    now_playing = demo_now_playing.model_dump() if demo_now_playing else None

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
                ui.Button("", icon="Shuffle", size="sm",
                          variant="secondary" if demo_shuffle else "ghost",
                          on_click=ui.Call("demo_shuffle")),
            ], direction="h", gap=1, wrap=False),
        ]
        if preview_url:
            children.append(ui.Audio(src=preview_url, title="30s preview"))

    return ui.Stack(children, direction="v", gap=2)
