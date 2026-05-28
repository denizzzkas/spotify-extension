"""Shared test fixtures for Spotify extension tests."""
from imperal_sdk.testing import MockContext
from imperal_sdk.testing.mock_context import MockHTTP

# httpx.AsyncClient.delete() doesn't accept json= — production _make_request() uses request().
# Patch MockHTTP so tests exercise the same code path.
if not hasattr(MockHTTP, "request"):
    async def _mock_http_request(self, method: str, url: str, **kwargs):
        return await getattr(self, method.lower())(url, **kwargs)
    MockHTTP.request = _mock_http_request

from app_helpers import _save_token

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


class MockCache:
    """In-memory ctx.cache stub for unit tests."""

    def __init__(self):
        self._data = {}

    async def get(self, key, model=None):
        val = self._data.get(key)
        if val is None:
            return None
        if model is not None and isinstance(val, dict):
            return model(**val)
        return val

    async def set(self, key, value, ttl_seconds=None):
        if hasattr(value, "model_dump"):
            self._data[key] = value.model_dump()
        else:
            self._data[key] = value

    async def delete(self, key):
        self._data.pop(key, None)


async def ctx_with_token(token: str = "test_token") -> MockContext:
    # spotify_client_id/secret are now app-level config, not per-user secrets
    ctx = MockContext(
        user_id="user1",
        config={
            "spotify_client_id": "test_client_id",
            "spotify_client_secret": "test_client_secret",
            "genius_access_token": "test_genius_token",
        },
    )
    ctx._cache = MockCache()
    await _save_token(ctx, "user1", {"access_token": token, "refresh_token": "refresh_abc"})
    return ctx
