"""Spotify lyrics handler — fetch song lyrics via lyrics.ovh, fallback to Genius URL."""
from __future__ import annotations

import logging

from pydantic import BaseModel, Field

from imperal_sdk import ActionResult

from app import chat
from return_models import LyricsRecord

log = logging.getLogger("spotify.lyrics")


class GetLyricsParams(BaseModel):
    track_name: str = Field(..., description="Song title")
    artist_name: str = Field(..., description="Artist name")


@chat.function(
    "get_lyrics",
    action_type="read",
    data_model=LyricsRecord,
    description="Fetch song lyrics text. Returns the full lyrics as text. Requires track_name and artist_name.",
)
async def fn_get_lyrics(ctx, params: GetLyricsParams) -> ActionResult:
    """Fetch lyrics via lyrics.ovh, fall back to Genius URL if not found."""
    try:
        # Primary: lyrics.ovh — free, no token, returns text directly
        ovh_resp = await ctx.http.get(
            f"https://api.lyrics.ovh/v1/{params.artist_name}/{params.track_name}",
        )
        if ovh_resp.ok:
            lyrics_text = ovh_resp.json().get("lyrics", "").strip()
            if lyrics_text:
                return ActionResult.success(
                    data={"lyrics": lyrics_text, "url": "", "title": params.track_name, "artist": params.artist_name},
                    summary=f"Lyrics for '{params.track_name}' by {params.artist_name}",
                )

        # Fallback: Genius — returns URL to lyrics page
        genius_token = await ctx.secrets.get("genius_access_token")
        if not genius_token:
            return ActionResult.error(
                f"Lyrics not found for '{params.track_name}' by {params.artist_name}.",
                retryable=False,
            )

        query = f"{params.track_name} {params.artist_name}"
        search_resp = await ctx.http.get(
            "https://api.genius.com/search",
            params={"q": query},
            headers={"Authorization": f"Bearer {genius_token}"},
        )
        if not search_resp.ok:
            return ActionResult.error(
                f"Lyrics not found for '{params.track_name}'.",
                retryable=(search_resp.status_code == 429),
            )

        hits = search_resp.json().get("response", {}).get("hits", [])
        if not hits:
            return ActionResult.error(f"Lyrics not found for '{params.track_name}'.")

        result = hits[0]["result"]
        return ActionResult.success(
            data={"lyrics": "", "url": result["url"], "title": result["title"], "artist": result["primary_artist"]["name"]},
            summary=f"Lyrics page for '{result['title']}' by {result['primary_artist']['name']}: {result['url']}",
        )

    except Exception as e:
        log.error("get_lyrics failed: %s", e)
        return ActionResult.error(f"Lyrics search failed: {str(e)}", retryable=True)
