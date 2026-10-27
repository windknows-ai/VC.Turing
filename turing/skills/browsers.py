"""Chrome and Edge profiles: open the browser straight into the account the user names
("用 student 那个账号打开 Chrome"), instead of at the "Who's using Chrome?" picker.

The profiles are read from the browser's own `Local State` file on this PC.
"""

import json
import os
import re
import subprocess
import winreg
from dataclasses import dataclass, field

# kind -> (user data folder under %LOCALAPPDATA%, exe name in App Paths)
BROWSERS = {
    "chrome": (r"Google\Chrome\User Data", "chrome.exe"),
    "edge": (r"Microsoft\Edge\User Data", "msedge.exe"),
}
NAMES = {"chrome": "Chrome", "edge": "Edge"}

# Words people use for an account, and what they'd be called in the profile.
_SYNONYMS = {"学生": "student", "学校": "student", "school": "student", "工作": "work",
             "公司": "work", "个人": "personal", "私人": "personal", "自己": "personal"}


@dataclass
class Profile:
    directory: str        # e.g. "Profile 2"
    label: str            # what to call it out loud, e.g. "Person 1（Alex Chen [Student]）"
    names: list[str] = field(default_factory=list)  # everything it could be called, lowercase


def kind_of(app_name: str) -> str | None:
    name = app_name.lower()
    if "chrome" in name or "谷歌" in name:
        return "chrome"
    if "edge" in name:
        return "edge"
    return None


def profiles(kind: str, local_appdata: str | None = None) -> list[Profile]:
    folder = os.path.join(local_appdata or os.environ.get("LOCALAPPDATA", ""), BROWSERS[kind][0])
    try:
        with open(os.path.join(folder, "Local State"), encoding="utf-8") as f:
            cache = json.load(f)["profile"]["info_cache"]
    except (OSError, ValueError, KeyError):
        return []
    found = []
    for directory, info in cache.items():
        name = (info.get("name") or directory).strip()
        account = (info.get("gaia_name") or "").strip()
        email = (info.get("user_name") or "").strip()
        names = [name, account, info.get("shortcut_name") or "", email, email.split("@")[0],
                 info.get("hosted_domain") or ""]
        label = f"{name}（{account}）" if account and account != name else name
        found.append(Profile(directory, label,
                             [n.lower() for n in names if n and n != "NO_HOSTED_DOMAIN"]))
    return found


def last_used(kind: str, local_appdata: str | None = None) -> Profile | None:
    """The profile the browser would pick itself, if it has more than one (else None)."""
    folder = os.path.join(local_appdata or os.environ.get("LOCALAPPDATA", ""), BROWSERS[kind][0])
    try:
        with open(os.path.join(folder, "Local State"), encoding="utf-8") as f:
            directory = json.load(f)["profile"].get("last_used") or "Default"
    except (OSError, ValueError, KeyError):
        return None
    choices = profiles(kind, local_appdata)
    if len(choices) < 2:
        return None  # one profile: there is no picker to skip
    return next((p for p in choices if p.directory == directory), None)


def find(query: str, choices: list[Profile]) -> Profile | None:
    """The one profile the user means, or None if none (or several) fit. The words as
    said are tried first, then with 学生 -> student and the like."""
    said = re.sub(r"\s+", " ", query.lower().strip())
    translated = said
    for word, meaning in _SYNONYMS.items():
        translated = translated.replace(word, meaning)
    for q in dict.fromkeys([said, translated]):
        if not q:
            continue
        exact = [p for p in choices if q in p.names]
        if len(exact) == 1:
            return exact[0]
        partial = [p for p in choices if any(q in n for n in p.names)]
        if len(partial) == 1:
            return partial[0]
    return None


def exe(kind: str) -> str | None:
    key = rf"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\{BROWSERS[kind][1]}"
    for root in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        try:
            with winreg.OpenKey(root, key) as k:
                path = winreg.QueryValueEx(k, "")[0]
                if os.path.exists(path):
                    return path
        except OSError:
            continue
    return None


def launch(kind: str, profile: Profile) -> bool:
    path = exe(kind)
    if not path:
        return False
    # Opens a window in that profile, whether or not the browser is already running.
    subprocess.Popen([path, f"--profile-directory={profile.directory}"])
    return True


# "打开谷歌浏览器，使用student那个账号" / "打开 Chrome 用学生账号"
_AFTER_ZH = re.compile(r"[，,、\s]*(?:并且|然后|再)?\s*(?:用|使用|以|切换到|切到|登录|登陆)\s*(?:我的)?\s*"
                       r"(.+?)\s*(?:那个|这个|的)?\s*(?:账号|帐号|账户|帐户|个人资料|用户|profile)\s*$",
                       re.I)
# "open chrome with my student account" / "open chrome as student"
_AFTER_EN = re.compile(r"\s+(?:with|using|as|in|on)\s+(?:my\s+|the\s+)?(.+?)"
                       r"(?:\s+(?:profile|account|user))?\s*$", re.I)
# "用student账号打开chrome"
_BEFORE = re.compile(r"^(?:用|使用|以)\s*(?:我的)?\s*(.+?)\s*(?:那个|这个|的)?\s*"
                     r"(?:账号|帐号|账户|帐户|个人资料|profile)\s*(?:来|去)?\s*"
                     r"(打开|启动|开)\s*(.+)$", re.I)


def split_profile(app_part: str) -> tuple[str, str]:
    """'谷歌浏览器，使用student那个账号' -> ('谷歌浏览器', 'student'); no account -> (app_part, '')."""
    app_part = app_part.rstrip("。.!！?？ ")
    for pattern in (_AFTER_ZH, _AFTER_EN):
        m = pattern.search(app_part)
        if m and m.start() > 0:
            return app_part[:m.start()].strip(" ，,、"), m.group(1).strip()
    return app_part, ""


def split_leading(text: str) -> tuple[str, str] | None:
    """'用student账号打开chrome' -> ('打开chrome', 'student')."""
    m = _BEFORE.match(text.strip().rstrip("。.!！?？ "))
    return (m.group(2) + m.group(3), m.group(1).strip()) if m else None
