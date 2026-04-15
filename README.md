# Spotify Extension for Imperal

Full access to your Spotify music library via OAuth 2.0.

## Features

| Function | Description | Type |
|---|---|---|
| `connect_spotify` | Connect account via OAuth 2.0 | write |
| `disconnect_spotify` | Remove stored credentials | write |
| `search_tracks` | Search tracks by title or artist | read |
| `get_recent_tracks` | Recently played tracks (Premium) | read |
| `get_liked_tracks` | Saved/liked tracks | read |
| `like_track` | Save a track to library | write |
| `unlike_track` | Remove a track from library | write |
| `get_user_profile` | Profile info + plan type | read |
| `get_playlists` | List all playlists | read |
| `get_playlist_tracks` | Tracks in a playlist | read |
| `create_playlist` | Create a new playlist | write |
| `add_track_to_playlist` | Add a track to a playlist | write |
| `remove_track_from_playlist` | Remove a track from a playlist | write |
| `play_track` | Get track data + trigger event | write |

## Events (for Automations)

| Event | Trigger |
|---|---|
| `track.liked` | User saves a track |
| `track.unliked` | User removes a saved track |
| `track.played` | User plays a track |
| `playlist.created` | New playlist created |
| `track.added_to_playlist` | Track added to a playlist |
| `track.removed_from_playlist` | Track removed from a playlist |

## Setup

### 1. Register a Spotify app (free)

Go to [developer.spotify.com](https://developer.spotify.com) → **Dashboard** → **Create app**.

Any free Spotify account works — no subscription needed for registration.

Fill in:
- **App name**: anything, e.g. `Imperal Music`
- **Redirect URI**: your Imperal webhook URL (see below)

You will receive a **Client ID** and **Client Secret**.

### 2. Set the Redirect URI

In the Spotify app settings, add:
```
https://<your-imperal-instance>/webhooks/spotify-extension/oauth/callback
```

### 3. Configure credentials in Imperal

```json
{
  "spotify.client_id": "YOUR_CLIENT_ID",
  "spotify.client_secret": "YOUR_CLIENT_SECRET",
  "spotify.redirect_uri": "https://<your-imperal-instance>/webhooks/spotify-extension/oauth/callback"
}
```

### 4. Connect your account

In Imperal chat:
```
Connect my Spotify account
```

Open the returned URL → authorise → done. Token is saved automatically and refreshed every hour.

## Free vs Premium

| Feature | Free | Premium |
|---|---|---|
| Search, playlists, likes, profile | ✅ | ✅ |
| `get_recent_tracks` (play history) | ❌ | ✅ |
| 30-second preview (`preview_url`) | ✅ | ✅ |
| Full audio playback | ❌ | ✅ |

## Chat examples

```
Connect my Spotify account
Search Spotify for "Midnight City"
Show my Spotify playlists
Show my saved tracks
Create a playlist called "Chill Vibes"
Add track 4iV5W9uYEdYUVa79Axb7Rh to my "Chill Vibes" playlist
Show my Spotify profile
Play track 4iV5W9uYEdYUVa79Axb7Rh
```

## Running tests

```bash
cd examples/soundcloud-extension
pip install -r requirements.txt
pytest tests/ -v
```

## Token management

- Tokens are stored in `sp_credentials` collection in `ctx.store`
- Spotify tokens expire after **1 hour** — the extension auto-refreshes using `refresh_token`
- If refresh fails, the user is prompted to reconnect
