from memory.providers.base import CaptureProvider
from memory.providers.base import RawSource as RawSource
from memory.providers.file import FileProvider

_registry: dict[str, CaptureProvider] = {}


def register(provider: CaptureProvider):
    for scheme in provider.supported_schemes:
        _registry[scheme] = provider


def get(scheme: str) -> CaptureProvider | None:
    return _registry.get(scheme)


def list_providers() -> list[str]:
    return list(_registry.keys())


# Register built-in providers
register(FileProvider())
