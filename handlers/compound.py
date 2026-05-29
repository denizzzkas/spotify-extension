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

log = logging.getLogger("spotify.compound")


class AddArtistTopTracksToPlaylistParams(BaseModel):
    artist_name: str = Field(..., description="Artist name to search for")
    playlist_id: str = Field(..., description="Spotify playlist ID to add tracks to")
    limit: int = Field(10, ge=1, le=10, description="Number of top tracks to add (max 10)")


class RemoveTracksFromPlaylistByNameParams(BaseModel):
    track_names: list[str] = Field(default=[], description="Track names to remove. Can be empty when using artist_name alone.")
    playlist_id: str = Field(..., description="Spotify playlist ID. Use get_playlists first if you only have the playlist name.")
    artist_name: str = Field("", description="Filter by artist name. If track_names is empty, matches all tracks by this artist.")
    exclude: bool = Field(False, description="If True, REMOVE everything EXCEPT the matching tracks (e.g. 'keep only tracks by artist X, remove the rest').")


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
    description="Remove tracks from a playlist by name or artist. Use when user says 'remove [track] from [playlist]' or 'remove all tracks by [artist]' or 'keep only [artist], remove everything else' (set exclude=True for the last case). track_names and artist_name can be combined or used alone.",
)
async def fn_remove_tracks_from_playlist_by_name(ctx, params: RemoveTracksFromPlaylistByNameParams) -> ActionResult:
    """Fetch playlist tracks, match by name/artist, remove matched (or unmatched if exclude=True)."""
    try:
        if not params.track_names and not params.artist_name:
            return ActionResult.error("Provide at least track_names or artist_name.", retryable=False)

        tracks = []
        url = f"{SP_API_BASE}/playlists/{params.playlist_id}/items"
        fetch_params = {"limit": 50, "fields": "items(track(id,name,uri,artists)),next"}
        while url:
            resp, err = await _spotify_call(ctx, "get", url, params=fetch_params)
            if err:
                return err
            if not resp.ok:
                return _spotify_err(resp)
            data = resp.json()
            for item in (data.get("items") or []):
                raw = item.get("track")
                if raw and raw.get("id"):
                    tracks.append(raw)
            url = data.get("next")
            fetch_params = {}

        search_names = [n.lower() for n in params.track_names]
        artist_filter = params.artist_name.lower()

        def _matches(track: dict) -> bool:
            name_lower = (track.get("name") or "").lower()
            if search_names:
                name_match = any(q in name_lower or name_lower in q for q in search_names)
                if not name_match:
                    return False
            if artist_filter:
                artists = [a.get("name", "").lower() for a in (track.get("artists") or [])]
                if not any(artist_filter in a or a in artist_filter for a in artists):
                    return False
            return True

        to_remove = []
        for track in tracks:
            matched = _matches(track)
            if (matched and not params.exclude) or (not matched and params.exclude):
                uri = track.get("uri") or f"spotify:track:{track['id']}"
                if uri not in [t["uri"] for t in to_remove]:
                    to_remove.append({"uri": uri, "name": track.get("name", track["id"])})

        if not to_remove:
            if params.track_names:
                names_str = ", ".join(f"'{n}'" for n in params.track_names)
                return ActionResult.error(f"No tracks matching {names_str} found in the playlist.", retryable=False)
            return ActionResult.error("No matching tracks found in the playlist.", retryable=False)

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
            data={
                "playlist_id": params.playlist_id,
                "removed_count": len(to_remove),
                "removed_tracks": removed_names,
            },
            summary=f"Removed {len(to_remove)} track(s) from playlist: {', '.join(removed_names[:5])}" + (" ..." if len(removed_names) > 5 else ""),
        )
    except Exception as e:
        log.error("remove_tracks_from_playlist_by_name failed: %s", e)
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
        tracks_resp, err = await _spotify_call(
            ctx, "get", f"{SP_API_BASE}/search",
            params={"q": params.artist_name, "type": "track", "limit": 20},
        )
        if err:
            return err
        if not tracks_resp.ok:
            return _spotify_err(tracks_resp)

        raw_tracks = tracks_resp.json().get("tracks", {}).get("items") or []

        artist_lower = params.artist_name.lower()
        filtered = [
            t for t in raw_tracks
            if any(artist_lower in a.get("name", "").lower() or a.get("name", "").lower() in artist_lower
                   for a in (t.get("artists") or []))
        ] or raw_tracks

        filtered.sort(key=lambda t: t.get("popularity", 0), reverse=True)
        artist_display = filtered[0]["artists"][0]["name"] if filtered else params.artist_name
        uris = [to_spotify_uri(t["id"]) for t in filtered[:params.limit] if t.get("id")]
        if not uris:
            return ActionResult.error(f"No tracks found for '{params.artist_name}'.", retryable=False)

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

        album = albums[0]
        album_id = album["id"]
        album_display = album["name"]

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
