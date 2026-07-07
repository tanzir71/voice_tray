import json
import os
import types

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def qt_modules():
    from PySide6 import QtCore, QtGui, QtWidgets

    app = QtWidgets.QApplication.instance()
    if app is None:
        app = QtWidgets.QApplication([])
    return types.SimpleNamespace(QtCore=QtCore, QtGui=QtGui, QtWidgets=QtWidgets)


def write_config(tmp_path, overrides=None):
    from voicetray.config import default_config, save_config

    cfg = default_config()
    if overrides:
        for section, values in overrides.items():
            cfg[section].update(values)
    path = tmp_path / "config.json"
    save_config(cfg, path)
    return path


def test_onboarding_wizard_has_required_steps_and_tracks_audio_level(tmp_path):
    from voicetray.ui.onboarding import OnboardingWizard

    config_path = write_config(tmp_path)
    wizard = OnboardingWizard(qt_modules=qt_modules(), config_path=config_path, hotkey_hint="F9")

    titles = [wizard.page(page_id).title() for page_id in wizard.pageIds()]

    assert titles == ["Welcome", "Microphone", "Model", "Hotkey", "Done"]
    assert wizard.hotkey_hint_label.text() == "F9"

    wizard.update_audio_level(0.42)

    assert wizard.level_bar.value() == 42
    assert "detected" in wizard.mic_status_label.text().lower()


def test_onboarding_model_download_updates_progress_and_selected_model(tmp_path):
    from voicetray.ui.onboarding import OnboardingWizard

    calls = []

    def fake_download(model_size, progress):
        calls.append(model_size)
        progress(37)

    config_path = write_config(tmp_path)
    wizard = OnboardingWizard(
        qt_modules=qt_modules(),
        config_path=config_path,
        model_download_callback=fake_download,
    )
    wizard.model_combo.setCurrentText("small")

    wizard.download_selected_model()

    assert calls == ["small"]
    assert wizard.model_progress.value() == 100
    assert "ready" in wizard.model_status_label.text().lower()


def test_onboarding_hotkey_page_marks_tutorial_text_received(tmp_path):
    from voicetray.ui.onboarding import OnboardingWizard

    config_path = write_config(tmp_path)
    wizard = OnboardingWizard(qt_modules=qt_modules(), config_path=config_path)

    wizard.hotkey_test_field.setPlainText("hello from dictation")

    assert "received" in wizard.hotkey_status_label.text().lower()


def test_onboarding_finish_sets_onboarded_and_applies_config(tmp_path):
    from voicetray.ui.onboarding import OnboardingWizard

    applied = []
    config_path = write_config(tmp_path, {"app": {"onboarded": False}})
    wizard = OnboardingWizard(
        qt_modules=qt_modules(),
        config_path=config_path,
        on_config_applied=applied.append,
    )
    wizard.model_combo.setCurrentText("small")

    assert wizard.finish_onboarding() is True

    saved = json.loads(config_path.read_text(encoding="utf-8"))
    assert saved["app"]["onboarded"] is True
    assert saved["stt"]["model_size"] == "small"
    assert applied[-1] == saved
