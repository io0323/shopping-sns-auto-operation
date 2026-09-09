from _pytest.monkeypatch import MonkeyPatch

from app.core.config import Settings


def test_cors_origins_defaults_to_localhost_3000() -> None:
    settings = Settings(_env_file=None)
    assert settings.cors_origins == ["http://localhost:3000"]


def test_cors_origins_parses_comma_separated_env_value(
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setenv("CORS_ORIGINS", "http://localhost:3000, http://localhost:3001")
    settings = Settings(_env_file=None)
    assert settings.cors_origins == ["http://localhost:3000", "http://localhost:3001"]


def test_cors_origins_ignores_empty_entries(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setenv("CORS_ORIGINS", "http://localhost:3000,,")
    settings = Settings(_env_file=None)
    assert settings.cors_origins == ["http://localhost:3000"]
