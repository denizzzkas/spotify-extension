"""Registers all @chat.function handlers on the ChatExtension instance."""
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


def register(chat) -> None:
    """Register all chat functions on the given ChatExtension instance."""

    @chat.function("search_tracks",
                   description="Search Spotify for tracks by title or artist name.",
                   action_type="read")
    async def wrapped_search_tracks(ctx, params: SearchTracksParams) -> ActionResult:
        """Search Spotify catalogue for tracks matching a query string."""
        return await fn_search_tracks(ctx, params)

    @chat.function("get_recommendations",
                   description="Get track recommendations based on an artist, track title, or genre.",
                   action_type="read")
    async def wrapped_get_recommendations(ctx, params: GetRecommendationsParams) -> ActionResult:
        """Return Spotify recommendations similar to the given artist, track, or genre."""
        return await fn_get_recommendations(ctx, params)

    @chat.function("get_recent_tracks",
                   description="Get the user's recently played tracks from Spotify (requires Premium).",
                   action_type="read")
    async def wrapped_get_recent_tracks(ctx, params: GetRecentTracksParams) -> ActionResult:
        """Return the user's Spotify playback history, most recent first."""
        return await fn_get_recent_tracks(ctx, params)

    @chat.function("get_liked_tracks",
                   description="Get all tracks saved in the user's Spotify library.",
                   action_type="read")
    async def wrapped_get_liked_tracks(ctx, params: GetLikedTracksParams) -> ActionResult:
        """Return tracks saved to the user's Spotify Liked Songs library."""
        return await fn_get_liked_tracks(ctx, params)

    @chat.function("like_track",
                   description="Save a track to the user's Spotify library.",
                   action_type="write", event="track.liked")
    async def wrapped_like_track(ctx, params: LikeTrackParams) -> ActionResult:
        """Add a track to the user's Liked Songs by Spotify track ID."""
        return await fn_like_track(ctx, params)

    @chat.function("unlike_track",
                   description="Remove a track from the user's Spotify library.",
                   action_type="write", event="track.unliked")
    async def wrapped_unlike_track(ctx, params: UnlikeTrackParams) -> ActionResult:
        """Remove a track from the user's Liked Songs by Spotify track ID."""
        return await fn_unlike_track(ctx, params)

    @chat.function("get_user_profile",
                   description="Get the authenticated user's Spotify profile: display name, email, plan.",
                   action_type="read")
    async def wrapped_get_user_profile(ctx, params: GetUserProfileParams) -> ActionResult:
        """Return the current user's Spotify account details and subscription plan."""
        return await fn_get_user_profile(ctx, params)

    @chat.function("get_playlists",
                   description="Get all playlists owned or followed by the authenticated Spotify user.",
                   action_type="read")
    async def wrapped_get_playlists(ctx, params: GetPlaylistsParams) -> ActionResult:
        """Return all playlists visible to the authenticated Spotify user."""
        return await fn_get_playlists(ctx, params)

    @chat.function("get_playlist_tracks",
                   description="Get all tracks in a specific Spotify playlist by its ID.",
                   action_type="read")
    async def wrapped_get_playlist_tracks(ctx, params: GetPlaylistTracksParams) -> ActionResult:
        """Return the full track listing for a given Spotify playlist ID."""
        return await fn_get_playlist_tracks(ctx, params)

    @chat.function("create_playlist",
                   description="Create a new playlist on the user's Spotify account.",
                   action_type="write", event="playlist.created")
    async def wrapped_create_playlist(ctx, params: CreatePlaylistParams) -> ActionResult:
        """Create a new named playlist on the user's Spotify account."""
        return await fn_create_playlist(ctx, params)

    @chat.function("add_track_to_playlist",
                   description="Add a track to an existing Spotify playlist.",
                   action_type="write", event="track.added_to_playlist")
    async def wrapped_add_track_to_playlist(ctx, params: AddTrackToPlaylistParams) -> ActionResult:
        """Append a track to an existing Spotify playlist by track and playlist ID."""
        return await fn_add_track_to_playlist(ctx, params)

    @chat.function("remove_track_from_playlist",
                   description="Remove a track from a Spotify playlist.",
                   action_type="write", event="track.removed_from_playlist")
    async def wrapped_remove_track_from_playlist(ctx, params: RemoveTrackFromPlaylistParams) -> ActionResult:
        """Remove a specific track from a Spotify playlist by track and playlist ID."""
        return await fn_remove_track_from_playlist(ctx, params)

    @chat.function("play_track",
                   description="Get track metadata and trigger a track.played event for platform playback.",
                   action_type="write", event="track.played")
    async def wrapped_play_track(ctx, params: PlayTrackParams) -> ActionResult:
        """Fetch track metadata and emit a track.played event for platform-level playback."""
        return await fn_play_track(ctx, params)

    @chat.function("play_track_by_name",
                   description="Search for a track by title and artist name, then play it.",
                   action_type="write", event="track.played")
    async def wrapped_play_track_by_name(ctx, params: PlayTrackByNameParams) -> ActionResult:
        """Find a track by name and artist and trigger platform playback."""
        return await fn_play_track_by_name(ctx, params)

    @chat.function("play_playlist",
                   description="Play all tracks in a Spotify playlist sequentially.",
                   action_type="write", event="playlist.played")
    async def wrapped_play_playlist(ctx, params: PlayPlaylistParams) -> ActionResult:
        """Load playlist queue and trigger platform playback."""
        return await fn_play_playlist(ctx, params)

    @chat.function("pause_playback",
                   description="Pause playback on the user's active Spotify device.",
                   action_type="read")
    async def wrapped_pause_playback(ctx, params: PausePlaybackParams) -> ActionResult:
        return await fn_pause_playback(ctx, params)

    @chat.function("resume_playback",
                   description="Resume playback on the user's active Spotify device.",
                   action_type="read")
    async def wrapped_resume_playback(ctx, params: ResumePlaybackParams) -> ActionResult:
        return await fn_resume_playback(ctx, params)

    @chat.function("next_track",
                   description="Skip to the next track on the user's active Spotify device.",
                   action_type="read")
    async def wrapped_next_track(ctx, params: NextTrackParams) -> ActionResult:
        return await fn_next_track(ctx, params)

    @chat.function("previous_track",
                   description="Skip to the previous track on the user's active Spotify device.",
                   action_type="read")
    async def wrapped_prev_track(ctx, params: PrevTrackParams) -> ActionResult:
        return await fn_prev_track(ctx, params)

    @chat.function("panel_search_tracks",
                   description="Search Spotify tracks and show results in the sidebar panel.",
                   action_type="read")
    async def wrapped_panel_search(ctx, params: PanelSearchParams) -> ActionResult:
        """Search tracks and push results into the left panel below the search bar."""
        return await fn_panel_search(ctx, params)

    @chat.function("open_playlist",
                   description="Open a playlist's tracks in the right detail panel.",
                   action_type="read")
    async def wrapped_open_playlist(ctx, params: OpenPlaylistParams) -> ActionResult:
        """Load playlist tracks into the right detail panel."""
        return await fn_open_playlist(ctx, params)

    @chat.function("open_liked_tracks",
                   description="Open liked/saved tracks in the right detail panel.",
                   action_type="read")
    async def wrapped_open_liked_tracks(ctx, params: OpenLikedTracksParams) -> ActionResult:
        """Load liked tracks into the right detail panel."""
        return await fn_open_liked_tracks(ctx, params)

    @chat.function("open_recent_tracks",
                   description="Open recently played tracks in the right detail panel.",
                   action_type="read")
    async def wrapped_open_recent_tracks(ctx, params: OpenRecentTracksParams) -> ActionResult:
        """Load recently played tracks into the right detail panel."""
        return await fn_open_recent_tracks(ctx, params)

    @chat.function("open_profile",
                   description="Open the user's Spotify profile in the right detail panel.",
                   action_type="read")
    async def wrapped_open_profile(ctx, params: OpenProfileParams) -> ActionResult:
        """Load user profile into the right detail panel."""
        return await fn_open_profile(ctx, params)
