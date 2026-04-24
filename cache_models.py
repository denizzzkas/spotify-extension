"""Pydantic models for ctx.cache — registered in app.py via ext.cache_model."""
from __future__ import annotations
from pydantic import BaseModel


class NowPlayingModel(BaseModel):
    id: str = ""
    title: str = ""
    artist: str = ""
    url: str = ""
    duration: str = ""
    duration_ms: int = 0
    popularity: int = 0
    preview_url: str = ""
    album: str = ""
    album_art: str = ""
    is_playing: bool = False


class SearchModel(BaseModel):
    query: str = ""
    tracks: list[dict] = []


class DetailModel(BaseModel):
    type: str = ""
    title: str = ""
    tracks: list[dict] = []
    profile: dict = {}


class PlaylistsModel(BaseModel):
    items: list[dict] = []


class QueueModel(BaseModel):
    playlist_id: str = ""
    playlist_name: str = ""
    tracks: list[dict] = []  # capped at 30 to stay under 64 KB
    index: int = 0
