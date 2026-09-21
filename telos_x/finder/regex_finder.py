"""Regex Finder."""

import re

from telos_x.finder.base_finder import BaseFinder


class RegexFinder(BaseFinder):
    """Regex Based Finder."""

    def __init__(self, regex: str) -> None:
        self.regex: re.Pattern = re.compile(
            regex,
            flags=re.IGNORECASE | re.MULTILINE,
        )

    async def find(self, raw_text: str) -> bool:
        if not raw_text:
            return False

        return self.regex.search(raw_text) is not None