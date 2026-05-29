"""Spotify right panel — render helpers for track lists, fetched pages, and profile."""
import datetime
import logging

from imperal_sdk import ui

from spotify_config import SP_API_BASE
from app_helpers import _get_access_token, _refresh_access_token
from utils import format_track

log = logging.getLogger("spotify.panels.right")


async def _render_fetched_tracks(ctx, url: str, title: str, item_key: str = "track", liked_context: bool = False, page: int = 0, cursor: str = "") -> ui.Stack:
    try:
        token = await _get_access_token(ctx)
        if not token:
            return ui.Empty("Not connected to Spotify.", icon="Music")

        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        fetch_params: dict = {"limit": 50}
        if liked_context:
            fetch_params["offset"] = page * 50
        elif cursor:
            fetch_params["before"] = cursor

        resp = await ctx.http.get(url, headers=headers, params=fetch_params)

        if resp.status_code == 401:
            token = await _refresh_access_token(ctx)
            if not token:
                return ui.Empty("Session expired. Reconnect Spotify.", icon="Lock")
            headers["Authorization"] = f"Bearer {token}"
            resp = await ctx.http.get(url, headers=headers, params=fetch_params)

        if resp.status_code == 403:
            try:
                body = resp.text
            except Exception:
                body = ""
            if "not registered" in body.lower():
                return ui.Empty("Account not registered for this app. Add it in Spotify Developer Dashboard → User Management.", icon="Lock")
            return ui.Empty("This feature requires Spotify Premium.", icon="Lock")

        if not resp.ok:
            return ui.Empty(f"Could not load tracks (HTTP {resp.status_code}).", icon="AlertCircle")

        data = resp.json()
        raw_list = data.get("items") or []
        tracks = [format_track(item[item_key]) for item in raw_list if item.get(item_key)]
        has_next = bool(data.get("next"))

        next_cursor = ""
        if not liked_context and has_next and raw_list:
            played_at = raw_list[-1].get("played_at", "")
            if played_at:
                try:
                    dt = datetime.datetime.fromisoformat(played_at.replace("Z", "+00:00"))
                    next_cursor = str(int(dt.timestamp() * 1000))
                except Exception:
                    pass

    except Exception as e:
        log.error("_render_fetched_tracks failed for %s: %s", url, e)
        return ui.Empty("Failed to load tracks.", icon="AlertCircle")

    detail_type = "liked_tracks" if liked_context else "recent_tracks"
    nav_buttons = []
    if liked_context:
        if page > 0:
            nav_buttons.append(ui.Button("← Back", size="sm", on_click=ui.Call("__panel__spotify_detail", detail_type=detail_type, page=page - 1)))
        if has_next:
            nav_buttons.append(ui.Button("Next →", size="sm", on_click=ui.Call("__panel__spotify_detail", detail_type=detail_type, page=page + 1)))
    else:
        if has_next and next_cursor:
            nav_buttons.append(ui.Button("Load older →", size="sm", on_click=ui.Call("__panel__spotify_detail", detail_type=detail_type, cursor=next_cursor)))

    track_list = _render_tracks(tracks, title, play_fn="play_track", liked_context=liked_context)
    if nav_buttons:
        return ui.Stack([track_list, ui.Stack(nav_buttons, direction="h", gap=1)], direction="v", gap=2)
    return track_list


async def _render_profile(ctx) -> ui.Stack:
    try:
        token = await _get_access_token(ctx)
        if not token:
            return ui.Empty("Not connected to Spotify.", icon="User")

        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        resp = await ctx.http.get(f"{SP_API_BASE}/me", headers=headers)

        if resp.status_code == 401:
            token = await _refresh_access_token(ctx)
            if token:
                headers["Authorization"] = f"Bearer {token}"
                resp = await ctx.http.get(f"{SP_API_BASE}/me", headers=headers)

        if not resp.ok:
            return ui.Empty(f"Could not load profile (HTTP {resp.status_code}).", icon="User")

        raw = resp.json()
        items = [
            ui.ListItem(id="name", title="Name", subtitle=raw.get("display_name") or raw.get("id", "")),
            ui.ListItem(id="email", title="Email", subtitle=raw.get("email", "")),
            ui.ListItem(id="plan", title="Plan", subtitle=(raw.get("product") or "free").capitalize()),
            ui.ListItem(id="followers", title="Followers", subtitle=str((raw.get("followers") or {}).get("total", 0))),
        ]
        return ui.Stack([
            ui.Header("My Profile", level=3),
            ui.List(items=items),
            ui.Button("Disconnect Spotify", variant="danger", icon="LogOut", on_click=ui.Call("disconnect_spotify")),
        ], direction="v", gap=2)

    except Exception as e:
        log.error("_render_profile failed: %s", e)

    return ui.Empty("Profile not loaded.", icon="User")


def _render_tracks(tracks: list[dict], title: str, play_fn: str = "play_track", playlist_id: str = "", liked_context: bool = False, has_next: bool = False, page: int = 0, playlist_name: str = "") -> ui.Stack:
    all_track_ids = [t["id"] for t in tracks if t.get("id")]

    def _play_action(track_id: str) -> ui.Call:
        if play_fn == "play_track" and playlist_id:
            return ui.Call(play_fn, track_id=track_id, playlist_id=playlist_id)
        if play_fn == "play_track" and len(all_track_ids) > 1:
            if liked_context:
                return ui.Call(play_fn, track_id=track_id, track_ids_queue=all_track_ids, is_liked=True)
            return ui.Call(play_fn, track_id=track_id, track_ids_queue=all_track_ids)
        if play_fn == "play_track" and liked_context:
            return ui.Call(play_fn, track_id=track_id, is_liked=True)
        return ui.Call(play_fn, track_id=track_id)

    track_items = [
        ui.ListItem(
            id=t["id"],
            title=t["title"],
            subtitle=t["artist"],
            meta=t["duration"],
            avatar=ui.Avatar(src=t["album_art"], fallback=(t["title"] or "?")[0].upper()),
            actions=[{"icon": "Play", "on_click": _play_action(t["id"])}],
        )
        for t in tracks
    ]

    children = [
        ui.Header(title, level=3),
        ui.List(items=track_items) if track_items else ui.Empty("No tracks found."),
    ]
    if playlist_id:
        nav_buttons = []
        if page > 0:
            nav_buttons.append(ui.Button("← Back", size="sm", on_click=ui.Call("__panel__spotify_detail", detail_type="tracks", playlist_id=playlist_id, playlist_name=playlist_name, page=page - 1)))
        if has_next:
            nav_buttons.append(ui.Button("Next →", size="sm", on_click=ui.Call("__panel__spotify_detail", detail_type="tracks", playlist_id=playlist_id, playlist_name=playlist_name, page=page + 1)))
        if nav_buttons:
            children.append(ui.Stack(nav_buttons, direction="h", gap=1))
    return ui.Stack(children, direction="v", gap=2)
