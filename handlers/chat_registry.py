"""Registers all @ext.tool handlers on the Extension instance."""
from __future__ import annotations

from imperal_sdk import ActionResult

from handlers.search import fn_search_tracks, SearchTracksParams, fn_get_recommendations, GetRecommendationsParams
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
from handlers.playback import (
    fn_play_track, PlayTrackParams,
    fn_play_track_by_name, PlayTrackByNameParams,
    fn_play_playlist, PlayPlaylistParams,
    fn_pause_playback, PausePlaybackParams,
    fn_resume_playback, ResumePlaybackParams,
    fn_next_track, NextTrackParams,
    fn_prev_track, PrevTrackParams,
)
from handlers.panel import (
    fn_panel_search, PanelSearchParams,
    fn_open_playlist, OpenPlaylistParams,
    fn_open_liked_tracks, OpenLikedTracksParams,
    fn_open_recent_tracks, OpenRecentTracksParams,
    fn_open_profile, OpenProfileParams,
)


def register(ext) -> None:
    """Register all tools on the given Extension instance."""

    @ext.tool("search_tracks",
               description="Search Spotify for tracks by title or artist name.")
    async def wrapped_search_tracks(ctx, params: SearchTracksParams) -> ActionResult:
        return await fn_search_tracks(ctx, params)

    @ext.tool("get_recommendations",
               description="Get track recommendations based on an artist, track title, or genre.")
    async def wrapped_get_recommendations(ctx, params: GetRecommendationsParams) -> ActionResult:
        return await fn_get_recommendations(ctx, params)

    @ext.tool("get_recent_tracks",
               description="Get the user's recently played tracks from Spotify (requires Premium).")
    async def wrapped_get_recent_tracks(ctx, params: GetRecentTracksParams) -> ActionResult:
        return await fn_get_recent_tracks(ctx, params)

    @ext.tool("get_liked_tracks",
               description="Get all tracks saved in the user's Spotify library.")
    async def wrapped_get_liked_tracks(ctx, params: GetLikedTracksParams) -> ActionResult:
        return await fn_get_liked_tracks(ctx, params)

    @ext.tool("like_track",
               description="Save a track to the user's Spotify library.")
    async def wrapped_like_track(ctx, params: LikeTrackParams) -> ActionResult:
        result = await fn_like_track(ctx, params)
        if result.status == "success":
            await ctx.extensions.emit("track.liked", {})
        return result

    @ext.tool("unlike_track",
               description="Remove a track from the user's Spotify library.")
    async def wrapped_unlike_track(ctx, params: UnlikeTrackParams) -> ActionResult:
        result = await fn_unlike_track(ctx, params)
        if result.status == "success":
            await ctx.extensions.emit("track.unliked", {})
        return result

    @ext.tool("get_user_profile",
               description="Get the authenticated user's Spotify profile: display name, email, plan.")
    async def wrapped_get_user_profile(ctx, params: GetUserProfileParams) -> ActionResult:
        return await fn_get_user_profile(ctx, params)

    @ext.tool("get_playlists",
               description="Get all playlists owned or followed by the authenticated Spotify user.")
    async def wrapped_get_playlists(ctx, params: GetPlaylistsParams) -> ActionResult:
        return await fn_get_playlists(ctx, params)

    @ext.tool("get_playlist_tracks",
               description="Get all tracks in a specific Spotify playlist by its ID.")
    async def wrapped_get_playlist_tracks(ctx, params: GetPlaylistTracksParams) -> ActionResult:
        return await fn_get_playlist_tracks(ctx, params)

    @ext.tool("create_playlist",
               description="Create a new playlist on the user's Spotify account.")
    async def wrapped_create_playlist(ctx, params: CreatePlaylistParams) -> ActionResult:
        result = await fn_create_playlist(ctx, params)
        if result.status == "success":
            await ctx.extensions.emit("playlist.created", {})
        return result

    @ext.tool("add_track_to_playlist",
               description="Add a track to an existing Spotify playlist.")
    async def wrapped_add_track_to_playlist(ctx, params: AddTrackToPlaylistParams) -> ActionResult:
        result = await fn_add_track_to_playlist(ctx, params)
        if result.status == "success":
            await ctx.extensions.emit("track.added_to_playlist", {})
        return result

    @ext.tool("remove_track_from_playlist",
               description="Remove a track from a Spotify playlist.")
    async def wrapped_remove_track_from_playlist(ctx, params: RemoveTrackFromPlaylistParams) -> ActionResult:
        result = await fn_remove_track_from_playlist(ctx, params)
        if result.status == "success":
            await ctx.extensions.emit("track.removed_from_playlist", {})
        return result

    @ext.tool("play_track",
               description="Get track metadata and trigger playback.")
    async def wrapped_play_track(ctx, params: PlayTrackParams) -> ActionResult:
        result = await fn_play_track(ctx, params)
        if result.status == "success":
            await ctx.extensions.emit("track.played", {})
        return result

    @ext.tool("play_track_by_name",
               description="Search for a track by title and artist name, then play it.")
    async def wrapped_play_track_by_name(ctx, params: PlayTrackByNameParams) -> ActionResult:
        result = await fn_play_track_by_name(ctx, params)
        if result.status == "success":
            await ctx.extensions.emit("track.played", {})
        return result

    @ext.tool("play_playlist",
               description="Play all tracks in a Spotify playlist sequentially.")
    async def wrapped_play_playlist(ctx, params: PlayPlaylistParams) -> ActionResult:
        result = await fn_play_playlist(ctx, params)
        if result.status == "success":
            await ctx.extensions.emit("playlist.played", {})
        return result

    @ext.tool("pause_playback",
               description="Pause playback on the user's active Spotify device.")
    async def wrapped_pause_playback(ctx, params: PausePlaybackParams) -> ActionResult:
        return await fn_pause_playback(ctx, params)

    @ext.tool("resume_playback",
               description="Resume playback on the user's active Spotify device.")
    async def wrapped_resume_playback(ctx, params: ResumePlaybackParams) -> ActionResult:
        return await fn_resume_playback(ctx, params)

    @ext.tool("next_track",
               description="Skip to the next track on the user's active Spotify device.")
    async def wrapped_next_track(ctx, params: NextTrackParams) -> ActionResult:
        return await fn_next_track(ctx, params)

    @ext.tool("previous_track",
               description="Skip to the previous track on the user's active Spotify device.")
    async def wrapped_prev_track(ctx, params: PrevTrackParams) -> ActionResult:
        return await fn_prev_track(ctx, params)

    @ext.tool("panel_search_tracks",
               description="Search Spotify tracks and show results in the sidebar panel.")
    async def wrapped_panel_search(ctx, params: PanelSearchParams) -> ActionResult:
        return await fn_panel_search(ctx, params)

    @ext.tool("open_playlist",
               description="Open a playlist's tracks in the right detail panel.")
    async def wrapped_open_playlist(ctx, params: OpenPlaylistParams) -> ActionResult:
        return await fn_open_playlist(ctx, params)

    @ext.tool("open_liked_tracks",
               description="Open liked/saved tracks in the right detail panel.")
    async def wrapped_open_liked_tracks(ctx, params: OpenLikedTracksParams) -> ActionResult:
        return await fn_open_liked_tracks(ctx, params)

    @ext.tool("open_recent_tracks",
               description="Open recently played tracks in the right detail panel.")
    async def wrapped_open_recent_tracks(ctx, params: OpenRecentTracksParams) -> ActionResult:
        return await fn_open_recent_tracks(ctx, params)

    @ext.tool("open_profile",
               description="Open the user's Spotify profile in the right detail panel.")
    async def wrapped_open_profile(ctx, params: OpenProfileParams) -> ActionResult:
        return await fn_open_profile(ctx, params)
