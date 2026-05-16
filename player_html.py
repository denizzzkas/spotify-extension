"""Spotify Web Playback SDK HTML/JS widget for the left panel."""


def build_player_html(
    token: str,
    track_to_play: str,
    np_album_art: str,
    np_title: str,
    np_artist: str,
    np_display: str,
    art_display: str,
) -> str:
    return f"""<div style="padding:4px 0;">
<div id="sp-status" style="font-size:10px;color:#888;min-height:14px;"></div>
<div id="sp-player-ui" style="display:{np_display};margin-top:6px;">
  <img id="sp-album-art" src="{np_album_art}"
       style="width:100%;border-radius:6px;object-fit:cover;display:{art_display};">
  <div id="sp-track-name"
       style="font-size:13px;font-weight:600;color:#fff;margin-top:6px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">{np_title}</div>
  <div id="sp-artist-name"
       style="font-size:11px;color:#aaa;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">{np_artist}</div>

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
    window._spotifyPaused = !!state.paused;
    if (btnEl) btnEl.textContent = state.paused ? '▶' : '⏸';
    if (track.id && track.id !== window._spotifyCurrentTrackId) {{
      window._spotifyCurrentTrackId = track.id;
      fetch('https://api.spotify.com/v1/me/tracks/contains?ids=' + track.id, {{
        headers: {{'Authorization': 'Bearer ' + TOKEN}}
      }}).then(function(r) {{ return r.json(); }}).then(function(data) {{
        window._currentTrackLiked = !!(data && data[0]);
        var lb = document.getElementById('sp-like-btn');
        if (lb) {{ lb.textContent = window._currentTrackLiked ? '♥' : '♡'; lb.style.color = window._currentTrackLiked ? '#1DB954' : '#aaa'; }}
      }}).catch(function() {{}});
    }}
  }}

  function doPlay(deviceId) {{
    if (!TRACK_TO_PLAY || TRACK_TO_PLAY === window._lastPlayedTrack) return;
    window._lastPlayedTrack = TRACK_TO_PLAY;
    fetch('https://api.spotify.com/v1/me/player', {{
      method: 'PUT',
      headers: {{'Authorization': 'Bearer ' + TOKEN, 'Content-Type': 'application/json'}},
      body: JSON.stringify({{device_ids: [deviceId], play: false}})
    }}).then(function() {{
      return fetch('https://api.spotify.com/v1/me/player/play?device_id=' + deviceId, {{
        method: 'PUT',
        headers: {{'Authorization': 'Bearer ' + TOKEN, 'Content-Type': 'application/json'}},
        body: JSON.stringify({{uris: [TRACK_TO_PLAY], position_ms: 0}})
      }});
    }}).catch(function(e) {{ setStatus('Play error: ' + e.message); }});
  }}

  window.spPrev = function() {{
    fetch('https://api.spotify.com/v1/me/player/previous', {{
      method: 'POST', headers: {{'Authorization': 'Bearer ' + TOKEN}}
    }}).catch(function(e) {{ setStatus('Error: ' + e.message); }});
  }};
  window.spNext = function() {{
    fetch('https://api.spotify.com/v1/me/player/next', {{
      method: 'POST', headers: {{'Authorization': 'Bearer ' + TOKEN}}
    }}).catch(function(e) {{ setStatus('Error: ' + e.message); }});
  }};
  window.spPlayPause = function() {{
    var url = window._spotifyPaused
      ? 'https://api.spotify.com/v1/me/player/play'
      : 'https://api.spotify.com/v1/me/player/pause';
    fetch(url, {{
      method: 'PUT', headers: {{'Authorization': 'Bearer ' + TOKEN}}
    }}).then(function() {{
      window._spotifyPaused = !window._spotifyPaused;
      var btn = document.getElementById('sp-play-btn');
      if (btn) btn.textContent = window._spotifyPaused ? '▶' : '⏸';
    }}).catch(function(e) {{ setStatus('Error: ' + e.message); }});
  }};
  window.spShuffle = function() {{
    window._shuffleOn = !window._shuffleOn;
    var btn = document.getElementById('sp-shuffle-btn');
    if (btn) btn.style.color = window._shuffleOn ? '#1DB954' : '#aaa';
    fetch('https://api.spotify.com/v1/me/player/shuffle?state=' + window._shuffleOn, {{
      method: 'PUT', headers: {{'Authorization': 'Bearer ' + TOKEN}}
    }}).catch(function() {{ window._shuffleOn = !window._shuffleOn; if (btn) btn.style.color = '#aaa'; }});
  }};
  window.spLike = function() {{
    if (!window._spotifyCurrentTrackId) return;
    var liked = window._currentTrackLiked;
    fetch('https://api.spotify.com/v1/me/tracks', {{
      method: liked ? 'DELETE' : 'PUT',
      headers: {{'Authorization': 'Bearer ' + TOKEN, 'Content-Type': 'application/json'}},
      body: JSON.stringify({{ids: [window._spotifyCurrentTrackId]}})
    }}).then(function() {{
      window._currentTrackLiked = !liked;
      var btn = document.getElementById('sp-like-btn');
      if (btn) {{ btn.textContent = window._currentTrackLiked ? '♥' : '♡'; btn.style.color = window._currentTrackLiked ? '#1DB954' : '#aaa'; }}
    }}).catch(function(e) {{ setStatus('Like error: ' + e.message); }});
  }};

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
