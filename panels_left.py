"""Spotify extension — left panel UI."""
import logging

from imperal_sdk import ui

from app import ext
from panels_demo import render_demo_state
from spotify_config import SP_API_BASE
from app_helpers import _get_access_token, _refresh_access_token
from utils import format_playlist, format_track
from cache_models import SearchModel, PlaylistsModel

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
    refresh="on_event:spotify-extension.connected,spotify-extension.disconnected,spotify-extension.track.liked,spotify-extension.track.unliked,spotify-extension.playlist.created",
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
    if query_param:
        await panel_search_tracks(ctx, query=query_param)

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
                if resp.status_code == 401:
                    token = await _refresh_access_token(ctx)
                    if token:
                        headers["Authorization"] = f"Bearer {token}"
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
                        ttl_seconds=300,
                    )
        except Exception as e:
            log.error("Failed to fetch playlists: %s", e)

    # Web Playback SDK — инициализирует виртуальное Spotify-устройство "Imperal Spotify" в браузере.
    # sandbox=False: HTML инжектируется прямо в страницу (не iframe), JS выполняется в page context.
    # Если панель перерисовывается, window._spotifyPlayer уже существует — восстанавливаем статус без повторной инициализации.
    player_html = f"""<div style="padding:4px 2px;">
<div id="sp-status" style="font-size:10px;color:#888;"></div>
<div id="sp-now-playing" style="display:none;margin-top:6px;">
  <div id="sp-track" style="font-size:12px;font-weight:600;color:#fff;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:240px;"></div>
  <div id="sp-artist" style="font-size:11px;color:#aaa;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:240px;"></div>
</div>
</div>
<script src="https://sdk.scdn.co/spotify-player.js"></script>
<script>
(function() {{
  function setStatus(msg) {{
    var el = document.getElementById('sp-status');
    if (el) el.textContent = msg;
  }}
  function updateNowPlaying(state) {{
    if (!state) return;
    var track = state.track_window && state.track_window.current_track;
    if (!track) return;
    var artists = track.artists.map(function(a) {{ return a.name; }}).join(', ');
    var prefix = state.paused ? '⏸ ' : '▶ ';
    var trackEl = document.getElementById('sp-track');
    var artistEl = document.getElementById('sp-artist');
    var npEl = document.getElementById('sp-now-playing');
    if (trackEl) trackEl.textContent = prefix + track.name;
    if (artistEl) artistEl.textContent = artists;
    if (npEl) npEl.style.display = 'block';
  }}
  if (window._spotifyPlayer) {{
    setStatus('Player ready ✓');
    window._spotifyPlayer.getCurrentState().then(function(state) {{
      if (state) updateNowPlaying(state);
    }});
    return;
  }}
  setStatus('Connecting...');
  window.onSpotifyWebPlaybackSDKReady = function() {{
    var player = new Spotify.Player({{
      name: 'Imperal Spotify',
      getOAuthToken: function(cb) {{ cb('{token}'); }},
      volume: 0.8
    }});
    player.addListener('ready', function() {{
      setStatus('Player ready ✓');
    }});
    player.addListener('not_ready', function() {{
      setStatus('Player disconnected');
      window._spotifyPlayer = null;
    }});
    player.addListener('initialization_error', function(e) {{
      setStatus('Init error: ' + e.message);
    }});
    player.addListener('authentication_error', function(e) {{
      setStatus('Auth error: ' + e.message);
    }});
    player.addListener('account_error', function() {{
      setStatus('Spotify Premium required');
    }});
    player.addListener('player_state_changed', function(state) {{
      updateNowPlaying(state);
    }});
    player.connect();
    window._spotifyPlayer = player;
  }};
  setTimeout(function() {{
    if (!window._spotifyPlayer) setStatus('SDK failed to load');
  }}, 8000);
}})();
</script>"""

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
        ui.Html(content=player_html, sandbox=False),
        ui.Header("Spotify", level=3),
        ui.Input(
            placeholder="Search tracks...",
            param_name="query",
            on_submit=ui.Call("__panel__spotify"),
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
