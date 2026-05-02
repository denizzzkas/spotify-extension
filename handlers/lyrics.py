"""Genius lyrics handler — fetch song lyrics from Genius API."""
from __future__ import annotations

from pydantic import BaseModel, Field

from imperal_sdk import ActionResult

GENIUS_ACCESS_TOKEN = "kLp7D46sSLTNr3_eZFz4vLinJeiaYbx_7bSu20-itx4g-WBa_IKCMYh-AmtaBbMI"


class GetLyricsParams(BaseModel):
    track_name: str = Field(..., description="Song title")
    artist_name: str = Field(..., description="Artist name")


async def fn_get_lyrics(ctx, params: GetLyricsParams) -> ActionResult:
    """Fetch song lyrics from Genius API."""
    if not GENIUS_ACCESS_TOKEN:
        return ActionResult.error(
            "Genius API token not configured.",
            retryable=False
        )

    query = f"{params.track_name} {params.artist_name}"

    try:
        headers = {"Authorization": f"Bearer {GENIUS_ACCESS_TOKEN}"}
        search_resp = await ctx.http.get(
            "https://api.genius.com/search",
            params={"q": query},
            headers=headers,
        )

        if not search_resp.ok:
            return ActionResult.error(
                f"Genius search failed: {search_resp.status_code}",
                retryable=(search_resp.status_code == 429)
            )

        hits = search_resp.json().get("response", {}).get("hits", [])
        if not hits:
            return ActionResult.error(
                f"No lyrics found for '{query}'",
                retryable=False
            )

        song_url = hits[0]["result"]["url"]

        lyrics_resp = await ctx.http.get(song_url)
        if not lyrics_resp.ok:
            return ActionResult.error(
                "Failed to fetch lyrics page",
                retryable=True
            )

        import re
        html = lyrics_resp.text

        lyrics_pattern = r'<div data-lyrics-container="true">(.*?)</div>'
        matches = re.findall(lyrics_pattern, html, re.DOTALL)

        if not matches:
            return ActionResult.error(
                "Could not parse lyrics from page",
                retryable=False
            )

        def clean_html(text):
            text = re.sub(r'<br\s*/?>', '\n', text)
            text = re.sub(r'<[^>]+>', '', text)
            text = text.strip()
            return text

        lyrics = "\n\n".join([clean_html(match) for match in matches])

        if not lyrics.strip():
            return ActionResult.error(
                "Lyrics are empty",
                retryable=False
            )

        song_title = hits[0]["result"]["title"]
        song_artist = hits[0]["result"]["primary_artist"]["name"]

        return ActionResult.success(
            data={"lyrics": lyrics, "title": song_title, "artist": song_artist},
            summary=f"Lyrics for '{song_title}' by {song_artist}"
        )

    except Exception as e:
        return ActionResult.error(f"Error fetching lyrics: {str(e)}", retryable=True)
