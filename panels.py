"""Spotify extension — UI panel registration."""
from imperal_sdk import ui

from app import ext
from handlers.auth import get_access_token


@ext.panel(
    "spotify",
    slot="left",
    title="Spotify",
    icon="Music",
    default_width=280,
    min_width=200,
    max_width=400,
    refresh="on_event:spotify.connected,spotify.disconnected,track.liked,track.unliked,playlist.created,track.added_to_playlist,track.removed_from_playlist",
)
async def panel_spotify(ctx, **kwargs):
    try:
        token = await get_access_token(ctx)
    except Exception:
        token = None

    if not token:
        return ui.Stack([
            ui.Header("Spotify", level=3),
            ui.Alert("Not connected. Click below to link your Spotify account.", type="warn"),
            ui.Button("Connect Spotify", variant="primary", icon="Music",
                      on_click=ui.Send("Connect my Spotify account")),
        ], direction="v", gap=2)

    return ui.Stack([
        ui.Header("Spotify", level=3),
        ui.Alert("Connected", type="success"),
        ui.Stack([
            ui.Button("Search Tracks", variant="secondary", size="sm",
                      on_click=ui.Send("Search Spotify tracks")),
            ui.Button("My Playlists", variant="secondary", size="sm",
                      on_click=ui.Send("Show my Spotify playlists")),
            ui.Button("Saved Tracks", variant="secondary", size="sm",
                      on_click=ui.Send("Show my saved tracks on Spotify")),
            ui.Button("Recent Tracks", variant="secondary", size="sm",
                      on_click=ui.Send("Show my recently played Spotify tracks")),
            ui.Button("My Profile", variant="secondary", size="sm",
                      on_click=ui.Send("Show my Spotify profile")),
        ], direction="v", gap=1),
        ui.Divider(),
        ui.Button("Disconnect", variant="danger", size="sm", icon="LogOut",
                  on_click=ui.Send("Disconnect Spotify")),
    ], direction="v", gap=2)
