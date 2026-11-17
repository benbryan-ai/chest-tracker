"""Finds a newer release on GitHub, downloads it, checks it, and swaps it in for the running exe.

Nothing is sent but the usual web request. A download is only installed if its SHA-256 matches the
checksum GitHub lists for that release file, and the old exe is put back if the swap goes wrong.
"""

import hashlib
import os
import re
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import requests

from version import ASSET_NAME, REPO, VERSION

API = "https://api.github.com"
MAX_DOWNLOAD = 400 * 1024 * 1024  # a sanity cap: the app is a fraction of this
NOTES_LIMIT = 2000
DETACHED_PROCESS = 0x00000008
CREATE_NEW_PROCESS_GROUP = 0x00000200


class UpdateError(Exception):
    """An update problem the person can be told about in a sentence."""


@dataclass
class Release:
    tag: str
    notes: str
    url: str
    size: int
    sha256: str | None
    page: str

    @property
    def version(self) -> str:
        return self.tag.lstrip("vV")


@dataclass
class CheckResult:
    status: str  # "newer", "current" or "error"
    release: Release | None = None
    message: str = ""


def parse_version(text: str) -> tuple[tuple[int, ...], bool] | None:
    """(numbers, is_final) for "v1.2.3" or "1.2.0-beta"; a beta sorts before its final release."""
    found = re.fullmatch(r"[vV]?(\d+(?:\.\d+){0,3})(?:[-+].*)?", text.strip())
    if not found:
        return None
    numbers = tuple(int(part) for part in found.group(1).split("."))
    return numbers + (0,) * (4 - len(numbers)), "-" not in text.strip() and "+" not in text.strip()


def is_newer(remote: str, local: str = VERSION) -> bool:
    new, old = parse_version(remote), parse_version(local)
    if new is None or old is None:
        return False
    return (new[0], new[1]) > (old[0], old[1])


def plain_notes(markdown: str) -> str:
    """Release notes as plain text for a message box."""
    text = (markdown or "").replace("\r\n", "\n")
    text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)  # [words](link) -> words
    text = re.sub(r"^#{1,6}\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"^\s*[-*]\s+", "• ", text, flags=re.MULTILINE)
    text = text.replace("**", "").replace("`", "")
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text if len(text) <= NOTES_LIMIT else text[:NOTES_LIMIT].rstrip() + "…"


def _release_from(data: dict, repo: str) -> Release | None:
    asset = next((a for a in data.get("assets", []) if a.get("name") == ASSET_NAME), None)
    if not asset:
        return None
    url = str(asset.get("browser_download_url", ""))
    if not url.startswith(f"https://github.com/{repo}/releases/download/"):
        return None  # only ever download from this project's own releases
    digest = str(asset.get("digest") or "")
    sha = digest.split(":", 1)[1].lower() if digest.lower().startswith("sha256:") else None
    return Release(
        tag=str(data.get("tag_name", "")),
        notes=plain_notes(str(data.get("body") or "")),
        url=url,
        size=int(asset.get("size") or 0),
        sha256=sha,
        page=str(data.get("html_url") or f"https://github.com/{repo}/releases"),
    )


def check_latest(
    current: str = VERSION, repo: str = REPO, base_url: str = API, get: Callable = requests.get
) -> CheckResult:
    """Asks GitHub for the latest release and says whether it is newer than this build."""
    try:
        response = get(
            f"{base_url}/repos/{repo}/releases/latest",
            headers={"Accept": "application/vnd.github+json", "User-Agent": f"Chest-Tracker/{current}"},
            timeout=10,
        )
    except requests.RequestException:
        return CheckResult("error", message="Couldn't reach GitHub. Check your internet connection.")
    if response.status_code == 404:
        return CheckResult("error", message="No release found. The repository may be private or have no releases yet.")
    if response.status_code in (403, 429):
        return CheckResult("error", message="GitHub is limiting requests right now. Try again in a while.")
    if not response.ok:
        return CheckResult("error", message=f"GitHub answered with an error ({response.status_code}).")
    try:
        data = response.json()
        tag = str(data["tag_name"])
    except (ValueError, KeyError, TypeError):
        return CheckResult("error", message="GitHub's answer wasn't what was expected.")
    if not is_newer(tag, current):
        return CheckResult("current")
    release = _release_from(data, repo)
    if release is None:
        return CheckResult("error", message=f"Version {tag.lstrip('vV')} is out, but its download isn't attached to the release.")
    return CheckResult("newer", release)


def download_update(
    release: Release, destination: Path, fetch: Callable = requests.get,
    on_progress: Callable[[float], None] = lambda fraction: None,
) -> None:
    """Downloads the new exe to `destination`, and only keeps it if it checks out.

    A release without a checksum is refused: there would be no way to know the file is the real one.
    """
    if not release.sha256:
        raise UpdateError("This release has no checksum to check the download against, so it won't be installed.")
    part = destination.with_name(destination.name + ".part")
    digest = hashlib.sha256()
    total = 0
    try:
        with fetch(release.url, stream=True, timeout=30, headers={"User-Agent": f"Chest-Tracker/{VERSION}"}) as response:
            if not response.ok:
                raise UpdateError(f"The download failed ({response.status_code}).")
            with open(part, "wb") as out:
                for chunk in response.iter_content(chunk_size=256 * 1024):
                    if not chunk:
                        continue
                    total += len(chunk)
                    if total > MAX_DOWNLOAD:
                        raise UpdateError("The download was larger than expected, so it was stopped.")
                    digest.update(chunk)
                    out.write(chunk)
                    if release.size:
                        on_progress(min(1.0, total / release.size))
        if release.size and total != release.size:
            raise UpdateError("The download was cut short. Try again.")
        if digest.hexdigest() != release.sha256:
            raise UpdateError("The download didn't match its checksum, so it was thrown away.")
        os.replace(part, destination)
    except requests.RequestException as error:
        raise UpdateError("The download was interrupted. Try again.") from error
    except OSError as error:
        raise UpdateError(f"Couldn't save the download: {error.strerror or error}") from error
    finally:
        part.unlink(missing_ok=True)


def install_update(exe: Path, downloaded: Path) -> None:
    """Puts the downloaded exe in place of the running one. Windows lets a running exe be renamed."""
    backup = exe.with_name(exe.name + ".old")
    try:
        backup.unlink(missing_ok=True)
    except OSError:
        pass
    try:
        os.replace(exe, backup)
    except OSError as error:
        raise UpdateError(f"Couldn't replace the app: {error.strerror or error}") from error
    try:
        os.replace(downloaded, exe)
    except OSError as error:
        try:
            os.replace(backup, exe)  # put the working copy back
        except OSError:
            pass
        raise UpdateError(f"Couldn't install the update: {error.strerror or error}") from error


def clean_up_leftovers(exe: Path) -> None:
    """Removes what a finished update leaves next to the exe."""
    for suffix in (".old", ".new", ".part"):
        try:
            exe.with_name(exe.name + suffix).unlink(missing_ok=True)
        except OSError:
            pass


def relaunch(exe: Path, start: Callable = subprocess.Popen) -> None:
    """Starts the new copy. It waits until this one has closed (see app.py) before taking over."""
    env = dict(os.environ)
    env["CHEST_TRACKER_UPDATED"] = "1"
    env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"  # a packaged exe started from a packaged exe needs its own unpacking
    flags = DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0
    start([str(exe)], env=env, close_fds=True, creationflags=flags)


def running_exe() -> Path | None:
    """The packaged exe, or None when running from source (nothing to replace)."""
    return Path(sys.executable).resolve() if getattr(sys, "frozen", False) else None
