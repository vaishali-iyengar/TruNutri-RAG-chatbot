from pathlib import Path

import pytest

from guidance_rag.config import ConfigError, load_settings


def test_loads_from_env_file(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("GROQ_API_KEY=sk-test\nTAU_ANSWER=0.55\n")

    settings = load_settings(env_file)

    assert settings.groq_api_key.get_secret_value() == "sk-test"
    assert settings.tau_answer == 0.55
    assert settings.generator_model == "openai/gpt-oss-120b"
    assert settings.evidence_check_model == "openai/gpt-oss-20b"


def test_environment_overrides_env_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("GROQ_API_KEY=from-file\n")
    monkeypatch.setenv("GROQ_API_KEY", "from-env")

    assert load_settings(env_file).groq_api_key.get_secret_value() == "from-env"


def test_missing_api_key_raises_clear_error(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match=r"GROQ_API_KEY.*\.env\.example"):
        load_settings(tmp_path / "does-not-exist.env")


def test_invalid_threshold_raises_config_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GROQ_API_KEY", "sk-test")
    monkeypatch.setenv("TAU_ANSWER", "1.5")

    with pytest.raises(ConfigError, match="Invalid settings"):
        load_settings(None)


def test_api_key_is_not_shown_in_repr(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GROQ_API_KEY", "sk-secret-value")

    assert "sk-secret-value" not in repr(load_settings(None))


def test_blank_api_key_raises_clear_error(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("GROQ_API_KEY=\n")

    with pytest.raises(ConfigError, match="GROQ_API_KEY is empty"):
        load_settings(env_file)
