"""Shared test fixtures for Spotify extension tests."""
from imperal_sdk.testing import MockContext
from handlers.auth import save_token

SP_CONFIG = {
    "spotify": {
        "client_id": "test_client_id",
        "client_secret": "test_client_secret",
    }
}

SAMPLE_TRACK = {
    "id": "4iV5W9uYEdYUVa79Axb7Rh",
    "name": "Midnight City",
    "artists": [{"id": "artist_123", "name": "M83"}],
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


async def ctx_with_token(token: str = "test_token") -> MockContext:
    ctx = MockContext(user_id="user1", config=SP_CONFIG)
    await save_token(ctx, {"access_token": token, "refresh_token": "refresh_abc"})
    return ctx
