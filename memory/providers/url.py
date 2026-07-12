"""Generic web-page capture provider."""

import re

import httpx

from memory.providers.base import CaptureProvider, RawSource


class URLProvider(CaptureProvider):
    @property
    def name(self) -> str:
        return "url"

    @property
    def supported_schemes(self) -> list[str]:
        return ["http", "https"]

    def capture(self, target: str) -> RawSource:
        response = httpx.get(target, follow_redirects=True, timeout=30)
        response.raise_for_status()
        content_type = response.headers.get("content-type", "")
        text = response.text
        title = target
        if "html" in content_type:
            match = re.search(r"<title[^>]*>(.*?)</title>", text, re.I | re.S)
            if match:
                title = re.sub(r"\s+", " ", match.group(1)).strip()
            text = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", text, flags=re.I | re.S)
            text = re.sub(r"<[^>]+>", " ", text)
            text = re.sub(r"[ \t]+", " ", text)
            text = re.sub(r"\n\s*\n+", "\n\n", text).strip()
        return RawSource(
            source_type="url",
            source_uri=str(response.url),
            title=title,
            content=text,
            metadata={"content_type": content_type, "status_code": response.status_code},
        )
