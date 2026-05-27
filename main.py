"""Spotify v2.0.0 · Music library extension for Imperal Cloud."""
from __future__ import annotations

import sys
import os

_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _dir)

for _m in [k for k in sys.modules if k in (
    "app", "skeleton", "panels", "panels_left", "panels_right", "panels_demo", "spotify_config", "utils", "demo_data",
    "handlers", "handlers.auth", "handlers.search",
    "handlers.playlists", "handlers.library", "handlers.playback",
    "handlers.demo", "handlers.lyrics", "handlers.player_webhook", "handlers.player_controls",
    "handlers.artists", "handlers.albums",
)]:
    del sys.modules[_m]

from app import ext, chat  # noqa: F401
import handlers.auth  # noqa: F401
import handlers.search  # noqa: F401
import handlers.playlists  # noqa: F401
import handlers.library  # noqa: F401
import handlers.playback  # noqa: F401
import handlers.demo  # noqa: F401
import handlers.lyrics  # noqa: F401
import handlers.player_webhook  # noqa: F401
import handlers.player_controls  # noqa: F401
import handlers.artists  # noqa: F401
import handlers.albums  # noqa: F401
import skeleton  # noqa: F401
import panels  # noqa: F401
