# Spotify Extension for Imperal

Full access to your Spotify music library through chat.

## Getting started

In Imperal chat:
```
Connect my Spotify account
```

Open the returned URL → authorise → done. Your token is saved automatically and refreshed when needed.

## What you can do

### Playback
| Function | Description |
|---|---|
| `play_track` | Play a track by name or ID |
| `play_playlist` | Play a playlist |
| `play_album` | Play an album by name |
| `sp_prev` / `sp_next` | Skip to previous / next track |
| `sp_play_pause` | Toggle play / pause |
| `sp_shuffle` | Toggle shuffle mode |
| `sp_like` | Like / unlike the currently playing track |

### Search & Browse
| Function | Description |
|---|---|
| `search_tracks` | Search tracks by title or artist |
| `get_artist_top_tracks` | Top tracks for an artist |
| `get_artist_albums` | Albums and singles by an artist |
| `get_album_tracks` | All tracks from an album |
| `get_lyrics` | Lyrics or Genius link for a track |

### Library
| Function | Description |
|---|---|
| `get_recent_tracks` | Recently played tracks (Premium) |
| `get_liked_tracks` | Your saved/liked tracks |
| `like_track` | Save a specific track by ID |
| `unlike_track` | Remove a track from library |
| `get_user_profile` | Your profile info and plan type |

### Playlists
| Function | Description |
|---|---|
| `get_playlists` | List all your playlists |
| `get_playlist_tracks` | Tracks inside a playlist |
| `create_playlist` | Create a new playlist |
| `add_track_to_playlist` | Add one track to a playlist |
| `add_tracks_to_playlist` | Add multiple tracks at once |
| `remove_track_from_playlist` | Remove a track from a playlist |
| `delete_playlist` | Delete a playlist |
| `add_artist_top_tracks_to_playlist` | Add an artist's top tracks to a playlist |
| `add_album_tracks_to_playlist` | Add an album's tracks to a playlist |

## Chat examples

```
Connect my Spotify account
Play Bohemian Rhapsody
Show top tracks by Radiohead
What albums does Arctic Monkeys have?
Show tracks from the album AM
Add top tracks by Oasis to my playlist "Britpop"
Add first 5 tracks from OK Computer to my playlist "Favourites"
Show my liked tracks
Create a playlist called "Evening Chill"
Remove the track Creep from my playlist "Favourites"
Delete my playlist "Old stuff"
What's the shuffle state?
Like this song
```

## Free vs Premium

| Feature | Free | Premium |
|---|---|---|
| Search, browse, lyrics | ✅ | ✅ |
| Playlists, library, likes | ✅ | ✅ |
| Profile | ✅ | ✅ |
| Recently played tracks | ❌ | ✅ |
| Full audio playback | ❌ | ✅ |

## Events (for Automations)

| Event | Trigger |
|---|---|
| `track.liked` | User saves a track |
| `track.unliked` | User removes a saved track |
| `track.played` | User plays a track |
| `playlist.created` | New playlist created |
| `track.added_to_playlist` | Track added to a playlist |
| `track.removed_from_playlist` | Track removed from a playlist |
| `playlist.deleted` | Playlist deleted |
