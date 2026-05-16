"""Spotify API constants, OAuth config, and Imperal store collection names."""

# Spotify API endpoints
SP_API_BASE = "https://api.spotify.com/v1"
SP_AUTH_URL = "https://accounts.spotify.com/authorize"
SP_TOKEN_URL = "https://accounts.spotify.com/api/token"
# OAuth scopes
SP_SCOPES = " ".join([
    "user-read-private",
    "user-read-email",
    "user-library-read",
    "user-library-modify",
    "user-read-recently-played",
    "playlist-read-private",
    "playlist-read-collaborative",
    "playlist-modify-public",
    "playlist-modify-private",
    "streaming",
    "user-read-playback-state",
    "user-modify-playback-state",
])

# Store collections
CRED_COLLECTION = "sp_credentials"
OAUTH_STATE_COLLECTION = "sp_oauth_states"
DEMO_PLAYER_STATE = "sp_demo_player"
SP_PLAYER_DEVICES = "sp_player_devices"
DEMO_PANEL_STATE = "sp_demo_panel"

# Pagination defaults
DEFAULT_SEARCH_LIMIT = 20
DEFAULT_HISTORY_LIMIT = 50
DEFAULT_LIKES_LIMIT = 50
MAX_LIMIT = 50
