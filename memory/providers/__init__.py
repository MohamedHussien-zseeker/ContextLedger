from memory.providers.base import CaptureProvider, RawSource

_registry: dict[str, CaptureProvider] = {}


def register(provider: CaptureProvider):
    for scheme in provider.supported_schemes:
        _registry[scheme] = provider


def get(scheme: str) -> CaptureProvider | None:
    return _registry.get(scheme)


def list_providers() -> list[str]:
    return list(_registry.keys())
