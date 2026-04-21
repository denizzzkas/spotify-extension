"""Tests for panel-specific handler functions."""
from imperal_sdk.testing import MockContext

from handlers.panel import (
    fn_panel_search, PanelSearchParams,
    fn_open_playlist, OpenPlaylistParams,
    fn_open_liked_tracks, OpenLikedTracksParams,
    fn_open_recent_tracks, OpenRecentTracksParams,
    fn_open_profile, OpenProfileParams,
    SKELETON_DETAIL, SKELETON_SEARCH,
)
from tests.fixtures import ctx_with_token, SAMPLE_TRACK, SAMPLE_USER


# ── panel_search_tracks ───────────────────────────────────────────────────────

async def test_panel_search_writes_to_skeleton():
    ctx = await ctx_with_token()
    ctx.http.mock_get(
        "api.spotify.com/v1/search",
        {"tracks": {"items": [SAMPLE_TRACK]}},
    )
    result = await fn_panel_search(ctx, PanelSearchParams(query="Midnight City"))
    assert result.status == "success"
    assert result.data["count"] == 1
    stored = await ctx.skeleton.get(SKELETON_SEARCH)
    assert stored["query"] == "Midnight City"
    assert stored["tracks"][0]["title"] == "Midnight City"
    assert stored["tracks"][0]["album_art"] != ""


async def test_panel_search_empty_results():
    ctx = await ctx_with_token()
    ctx.http.mock_get("api.spotify.com/v1/search", {"tracks": {"items": []}})
    result = await fn_panel_search(ctx, PanelSearchParams(query="xyznotfound"))
    assert result.status == "success"
    stored = await ctx.skeleton.get(SKELETON_SEARCH)
    assert stored["tracks"] == []


async def test_panel_search_no_token_returns_error():
    ctx = MockContext(user_id="user1")
    result = await fn_panel_search(ctx, PanelSearchParams(query="test"))
    assert result.status == "error"


async def test_panel_search_refreshes_left_panel():
    ctx = await ctx_with_token()
    ctx.http.mock_get("api.spotify.com/v1/search", {"tracks": {"items": []}})
    result = await fn_panel_search(ctx, PanelSearchParams(query="test"))
    assert "spotify" in (result.refresh_panels or [])


# ── open_playlist ─────────────────────────────────────────────────────────────

async def test_open_playlist_writes_tracks_to_skeleton():
    ctx = await ctx_with_token()
    ctx.http.mock_get(
        "api.spotify.com/v1/playlists/pl123/tracks",
        {"items": [{"track": SAMPLE_TRACK}]},
    )
    result = await fn_open_playlist(ctx, OpenPlaylistParams(playlist_id="pl123", playlist_name="My Mix"))
    assert result.status == "success"
    stored = await ctx.skeleton.get(SKELETON_DETAIL)
    assert stored["type"] == "tracks"
    assert stored["title"] == "My Mix"
    assert len(stored["tracks"]) == 1
    assert stored["tracks"][0]["title"] == "Midnight City"


async def test_open_playlist_uses_id_as_fallback_name():
    ctx = await ctx_with_token()
    ctx.http.mock_get("api.spotify.com/v1/playlists/pl123/tracks", {"items": []})
    result = await fn_open_playlist(ctx, OpenPlaylistParams(playlist_id="pl123"))
    assert result.status == "success"
    stored = await ctx.skeleton.get(SKELETON_DETAIL)
    assert stored["title"] == "pl123"


async def test_open_playlist_no_token_returns_error():
    ctx = MockContext(user_id="user1")
    result = await fn_open_playlist(ctx, OpenPlaylistParams(playlist_id="pl123"))
    assert result.status == "error"


async def test_open_playlist_refreshes_detail_panel():
    ctx = await ctx_with_token()
    ctx.http.mock_get("api.spotify.com/v1/playlists/pl123/tracks", {"items": []})
    result = await fn_open_playlist(ctx, OpenPlaylistParams(playlist_id="pl123"))
    assert "spotify_detail" in (result.refresh_panels or [])


# ── open_liked_tracks ─────────────────────────────────────────────────────────

async def test_open_liked_tracks_writes_to_skeleton():
    ctx = await ctx_with_token()
    ctx.http.mock_get(
        "api.spotify.com/v1/me/tracks",
        {"items": [{"track": SAMPLE_TRACK, "added_at": "2026-01-01T12:00:00Z"}]},
    )
    result = await fn_open_liked_tracks(ctx, OpenLikedTracksParams())
    assert result.status == "success"
    stored = await ctx.skeleton.get(SKELETON_DETAIL)
    assert stored["type"] == "tracks"
    assert stored["title"] == "Liked Tracks"
    assert len(stored["tracks"]) == 1


async def test_open_liked_tracks_no_token_returns_error():
    ctx = MockContext(user_id="user1")
    result = await fn_open_liked_tracks(ctx, OpenLikedTracksParams())
    assert result.status == "error"


# ── open_recent_tracks ────────────────────────────────────────────────────────

async def test_open_recent_tracks_writes_to_skeleton():
    ctx = await ctx_with_token()
    ctx.http.mock_get(
        "api.spotify.com/v1/me/player/recently-played",
        {"items": [{"track": SAMPLE_TRACK, "played_at": "2026-01-01T12:00:00Z"}]},
    )
    result = await fn_open_recent_tracks(ctx, OpenRecentTracksParams())
    assert result.status == "success"
    stored = await ctx.skeleton.get(SKELETON_DETAIL)
    assert stored["type"] == "tracks"
    assert stored["title"] == "Recent Tracks"


async def test_open_recent_tracks_premium_required():
    ctx = await ctx_with_token()
    ctx.http.mock_get("api.spotify.com/v1/me/player/recently-played", {}, status=403)
    result = await fn_open_recent_tracks(ctx, OpenRecentTracksParams())
    assert result.status == "error"
    assert result.retryable is False


async def test_open_recent_tracks_no_token_returns_error():
    ctx = MockContext(user_id="user1")
    result = await fn_open_recent_tracks(ctx, OpenRecentTracksParams())
    assert result.status == "error"


# ── open_profile ──────────────────────────────────────────────────────────────

async def test_open_profile_writes_to_skeleton():
    ctx = await ctx_with_token()
    ctx.http.mock_get("api.spotify.com/v1/me", SAMPLE_USER)
    result = await fn_open_profile(ctx, OpenProfileParams())
    assert result.status == "success"
    stored = await ctx.skeleton.get(SKELETON_DETAIL)
    assert stored["type"] == "profile"
    assert stored["profile"]["display_name"] == "Test User"
    assert stored["profile"]["product"] == "premium"
    assert stored["profile"]["followers"] == 42


async def test_open_profile_no_token_returns_error():
    ctx = MockContext(user_id="user1")
    result = await fn_open_profile(ctx, OpenProfileParams())
    assert result.status == "error"


async def test_open_profile_refreshes_detail_panel():
    ctx = await ctx_with_token()
    ctx.http.mock_get("api.spotify.com/v1/me", SAMPLE_USER)
    result = await fn_open_profile(ctx, OpenProfileParams())
    assert "spotify_detail" in (result.refresh_panels or [])
