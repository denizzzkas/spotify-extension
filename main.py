"""Spotify v1.0.0 · Music library extension for Imperal Cloud."""
from __future__ import annotations

import sys
import os

_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _dir)

for _m in [k for k in sys.modules if k in (
    "app", "panels", "spotify_config", "utils",
    "handlers", "handlers.auth", "handlers.search",
    "handlers.playlists", "handlers.library", "handlers.playback",
    "handlers.chat_registry",
)]:
    del sys.modules[_m]

from app import ext, chat  # noqa: F401
import panels  # noqa: F401
