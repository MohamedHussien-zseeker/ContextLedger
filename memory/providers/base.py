from abc import ABC, abstractmethod
from datetime import datetime, timezone

from pydantic import BaseModel


class RawSource(BaseModel):
    source_type: str
    source_uri: str
    title: str
    content: str
    captured_at: str = ""
    metadata: dict = {}

    def model_post_init(self, __context):
        if not self.captured_at:
            self.captured_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class CaptureProvider(ABC):
    @property
    @abstractmethod
    def name(self) -> str: ...

    @abstractmethod
    def capture(self, target: str) -> RawSource: ...

    @property
    @abstractmethod
    def supported_schemes(self) -> list[str]: ...
