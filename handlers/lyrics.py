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
    description="Fetch full song lyrics. Returns the complete lyrics as formatted text. Only track_name is required; providing artist_name improves accuracy. If lyrics are found, they are displayed in full — no need to call search_tracks first.",
)
async def fn_get_lyrics(ctx, params: GetLyricsParams) -> ActionResult:
    """Fetch lyrics via lrclib.net (exact then fuzzy), fall back to Genius URL."""
    try:
        lyrics_text = ""
        found_title = params.track_name
        found_artist = params.artist_name

        # 1. Exact lookup with artist (most accurate)
        if params.artist_name:
            lrc_resp = await ctx.http.get(
                "https://lrclib.net/api/get",
                params={"track_name": params.track_name, "artist_name": params.artist_name},
            )
            if lrc_resp.ok:
                try:
                    body = lrc_resp.json()
                    lyrics_text = (body.get("plainLyrics") or "").strip()
                    if lyrics_text:
                        found_title = body.get("trackName") or params.track_name
                        found_artist = body.get("artistName") or params.artist_name
                except Exception:
                    pass

        # 1b. Exact lookup by title only (when no artist provided)
        if not lyrics_text:
            lrc_resp = await ctx.http.get(
                "https://lrclib.net/api/get",
                params={"track_name": params.track_name},
            )
            if lrc_resp.ok:
                try:
                    body = lrc_resp.json()
                    lyrics_text = (body.get("plainLyrics") or "").strip()
                    if lyrics_text:
                        found_title = body.get("trackName") or params.track_name
                        found_artist = body.get("artistName") or params.artist_name
                except Exception:
                    pass

        # 2. Fuzzy search — handles partial name mismatches
        if not lyrics_text:
            q = f"{params.track_name} {params.artist_name}".strip()
            search_resp = await ctx.http.get(
                "https://lrclib.net/api/search",
                params={"q": q},
            )
            if search_resp.ok:
                try:
                    for item in (search_resp.json() or []):
                        text = (item.get("plainLyrics") or "").strip()
                        if text:
                            lyrics_text = text
                            found_title = item.get("trackName") or params.track_name
                            found_artist = item.get("artistName") or params.artist_name
                            break
                except Exception:
                    pass

        if lyrics_text:
            paragraphs = [p.strip() for p in lyrics_text.split("\n\n") if p.strip()]
            formatted = "\n\n".join(paragraphs)
            summary = f"**{found_title}** — {found_artist}\n\n{formatted}"
            return ActionResult.success(
                data={"lyrics": lyrics_text, "url": "", "title": found_title, "artist": found_artist},
                summary=summary,
            )

        # 3. Fallback: Genius URL
        genius_token = await ctx.secrets.get("genius_access_token")
        query = f"{params.track_name} {params.artist_name}".strip()

        if genius_token:
            genius_resp = await ctx.http.get(
                "https://api.genius.com/search",
                params={"q": query},
                headers={"Authorization": f"Bearer {genius_token}"},
            )
            if genius_resp.ok:
                hits = genius_resp.json().get("response", {}).get("hits", [])
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
