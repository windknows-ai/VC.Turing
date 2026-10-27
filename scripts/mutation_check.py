"""Put old bugs back into the code one at a time and check that a test fails for each.

    python scripts/mutation_check.py

Every file is restored byte for byte afterwards."""
import subprocess
import sys
from pathlib import Path

MUTATIONS = [
    ("?background in the page address", "turing/control_center/__init__.py",
     'url=(WEB / "index.html").as_uri() + f"#{tab}",', 'url=(WEB / "index.html").as_uri() + "?background" + f"#{tab}",',
     "test_main_page_address_has_no_query"),
    ("win32gui.IsZoomed", "turing/skills/windows.py", "_user32.IsZoomed(", "win32gui.IsZoomed(", "test_window_actions_use_calls_that_exist"),
    ("any 是 counts as yes", "turing/app.py", "    if _YES_FULL.match(a):\n        return True",
     "    if _YES_FULL.match(a) or _YES.search(a):\n        return True", "test_only_a_clear_yes_sends"),
    ("forcing hidden windows visible", "turing/keyboard.py", "    if not win32gui.IsWindowVisible(hwnd):\n        return False",
     "    if not win32gui.IsWindowVisible(hwnd):\n        win32gui.ShowWindow(hwnd, 5)", "test_hidden_windows_are_never_shown_from_outside"),
    ("OpenBLAS per-thread buffers", "turing/__init__.py", 'os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")', "pass",
     "test_numpy_does_not_reserve_memory_per_cpu_thread"),
    ("closing waits for the page", "turing/control_center/floating.py",
     "threading.Thread(target=self._tell_page, args=(visible,), daemon=True).start()", "self._tell_page(visible)",
     "test_closing_the_main_window_never_waits_for_its_page"),
    ("这周 read as Sunday", "turing/skills/weather.py",
     '    elif _WEEK_WORDS.search(text):\n        day = WEEK\n    elif m := re.search(r"(?:周|星期|礼拜)([一二三四五六日天])(?!气)", text):',
     '    elif m := re.search(r"(?:周|星期|礼拜)([一二三四五六日天])", text):',
     "test_this_week_is_not_sunday"),
    ("QQ messages sent through WeChat", "turing/skills/messaging.py",
     'if other and "微信" not in asked', 'if False and other and "微信" not in asked',
     "test_qq_requests_never_go_out_on_wechat"),
    ("Alt tap when bringing a window forward", "turing/keyboard.py",
     "    front = _user32.GetForegroundWindow()",
     "    _user32.keybd_event(0x12, 0, 0, 0)\n    _user32.keybd_event(0x12, 0, 2, 0)\n    front = _user32.GetForegroundWindow()",
     "test_bringing_a_window_forward_does_not_tap_alt"),
    ("WeChat forced out of the tray (froze)", "turing/skills/apps.py",
     "            if not show_wechat_from_tray(hwnd):\n                raise TrayError(app.name)",
     "            win32gui.ShowWindow(hwnd, 5)",
     "test_wechat_in_the_tray_is_brought_back_by_its_own_shortcut"),
    ("Ollama started twice", "turing/control_center/ollama.py", "    if server_process_running():", "    if False:",
     "test_ollama_is_not_started_twice"),
]

ok = True
for name, path, old, new, test in MUTATIONS:
    p = Path(path)
    original = p.read_bytes().decode("utf-8")
    if old not in original and old.replace("\n", "\r\n") in original:  # a file with Windows line endings
        old, new = old.replace("\n", "\r\n"), new.replace("\n", "\r\n")
    if old not in original:
        print(f"?? {name}: pattern not found"); ok = False; continue
    p.write_bytes(original.replace(old, new, 1).encode("utf-8"))
    try:
        r = subprocess.run([sys.executable, "-m", "pytest", "-q", "-k", test], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300)
        caught = r.returncode != 0
    finally:
        p.write_bytes(original.encode("utf-8"))  # byte for byte: line endings untouched
    print(f"{'caught ' if caught else 'MISSED '} {name}  ({test})")
    ok &= caught
print("all old bugs are caught" if ok else "some old bugs would slip through")
