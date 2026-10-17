"""Environment precedence and connection caching without credentials or Atlas."""

from unittest.mock import Mock

import pytest
from app import config, db


@pytest.fixture(autouse=True)
def clear_config_cache():
    config.get_config.cache_clear()
    yield
    config.get_config.cache_clear()


def test_environment_precedence(tmp_path, monkeypatch):
    (tmp_path / "backend").mkdir()
    (tmp_path / ".env.local").write_text("TEST_ENV=legacy\nTEST_FALLBACK=legacy\n")
    (tmp_path / "backend/.env").write_text("TEST_ENV=backend\nTEST_FILE=backend\n")
    (tmp_path / "backend/.env.local").write_text("TEST_FILE=unsupported\n")
    monkeypatch.setattr(config, "ROOT", tmp_path)
    monkeypatch.setenv("TEST_ENV", "process")
    monkeypatch.delenv("TEST_FILE", raising=False)
    monkeypatch.delenv("TEST_FALLBACK", raising=False)
    result = config.get_config()
    assert result["TEST_ENV"] == "process"
    assert result["TEST_FILE"] == "backend"
    assert result["TEST_FALLBACK"] == "legacy"
    (tmp_path / "backend/.env").write_text("TEST_FILE=changed\n")
    assert config.get_config()["TEST_FILE"] == "backend"


def test_database_configuration_is_read_once(monkeypatch):
    settings = Mock(return_value={"MONGODB_URI": "mongodb://test.invalid", "MONGODB_DB": "test"})
    client = Mock()
    client.__getitem__ = Mock(return_value="database")
    constructor = Mock(return_value=client)
    monkeypatch.setattr(db, "_client", None)
    monkeypatch.setattr(db, "_database_name", None)
    monkeypatch.setattr(db, "get_config", settings)
    monkeypatch.setattr(db, "AsyncMongoClient", constructor)
    assert db.get_db() == "database"
    assert db.get_db() == "database"
    settings.assert_called_once()
    constructor.assert_called_once()
    assert all(call.args == ("test",) for call in client.__getitem__.call_args_list)
