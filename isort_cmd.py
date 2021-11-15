import locale
import logging
import os
import subprocess
import sys
import time
from subprocess import PIPE
from typing import Any, List, Optional, Union

import sublime
import sublime_plugin

from .isort_lib import LIB_NAME, utils
from .isort_lib.settings import IsortSettings
from .isort_lib.utils import logger

_default_kw = {
    "universal_newlines": True,
    "stdin": PIPE,
    "stdout": PIPE,
    "stderr": PIPE,
}


def isort_file(
    exe: str,
    file: str,
    check: bool = False,
    verbose: bool = False,
    cwd: Optional[str] = None,
) -> subprocess.Popen:
    # (str, str, bool, bool, str) -> subprocess.Popen
    args = [exe, "--stdout"]
    if check:
        args.append("-c")
    args.extend(["--filename", file, "-"])
    if cwd is None:
        cwd = os.path.dirname(file)
    kw = _default_kw.copy()
    kw["cwd"] = cwd
    return subprocess.Popen(args, **kw)


class IsortEventListener(sublime_plugin.EventListener):
    def on_pre_save(self, view: sublime.View):
        if not utils.is_python(view):
            return
        settings = IsortSettings(view)
        settings.load()
        # print(settings._settings.to_dict())
        if not settings.on_save:
            return
        print("Python and isorting on save.")


class IsortPythonCommand(sublime_plugin.TextCommand):
    encoding: str = "utf-8"
    killed: bool = False
    proc: Optional[subprocess.Popen] = None
    isort_avaiable: bool = True
    timeout: Union[int, float] = 1
    chunk_size: int = 2 ** 13
    start_time: Optional[float] = None

    def __init__(self, *args: Any, **kwargs: Any):
        super().__init__(*args, **kwargs)
        self.pyenv_root: Optional[str] = os.environ.get("PYENV_ROOT")
        self.cache_path: str = os.path.join(sublime.cache_path(), "isorter")
        if not os.path.isdir(self.cache_path):
            os.makedirs(self.cache_path)
        self.settings = IsortSettings(self.view)
        self.encoding = locale.getpreferredencoding(False)

    def is_enabled(
        self, check: bool = False, sort_all: bool = False, kill: bool = False
    ):
        view = self.view
        return not view.is_read_only() and utils.is_python(view)

    is_visible = is_enabled

    def kill(self):
        if self.proc:
            self.killed = True
            self.proc.terminate()

    @property
    def project_path(self):
        return self.view.window().extract_variables().get("project_path")

    def active_view(self):
        return self.view.window().active_view()

    def get_active_file(self):
        file = self.view.file_name()
        if not utils.is_python(self.view):
            logger.info("Selected file is not python")
            return None
        return file

    def get_cwd(self):
        window = self.view.window()
        if window is not None:
            window_vars = window.extract_variables()
            cwd = window_vars.get("project_path")
            if cwd is None:
                cwd = window_vars.get("file_path")
            return cwd

        file_name = self.view.file_name()
        if file_name is not None:
            return os.path.dirname(file_name)
        return None

    def run(self, edit: sublime.Edit, check: bool = False, kill: bool = False):
        self.settings.load(self.view)
        logger.debug(
            "id(self) = 0x%x, id(settings) = 0x%x", id(self), id(self.settings)
        )
        if kill:
            self.kill()
            return
        working_dir = self.get_cwd()
        if self.proc is not None:
            utils.kill_proc(self.proc)
            self.proc = None
        file = self.get_active_file()
        if file is None:
            return
        self.killed = False
        logger.debug("Running isort on %s", file)
        verbose = self.settings.verbose
        exe = self.settings.path or "isort"
        self.start_time = time.perf_counter()
        self.proc = isort_file(exe, file, check, verbose, working_dir)
        self.do_isort(edit, file, check)

    def do_isort(self, edit: sublime.Edit, file: str, check: bool):
        if self.proc is None:
            return
        logger.debug('cmd: "%s"', " ".join(self.proc.args))
        timeout = self.settings.timeout
        sel = sublime.Region(0, self.view.size())
        cts = self.view.substr(sel)
        timed_out = False
        msg: str
        level: int
        try:
            stdout, stderr = self.proc.communicate(input=cts, timeout=timeout)
        except subprocess.TimeoutExpired:
            msg, level = "Cancelled", logging.INFO
            stdout, stderr = None, None
            timed_out = True
            utils.kill_proc(self.proc)
        else:
            msg, level = "Finished", logging.DEBUG
        elapsed = time.perf_counter() - self.start_time
        logger.debug("Sorted %s in %.2f seconds", file, elapsed)
        logger.log(level, "[%s]", msg)
        returncode = getattr(self.proc, "returncode", 1)
        if not returncode and not timed_out:
            self.set_status("isort(sorted)")
        elif timed_out:
            self.set_status("isort(timeout)")
        elif stderr is not None:
            print(stderr.strip())
            logger.warning("isort exited with code {0}".format(returncode))
            self.set_status("isort(err, {0})".format(returncode))
        if stdout is not None and stdout != cts and not check:
            logger.debug("Replacing contents")
            self.view.replace(edit, sel, stdout)
        self.proc = None

    def queue_write(self, text: str, level: int = logging.INFO):
        logger.log(level, text)

    def set_status(self, status: str, timeout: float = 1000):
        self.view.set_status("isort", status)
        sublime.set_timeout_async(self.clear_status, timeout)

    def clear_status(self):
        self.view.erase_status("isort")


def plugin_loaded():
    utils.configure_logger(logger)
    logger.info("Loaded isort plugin (%s).", __name__)


def plugin_unloaded():
    to_pop: List[str] = []
    for mod_name in sys.modules:
        if LIB_NAME in mod_name:
            to_pop.append(mod_name)
    for mod_name in to_pop:
        sys.modules.pop(mod_name)
