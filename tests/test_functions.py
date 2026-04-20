"""Tests for all Spotify handler functions (search, playlists, library, playback)."""
from imperal_sdk.testing import MockContext

from handlers.auth import save_token
from handlers.search import fn_search_tracks, SearchTracksParams
from handlers.playlists import (
    fn_get_playlists, GetPlaylistsParams,
    fn_get_playlist_tracks, GetPlaylistTracksParams,
    fn_create_playlist, CreatePlaylistParams,
    fn_add_track_to_playlist, AddTrackToPlaylistParams,
    fn_remove_track_from_playlist, RemoveTrackFromPlaylistParams,
)
from handlers.library import (
    fn_get_recent_tracks, GetRecentTracksParams,
    fn_get_liked_tracks, GetLikedTracksParams,
    fn_like_track, LikeTrackParams,
    fn_unlike_track, UnlikeTrackParams,
    fn_get_user_profile, GetUserProfileParams,
)
from handlers.playback import fn_play_track, PlayTrackParams


SP_CONFIG = {
    "spotify": {
        "client_id": "test_client_id",
        "client_secret": "test_client_secret",
    }
}

SAMPLE_TRACK = {
    "id": "4iV5W9uYEdYUVa79Axb7Rh",
    "name": "Midnight City",
    "artists": [{"name": "M83"}],
    "external_urls": {"spotify": "https://open.spotify.com/track/4iV5W9uYEdYUVa79Axb7Rh"},
    "duration_ms": 244000,
    "popularity": 85,
    "preview_url": "https://p.scdn.co/mp3-preview/abc123.mp3",
    "album": {
        "name": "Hurry Up, We're Dreaming",
        "images": [{"url": "https://i.scdn.co/image/album.jpg"}],
    },
}

SAMPLE_PLAYLIST = {
    "id": "37i9dQZF1DXcBWIGoYBM5M",
    "name": "My Workout",
    "tracks": {"total": 10},
    "external_urls": {"spotify": "https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M"},
    "description": "Pump it up",
    "public": True,
}

SAMPLE_USER = {
    "id": "spotify_user_123",
    "display_name": "Test User",
    "email": "test@example.com",
    "external_urls": {"spotify": "https://open.spotify.com/user/spotify_user_123"},
    "images": [{"url": "https://i.scdn.co/image/abc.jpg"}],
    "followers": {"total": 42},
    "product": "premium",
}

async def _ctx_with_token(token: str = "test_token") -> MockContext:
    ctx = MockContext(user_id="user1", config=SP_CONFIG)
    await save_token(ctx, {"access_token": token, "refresh_token": "refresh_abc"})
    return ctx


# ── search_tracks ─────────────────────────────────────────────────────────────
async def test_search_tracks_returns_formatted_tracks():
    ctx = await _ctx_with_token()
    ctx.http.mock_get(
        "api.spotify.com/v1/search",
        {"tracks": {"items": [SAMPLE_TRACK]}},
    )
    result = await fn_search_tracks(ctx, SearchTracksParams(query="Midnight City"))
    assert result.status == "success"
    assert result.data["count"] == 1
    assert result.data["tracks"][0]["title"] == "Midnight City"


async def test_search_tracks_empty_results():
    ctx = await _ctx_with_token()
    ctx.http.mock_get("api.spotify.com/v1/search", {"tracks": {"items": []}})
    result = await fn_search_tracks(ctx, SearchTracksParams(query="xyznotfound"))
    assert result.status == "success"
    assert result.data["count"] == 0


async def test_search_tracks_no_token_returns_error():
    ctx = MockContext(user_id="user1")
    result = await fn_search_tracks(ctx, SearchTracksParams(query="test"))
    assert result.status == "error"
    assert "Not connected" in result.error


async def test_search_tracks_rate_limit_is_retryable():
    ctx = await _ctx_with_token()
    ctx.http.mock_get("api.spotify.com/v1/search", {}, status=429)
    result = await fn_search_tracks(ctx, SearchTracksParams(query="test"))
    assert result.status == "error"
    assert result.retryable is True


# ── get_playlists ─────────────────────────────────────────────────────────────
async def test_get_playlists_returns_list():
    ctx = await _ctx_with_token()
    ctx.http.mock_get("api.spotify.com/v1/me/playlists", {"items": [SAMPLE_PLAYLIST]})
    result = await fn_get_playlists(ctx, GetPlaylistsParams())
    assert result.status == "success"
    assert result.data["count"] == 1
    assert result.data["playlists"][0]["title"] == "My Workout"


async def test_get_playlists_no_token_returns_error():
    ctx = MockContext(user_id="user1")
    result = await fn_get_playlists(ctx, GetPlaylistsParams())
    assert result.status == "error"


# ── get_playlist_tracks ───────────────────────────────────────────────────────
async def test_get_playlist_tracks_returns_tracks():
    ctx = await _ctx_with_token()
    ctx.http.mock_get(
        "api.spotify.com/v1/playlists/37i9dQZF1DXcBWIGoYBM5M/tracks",
        {"items": [{"track": SAMPLE_TRACK}]},
    )
    result = await fn_get_playlist_tracks(
        ctx, GetPlaylistTracksParams(playlist_id="37i9dQZF1DXcBWIGoYBM5M")
    )
    assert result.status == "success"
    assert result.data["count"] == 1
    assert result.data["tracks"][0]["title"] == "Midnight City"


# ── create_playlist ───────────────────────────────────────────────────────────
async def test_create_playlist_success():
    ctx = await _ctx_with_token()
    ctx.http.mock_get("api.spotify.com/v1/me", SAMPLE_USER)
    ctx.http.mock_post(
        "api.spotify.com/v1/users/spotify_user_123/playlists", SAMPLE_PLAYLIST
    )
    result = await fn_create_playlist(ctx, CreatePlaylistParams(name="My Workout"))
    assert result.status == "success"
    assert result.data["playlist"]["title"] == "My Workout"


async def test_create_playlist_no_token_returns_error():
    ctx = MockContext(user_id="user1")
    result = await fn_create_playlist(ctx, CreatePlaylistParams(name="Fail"))
    assert result.status == "error"


# ── add_track_to_playlist ─────────────────────────────────────────────────────
async def test_add_track_to_playlist_success():
    ctx = await _ctx_with_token()
    ctx.http.mock_post(
        "api.spotify.com/v1/playlists/37i9dQZF1DXcBWIGoYBM5M/tracks", {}
    )
    result = await fn_add_track_to_playlist(
        ctx,
        AddTrackToPlaylistParams(
            playlist_id="37i9dQZF1DXcBWIGoYBM5M",
            track_id="4iV5W9uYEdYUVa79Axb7Rh",
        ),
    )
    assert result.status == "success"
    assert result.data["added"] is True


# ── remove_track_from_playlist ────────────────────────────────────────────────
async def test_remove_track_from_playlist_success():
    ctx = await _ctx_with_token()
    ctx.http._mocks.append(
        ("DELETE", "api.spotify.com/v1/playlists/37i9dQZF1DXcBWIGoYBM5M/tracks", {}, 200)
    )
    result = await fn_remove_track_from_playlist(
        ctx,
        RemoveTrackFromPlaylistParams(
            playlist_id="37i9dQZF1DXcBWIGoYBM5M",
            track_id="4iV5W9uYEdYUVa79Axb7Rh",
        ),
    )
    assert result.status == "success"
    assert result.data["removed"] is True


# ── get_recent_tracks ─────────────────────────────────────────────────────────
async def test_get_recent_tracks_success():
    ctx = await _ctx_with_token()
    ctx.http.mock_get(
        "api.spotify.com/v1/me/player/recently-played",
        {"items": [{"track": SAMPLE_TRACK, "played_at": "2026-01-01T12:00:00Z"}]},
    )
    result = await fn_get_recent_tracks(ctx, GetRecentTracksParams())
    assert result.status == "success"
    assert result.data["tracks"][0]["title"] == "Midnight City"


async def test_get_recent_tracks_premium_required():
    ctx = await _ctx_with_token()
    ctx.http.mock_get(
        "api.spotify.com/v1/me/player/recently-played", {}, status=403
    )
    result = await fn_get_recent_tracks(ctx, GetRecentTracksParams())
    assert result.status == "error"
    assert "Premium" in result.error


async def test_get_recent_tracks_no_token_returns_error():
    ctx = MockContext(user_id="user1")
    result = await fn_get_recent_tracks(ctx, GetRecentTracksParams())
    assert result.status == "error"


# ── get_liked_tracks ──────────────────────────────────────────────────────────
async def test_get_liked_tracks_returns_tracks():
    ctx = await _ctx_with_token()
    ctx.http.mock_get(
        "api.spotify.com/v1/me/tracks",
        {"items": [{"track": SAMPLE_TRACK, "added_at": "2026-01-01T12:00:00Z"}]},
    )
    result = await fn_get_liked_tracks(ctx, GetLikedTracksParams())
    assert result.status == "success"
    assert result.data["count"] == 1


async def test_get_liked_tracks_no_token_returns_error():
    ctx = MockContext(user_id="user1")
    result = await fn_get_liked_tracks(ctx, GetLikedTracksParams())
    assert result.status == "error"


# ── like_track ────────────────────────────────────────────────────────────────
async def test_like_track_success():
    ctx = await _ctx_with_token()
    ctx.http._mocks.append(("PUT", "api.spotify.com/v1/me/tracks", {}, 200))
    result = await fn_like_track(ctx, LikeTrackParams(track_id="4iV5W9uYEdYUVa79Axb7Rh"))
    assert result.status == "success"
    assert result.data["liked"] is True


async def test_like_track_no_token_returns_error():
    ctx = MockContext(user_id="user1")
    result = await fn_like_track(ctx, LikeTrackParams(track_id="abc"))
    assert result.status == "error"


# ── unlike_track ──────────────────────────────────────────────────────────────
async def test_unlike_track_success():
    ctx = await _ctx_with_token()
    ctx.http._mocks.append(("DELETE", "api.spotify.com/v1/me/tracks", {}, 200))
    result = await fn_unlike_track(
        ctx, UnlikeTrackParams(track_id="4iV5W9uYEdYUVa79Axb7Rh")
    )
    assert result.status == "success"
    assert result.data["liked"] is False


# ── get_user_profile ──────────────────────────────────────────────────────────
async def test_get_user_profile_returns_profile():
    ctx = await _ctx_with_token()
    ctx.http.mock_get("api.spotify.com/v1/me", SAMPLE_USER)
    result = await fn_get_user_profile(ctx, GetUserProfileParams())
    assert result.status == "success"
    assert result.data["profile"]["display_name"] == "Test User"
    assert result.data["profile"]["product"] == "premium"
    assert result.data["profile"]["followers_count"] == 42


async def test_get_user_profile_no_token_returns_error():
    ctx = MockContext(user_id="user1")
    result = await fn_get_user_profile(ctx, GetUserProfileParams())
    assert result.status == "error"


# ── play_track ────────────────────────────────────────────────────────────────
async def test_play_track_returns_track_data():
    ctx = await _ctx_with_token()
    ctx.http.mock_get(
        "api.spotify.com/v1/tracks/4iV5W9uYEdYUVa79Axb7Rh", SAMPLE_TRACK
    )
    result = await fn_play_track(ctx, PlayTrackParams(track_id="4iV5W9uYEdYUVa79Axb7Rh"))
    assert result.status == "success"
    assert result.data["track"]["title"] == "Midnight City"
    assert result.data["preview_url"] != ""
    assert "spotify.com/track" in result.data["spotify_url"]


async def test_play_track_no_token_returns_error():
    ctx = MockContext(user_id="user1")
    result = await fn_play_track(ctx, PlayTrackParams(track_id="abc"))
    assert result.status == "error"


async def test_play_track_not_found_returns_error():
    ctx = await _ctx_with_token()
    ctx.http.mock_get("api.spotify.com/v1/tracks/notexist", {}, status=404)
    result = await fn_play_track(ctx, PlayTrackParams(track_id="notexist"))
    assert result.status == "error"
