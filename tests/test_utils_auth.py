"""Tests for utils and auth handler."""
import pytest
from imperal_sdk.testing import MockContext

from handlers.auth import (
    get_access_token, save_token, clear_token,
    get_auth_headers, build_auth_url,
    create_oauth_state, consume_oauth_state,
)
from utils import format_duration, format_track, format_playlist, to_spotify_uri


SAMPLE_TRACK = {
    "id": "4iV5W9uYEdYUVa79Axb7Rh",
    "name": "Midnight City",
    "artists": [{"name": "M83"}],
    "external_urls": {"spotify": "https://open.spotify.com/track/4iV5W9uYEdYUVa79Axb7Rh"},
    "duration_ms": 244000,
    "popularity": 85,
    "preview_url": "https://p.scdn.co/mp3-preview/abc123.mp3",
    "album": {"name": "Hurry Up, We're Dreaming"},
}

SAMPLE_PLAYLIST = {
    "id": "37i9dQZF1DXcBWIGoYBM5M",
    "name": "My Workout",
    "tracks": {"total": 10},
    "external_urls": {"spotify": "https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M"},
    "description": "Pump it up",
    "public": True,
}


# ── format_duration ───────────────────────────────────────────────────────────

def test_format_duration_minutes_seconds():
    assert format_duration(65_000) == "1:05"

def test_format_duration_hours():
    assert format_duration(3_665_000) == "1:01:05"

def test_format_duration_zero():
    assert format_duration(0) == "0:00"

def test_format_duration_none():
    assert format_duration(None) == "0:00"


# ── format_track ──────────────────────────────────────────────────────────────

def test_format_track_all_fields():
    t = format_track(SAMPLE_TRACK)
    assert t["id"] == "4iV5W9uYEdYUVa79Axb7Rh"
    assert t["title"] == "Midnight City"
    assert t["artist"] == "M83"
    assert t["duration"] == "4:04"
    assert "spotify.com/track" in t["url"]

def test_format_track_multiple_artists():
    t = format_track({**SAMPLE_TRACK, "artists": [{"name": "A"}, {"name": "B"}]})
    assert t["artist"] == "A, B"

def test_format_track_missing_artists():
    t = format_track({"id": "1", "name": "No Artist"})
    assert t["artist"] == "Unknown"


# ── format_playlist ───────────────────────────────────────────────────────────

def test_format_playlist_fields():
    p = format_playlist(SAMPLE_PLAYLIST)
    assert p["id"] == "37i9dQZF1DXcBWIGoYBM5M"
    assert p["title"] == "My Workout"
    assert p["is_public"] is True
    assert p["track_count"] == 10

def test_format_playlist_private():
    p = format_playlist({**SAMPLE_PLAYLIST, "public": False})
    assert p["is_public"] is False


# ── to_spotify_uri ────────────────────────────────────────────────────────────

def test_to_spotify_uri_plain_id():
    assert to_spotify_uri("abc123") == "spotify:track:abc123"

def test_to_spotify_uri_already_uri():
    assert to_spotify_uri("spotify:track:abc123") == "spotify:track:abc123"


# ── auth token CRUD ───────────────────────────────────────────────────────────

async def test_save_and_get_token():
    ctx = MockContext(user_id="user1")
    assert await get_access_token(ctx) is None
    await save_token(ctx, {"access_token": "tok123"})
    assert await get_access_token(ctx) == "tok123"

async def test_save_token_updates_existing():
    ctx = MockContext(user_id="user1")
    await save_token(ctx, {"access_token": "old"})
    await save_token(ctx, {"access_token": "new"})
    assert await get_access_token(ctx) == "new"
    page = await ctx.store.query("sp_credentials", where={"user_id": "user1"})
    assert len(page.data) == 1

async def test_clear_token():
    ctx = MockContext(user_id="user1")
    await save_token(ctx, {"access_token": "tok"})
    await clear_token(ctx)
    assert await get_access_token(ctx) is None

async def test_get_auth_headers_bearer():
    ctx = MockContext(user_id="user1")
    await save_token(ctx, {"access_token": "my_token"})
    headers = await get_auth_headers(ctx)
    assert headers["Authorization"] == "Bearer my_token"

async def test_get_auth_headers_raises_no_token():
    ctx = MockContext(user_id="user1")
    with pytest.raises(ValueError, match="Not connected"):
        await get_auth_headers(ctx)


# ── OAuth state ───────────────────────────────────────────────────────────────

async def test_create_and_consume_state():
    ctx = MockContext(user_id="user1")
    state = await create_oauth_state(ctx)
    assert await consume_oauth_state(ctx, state) is True

async def test_consume_state_only_once():
    ctx = MockContext(user_id="user1")
    state = await create_oauth_state(ctx)
    await consume_oauth_state(ctx, state)
    assert await consume_oauth_state(ctx, state) is False

async def test_consume_unknown_state():
    ctx = MockContext(user_id="user1")
    assert await consume_oauth_state(ctx, "bogus") is False


# ── build_auth_url ────────────────────────────────────────────────────────────

def test_build_auth_url_params():
    url = build_auth_url("client123", "https://example.com/cb", "state_abc")
    assert "client_id=client123" in url
    assert "state=state_abc" in url
    assert "response_type=code" in url
    assert "scope=" in url
