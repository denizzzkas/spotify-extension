"""Utility helpers for the Spotify extension."""
from __future__ import annotations


def format_duration(milliseconds: int) -> str:
    """Convert milliseconds to human-readable M:SS or H:MM:SS."""
    if not milliseconds:
        return "0:00"
    total_sec = milliseconds // 1000
    hours, rem = divmod(total_sec, 3600)
    minutes, seconds = divmod(rem, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{seconds:02d}"
    return f"{minutes}:{seconds:02d}"


def format_track(raw: dict) -> dict:
    """Normalise a raw Spotify track object to a clean dict."""
    artists = raw.get("artists") or []
    artist_names = ", ".join(a.get("name", "") for a in artists) or "Unknown"
    album = raw.get("album") or {}
    images = album.get("images") or []
    return {
        "id": raw.get("id", ""),
        "title": raw.get("name", "Unknown"),
        "artist": artist_names,
        "url": (raw.get("external_urls") or {}).get("spotify", ""),
        "duration": format_duration(raw.get("duration_ms", 0)),
        "duration_ms": raw.get("duration_ms", 0),
        "popularity": raw.get("popularity", 0),
        "preview_url": raw.get("preview_url") or "",
        "album": album.get("name", ""),
        "album_art": images[0].get("url", "") if images else "",
    }


def format_playlist(raw: dict) -> dict:
    """Normalise a raw Spotify playlist object to a clean dict."""
    tracks = raw.get("tracks") or {}
    images = raw.get("images") or []
    return {
        "id": raw.get("id", ""),
        "title": raw.get("name", "Unknown"),
        "track_count": tracks.get("total", 0) if isinstance(tracks, dict) else 0,
        "url": (raw.get("external_urls") or {}).get("spotify", ""),
        "description": raw.get("description") or "",
        "is_public": raw.get("public") or False,
        "image_url": images[0].get("url", "") if images else "",
    }


def to_spotify_uri(track_id: str) -> str:
    """Ensure track ID is in spotify:track:xxx URI format."""
    if track_id.startswith("spotify:track:"):
        return track_id
    return f"spotify:track:{track_id}"


def sp_error(status_code: int) -> str:
    """Return a user-friendly message for a Spotify API error status."""
    messages = {
        400: "Invalid request parameters.",
        401: "Not authorised — please reconnect via connect_spotify().",
        403: "You do not have permission. Some features require Spotify Premium.",
        404: "Resource not found on Spotify.",
        429: "Spotify rate limit reached. Please wait a moment and try again.",
        500: "Spotify server error. Please try again later.",
    }
    return messages.get(status_code, f"Unexpected Spotify error (HTTP {status_code}).")
