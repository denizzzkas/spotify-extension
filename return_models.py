"""Return models for @chat.function data_model= declarations (SDL-typed, SDK 5.2.0)."""
from __future__ import annotations

from pydantic import BaseModel

from imperal_sdk import sdl


# ── Core entity types ─────────────────────────────────────────────────────────
# sdl.Entity gives the platform direct access to id / title / kind.
# Custom fields carry spotify.* semantic roles via sdl.field().

class TrackRecord(sdl.Entity):
    kind: str = "track"
    url: str = ""
    artist: str = sdl.field(role="spotify.artist", default="")
    duration: str = sdl.field(role="spotify.duration_label", default="")
    duration_ms: int = sdl.field(role="spotify.duration_ms", default=0)
    popularity: int = sdl.field(role="spotify.popularity", default=0)
    preview_url: str = sdl.field(role="spotify.preview_url", default="")
    album: str = sdl.field(role="spotify.album", default="")
    album_art: str = sdl.field(role="spotify.album_art", default="")


class PlaylistRecord(sdl.Entity):
    kind: str = "playlist"
    url: str = ""
    description: str = ""
    track_count: int = sdl.field(role="spotify.track_count", default=0)
    is_public: bool = sdl.field(role="spotify.is_public", default=False)
    image_url: str = sdl.field(role="spotify.image_url", default="")


class AlbumRecord(sdl.Entity):
    kind: str = "album"
    url: str = ""
    artist: str = sdl.field(role="spotify.artist", default="")
    tracks_count: int = sdl.field(role="spotify.tracks_count", default=0)
    image_url: str = sdl.field(role="spotify.image_url", default="")
    release_date: str = sdl.field(role="spotify.release_date", default="")
    album_type: str = sdl.field(role="spotify.album_type", default="")


# ── Action / state result models ──────────────────────────────────────────────

class PlayerActionRecord(BaseModel):
    pass


class ShuffleRecord(BaseModel):
    shuffle: bool


class TrackLikeRecord(BaseModel):
    track_id: str
    liked: bool


class SpotifyConnectionRecord(BaseModel):
    connected: bool
    token_scopes: str | None = None


class SpotifyAuthRecord(BaseModel):
    auth_url: str


class SpotifyDisconnectRecord(BaseModel):
    disconnected: bool


class UserProfileRecord(BaseModel):
    id: str
    username: str
    display_name: str
    email: str
    url: str
    avatar_url: str
    followers_count: int
    product: str


# ── Composite / list result models ────────────────────────────────────────────

class SearchResultRecord(BaseModel):
    tracks: list[TrackRecord]
    count: int
    query: str


class LyricsRecord(BaseModel):
    lyrics: str = ""
    url: str = ""
    title: str
    artist: str


class PlayTrackRecord(BaseModel):
    track_id: str
    track: TrackRecord
    full_playback: bool


class PlaylistTrackRecord(BaseModel):
    playlist_id: str
    track_id: str
    added: bool


class PlaylistRemoveRecord(BaseModel):
    playlist_id: str
    track_id: str
    removed: bool


class CreatePlaylistRecord(BaseModel):
    playlist_id: str
    name: str
    url: str
    tracks_added: int


class PlaylistPlayRecord(BaseModel):
    playlist_id: str
    tracks: list[TrackRecord]
    count: int


class DemoPlaylistRecord(BaseModel):
    count: int
    tracks: list[TrackRecord]


class DemoTrackRecord(BaseModel):
    track_id: str
    title: str
    artist: str


class AlbumPlayRecord(BaseModel):
    album_id: str
    album_name: str
    artist: str


class ArtistAlbumsRecord(BaseModel):
    albums: list[AlbumRecord]
    count: int
    artist: str


class AlbumTracksRecord(BaseModel):
    tracks: list[TrackRecord]
    count: int
    album: str
    artist: str


class DeletePlaylistRecord(BaseModel):
    playlist_id: str
    deleted: bool


class BulkAddTracksRecord(BaseModel):
    playlist_id: str
    tracks_added: int


class BulkRemoveTracksRecord(BaseModel):
    playlist_id: str
    removed_count: int
    removed_tracks: list[str]


class RenamePlaylistRecord(BaseModel):
    playlist_id: str
    name: str
