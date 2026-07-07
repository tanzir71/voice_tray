from pathlib import Path


def test_pyinstaller_build_script_uses_onedir_windowed_icon_and_version():
    script = Path("tools/build.ps1")

    assert script.exists()
    text = script.read_text(encoding="utf-8").lower()

    assert "pyinstaller" in text
    assert "--onedir" in text
    assert "--windowed" in text or "--noconsole" in text
    assert "--name" in text and "voicetray" in text
    assert "--icon" in text and "assets\\tray\\mic_idle.ico" in text
    assert "--version-file" in text
    assert "__version__" in text
    assert "voicetray\\__init__.py" in text
    assert "$lastexitcode" in text
    assert "pyinstaller failed" in text
    assert "--exclude-module" in text and "webrtcvad" in text


def test_pyinstaller_build_script_keeps_assets_and_models_external():
    text = Path("tools/build.ps1").read_text(encoding="utf-8").lower()

    assert "copy-item" in text
    assert "assets" in text
    assert "dist\\voicetray\\assets" in text
    assert "dist\\voicetray\\models" in text
    assert "new-item" in text


def test_pyinstaller_is_available_as_build_dependency():
    requirements = Path("requirements.txt").read_text(encoding="utf-8").lower()

    assert "pyinstaller" in requirements
