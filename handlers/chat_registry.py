"""Registers all @chat.function handlers on the ChatExtension instance."""
from __future__ import annotations

from imperal_sdk import ActionResult

from handlers.search import fn_search_tracks, SearchTracksParams
from handlers.playlists import (
    fn_get_playlists, GetPlaylistsParams,
    fn_get_playlist_tracks, GetPlaylistTracksParams,
    fn_create_playlist, CreatePlaylistParams,
    fn_add_track_to_playlist, AddTrackToPlaylistParams,
    fn_remove_track_from_playlist, RemoveTrackFromPlaylistParams,
)
from handlers.library import (
    fn_get_recent_tracks, GetRecentTracksParams,
    fn_get_liked_tracks, GetLikedTracksParams,
    fn_like_track, LikeTrackParams,
    fn_unlike_track, UnlikeTrackParams,
    fn_get_user_profile, GetUserProfileParams,
)
from handlers.playback import fn_play_track, PlayTrackParams


def register(chat) -> None:
    """Register all chat functions on the given ChatExtension instance."""

    @chat.function("search_tracks",
                   description="Search Spotify for tracks by title or artist name.",
                   action_type="read")
    async def wrapped_search_tracks(ctx, params: SearchTracksParams) -> ActionResult:
        return await fn_search_tracks(ctx, params)

    @chat.function("get_recent_tracks",
                   description="Get the user's recently played tracks from Spotify (requires Premium).",
                   action_type="read")
    async def wrapped_get_recent_tracks(ctx, params: GetRecentTracksParams) -> ActionResult:
        return await fn_get_recent_tracks(ctx, params)

    @chat.function("get_liked_tracks",
                   description="Get all tracks saved in the user's Spotify library.",
                   action_type="read")
    async def wrapped_get_liked_tracks(ctx, params: GetLikedTracksParams) -> ActionResult:
        return await fn_get_liked_tracks(ctx, params)

    @chat.function("like_track",
                   description="Save a track to the user's Spotify library.",
                   action_type="write", event="track.liked")
    async def wrapped_like_track(ctx, params: LikeTrackParams) -> ActionResult:
        return await fn_like_track(ctx, params)

    @chat.function("unlike_track",
                   description="Remove a track from the user's Spotify library.",
                   action_type="write", event="track.unliked")
    async def wrapped_unlike_track(ctx, params: UnlikeTrackParams) -> ActionResult:
        return await fn_unlike_track(ctx, params)

    @chat.function("get_user_profile",
                   description="Get the authenticated user's Spotify profile: display name, email, plan.",
                   action_type="read")
    async def wrapped_get_user_profile(ctx, params: GetUserProfileParams) -> ActionResult:
        return await fn_get_user_profile(ctx, params)

    @chat.function("get_playlists",
                   description="Get all playlists owned or followed by the authenticated Spotify user.",
                   action_type="read")
    async def wrapped_get_playlists(ctx, params: GetPlaylistsParams) -> ActionResult:
        return await fn_get_playlists(ctx, params)

    @chat.function("get_playlist_tracks",
                   description="Get all tracks in a specific Spotify playlist by its ID.",
                   action_type="read")
    async def wrapped_get_playlist_tracks(ctx, params: GetPlaylistTracksParams) -> ActionResult:
        return await fn_get_playlist_tracks(ctx, params)

    @chat.function("create_playlist",
                   description="Create a new playlist on the user's Spotify account.",
                   action_type="write", event="playlist.created")
    async def wrapped_create_playlist(ctx, params: CreatePlaylistParams) -> ActionResult:
        return await fn_create_playlist(ctx, params)

    @chat.function("add_track_to_playlist",
                   description="Add a track to an existing Spotify playlist.",
                   action_type="write", event="track.added_to_playlist")
    async def wrapped_add_track_to_playlist(ctx, params: AddTrackToPlaylistParams) -> ActionResult:
        return await fn_add_track_to_playlist(ctx, params)

    @chat.function("remove_track_from_playlist",
                   description="Remove a track from a Spotify playlist.",
                   action_type="write", event="track.removed_from_playlist")
    async def wrapped_remove_track_from_playlist(ctx, params: RemoveTrackFromPlaylistParams) -> ActionResult:
        return await fn_remove_track_from_playlist(ctx, params)

    @chat.function("play_track",
                   description="Get track metadata and trigger a track.played event for platform playback.",
                   action_type="write", event="track.played")
    async def wrapped_play_track(ctx, params: PlayTrackParams) -> ActionResult:
        return await fn_play_track(ctx, params)
