"""Return models for @chat.function data_model= declarations (SDK 5.0.1 V23/V24)."""
from __future__ import annotations

from pydantic import BaseModel


class TrackRecord(BaseModel):
    id: str
    title: str
    artist: str
    url: str
    duration: str
    duration_ms: int
    popularity: int
    preview_url: str
    album: str
    album_art: str


class PlaylistRecord(BaseModel):
    id: str
    title: str
    track_count: int
    url: str
    description: str
    is_public: bool
    image_url: str


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


class AlbumRecord(BaseModel):
    id: str
    name: str
    artist: str
    url: str
    tracks_count: int
    image_url: str
    release_date: str
    album_type: str


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
