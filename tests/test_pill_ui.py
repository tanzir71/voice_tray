import os
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def qt_modules():
    from PySide6 import QtCore, QtGui, QtWidgets

    app = QtWidgets.QApplication.instance()
    if app is None:
        app = QtWidgets.QApplication([])
    return SimpleNamespace(QtCore=QtCore, QtGui=QtGui, QtWidgets=QtWidgets)


def test_pill_recording_state_shows_level_elapsed_and_hotkey_hint():
    from voicetray.ui.pill import PillState, VoiceTrayPill

    qt = qt_modules()
    ticks = [100.0]
    pill = VoiceTrayPill(
        qt_modules=qt,
        hotkey_hint="F9",
        clock=lambda: ticks[0],
        screen_geometry_provider=lambda: qt.QtCore.QRect(100, 200, 800, 600),
    )

    pill.show_recording()
    ticks[0] = 165.0
    pill.refresh_elapsed()
    pill.update_level(0.125)

    assert pill.state == PillState.RECORDING
    assert pill.isVisible()
    assert pill.status_label.text() == "Recording"
    assert pill.elapsed_label.text() == "1:05"
    assert pill.hotkey_label.text() == "F9"
    assert pill.level_meter.level == 1.0
    assert pill.geometry().left() == 320
    assert pill.geometry().top() == 660


def test_pill_processing_and_completion_auto_hide():
    from voicetray.ui.pill import PillState, VoiceTrayPill

    qt = qt_modules()
    scheduled = []
    pill = VoiceTrayPill(
        qt_modules=qt,
        timer_single_shot=lambda ms, callback: scheduled.append((ms, callback)),
    )

    pill.show_processing()

    assert pill.state == PillState.PROCESSING
    assert pill.isVisible()
    assert pill.status_label.text() == "Polishing..."
    assert pill.spinner_label.isVisible()

    pill.finish_success()
    assert scheduled[-1][0] == 650
    scheduled[-1][1]()
    assert not pill.isVisible()


def test_pill_error_flashes_message_and_auto_hides():
    from voicetray.ui.pill import PillState, VoiceTrayPill

    qt = qt_modules()
    scheduled = []
    pill = VoiceTrayPill(
        qt_modules=qt,
        timer_single_shot=lambda ms, callback: scheduled.append((ms, callback)),
    )

    pill.show_error("No microphone")

    assert pill.state == PillState.ERROR
    assert pill.isVisible()
    assert pill.status_label.text() == "No microphone"
    assert "background: #b91c1c" in pill.styleSheet()
    assert scheduled[-1][0] == 2200
    scheduled[-1][1]()
    assert not pill.isVisible()


def test_pill_is_frameless_topmost_tool_window():
    from voicetray.ui.pill import VoiceTrayPill

    qt = qt_modules()
    pill = VoiceTrayPill(qt_modules=qt)
    flags = pill.windowFlags()

    assert flags & qt.QtCore.Qt.FramelessWindowHint
    assert flags & qt.QtCore.Qt.WindowStaysOnTopHint
    assert flags & qt.QtCore.Qt.Tool
    assert pill.testAttribute(qt.QtCore.Qt.WA_TranslucentBackground)
