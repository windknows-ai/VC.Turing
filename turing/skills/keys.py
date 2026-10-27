"""Typing and key presses in whatever app the user is working in (AI tools only)."""

from . import Context, Skill, Tool, schema


def not_the_app_just_opened(ctx, hwnd: int) -> str | None:
    """If an app was just opened for this command, keys may only go to that app: an
    error saying so when `hwnd` is some other window (None when it's fine)."""
    import os
    import time

    import psutil
    import win32gui
    import win32process

    opened = ctx.state.get("opened")
    if not opened or time.monotonic() - opened["at"] >= 30:
        return None
    title = win32gui.GetWindowText(hwnd) or "an untitled window"
    try:
        exe = psutil.Process(win32process.GetWindowThreadProcessId(hwnd)[1]).exe()
    except psutil.Error:
        exe = ""
    same_exe = opened["exe"] and exe and os.path.normcase(exe) == os.path.normcase(opened["exe"])
    if same_exe or opened["name"].lower() in title.lower():
        return None
    return (f"Error: nothing sent. {opened['name']} was just opened but isn't in front yet; the "
            f"window in front is \"{title}\". Don't claim it worked. For searching, use search_in_app.")


class Keys(Skill):
    name = "keys"

    def handle(self, text: str, ctx: Context) -> str | None:
        return None  # only offered to the AI, which decides what to type where

    def tools(self) -> list[Tool]:
        from .. import keyboard

        def refusal(ctx) -> str | None:
            """Why the keys mustn't be sent to the window in front, or None if they may."""
            import os

            import win32gui
            import win32process

            hwnd = win32gui.GetForegroundWindow()
            if win32process.GetWindowThreadProcessId(hwnd)[1] == os.getpid():
                return ("Error: nothing sent. The window in front is Turing itself, not the app "
                        "the user means. Don't claim it worked; tell the user to click into "
                        "that app first.")
            return not_the_app_just_opened(ctx, hwnd)

        def target():
            import win32gui

            return win32gui.GetWindowText(win32gui.GetForegroundWindow()) or "an untitled window"

        def type_text(args, ctx):
            if why := refusal(ctx):
                return why
            window = target()
            keyboard.type_text(args["text"])
            return (f"typed into the window \"{window}\". UNVERIFIED: don't tell the user it "
                    f"was sent or done; say you tried, or look_at_screen to check.")

        def press_keys(args, ctx):
            if why := refusal(ctx):
                return why
            window = target()
            keyboard.press(args["keys"])
            return (f"pressed in the window \"{window}\". UNVERIFIED: don't tell the user it "
                    f"worked; say you tried, or look_at_screen to check.")

        return [
            Tool("type_text",
                 "Type text into the field that has the keyboard focus in the app the user is "
                 "using. Doesn't press Enter.",
                 schema({"text": {"type": "string"}}, ["text"]), type_text),
            Tool("press_keys",
                 "Press a key or shortcut in the app the user is using, e.g. \"enter\", "
                 "\"ctrl+s\", \"ctrl+shift+t\", \"esc\". Ask the user first (end your reply "
                 "with a question) before a key that sends, submits, deletes or pays.",
                 schema({"keys": {"type": "string"}}, ["keys"]), press_keys),
        ]
