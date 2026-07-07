from pathlib import Path


def test_default_models_dir_uses_exe_sibling_when_frozen(monkeypatch, tmp_path):
    import sys

    from voicetray.model_download import default_models_dir

    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(tmp_path / "VoiceTray.exe"))

    assert default_models_dir() == tmp_path / "models"


def test_download_whisper_model_uses_external_download_root_and_reports_progress(tmp_path):
    from voicetray.model_download import download_whisper_model

    calls = []
    progress = []

    def fake_factory(*args, **kwargs):
        calls.append((args, kwargs))
        return object()

    result = download_whisper_model(
        "base",
        progress_callback=progress.append,
        model_factory=fake_factory,
        models_dir=tmp_path / "models",
        config={
            "stt": {
                "device": "cpu",
                "compute_type": "int8",
            }
        },
    )

    assert result == tmp_path / "models" / "whisper"
    assert progress == [5, 100]
    assert calls == [
        (
            ("base",),
            {
                "device": "cpu",
                "compute_type": "int8",
                "local_files_only": False,
                "download_root": str(tmp_path / "models" / "whisper"),
            },
        )
    ]
