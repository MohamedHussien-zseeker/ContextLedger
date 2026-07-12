from abc import ABC, abstractmethod
from datetime import datetime, timezone
from pydantic import BaseModel, Field


class RawSource(BaseModel):
    source_type: str
    source_uri: str
    title: str
    content: str
    captured_at: str = ""
    metadata: dict = Field(default_factory=dict)
    content_hash: str = ""
    confidentiality: str = "confidential"

    def model_post_init(self, __context):
        if not self.captured_at:
            self.captured_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        if not self.content_hash:
            import hashlib
            self.content_hash = hashlib.sha256(self.content.encode()).hexdigest()


class CaptureProvider(ABC):
    @property
    @abstractmethod
    def name(self) -> str: ...

    @abstractmethod
    def capture(self, target: str) -> RawSource: ...

    @property
    @abstractmethod
    def supported_schemes(self) -> list[str]: ...
