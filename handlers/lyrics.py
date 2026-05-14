"""Spotify lyrics handler — fetch song lyrics from Genius API."""
from __future__ import annotations

import logging

from pydantic import BaseModel, Field

from imperal_sdk import ActionResult

from app import chat

log = logging.getLogger("spotify.lyrics")


class GetLyricsParams(BaseModel):
    track_name: str = Field(..., description="Song title")
    artist_name: str = Field(..., description="Artist name")


@chat.function(
    "get_lyrics",
    action_type="read",
    description="Search for song lyrics on Genius. Returns URL to full lyrics page.",
)
async def fn_get_lyrics(ctx, params: GetLyricsParams) -> ActionResult:
    """Search for song lyrics on Genius. Returns URL to full lyrics page."""
    genius_token = await ctx.secrets.get("genius_access_token")
    if not genius_token:
        return ActionResult.error(
            "Genius API token not configured. Set it in extension settings.",
            retryable=False,
        )

    query = f"{params.track_name} {params.artist_name}"

    try:
        headers = {"Authorization": f"Bearer {genius_token}"}
        search_resp = await ctx.http.get(
            "https://api.genius.com/search",
            params={"q": query},
            headers=headers,
        )

        if not search_resp.ok:
            return ActionResult.error(
                f"Genius search failed (HTTP {search_resp.status_code})",
                retryable=(search_resp.status_code == 429),
            )

        hits = search_resp.json().get("response", {}).get("hits", [])
        if not hits:
            return ActionResult.error(f"No lyrics found for '{query}'")

        result = hits[0]["result"]
        song_url = result["url"]
        song_title = result["title"]
        song_artist = result["primary_artist"]["name"]

        return ActionResult.success(
            data={"url": song_url, "title": song_title, "artist": song_artist},
            summary=f"Found '{song_title}' by {song_artist}",
        )

    except Exception as e:
        log.error("get_lyrics failed: %s", e)
        return ActionResult.error(f"Lyrics search failed: {str(e)}", retryable=True)
