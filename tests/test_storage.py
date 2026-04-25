"""Tests del backend de storage."""
import os
import pytest
from app.services.storage import LocalStorage, leer_url_como_bytes


@pytest.fixture
def tmp_storage(tmp_path):
    return LocalStorage(str(tmp_path), "/media")


async def test_local_storage_guarda_y_genera_url(tmp_storage):
    url = await tmp_storage.guardar_bytes("test/foo.txt", b"hola mundo", "text/plain")
    assert url == "/media/test/foo.txt"
    ruta = os.path.join(tmp_storage.base_path, "test/foo.txt")
    assert os.path.exists(ruta)
    with open(ruta, "rb") as f:
        assert f.read() == b"hola mundo"


async def test_local_storage_eliminar(tmp_storage):
    await tmp_storage.guardar_bytes("borrar.txt", b"x", "text/plain")
    assert await tmp_storage.eliminar("borrar.txt") is True
    assert await tmp_storage.eliminar("no-existe.txt") is False


async def test_url_publica_construye_url_correcta(tmp_storage):
    assert tmp_storage.url_publica("a/b/c.jpg") == "/media/a/b/c.jpg"
    assert tmp_storage.url_publica("/a/b.jpg") == "/media/a/b.jpg"


async def test_leer_url_como_bytes_local(tmp_path, monkeypatch):
    """Lee un archivo local vía URL relativa."""
    monkeypatch.setenv("STORAGE_LOCAL_PATH", str(tmp_path))
    from app.config import settings
    settings.storage_local_path = str(tmp_path)
    settings.storage_local_base_url = "/media"

    archivo = tmp_path / "test.txt"
    archivo.write_bytes(b"contenido test")

    datos = await leer_url_como_bytes("/media/test.txt")
    assert datos == b"contenido test"


async def test_leer_url_inexistente_devuelve_none():
    datos = await leer_url_como_bytes("/media/no-existe-jamas.xyz")
    assert datos is None
