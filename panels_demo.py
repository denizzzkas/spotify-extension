"""Demo/unauthenticated state renderer for the Spotify left panel."""
import logging

from imperal_sdk import ui

from app import NowPlayingModel, DemoStateModel
from app_helpers import prepare_oauth_url
from demo_data import DEMO_TRACKS, DEMO_PLAYLIST_ID, DEMO_PLAYLIST_NAME

log = logging.getLogger("spotify.panels.demo")


async def render_demo_state(ctx) -> ui.Stack:
    auth_url = await prepare_oauth_url(ctx)
    connect_button = ui.Button(
        "Connect Spotify", variant="primary", icon="Music",
        on_click=ui.Open(auth_url) if auth_url else ui.Call("connect_spotify"),
    )

    children = [
        ui.Header("Spotify", level=3),
        ui.Alert("Connect your Spotify account to get started.", type="info"),
        connect_button,
        ui.Alert("Spotify is available in developer mode only. It will be available for all users soon.", type="info"),
    ]

    children.append(
        ui.Accordion(sections=[{
            "id": "demo_playlists",
            "title": "My Playlists",
            "children": [ui.List(items=[
                ui.ListItem(
                    id=DEMO_PLAYLIST_ID,
                    title=DEMO_PLAYLIST_NAME,
                    subtitle=f"{len(DEMO_TRACKS)} tracks",
                    avatar=ui.Avatar(src=DEMO_TRACKS[0]["album_art"], fallback="D"),
                    on_click=ui.Call("__panel__spotify_detail", detail_type="tracks",
                                     playlist_id=DEMO_PLAYLIST_ID, playlist_name=DEMO_PLAYLIST_NAME),
                ),
            ])],
        }])
    )

    demo_now_playing = None
    demo_shuffle = False

    try:
        demo_now_playing = await ctx.cache.get(key="now_playing", model=NowPlayingModel)
    except Exception:
        pass

    if demo_now_playing:
        try:
            demo_state_cached = await ctx.cache.get(key="demo_state", model=DemoStateModel)
            if demo_state_cached:
                demo_shuffle = demo_state_cached.shuffle
        except Exception:
            pass

    now_playing = demo_now_playing.model_dump() if demo_now_playing else None

    if now_playing:
        is_playing = now_playing.get("is_playing", True)
        preview_url = now_playing.get("preview_url", "")
        children += [
            ui.Divider(),
            ui.Image(src=now_playing.get("album_art", ""), width="100%", object_fit="cover"),
            ui.Text(now_playing.get("title", ""), variant="heading"),
            ui.Text(now_playing.get("artist", ""), variant="caption"),
            ui.Stack([
                ui.Button("", icon="SkipBack", variant="ghost", size="sm",
                          on_click=ui.Call("demo_prev_track")),
                ui.Button("", icon="Pause" if is_playing else "Play", variant="ghost", size="sm",
                          on_click=ui.Call("demo_pause")),
                ui.Button("", icon="SkipForward", variant="ghost", size="sm",
                          on_click=ui.Call("demo_next_track")),
                ui.Button("", icon="Shuffle", size="sm",
                          variant="secondary" if demo_shuffle else "ghost",
                          on_click=ui.Call("demo_shuffle")),
            ], direction="h", gap=1, wrap=False),
        ]
        if preview_url:
            children.append(ui.Audio(src=preview_url, title="30s preview"))

    return ui.Stack(children, direction="v", gap=2)
