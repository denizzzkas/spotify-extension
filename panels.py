"""Spotify extension — UI panel registration and coordination."""
import panels_left  # noqa: F401
import panels_right  # noqa: F401

# Panels are registered via @ext.panel decorators in panels_left and panels_right
# This module coordinates panel imports to ensure they're loaded with the extension
