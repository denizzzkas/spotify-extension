# Changelog

## [2.1.0] - 2026-05-18

### SDK Migration: 4.1.2 → 5.0.1

- **Typed return contracts** — added `data_model=` to all 28 `@chat.function` handlers (SDK 5.0.1 V23); created `return_models.py` with 14 Pydantic response models
- **Orchestrator removed** — migrated from `owner_chat_tool` shim pattern to direct `ChatExtension` registration (SDK 5.0.0 V25 compliance)
- **`ChatExtension` constructor** — aligned with SDK 5.0.0; `tool_name` positional form noted (kwarg deprecated, removal in 5.1.0)

### Platform Compliance Fixes

- **`app_id` renamed** `"spotify-extension"` → `"spotify"` — enforces federal event prefix rule; all emitted events now correctly namespaced as `spotify.*`
- **`capabilities` filled** — `["music:read", "music:write", "playback:control", "auth:oauth"]` declared in `Extension()` constructor (was empty `[]`)
- **`event=` format corrected** — all `@chat.function` decorators now pass event suffix only (e.g. `"track.liked"`); platform prepends `app_id` automatically. Previously used full names (`"spotify.track.liked"`) causing double-prefix on emit
- **`scopes=` removed** from all `@chat.function` decorators — parameter not supported by SDK 5.0.1; was causing `TypeError` on platform load and blocking deployment
- **Webhook paths** — added leading slash to `/callback` and `/player-ready` (SDK 5.0.1 M4 validator pattern `^/[a-z0-9_/-]+$`)

### Web Playback SDK Integration

- **`handlers/player_webhook.py`** — new `POST /player-ready` webhook receives `device_id` from in-browser Spotify player and stores it per user via `StoreClient`
- **`player_html.py`** — Spotify Web Playback SDK browser component; registers "Imperal Spotify" virtual device, reports `device_id` to extension
- **`play_track`** — prefers "Imperal Spotify" device for full playback via Spotify Connect; falls back to preview URL when no device active

### Bug Fixes

- **Health check** — reads `spotify_client_id` via `ctx.secrets.get()` instead of `ctx.config` (was always returning degraded)
- **OAuth callback** — `StoreClient` scoped to real `user_id` for token storage; webhook context runs as `__webhook__`, not `__system__`
- **`player_webhook`** — fixed `StoreClient` constructor args; properly queries and upserts device record
- **Event declarations** — `@ext.emits` stacked on single `_declare_events()` function; all 19 event types declared with correct full names
- **`panels_left.py`** — `on_event:` refresh string updated to match corrected event namespace (`spotify.*`)

### Breaking Changes

For external extensions subscribing to Spotify events:
- Old: `"spotify-extension.connected"` → New: `"spotify.connected"`
- Old: `"spotify-extension.track.played"` → New: `"spotify.track.played"`
- Pattern: all events now use `spotify.` prefix instead of `spotify-extension.`

---

## [2.0.0] - 2026-05-06

### Major Refactoring

#### Architecture & Pattern Compliance
- **SDK 4.1.2 Handler Pattern**: Complete refactor to align with Imperal SDK 4.1.2 specifications
  - All handlers now use `@chat.function` decorator with Pydantic `ActionResult` returns
  - Proper error handling via `ActionResult(status="error", error="message", retryable=True/False)`
  - Function parameters validated with Pydantic models
  
#### Code Organization
- **Eliminated Wrapper Indirection**: Removed `handlers/chat_registry.py` (259 lines of unnecessary wrapper code)
  - Direct handler imports in `main.py` instead of registry indirection
  - Cleaner call stack and easier debugging
  
- **Separated Responsibilities**:
  - Deleted `handlers/panel.py` - UI-specific logic integrated into `panels.py`
  - `panels.py` now handles all UI rendering without handler mixing
  - `handlers/` directory contains only chat functions accessible to LLM

#### OAuth & Authentication
- **Fixed OAuth State Garbage Collection**: States no longer created on every panel render
  - OAuth flow triggered via `ui.Call("connect_spotify")` button click
  - States properly cleaned up after auth callback
  - Prevents memory leaks and race conditions
  
- **Preserved Refresh Token**: Token refresh now preserves `refresh_token` for subsequent calls
  - Fixed `_refresh_access_token()` to maintain refresh token lifecycle
  
- **Centralized Auth Helpers**: All auth logic in `app.py`
  - `_get_access_token()` - retrieves token or initiates OAuth
  - `_refresh_access_token()` - refreshes with error handling
  - `_require_auth()` - validates authenticated state before handler execution

#### Event System
- **Event Namespace Prefix**: All events now use `"spotify-extension."` namespace
  - Prevents conflicts with other extensions
  - Examples: `"spotify-extension.connected"`, `"spotify-extension.track.played"`
  - Panel refresh events properly declared in decorator

#### State Management
- **Separated Demo State Collections**:
  - `DEMO_PLAYER_STATE` - playback state (current track, shuffle, is_playing)
  - `DEMO_PANEL_STATE` - panel UI state (reserved for future)
  - Prevents state confusion between demo player and panel rendering

#### Composite Functions
- **ID Projection Support**: Functions that operate on identified resources
  - `add_track_to_playlist` with `id_projection="playlist_id"`
  - `remove_track_from_playlist` with `id_projection="playlist_id"`
  - Enables direct resource operations in chat context

#### Panel UI Improvements
- **Right Panel with Parameters**: Detail view now receives context parameters
  - `detail_type`, `playlist_id`, `playlist_name` passed from left panel clicks
  - Avoids redundant API calls and cache dependencies
  - Cleaner UI state management

- **Live API Integration**: Playlists fetched directly in panel (not cached on first render)
  - First load triggers API fetch from Spotify
  - Results cached for performance
  - Proper error handling on auth failures

#### Configuration & Secrets
- **Environment Variables**: All secrets now from environment
  - `SPOTIFY_CLIENT_ID` and `SPOTIFY_CLIENT_SECRET` from `os.environ`
  - `GENIUS_ACCESS_TOKEN` from `os.environ`
  - Removed hardcoded tokens from code

#### Testing Infrastructure
- **Fixed Test Fixtures**: `MockCache` properly simulates `ctx.cache` behavior
  - Fixed imports: `_save_token` moved from `handlers.auth` to `app.py`
  - Tests use correct function signatures with `user_id` parameter
  
- **Comprehensive Test Coverage**:
  - Search with token refresh on 401
  - Playlist CRUD operations
  - Track library operations (like/unlike)
  - Recent tracks (premium account validation)
  - Profile retrieval
  - All tests mock HTTP and validate ActionResult responses

### Bug Fixes (17 Total)

1. **OAuth State Cleanup**: Fixed memory leak from states created on every render
2. **Token Refresh**: Preserved `refresh_token` across refresh cycles
3. **Event Namespacing**: Added `"spotify-extension."` prefix to all events
4. **Auth Flow**: Moved OAuth initiation from panel render to button click
5. **Uninstall Cleanup**: Properly clear all collections on extension uninstall
6. **Panel State Separation**: Separate demo player state from panel state
7. **Import Organization**: Removed circular dependencies via registry indirection
8. **Composite Functions**: Added `id_projection` to playlist track operations
9. **Skeleton API**: Properly implemented with TTL and caching
10. **Panel Parameters**: Right panel receives context from left panel clicks
11. **Error Messages**: Enhanced function descriptions with auth requirements
12. **Handler Decorators**: Migrated from `@chat.webhook` to `@ext.webhook`
13. **User ID Validation**: Added proper user ID requirement checks
14. **Cache Models**: Fixed Pydantic v2 compatibility in all models
15. **Test Mocks**: Fixed HTTP mock setup for all test cases
16. **Configuration Loading**: Moved to environment variables for security
17. **Demo Implementation**: Properly integrated demo mode without state conflicts

### Files Changed

#### Modified
- `app.py` - Centralized auth, events, helpers; environment variable loading
- `imperal.json` - Version bumped to 2.0.0
- `main.py` - Direct handler imports; removed registry indirection
- `panels.py` - Complete refactor with live API, parameter-based detail view
- `skeleton.py` - Fixed imports, proper TTL implementation
- `handlers/auth.py` - @chat.function decorators, ActionResult returns
- `handlers/search.py` - @chat.function with live API and token refresh
- `handlers/playlists.py` - @chat.function with id_projection support
- `handlers/library.py` - @chat.function for all library operations
- `handlers/playback.py` - @chat.function with namespace-prefixed events
- `handlers/demo.py` - Complete rewrite with @chat.function on all operations
- `handlers/lyrics.py` - Environment variable for Genius token
- `tests/fixtures.py` - Fixed imports and MockCache implementation
- `tests/test_functions.py` - Updated import paths

#### Deleted
- `handlers/chat_registry.py` - Unnecessary wrapper indirection (259 lines)
- `handlers/panel.py` - Functionality merged into panels.py

### Breaking Changes

None for end users. Internal refactoring only affects:
- Handler import paths (now direct imports in `main.py`)
- Event names (now require `"spotify-extension."` namespace prefix in observers)

### Dependencies

- Imperal SDK v4.1.2 or later (required for decorator and pattern support)
- Python 3.11+ (SDK requirement)
- Pydantic 2.0+ (for ActionResult and parameter models)

### Migration Guide

For external extensions observing Spotify events:
- Old: `"spotify.connected"` → New: `"spotify-extension.connected"`
- Old: `"spotify.track.played"` → New: `"spotify-extension.track.played"`

All event names now use the full app_id namespace prefix.

### Performance

- Reduced memory footprint: OAuth state cleanup prevents accumulation
- Faster imports: Direct handler imports eliminate registry lookups
- Smarter caching: Panel caching strategy improved for large playlists
- Extended auth: Proper refresh token management extends session lifespan

---

## [1.0.0] - 2026-04-18

### Added
- Initial release
- Spotify playback control (play, pause, skip, volume)
- Search tracks, albums, artists
- Library management (saved tracks, playlists)
- OAuth 2.0 authentication flow
- Sidebar panel with now playing and controls
- Skeleton refresh for current track state
