import re
from typing import Optional, Tuple

import sublime

from .settings import IsortSettings

ENCODING_PATTERN = re.compile(r"^[ \t\v]*#.*?coding[:=][ \t]*([-_.a-zA-Z0-9]+)")


def get_encoding_from_region(
    region: sublime.Region, view: sublime.View
) -> Optional[str]:
    line = view.substr(region)
    enc = ENCODING_PATTERN.findall(line)
    return enc[0] if enc else None


def get_encoding_from_file(view: sublime.View) -> Optional[str]:
    region = view.line(sublime.Region(0))
    encoding = get_encoding_from_region(region, view)
    if encoding:
        return encoding
    else:
        line = view.line(region.end() + 1)
        return get_encoding_from_region(line, view)
    return None


class Sorter(object):
    def __init__(self, view: sublime.View):
        self.view: sublime.View = view
        self.extent: sublime.Region = sublime.Region(0, self.view.size())
        self.settings = IsortSettings(self.view)

    def get_content(self) -> Tuple[bytes, str]:
        encoding = self.view.encoding()
        if encoding == "Undefined":
            encoding = get_encoding_from_file(self.view)
        else:
            encoding = self.settings.encoding

        content = self.view.substr(self.extent).encode(encoding)
        return content, encoding

    def run(self, edit: sublime.Edit):
        # content, encoding= self.get_content()
        pass
