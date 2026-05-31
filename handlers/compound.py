"""Compound handlers — multi-step Spotify operations in a single function call."""
from __future__ import annotations

import logging

from pydantic import BaseModel, Field

from imperal_sdk import ActionResult

from app import chat
from return_models import BulkAddTracksRecord, BulkRemoveTracksRecord
from spotify_config import SP_API_BASE
from app_helpers import _spotify_call, _spotify_err
from utils import to_spotify_uri
from handlers.artists import _find_artist_id

log = logging.getLogger("spotify.compound")


async def _fetch_playlist_tracks(ctx, playlist_id: str):
    tracks, url, fetch_params = [], f"{SP_API_BASE}/playlists/{playlist_id}/items", {"limit": 50}
    while url:
        resp, err = await _spotify_call(ctx, "get", url, params=fetch_params)
        if err:
            return None, err
        if not resp.ok:
            return None, _spotify_err(resp)
        data = resp.json()
        for item in (data.get("items") or []):
            raw = item.get("item")
            if raw and raw.get("id"):
                tracks.append(raw)
        url, fetch_params = data.get("next"), {}
    return tracks, None


class AddArtistTopTracksToPlaylistParams(BaseModel):
    artist_name: str = Field(..., description="Artist name to search for")
    playlist_id: str = Field(..., description="Spotify playlist ID to add tracks to")
    limit: int = Field(10, ge=1, le=10, description="Number of top tracks to add (max 10)")


class RemoveTracksFromPlaylistByNameParams(BaseModel):
    track_names: list[str] = Field(default=[], description="Track names to remove. Leave empty when filtering by artist_name or duration alone.")
    playlist_id: str = Field(..., description="Spotify playlist ID. Use get_playlists first if you only have the playlist name.")
    artist_name: str = Field("", description="Filter by artist name. Removes all tracks by this artist when track_names is empty.")
    exclude: bool | None = Field(None, description="Set to True to REMOVE everything EXCEPT matches — e.g. 'keep only Artist X, remove the rest'.")
    min_duration_ms: int | None = Field(None, description="Remove tracks LONGER than this ms. 4 min = 240000, 5 min = 300000.")
    max_duration_ms: int | None = Field(None, description="Remove tracks SHORTER than this ms. 2 min = 120000, 3 min = 180000.")


class RemoveDuplicateTracksParams(BaseModel):
    playlist_id: str = Field(..., description="Spotify playlist ID to remove duplicate tracks from")


class AddAlbumTracksToPlaylistParams(BaseModel):
    album_name: str = Field(..., description="Album name to search for")
    artist_name: str = Field("", description="Artist name to narrow the album search (optional)")
    playlist_id: str = Field(..., description="Spotify playlist ID to add tracks to")
    limit: int = Field(50, ge=1, le=50, description="Maximum number of tracks to add from the album")


@chat.function(
    "remove_tracks_from_playlist_by_name",
    action_type="write",
    chain_callable=True,
    id_projection="playlist_id",
    effects=["playlist:remove_track"],
    event="track.removed_from_playlist",
    data_model=BulkRemoveTracksRecord,
    description="Remove tracks from a playlist by name, artist, or duration. Examples: 'remove [track]', 'remove all tracks by [artist]', 'remove tracks longer than 4 minutes' (min_duration_ms=240000), 'keep only [artist]' (exclude=True). Filters can be combined.",
)
async def fn_remove_tracks_from_playlist_by_name(ctx, params: RemoveTracksFromPlaylistByNameParams) -> ActionResult:
    """Fetch playlist tracks, match by name/artist/duration, remove matched (or unmatched if exclude=True)."""
    try:
        has_filter = params.track_names or params.artist_name or params.min_duration_ms is not None or params.max_duration_ms is not None
        if not has_filter:
            return ActionResult.error("Provide at least one filter: track_names, artist_name, min_duration_ms, or max_duration_ms.", retryable=False)

        tracks, err = await _fetch_playlist_tracks(ctx, params.playlist_id)
        if err:
            return err
        search_names = [n.lower() for n in params.track_names]
        artist_filter = params.artist_name.lower()
        exclude = bool(params.exclude)

        def _matches(t: dict) -> bool:
            name = (t.get("name") or "").lower()
            if search_names and not any(q in name or name in q for q in search_names):
                return False
            artists = [a.get("name", "").lower() for a in (t.get("artists") or [])]
            if artist_filter and not any(artist_filter in a or a in artist_filter for a in artists):
                return False
            dur = t.get("duration_ms") or 0
            return (params.min_duration_ms is None or dur >= params.min_duration_ms) and (params.max_duration_ms is None or dur <= params.max_duration_ms)

        seen_uris: set[str] = set()
        to_remove = []
        for track in tracks:
            uri = track.get("uri") or f"spotify:track:{track['id']}"
            if _matches(track) != exclude and uri not in seen_uris:
                seen_uris.add(uri)
                to_remove.append({"uri": uri, "name": track.get("name", track["id"])})

        if not to_remove:
            detail = f" matching {', '.join(repr(n) for n in params.track_names)}" if params.track_names else ""
            return ActionResult.error(f"No tracks{detail} found in the playlist.", retryable=False)

        removed_names = [t["name"] for t in to_remove]
        for i in range(0, len(to_remove), 100):
            batch = to_remove[i:i + 100]
            del_resp, err = await _spotify_call(
                ctx, "delete", f"{SP_API_BASE}/playlists/{params.playlist_id}/items",
                json={"items": [{"uri": t["uri"]} for t in batch]},
            )
            if err:
                return err
            if not del_resp.ok:
                return _spotify_err(del_resp)

        return ActionResult.success(
            data={"playlist_id": params.playlist_id, "removed_count": len(to_remove), "removed_tracks": removed_names},
            summary=f"Removed {len(to_remove)} track(s): {', '.join(removed_names[:5])}" + (" ..." if len(removed_names) > 5 else ""),
        )
    except Exception as e:
        log.error("remove_tracks_from_playlist_by_name failed: %s", e)
        return ActionResult.error(f"Failed: {str(e)}", retryable=False)


@chat.function(
    "remove_duplicate_tracks",
    action_type="write",
    chain_callable=True,
    id_projection="playlist_id",
    effects=["playlist:remove_track"],
    event="track.removed_from_playlist",
    data_model=BulkRemoveTracksRecord,
    description="Remove duplicate tracks from a playlist, keeping the first occurrence of each track.",
)
async def fn_remove_duplicate_tracks(ctx, params: RemoveDuplicateTracksParams) -> ActionResult:
    """Fetch all playlist tracks, find duplicates by ID, remove extra occurrences using positions."""
    try:
        tracks, err = await _fetch_playlist_tracks(ctx, params.playlist_id)
        if err:
            return err

        seen_ids: set[str] = set()
        dup_uris: dict[str, int] = {}
        for track in tracks:
            tid = track["id"]
            uri = track.get("uri") or f"spotify:track:{tid}"
            if tid in seen_ids:
                dup_uris[uri] = dup_uris.get(uri, 0) + 1
            else:
                seen_ids.add(tid)

        if not dup_uris:
            return ActionResult.error("No duplicate tracks found in the playlist.", retryable=False)

        uris_to_dedup = list(dup_uris.keys())
        removed_count = sum(dup_uris.values())

        for i in range(0, len(uris_to_dedup), 100):
            batch = [{"uri": uri} for uri in uris_to_dedup[i:i + 100]]
            del_resp, err = await _spotify_call(
                ctx, "delete", f"{SP_API_BASE}/playlists/{params.playlist_id}/items",
                json={"items": batch},
            )
            if err:
                return err
            if not del_resp.ok:
                return _spotify_err(del_resp)

        for i in range(0, len(uris_to_dedup), 100):
            batch = uris_to_dedup[i:i + 100]
            add_resp, err = await _spotify_call(
                ctx, "post", f"{SP_API_BASE}/playlists/{params.playlist_id}/items",
                json={"uris": batch},
            )
            if err:
                return err
            if not add_resp.ok:
                return _spotify_err(add_resp)

        return ActionResult.success(
            data={"playlist_id": params.playlist_id, "removed_count": removed_count, "removed_tracks": []},
            summary=f"Removed {removed_count} duplicate track(s) from playlist",
        )
    except Exception as e:
        log.error("remove_duplicate_tracks failed: %s", e)
        return ActionResult.error(f"Failed: {str(e)}", retryable=False)


@chat.function(
    "add_artist_top_tracks_to_playlist",
    action_type="write",
    chain_callable=True,
    id_projection="playlist_id",
    effects=["playlist:add_track"],
    event="track.added_to_playlist",
    data_model=BulkAddTracksRecord,
    description="Find an artist by name and add their top tracks to a playlist in one step. Use when the user says 'add top tracks from [artist] to [playlist]' or 'add N tracks by [artist] to [playlist]'.",
)
async def fn_add_artist_top_tracks_to_playlist(ctx, params: AddArtistTopTracksToPlaylistParams) -> ActionResult:
    """Search artist → get top tracks → add to playlist in one operation."""
    try:
        artist_id, artist_display, err = await _find_artist_id(ctx, params.artist_name)
        if err:
            return err

        tracks_resp, err = await _spotify_call(
            ctx, "get", f"{SP_API_BASE}/artists/{artist_id}/top-tracks",
        )
        if err:
            return err
        if not tracks_resp.ok:
            return _spotify_err(tracks_resp)

        raw_tracks = tracks_resp.json().get("tracks") or []
        uris = [to_spotify_uri(t["id"]) for t in raw_tracks[:params.limit] if t.get("id")]
        if not uris:
            return ActionResult.error(f"No top tracks found for '{params.artist_name}'.", retryable=False)

        add_resp, err = await _spotify_call(
            ctx, "post", f"{SP_API_BASE}/playlists/{params.playlist_id}/items",
            json={"uris": uris},
        )
        if err:
            return err
        if not add_resp.ok:
            return _spotify_err(add_resp)
        return ActionResult.success(
            data={"playlist_id": params.playlist_id, "tracks_added": len(uris)},
            summary=f"Added {len(uris)} top tracks by {artist_display} to playlist",
        )
    except Exception as e:
        log.error("add_artist_top_tracks_to_playlist failed: %s", e)
        return ActionResult.error(f"Failed: {str(e)}", retryable=False)


@chat.function(
    "add_album_tracks_to_playlist",
    action_type="write",
    chain_callable=True,
    id_projection="playlist_id",
    effects=["playlist:add_track"],
    event="track.added_to_playlist",
    data_model=BulkAddTracksRecord,
    description="Find an album by name and add its tracks to a playlist in one step. Use when the user says 'add tracks from [album] to [playlist]' or 'add first N tracks from [album] to [playlist]'.",
)
async def fn_add_album_tracks_to_playlist(ctx, params: AddAlbumTracksToPlaylistParams) -> ActionResult:
    """Search album → get tracks → add to playlist in one operation."""
    try:
        query = f"{params.album_name} {params.artist_name}".strip()
        search_resp, err = await _spotify_call(
            ctx, "get", f"{SP_API_BASE}/search",
            params={"q": query, "type": "album", "limit": 1},
        )
        if err:
            return err
        if not search_resp.ok:
            return _spotify_err(search_resp)

        albums = search_resp.json().get("albums", {}).get("items", [])
        if not albums:
            return ActionResult.error(f"Album '{params.album_name}' not found on Spotify.", retryable=False)

        album_id, album_display = albums[0]["id"], albums[0]["name"]

        tracks_resp, err = await _spotify_call(
            ctx, "get", f"{SP_API_BASE}/albums/{album_id}/tracks",
            params={"limit": 50},
        )
        if err:
            return err
        if not tracks_resp.ok:
            return _spotify_err(tracks_resp)

        raw_tracks = tracks_resp.json().get("items") or []
        uris = [to_spotify_uri(t["id"]) for t in raw_tracks[:params.limit] if t.get("id")]
        if not uris:
            return ActionResult.error(f"No tracks found in album '{album_display}'.", retryable=False)

        add_resp, err = await _spotify_call(
            ctx, "post", f"{SP_API_BASE}/playlists/{params.playlist_id}/items",
            json={"uris": uris},
        )
        if err:
            return err
        if not add_resp.ok:
            return _spotify_err(add_resp)

        return ActionResult.success(
            data={"playlist_id": params.playlist_id, "tracks_added": len(uris)},
            summary=f"Added {len(uris)} tracks from '{album_display}' to playlist",
        )
    except Exception as e:
        log.error("add_album_tracks_to_playlist failed: %s", e)
        return ActionResult.error(f"Failed: {str(e)}", retryable=False)
