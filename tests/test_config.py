import json
from pathlib import Path


def test_default_config_contains_schema_and_expected_defaults(tmp_path):
    from voicetray.config import CONFIG_SCHEMA, default_config, default_config_path

    cfg = default_config()

    assert cfg["schema_version"] == 1
    assert cfg["hotkeys"]["speech"] == "f9"
    assert cfg["hotkeys"]["speech_alternative"] == "ctrl+win"
    assert cfg["hotkeys"]["save"] == "f10"
    assert cfg["hotkeys"]["cancel"] == "esc"
    assert cfg["hotkeys"]["tap_lock_ms"] == 300
    assert cfg["app"]["auto_start_listening"] is True
    assert cfg["app"]["start_with_windows"] is False
    assert cfg["app"]["onboarded"] is False
    assert cfg["recording"]["max_seconds"] == 600
    assert cfg["recording"]["warning_seconds"] == 540
    assert cfg["dictation"]["mode"] == "balanced"
    assert cfg["dictation"]["profile"] == "general"
    assert cfg["stt"]["model_size"] == "base"
    assert cfg["stt"]["compute_type"] == "int8"
    assert cfg["stt"]["local_files_only"] is True
    assert cfg["stt"]["silence_trim"] is True
    assert cfg["stt"]["silence_padding_ms"] == 120
    assert cfg["stt"]["vad_aggressiveness"] == 2
    assert cfg["stt"]["vad_energy_threshold"] == 0.003
    assert cfg["llm"]["enabled"] is False
    assert cfg["llm"]["model_path"] == "models/llm/model.gguf"
    assert set(CONFIG_SCHEMA) == set(cfg)
    assert default_config_path(tmp_path) == tmp_path / "VoiceTray" / "config.json"


def test_load_config_writes_defaults_when_no_files_exist(tmp_path):
    from voicetray.config import load_config

    config_path = tmp_path / "config.json"

    cfg = load_config(config_path=config_path, settings_path=tmp_path / "missing-settings.txt")

    assert cfg["hotkeys"]["speech"] == "f9"
    assert config_path.exists()
    assert json.loads(config_path.read_text(encoding="utf-8")) == cfg


def test_load_config_migrates_settings_txt_once_and_keeps_old_file_untouched(tmp_path):
    from voicetray.config import load_config

    config_path = tmp_path / "config.json"
    settings_path = tmp_path / "settings.txt"
    settings_text = "\n".join(
        [
            "# keep me",
            "speech_hotkey=ctrl+shift+r",
            "save_hotkey=f8",
            "start_with_windows=true",
            "auto_start_listening=false",
            "notification_duration=7",
            "dictation_mode=aggressive",
            "format_profile=email",
            "glossary_path=custom_glossary.json",
            "app_profiles_path=custom_profiles.json",
            "llm_enabled=true",
            "llm_model_path=models/custom.gguf",
            "llm_n_ctx=4096",
            "llm_max_tokens=512",
            "llm_temperature=0.1",
            "llm_top_p=0.8",
            "llm_threads=4",
            "llm_gpu_layers=1",
        ]
    )
    settings_path.write_text(settings_text, encoding="utf-8")

    cfg = load_config(config_path=config_path, settings_path=settings_path)

    assert cfg["hotkeys"] == {
        "speech": "ctrl+shift+r",
        "speech_alternative": "ctrl+win",
        "save": "f8",
        "cancel": "esc",
        "tap_lock_ms": 300,
    }
    assert cfg["app"]["start_with_windows"] is True
    assert cfg["app"]["auto_start_listening"] is False
    assert cfg["app"]["notification_duration"] == 7
    assert cfg["recording"]["max_seconds"] == 600
    assert cfg["recording"]["warning_seconds"] == 540
    assert cfg["dictation"]["mode"] == "aggressive"
    assert cfg["dictation"]["profile"] == "email"
    assert cfg["dictation"]["glossary_path"] == "custom_glossary.json"
    assert cfg["dictation"]["app_profiles_path"] == "custom_profiles.json"
    assert cfg["llm"]["enabled"] is True
    assert cfg["llm"]["model_path"] == "models/custom.gguf"
    assert cfg["llm"]["n_ctx"] == 4096
    assert cfg["llm"]["max_tokens"] == 512
    assert cfg["llm"]["temperature"] == 0.1
    assert cfg["llm"]["top_p"] == 0.8
    assert cfg["llm"]["threads"] == 4
    assert cfg["llm"]["gpu_layers"] == 1
    assert settings_path.read_text(encoding="utf-8") == settings_text
    assert json.loads(config_path.read_text(encoding="utf-8")) == cfg

    settings_path.write_text("speech_hotkey=changed-after-migration", encoding="utf-8")
    assert load_config(config_path=config_path, settings_path=settings_path) == cfg


def test_existing_config_ignores_unknown_keys_and_fills_missing_defaults(tmp_path):
    from voicetray.config import load_config

    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "hotkeys": {"speech": "f7", "unused": "drop-me"},
                "dictation": {"profile": "notes"},
                "unknown_top_level": True,
                "llm": {"enabled": "not-a-bool", "threads": None},
            }
        ),
        encoding="utf-8",
    )

    cfg = load_config(config_path=config_path, settings_path=tmp_path / "settings.txt")

    assert cfg["hotkeys"] == {
        "speech": "f7",
        "speech_alternative": "ctrl+win",
        "save": "f10",
        "cancel": "esc",
        "tap_lock_ms": 300,
    }
    assert cfg["dictation"]["mode"] == "balanced"
    assert cfg["dictation"]["profile"] == "notes"
    assert cfg["llm"]["enabled"] is False
    assert cfg["llm"]["threads"] is None
    assert "unknown_top_level" not in cfg
    assert "unused" not in cfg["hotkeys"]
    assert json.loads(config_path.read_text(encoding="utf-8")) == cfg


def test_main_initializes_logging_and_config_before_qt_shell(monkeypatch):
    import sys
    import types

    import voicetray.config as config
    import voicetray.logging_config as logging_config
    import voicetray.main as main

    calls = []
    monkeypatch.setattr(logging_config, "configure_logging", lambda: calls.append("logging"))
    monkeypatch.setattr(config, "load_config", lambda: calls.append("config"))
    class FakeQtApp:
        def run(self):
            calls.append("qt")
            return 0

    monkeypatch.setitem(
        sys.modules,
        "voicetray.app",
        types.SimpleNamespace(VoiceTrayApp=lambda: FakeQtApp()),
    )

    assert main.main() == 0

    assert calls == ["logging", "config", "qt"]
