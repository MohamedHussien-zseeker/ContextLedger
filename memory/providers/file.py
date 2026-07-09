from pathlib import Path

from memory.providers.base import CaptureProvider, RawSource


class FileProvider(CaptureProvider):
    @property
    def name(self) -> str:
        return "file"

    @property
    def supported_schemes(self) -> list[str]:
        return ["file"]

    def capture(self, target: str) -> RawSource:
        path = Path(target)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {target}")
        content = path.read_text(encoding="utf-8", errors="replace")
        title = path.stem.replace("-", " ").replace("_", " ").title()
        return RawSource(
            source_type="file",
            source_uri=str(path.resolve()),
            title=title,
            content=content,
            metadata={"filename": path.name, "size": path.stat().st_size},
        )
