"""Spotify extension — left panel UI."""
import logging

from imperal_sdk import ui

from app import ext, NowPlayingModel
from panels_demo import render_demo_state
from spotify_config import SP_API_BASE
from app_helpers import _get_access_token, _refresh_access_token, _spotify_call
from utils import format_playlist, format_track
from cache_models import SearchModel, PlaylistsModel
from player_html import build_player_html

log = logging.getLogger("spotify.panels.left")


async def _get_auth_headers(ctx) -> dict | None:
    """Get auth headers with token refresh if needed."""
    token = await _get_access_token(ctx)
    if not token:
        return None
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


async def panel_search_tracks(ctx, query: str = "", limit: int = 20) -> dict:
    """Search tracks for panel display using the centralized Spotify call helper."""
    if not query:
        return {}

    try:
        resp, err = await _spotify_call(
            ctx, "get", f"{SP_API_BASE}/search",
            params={"q": query, "type": "track", "limit": limit},
        )
        if err or not resp or not resp.ok:
            log.warning("panel_search_tracks: search failed for %r (err=%s, status=%s)",
                        query, err, resp.status_code if resp else None)
            return {"error": True}

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
        return {"error": True}


@ext.panel(
    "spotify",
    slot="left",
    title="Spotify",
    icon="Music",
    default_width=280,
    min_width=220,
    max_width=400,
    refresh="on_event:spotify.connected,spotify.disconnected,spotify.track.liked,spotify.track.unliked,spotify.playlist.created,spotify.player.shuffle,spotify.track.played",
)
async def panel_spotify(ctx, **kwargs):
    """Left sidebar panel showing authentication state, playlists, and search."""
    query_param = kwargs.get("query", "")

    try:
        token = await _get_access_token(ctx)
    except Exception:
        token = None

    if not token:
        return await render_demo_state(ctx)

    # Authenticated state: run search if query param provided, then load cache
    search_error = False
    if query_param:
        result = await panel_search_tracks(ctx, query=query_param)
        search_error = result.get("error", False)

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
                all_playlists = []
                url = f"{SP_API_BASE}/me/playlists"
                fetch_params = {"limit": 50}
                while url:
                    resp = await ctx.http.get(url, headers=headers, params=fetch_params)
                    if resp.status_code == 401:
                        token = await _refresh_access_token(ctx)
                        if token:
                            headers["Authorization"] = f"Bearer {token}"
                            resp = await ctx.http.get(url, headers=headers, params=fetch_params)
                    if not resp.ok:
                        break
                    data = resp.json()
                    all_playlists.extend([format_playlist(p) for p in (data.get("items") or [])])
                    url = data.get("next")
                    fetch_params = {}
                if all_playlists:
                    playlists = all_playlists
                    await ctx.cache.set(
                        key="playlists",
                        value=PlaylistsModel(items=playlists),
                        ttl_seconds=300,
                    )
        except Exception as e:
            log.error("Failed to fetch playlists: %s", e)

    try:
        now_playing = await ctx.cache.get(key="now_playing", model=NowPlayingModel)
    except Exception:
        now_playing = None

    np_album_art = now_playing.album_art if now_playing else ""
    np_title = now_playing.title if now_playing else ""
    np_artist = now_playing.artist if now_playing else ""
    np_is_playing = now_playing.is_playing if now_playing else False
    np_shuffle = now_playing.shuffle if now_playing else False
    np_is_liked = now_playing.is_liked if now_playing else False
    track_to_play = f"spotify:track:{now_playing.id}" if (now_playing and now_playing.id) else ""
    np_display = "block" if (now_playing and now_playing.id) else "none"
    art_display = "block" if np_album_art else "none"
    play_icon = "⏸" if np_is_playing else "▶"
    like_icon = "♥" if np_is_liked else "♡"
    shuffle_variant = "primary" if np_shuffle else "ghost"

    player_html = build_player_html(
        token=token,
        track_to_play=track_to_play,
        np_album_art=np_album_art,
        np_title=np_title,
        np_artist=np_artist,
        np_display=np_display,
        art_display=art_display,
    )

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

    controls = ui.Stack([
        ui.Button(like_icon, size="sm", variant="primary" if np_is_liked else "ghost", on_click=ui.Call("sp_like")),
        ui.Button("⏮", size="sm", on_click=ui.Call("sp_prev")),
        ui.Button(play_icon, size="sm", on_click=ui.Call("sp_play_pause")),
        ui.Button("⏭", size="sm", on_click=ui.Call("sp_next")),
        ui.Button("⇄", size="sm", variant=shuffle_variant, on_click=ui.Call("sp_shuffle")),
    ], direction="h", gap=1)

    children = [
        ui.Html(content=player_html, sandbox=False),
        controls,
        ui.Header("Spotify", level=3),
        ui.Input(
            placeholder="Search tracks...",
            param_name="query",
            value=search_query,
            on_submit=ui.Call("__panel__spotify"),
        ),
    ]

    if search_error:
        children.append(ui.Text("Search failed — check your Spotify connection.", variant="caption"))
    elif search_result_items:
        children.append(ui.Text(f'Results for "{search_query}"', variant="caption"))
        children.append(ui.List(items=search_result_items))
        children.append(ui.Divider())
    elif query_param and not search_error:
        children.append(ui.Text(f'No results for "{query_param}"', variant="caption"))

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
                "children": [ui.Button("Open", size="sm", on_click=ui.Call("__panel__spotify_detail", detail_type="liked_tracks"))],
            },
            {
                "id": "recent_tracks",
                "title": "Recent Tracks",
                "children": [ui.Button("Open", size="sm", on_click=ui.Call("__panel__spotify_detail", detail_type="recent_tracks"))],
            },
            {
                "id": "profile",
                "title": "My Profile",
                "children": [ui.Button("Open", size="sm", on_click=ui.Call("__panel__spotify_detail", detail_type="profile"))],
            },
        ])
    )

    return ui.Stack(children, direction="v", gap=2)
