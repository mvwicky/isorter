import logging
import os
import re
import subprocess
import sys
from itertools import tee
from pathlib import Path
from typing import Literal, Optional, Union

import sublime

from .consts import NAME

# print(datetime.now())
WHITE_RE = re.compile(br"\s")
SETTINGS_NAME = "{0}.sublime-settings".format(NAME)

LEVEL_NAMES = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")
LOG_LEVELS = {name: getattr(logging, name) for name in LEVEL_NAMES}

logger = logging.getLogger(NAME)


def is_python(view: sublime.View) -> bool:
    return view.match_selector(0, "source.python")


def merge(*dicts: dict) -> dict:
    dicts, dicts_copy = tee(dicts)
    it = iter(dicts_copy)
    try:
        dest = next(it)
    except StopIteration:
        return None
    res = dest.copy()
    for d in it:
        res.update(d)
    return res


def expand(value: str, view: Union[sublime.View, sublime.Window, None]) -> str:
    if isinstance(view, sublime.Window):
        window = view
    elif view is not None:
        window = view.window()
    else:
        window = sublime.active_window()
    if view is not None and window is not None:
        variables = window.extract_variables()
    else:
        variables = {}
    return sublime.expand_variables(value, merge(variables, os.environ))


def kill_proc(proc: subprocess.Popen) -> None:
    try:
        proc.terminate()
    except ProcessLookupError:
        return
    try:
        proc.wait(1.5)
    except subprocess.TimeoutExpired:
        proc.kill()


def exists(path: Union[Path, str, bytes], file: bool = False) -> bool:
    fn = os.path.isfile if file else os.path.isdir
    return path is not None and fn(path)


def read_file(
    file: Union[Path, str, bytes], mode: Literal["t", "b"]
) -> Union[str, bytes]:
    open_mode = f"r{mode}"
    with open(file, open_mode) as f:
        return f.read()


def read_file_cts(file: Union[Path, str, bytes]) -> bytes:
    with open(file, "rb") as f:
        return f.read()


def read_file_text(file: Union[Path, str, bytes]) -> str:
    with open(file, "rt") as f:
        return f.read()


def strip_file(file: Union[Path, str, bytes]) -> bytes:
    data = read_file_cts(file)
    data = WHITE_RE.sub(b"", data)
    return data


def configure_logger(log: logging.Logger) -> None:
    log.setLevel(logging.INFO)
    log.propagate = False
    fmt = "[{{asctime}}] [{{levelname:7}}] {0}:{{filename}} {{message}}".format(NAME)
    formatter = logging.Formatter(fmt=fmt, style="{", datefmt="%Y-%m-%d %H:%M:%S")

    if not log.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(formatter)
        log.addHandler(handler)

    if len(log.handlers) > 1:
        log.handlers = log.handlers[:1]

    log.handlers[0].setFormatter(formatter)
    log.debug("Configured %r", log)
    return log


def unconfigure_logger(log: logging.Logger) -> None:
    if log.handlers:
        handler = log.handlers[0]
        log.removeHandler(handler)


def find_package(
    root: Union[Path, str, bytes], pkg_name: str = "isort"
) -> Optional[str]:
    lib = os.path.join(root, "lib")
    if not os.path.isdir(lib):
        return None

    versions = []
    for name in os.listdir(lib):  # type: str
        if name.startswith("python3"):
            try:
                versions.append(int(name.split(".")[-1]))
            except ValueError:
                continue
    if not versions:
        return None
    ver = max(versions)
    version_path = os.path.join(lib, "python3.{0}".format(ver))
    if not os.path.isdir(version_path):
        return None
    pkg_path = os.path.join(version_path, "site-packages", pkg_name)
    if not os.path.isdir(pkg_path):
        return None
    return pkg_path


def patch_path() -> bool:
    HOME = os.environ.get("HOME", None)

    for path in sys.path:
        if "isort" in path:  # Don't patch more than once.
            logging.getLogger(NAME).debug("Already in path (%s)", path)
            return True

    roots = [os.getenv("VIRTUAL_ENV", None), os.getenv("PYENV_VIRTUAL_ENV", None)]

    pipx_home = os.environ.get("PIPX_HOME", None)
    if pipx_home is None:
        if HOME is not None:
            pipx_home = os.path.join(HOME, ".local", "pipx")
    if pipx_home is not None:
        pipx_isort = os.path.join(pipx_home, "venvs", "isort")
        if os.path.isdir(pipx_isort):
            roots.append(pipx_isort)
    for root in roots:
        if root is not None and os.path.isdir(root):
            isort_path = find_package(root)
            if isort_path is not None:
                print(isort_path)
                sys.path.insert(-1, isort_path)
                return True
    return False
