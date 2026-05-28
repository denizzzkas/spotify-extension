"""Spotify lyrics handler — fetch song lyrics via lrclib.net, fallback to Genius URL."""
from __future__ import annotations

import logging

from pydantic import BaseModel, Field

from imperal_sdk import ActionResult

from app import chat
from return_models import LyricsRecord

log = logging.getLogger("spotify.lyrics")


class GetLyricsParams(BaseModel):
    track_name: str = Field(..., description="Song title")
    artist_name: str = Field("", description="Artist name (optional, improves accuracy)")


@chat.function(
    "get_lyrics",
    action_type="read",
    data_model=LyricsRecord,
    description="Fetch full song lyrics text. Returns the complete lyrics as text if found on lrclib.net, otherwise returns a Genius URL. Only track_name is required; providing artist_name improves accuracy.",
)
async def fn_get_lyrics(ctx, params: GetLyricsParams) -> ActionResult:
    """Fetch lyrics via lrclib.net, fall back to Genius URL if not found."""
    try:
        # Primary: lrclib.net — free, no token, returns full plainLyrics
        lrc_params: dict = {"track_name": params.track_name}
        if params.artist_name:
            lrc_params["artist_name"] = params.artist_name

        lrc_resp = await ctx.http.get("https://lrclib.net/api/get", params=lrc_params)
        if lrc_resp.ok:
            body = lrc_resp.json()
            lyrics_text = (body.get("plainLyrics") or "").strip()
            if lyrics_text:
                artist = body.get("artistName") or params.artist_name
                title = body.get("trackName") or params.track_name
                return ActionResult.success(
                    data={"lyrics": lyrics_text, "url": "", "title": title, "artist": artist},
                    summary=f"Lyrics for '{title}' by {artist}",
                )

        # Fallback: Genius — return URL to lyrics page
        genius_token = await ctx.secrets.get("genius_access_token")
        query = f"{params.track_name} {params.artist_name}".strip()

        if genius_token:
            search_resp = await ctx.http.get(
                "https://api.genius.com/search",
                params={"q": query},
                headers={"Authorization": f"Bearer {genius_token}"},
            )
            if search_resp.ok:
                hits = search_resp.json().get("response", {}).get("hits", [])
                if hits:
                    result = hits[0]["result"]
                    genius_url = result["url"]
                    title = result["title"]
                    artist = result["primary_artist"]["name"]
                    return ActionResult.success(
                        data={"lyrics": "", "url": genius_url, "title": title, "artist": artist},
                        summary=f"Lyrics page for '{title}' by {artist}: {genius_url}",
                    )

        return ActionResult.error(
            f"Lyrics not found for '{params.track_name}'"
            + (f" by {params.artist_name}" if params.artist_name else "") + ".",
            retryable=False,
        )

    except Exception as e:
        log.error("get_lyrics failed: %s", e)
        return ActionResult.error(f"Lyrics search failed: {str(e)}", retryable=True)
