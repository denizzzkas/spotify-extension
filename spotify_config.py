"""Spotify API constants and Imperal store collection names."""

# Spotify API
SP_API_BASE = "https://api.spotify.com/v1"
SP_AUTH_URL = "https://accounts.spotify.com/authorize"
SP_TOKEN_URL = "https://accounts.spotify.com/api/token"
SP_REDIRECT_URI = "https://imperal.cloud/oauth/callback"

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
])

# Store collections
CRED_COLLECTION = "sp_credentials"
OAUTH_STATE_COLLECTION = "sp_oauth_states"

# Pagination defaults
DEFAULT_SEARCH_LIMIT = 20
DEFAULT_HISTORY_LIMIT = 50
DEFAULT_LIKES_LIMIT = 50
MAX_LIMIT = 50  # Spotify max per request
