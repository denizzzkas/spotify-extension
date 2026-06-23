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


class SpotifyConnectRecord(BaseModel):
    auth_url: str


class SpotifyConnectionRecord(BaseModel):
    connected: bool
    token_scopes: str | None = None


class SpotifyDisconnectRecord(BaseModel):
    disconnected: bool


class UserProfileRecord(sdl.Entity):
    kind: str = "user"
    username: str = sdl.field(role="spotify.username", default="")
    email: str = sdl.field(role="spotify.email", default="")
    avatar_url: str = sdl.field(role="spotify.avatar_url", default="")
    followers_count: int = sdl.field(role="spotify.followers_count", default=0)
    product: str = sdl.field(role="spotify.product", default="")


# ── Composite / list result models ────────────────────────────────────────────

class SearchResultRecord(sdl.EntityList[TrackRecord]):
    query: str = ""


class LyricsRecord(sdl.Entity):
    kind: str = "lyrics"
    lyrics: str = sdl.field(role="spotify.lyrics", default="")


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


class RecentTracksRecord(sdl.EntityList[TrackRecord]):
    pass


class LikedTracksRecord(sdl.EntityList[TrackRecord]):
    pass


class UserPlaylistsRecord(sdl.EntityList[PlaylistRecord]):
    pass


class PlaylistTracksRecord(sdl.EntityList[TrackRecord]):
    playlist_id: str = sdl.field(role="spotify.playlist_id", default="")


class PlaylistPlayRecord(sdl.EntityList[TrackRecord]):
    playlist_id: str = sdl.field(role="spotify.playlist_id", default="")


class DemoPlaylistRecord(sdl.EntityList[TrackRecord]):
    pass


class DemoTrackRecord(BaseModel):
    track_id: str
    title: str
    artist: str


class AlbumPlayRecord(BaseModel):
    album_id: str
    album_name: str
    artist: str


class ArtistAlbumsRecord(sdl.EntityList[AlbumRecord]):
    artist: str = sdl.field(role="spotify.artist", default="")


class AlbumTracksRecord(sdl.EntityList[TrackRecord]):
    album: str = sdl.field(role="spotify.album", default="")
    artist: str = sdl.field(role="spotify.artist", default="")


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
