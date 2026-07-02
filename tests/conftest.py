"""Shared test infrastructure. Tests are OFFLINE (CLAUDE.md): the autouse network guard fails
any test that opens a real socket. Recorded fixtures live in tests/fixtures/."""

import socket

import pytest

from prospector.store.layout import StoreLayout
from prospector.store.registry import Registry

_real_connect = socket.socket.connect


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    def guarded(self, addr):
        if self.family == socket.AF_UNIX:
            return _real_connect(self, addr)
        raise RuntimeError(
            f"test attempted a network connection to {addr!r} — tests are offline; "
            "record a fixture instead (CLAUDE.md)")

    monkeypatch.setattr(socket.socket, "connect", guarded)
    yield


@pytest.fixture
def store_root(tmp_path):
    return tmp_path / "store"


@pytest.fixture
def layout(store_root):
    return StoreLayout(store_root)


@pytest.fixture
def registry(layout):
    r = Registry(layout.registry_path())
    yield r
    r.close()
