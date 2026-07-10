from memory.providers import get, list_providers, register
from memory.providers.base import CaptureProvider, RawSource


class DummyProvider(CaptureProvider):
    @property
    def name(self):
        return "dummy"

    @property
    def supported_schemes(self):
        return ["dummy"]

    def capture(self, target: str) -> RawSource:
        return RawSource(source_type="dummy", source_uri=target, title="Dummy", content="test")


def test_raw_source_defaults():
    rs = RawSource(source_type="file", source_uri="/tmp/test.md", title="Test", content="hello")
    assert rs.captured_at is not None
    assert rs.metadata == {}


def test_provider_interface():
    p = DummyProvider()
    assert p.name == "dummy"
    rs = p.capture("test://input")
    assert rs.source_type == "dummy"
    assert rs.title == "Dummy"


def test_provider_registry():
    p = DummyProvider()
    register(p)
    assert "dummy" in list_providers()
    assert get("dummy") is p
    assert get("nonexistent") is None
