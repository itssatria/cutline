"""Build info, "check for updates" and "pull latest".

For git installs the check uses `git fetch` (no GitHub API, so no API rate limit). For zip installs it reads
cutline/__init__.py from raw.githubusercontent.com. Only GitHub is contacted, only when you click the button
or once (cached for a few hours) at startup. Set CUTLINE_NO_UPDATE_CHECK=1 to disable the startup check.
"""
import functools
import json
import os
import re
import shutil
import subprocess
import time
from pathlib import Path

import requests

from . import __build__, __version__, config

ROOT = Path(__file__).resolve().parent.parent
CACHE_FILE = Path.home() / ".cutline" / "update_check.json"
CACHE_SECONDS = 6 * 3600


def _git(*args, timeout=30):
    git = shutil.which("git")
    if not git:
        raise RuntimeError("git is not installed")
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}          # never wait for a password prompt
    r = subprocess.run([git, *args], cwd=ROOT, capture_output=True, text=True, timeout=timeout, env=env)
    return r.returncode, (r.stdout + r.stderr).strip()


def is_git_checkout():
    return (ROOT / ".git").exists() and shutil.which("git") is not None


@functools.lru_cache(maxsize=1)
def local_info():
    """Version, build number and (for git checkouts) commit / branch."""
    info = {"version": __version__, "build": __build__, "sha": None, "branch": None, "git": False}
    if is_git_checkout():
        try:
            rc, sha = _git("rev-parse", "HEAD")
            if rc == 0:
                info.update(sha=sha, git=True)
                rc, br = _git("rev-parse", "--abbrev-ref", "HEAD")
                if rc == 0 and br != "HEAD":
                    info["branch"] = br
                rc, n = _git("rev-list", "--count", "HEAD")
                if rc == 0 and n.isdigit():
                    info["build"] = int(n)      # commit count is the build number for git checkouts
        except Exception:
            pass
    return info


def build_label():
    i = local_info()
    label = f"Cutline v{i['version']} · build {i['build']}"
    return label + (f" · {i['sha'][:7]}" if i["sha"] else "")


def _vtuple(v):
    return tuple(int(x) for x in re.findall(r"\d+", v or "0"))[:4]


def _parse_init(text):
    v = re.search(r'__version__\s*=\s*"([^"]+)"', text or "")
    b = re.search(r"__build__\s*=\s*(\d+)", text or "")
    return (v.group(1) if v else None), (int(b.group(1)) if b else None)


def _result(state, title, detail="", can_pull=False, remote_version=None):
    return {"state": state, "title": title, "detail": detail, "can_pull": can_pull, "remote_version": remote_version}


def _check_git(branch):
    """None if git could not reach the remote, else a result dict."""
    rc, out = _git("fetch", "--quiet", "origin", branch, timeout=45)
    if rc != 0:
        return None, out
    rc, cnt = _git("rev-list", "--left-right", "--count", "HEAD...FETCH_HEAD")
    if rc != 0 or len(cnt.split()) != 2:
        return None, cnt
    ahead, behind = (int(x) for x in cnt.split())
    rc, txt = _git("show", "FETCH_HEAD:cutline/__init__.py")
    rv = _parse_init(txt)[0] if rc == 0 else None
    if behind > 0:
        return _result("update", "Update available",
                       f"GitHub has {behind} newer commit{'s' if behind != 1 else ''}" + (f" (v{rv})." if rv else "."),
                       True, rv), ""
    if ahead > 0:
        return _result("ahead", "Your copy is newer than GitHub",
                       "It contains commits that are not on GitHub yet.", False, rv), ""
    return _result("current", "You're up to date", f"{build_label()}.", False, rv), ""


def check_update(timeout=8):
    """Returns {state, title, detail, can_pull, remote_version}; state: update | current | ahead | error."""
    info = local_info()
    repo, branch = config.GITHUB_REPO, info["branch"] or config.DEFAULT_BRANCH
    git_err = ""
    if info["git"]:
        try:
            res, git_err = _check_git(branch)
            if res:
                return res
        except Exception as e:
            git_err = str(e)
    url = f"https://raw.githubusercontent.com/{repo}/{branch}/cutline/__init__.py"
    try:
        r = requests.get(url, timeout=timeout, headers={"User-Agent": "Cutline-update-check"})
    except requests.RequestException as e:
        return _result("error", "Could not check for updates", f"{type(e).__name__}. Are you online?")
    if r.status_code == 404:
        hint = (" Git said: " + git_err.splitlines()[-1][:160]) if git_err else ""
        return _result("error", "Repository not found",
                       f"Could not find cutline/__init__.py in {repo} ({branch}) on GitHub. The repository may not "
                       "exist yet, may be private, or GITHUB_REPO / DEFAULT_BRANCH in cutline/config.py may be wrong."
                       + hint)
    if r.status_code != 200:
        return _result("error", "Could not check for updates", f"GitHub answered with status {r.status_code}.")
    rv, rb = _parse_init(r.text)
    newer = bool(rv) and (_vtuple(rv) > _vtuple(info["version"]) or
                          (not info["git"] and _vtuple(rv) == _vtuple(info["version"]) and (rb or 0) > info["build"]))
    if newer:
        return _result("update", "Update available", f"Latest is v{rv}; you have v{info['version']}.",
                       info["git"], rv)
    return _result("current", "You're up to date", f"{build_label()}.", False, rv)


def cached_check(max_age=CACHE_SECONDS, timeout=6):
    """Startup check: reuse a recent successful answer so GitHub is not contacted on every launch."""
    stamp = build_label()
    try:
        d = json.loads(CACHE_FILE.read_text())
        if d.get("stamp") == stamp and time.time() - d.get("t", 0) < max_age:
            return d["res"]
    except Exception:
        pass
    res = check_update(timeout=timeout)
    if res["state"] != "error":
        try:
            CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
            CACHE_FILE.write_text(json.dumps({"stamp": stamp, "t": time.time(), "res": res}))
        except OSError:
            pass
    return res


def pull_latest():
    """git pull --ff-only. Returns (ok, output)."""
    if not is_git_checkout():
        return False, "This copy was not installed with git, so it cannot update itself."
    try:
        rc, out = _git("pull", "--ff-only", timeout=180)
    except Exception as e:
        return False, str(e)
    local_info.cache_clear()
    try:
        CACHE_FILE.unlink()
    except OSError:
        pass
    return rc == 0, out
