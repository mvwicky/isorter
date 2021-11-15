import logging
from typing import Any, ClassVar, List, NamedTuple, Optional, Tuple

import sublime

from .consts import NAME, SETTINGS_NAME
from .utils import expand, logger

_UNSET = "__UNSET_SETTINGS_KEY__"


class Setting(NamedTuple):
    default: Any


class IsortSettings(object):
    settings_attrs: ClassVar[Tuple[str, ...]] = (
        "verbose",
        "timeout",
        "path",
        "log_level",
        "on_save",
        "encoding",
    )
    settings_defaults = {
        "verbose": False,
        "timeout": 1.0,
        "path": None,
        "log_level": "INFO",
        "on_save": False,
        "encoding": "utf-8",
    }
    default_settings = {
        "verbose": False,
        "timeout": 1.0,
        "path": None,
        "log_level": "INFO",
        "on_save": False,
        "encoding": "utf-8",
    }

    verbose: bool
    timeout: float
    path: Optional[str]
    log_level: str
    on_save: bool
    encoding: str

    def __init__(self, view: Optional[sublime.View] = None):
        self._settings: Optional[sublime.Settings] = None
        self.current_settings = self.default_settings.copy()
        self.view = view

    def __dir__(self) -> List[str]:
        return sorted(set(self.default_settings).union(object.__dir__(self)))

    def __getattr__(self, key: str):
        if self._settings is None and self.view is not None:
            self.load()
        try:
            return self.current_settings[key]
        except KeyError:
            return object.__getattr__(self, key)

    def global_key(self, key: str) -> str:
        return "_".join(("isort", key))

    def flat_key(self, key: str) -> str:
        return ".".join((NAME, key))

    def load(self, view: Optional[sublime.View] = None, force: bool = False) -> dict:
        if view is not None:
            self.view = view
        if force or view is not None or self._settings is None:
            self._load()
            self.update_settings()
        logger.debug("Settings %r", self.current_settings)
        return self._settings

    def _load(self) -> None:
        self._settings = sublime.load_settings(SETTINGS_NAME)
        self._settings.clear_on_change(NAME)
        self._settings.add_on_change(NAME, self.update_settings)

        for key in self.default_settings:
            self._settings.clear_on_change(self.global_key(key))

    def as_dict(self):
        return {k: getattr(self, k) for k in self.default_settings}

    def update_settings(self):
        logger.debug("Updating settings")
        settings = self._settings
        if settings is None:
            logger.debug("Loading settings (%r)", SETTINGS_NAME)
            settings = sublime.load_settings(SETTINGS_NAME)
        if self.view is not None:
            flat = self.view.settings()
            nested = flat.get(NAME, {})
        else:
            flat, nested = {}, {}

        for key in self.default_settings:
            flat_key = self.flat_key(key)
            global_key = self.global_key(key)

            value = flat.get(flat_key, _UNSET)
            if value != _UNSET:
                logger.debug("Got %r from flat settings (%s=%r)", key, flat_key, value)
                self.current_settings[key] = expand(value, self.view)
                continue
            value = nested.get(key, _UNSET)
            if value != _UNSET:
                logger.debug("Got %r from nested settings (%r)", key, value)
                self.current_settings[key] = expand(value, self.view)
                continue
            value = settings.get(global_key, _UNSET)
            if value != _UNSET:
                logger.debug(
                    "Got %r from global settings (%s=%r)", key, global_key, value
                )
                self.current_settings[key] = expand(value, self.view)
                continue
        # if self._settings is not None:
        #     for key, value in self.current_settings.items():
        #         self._settings.set(self.global_key(key), value)
        self.set_log_level()

    def set_log_level(self):
        level = self.log_level
        if level is not None:
            try:
                logger.setLevel(level)
            except ValueError as e:
                logger.error(e)
                logger.setLevel(logging.WARNING)
                logger.error("Falling back to level=WARNING")
