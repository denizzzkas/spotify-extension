"""Spotify extension — left panel UI."""
import logging

from imperal_sdk import ui

from app import ext, NowPlayingModel
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

    try:
        now_playing = await ctx.cache.get(key="now_playing", model=NowPlayingModel)
    except Exception:
        now_playing = None

    np_album_art = now_playing.album_art if now_playing else ""
    np_title = now_playing.title if now_playing else ""
    np_artist = now_playing.artist if now_playing else ""
    np_is_playing = now_playing.is_playing if now_playing else False
    track_to_play = f"spotify:track:{now_playing.id}" if (now_playing and now_playing.id) else ""
    np_display = "block" if (now_playing and now_playing.id) else "none"
    art_display = "block" if np_album_art else "none"
    play_icon = "⏸" if np_is_playing else "▶"

    player_html = f"""<div style="padding:4px 0;">
<div id="sp-status" style="font-size:10px;color:#888;min-height:14px;"></div>
<div id="sp-player-ui" style="display:{np_display};margin-top:6px;">
  <img id="sp-album-art" src="{np_album_art}"
       style="width:100%;border-radius:6px;object-fit:cover;display:{art_display};">
  <div id="sp-track-name"
       style="font-size:13px;font-weight:600;color:#fff;margin-top:6px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">{np_title}</div>
  <div id="sp-artist-name"
       style="font-size:11px;color:#aaa;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">{np_artist}</div>
  <div style="display:flex;justify-content:center;align-items:center;gap:12px;margin-top:10px;">
    <button onclick="if(window._spotifyPlayer)window._spotifyPlayer.previousTrack();"
            style="background:none;border:none;color:#aaa;cursor:pointer;font-size:20px;padding:4px;line-height:1;">&#9198;</button>
    <button id="sp-play-btn"
            onclick="if(window._spotifyPlayer)window._spotifyPlayer.togglePlay();"
            style="background:#1DB954;border:none;color:#000;cursor:pointer;border-radius:50%;width:38px;height:38px;font-size:16px;display:inline-flex;align-items:center;justify-content:center;">{play_icon}</button>
    <button onclick="if(window._spotifyPlayer)window._spotifyPlayer.nextTrack();"
            style="background:none;border:none;color:#aaa;cursor:pointer;font-size:20px;padding:4px;line-height:1;">&#9197;</button>
  </div>
</div>
</div>
<script src="https://sdk.scdn.co/spotify-player.js"></script>
<script>
(function() {{
  var TOKEN = '{token}';
  var TRACK_TO_PLAY = '{track_to_play}';

  function setStatus(msg) {{
    var el = document.getElementById('sp-status');
    if (el) el.textContent = msg;
  }}

  function updateUI(state) {{
    if (!state) return;
    var track = state.track_window && state.track_window.current_track;
    if (!track) return;
    var nameEl = document.getElementById('sp-track-name');
    var artistEl = document.getElementById('sp-artist-name');
    var artEl = document.getElementById('sp-album-art');
    var uiEl = document.getElementById('sp-player-ui');
    var btnEl = document.getElementById('sp-play-btn');
    if (nameEl) nameEl.textContent = track.name;
    if (artistEl) artistEl.textContent = track.artists.map(function(a) {{ return a.name; }}).join(', ');
    if (artEl && track.album && track.album.images && track.album.images[0]) {{
      artEl.src = track.album.images[0].url;
      artEl.style.display = 'block';
    }}
    if (uiEl) uiEl.style.display = 'block';
    if (btnEl) btnEl.textContent = state.paused ? '▶' : '⏸';
  }}

  function doPlay(deviceId) {{
    if (!TRACK_TO_PLAY || TRACK_TO_PLAY === window._lastPlayedTrack) return;
    window._lastPlayedTrack = TRACK_TO_PLAY;
    fetch('https://api.spotify.com/v1/me/player/play?device_id=' + deviceId, {{
      method: 'PUT',
      headers: {{'Authorization': 'Bearer ' + TOKEN, 'Content-Type': 'application/json'}},
      body: JSON.stringify({{uris: [TRACK_TO_PLAY], position_ms: 0}})
    }}).catch(function(e) {{ setStatus('Play error: ' + e.message); }});
  }}

  if (window._spotifyPlayer && window._spotifyDeviceId) {{
    setStatus('Player ready ✓');
    doPlay(window._spotifyDeviceId);
    window._spotifyPlayer.getCurrentState().then(function(state) {{
      if (state) updateUI(state);
    }});
    return;
  }}

  setStatus('Connecting...');

  window.onSpotifyWebPlaybackSDKReady = function() {{
    var player = new Spotify.Player({{
      name: 'Imperal Spotify',
      getOAuthToken: function(cb) {{ cb(TOKEN); }},
      volume: 0.8
    }});

    player.addListener('initialization_error', function(e) {{ setStatus('Init error: ' + e.message); }});
    player.addListener('authentication_error', function(e) {{ setStatus('Auth error: ' + e.message); }});
    player.addListener('account_error', function() {{ setStatus('Spotify Premium required'); }});
    player.addListener('playback_error', function(e) {{ setStatus('Playback error: ' + e.message); }});

    player.addListener('ready', function(data) {{
      window._spotifyDeviceId = data.device_id;
      setStatus('Player ready ✓');
      setTimeout(function() {{ doPlay(data.device_id); }}, 1000);
    }});

    player.addListener('not_ready', function() {{
      setStatus('Player disconnected');
      window._spotifyDeviceId = null;
    }});

    player.addListener('player_state_changed', function(state) {{
      if (state) updateUI(state);
    }});

    player.connect();
    window._spotifyPlayer = player;
  }};

  setTimeout(function() {{
    if (!window._spotifyPlayer) setStatus('SDK load timeout');
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
