"""Tests for playback handlers: play_track, play_track_by_name, play_playlist."""
from imperal_sdk.testing import MockContext

from handlers.playback import (
    fn_play_track, PlayTrackParams,
    fn_play_track_by_name, PlayTrackByNameParams,
    fn_play_playlist, PlayPlaylistParams,
)
from tests.fixtures import ctx_with_token, SAMPLE_TRACK


# ── play_track ────────────────────────────────────────────────────────────────

async def test_play_track_returns_track_data():
    ctx = await ctx_with_token()
    ctx.http.mock_get("api.spotify.com/v1/tracks/4iV5W9uYEdYUVa79Axb7Rh", SAMPLE_TRACK)
    result = await fn_play_track(ctx, PlayTrackParams(track_id="4iV5W9uYEdYUVa79Axb7Rh"))
    assert result.status == "success"
    assert result.data["track"]["title"] == "Midnight City"
    assert result.data["preview_url"] != ""
    assert "spotify.com/track" in result.data["spotify_url"]


async def test_play_track_writes_now_playing_to_skeleton():
    ctx = await ctx_with_token()
    ctx.http.mock_get("api.spotify.com/v1/tracks/4iV5W9uYEdYUVa79Axb7Rh", SAMPLE_TRACK)
    await fn_play_track(ctx, PlayTrackParams(track_id="4iV5W9uYEdYUVa79Axb7Rh"))
    stored = await ctx.skeleton.get("spotify_now_playing")
    assert stored["title"] == "Midnight City"
    assert stored["artist"] == "M83"


async def test_play_track_no_token_returns_error():
    ctx = MockContext(user_id="user1")
    assert (await fn_play_track(ctx, PlayTrackParams(track_id="abc"))).status == "error"


async def test_play_track_not_found_returns_error():
    ctx = await ctx_with_token()
    ctx.http.mock_get("api.spotify.com/v1/tracks/notexist", {}, status=404)
    assert (await fn_play_track(ctx, PlayTrackParams(track_id="notexist"))).status == "error"


# ── play_track_by_name ────────────────────────────────────────────────────────

async def test_play_track_by_name_success():
    ctx = await ctx_with_token()
    ctx.http.mock_get("api.spotify.com/v1/search", {"tracks": {"items": [SAMPLE_TRACK]}})
    result = await fn_play_track_by_name(ctx, PlayTrackByNameParams(title="Midnight City", artist="M83"))
    assert result.status == "success"
    assert result.data["track"]["title"] == "Midnight City"
    stored = await ctx.skeleton.get("spotify_now_playing")
    assert stored["title"] == "Midnight City"


async def test_play_track_by_name_not_found():
    ctx = await ctx_with_token()
    ctx.http.mock_get("api.spotify.com/v1/search", {"tracks": {"items": []}})
    result = await fn_play_track_by_name(ctx, PlayTrackByNameParams(title="xyznotfound"))
    assert result.status == "error"
    assert result.retryable is False


async def test_play_track_by_name_no_token():
    ctx = MockContext(user_id="user1")
    assert (await fn_play_track_by_name(ctx, PlayTrackByNameParams(title="test"))).status == "error"


# ── play_playlist ─────────────────────────────────────────────────────────────

async def test_play_playlist_success():
    ctx = await ctx_with_token()
    ctx.http.mock_get(
        "api.spotify.com/v1/playlists/pl123/tracks",
        {"items": [{"track": SAMPLE_TRACK}]},
    )
    result = await fn_play_playlist(ctx, PlayPlaylistParams(playlist_id="pl123", playlist_name="My Mix"))
    assert result.status == "success"
    assert result.data["count"] == 1
    queue = await ctx.skeleton.get("spotify_queue")
    assert queue["playlist_name"] == "My Mix"
    assert queue["index"] == 0
    assert (await ctx.skeleton.get("spotify_now_playing"))["title"] == "Midnight City"


async def test_play_playlist_empty_returns_error():
    ctx = await ctx_with_token()
    ctx.http.mock_get("api.spotify.com/v1/playlists/pl123/tracks", {"items": []})
    assert (await fn_play_playlist(ctx, PlayPlaylistParams(playlist_id="pl123"))).status == "error"


async def test_play_playlist_no_token():
    ctx = MockContext(user_id="user1")
    assert (await fn_play_playlist(ctx, PlayPlaylistParams(playlist_id="pl123"))).status == "error"
