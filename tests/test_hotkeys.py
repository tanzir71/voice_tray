class FakeClock:
    def __init__(self):
        self.value = 0.0

    def now(self):
        return self.value

    def advance(self, seconds):
        self.value += seconds


class FakeKeyboard:
    def __init__(self):
        self.registrations = []
        self.removed = []
        self.callbacks = {}

    def add_hotkey(
        self,
        hotkey,
        callback,
        args=(),
        suppress=False,
        timeout=1,
        trigger_on_release=False,
    ):
        handle = f"handle-{len(self.registrations)}"
        self.registrations.append(
            {
                "handle": handle,
                "hotkey": hotkey,
                "callback": callback,
                "args": args,
                "suppress": suppress,
                "timeout": timeout,
                "trigger_on_release": trigger_on_release,
            }
        )
        self.callbacks[(hotkey, trigger_on_release)] = callback
        return handle

    def remove_hotkey(self, handle):
        self.removed.append(handle)

    def press(self, hotkey):
        self.callbacks[(hotkey, False)]()

    def release(self, hotkey):
        self.callbacks[(hotkey, True)]()


def test_hold_hotkey_starts_on_press_and_stops_on_release_after_threshold():
    from voicetray.hotkeys import HotkeyConfig, HotkeyController

    clock = FakeClock()
    starts = []
    stops = []
    controller = HotkeyController(
        HotkeyConfig(record_hotkey="f9", alternate_record_hotkey=None, tap_lock_ms=300),
        on_record_start=lambda: starts.append("start"),
        on_record_stop=stops.append,
        clock=clock.now,
    )
    keyboard = FakeKeyboard()
    controller.start(keyboard)

    keyboard.press("f9")
    clock.advance(0.5)
    keyboard.release("f9")

    assert starts == ["start"]
    assert len(stops) == 1
    assert stops[0].duration_seconds == 0.5
    assert stops[0].locked is False
    assert controller.is_recording is False


def test_short_tap_enters_lock_mode_and_second_tap_stops_recording():
    from voicetray.hotkeys import HotkeyConfig, HotkeyController

    clock = FakeClock()
    starts = []
    stops = []
    controller = HotkeyController(
        HotkeyConfig(record_hotkey="f9", alternate_record_hotkey=None, tap_lock_ms=300),
        on_record_start=lambda: starts.append("start"),
        on_record_stop=stops.append,
        clock=clock.now,
    )
    keyboard = FakeKeyboard()
    controller.start(keyboard)

    keyboard.press("f9")
    clock.advance(0.1)
    keyboard.release("f9")

    assert starts == ["start"]
    assert stops == []
    assert controller.is_recording is True
    assert controller.is_locked is True

    keyboard.press("f9")
    clock.advance(0.1)
    keyboard.release("f9")

    assert starts == ["start"]
    assert len(stops) == 1
    assert stops[0].locked is True
    assert controller.is_recording is False
    assert controller.is_locked is False


def test_escape_stops_lock_mode_recording():
    from voicetray.hotkeys import HotkeyConfig, HotkeyController

    clock = FakeClock()
    starts = []
    stops = []
    controller = HotkeyController(
        HotkeyConfig(record_hotkey="f9", alternate_record_hotkey=None, cancel_hotkey="esc"),
        on_record_start=lambda: starts.append("start"),
        on_record_stop=stops.append,
        clock=clock.now,
    )
    keyboard = FakeKeyboard()
    controller.start(keyboard)

    keyboard.press("f9")
    clock.advance(0.1)
    keyboard.release("f9")
    clock.advance(2.0)
    keyboard.press("esc")

    assert starts == ["start"]
    assert len(stops) == 1
    assert stops[0].locked is True
    assert stops[0].duration_seconds == 2.1
    assert controller.is_recording is False


def test_controller_registers_configured_hold_hotkeys_and_unregisters_handles():
    from voicetray.hotkeys import HotkeyConfig, HotkeyController

    keyboard = FakeKeyboard()
    controller = HotkeyController(
        HotkeyConfig(
            record_hotkey="ctrl+alt+space",
            alternate_record_hotkey="ctrl+win",
            cancel_hotkey="esc",
            suppress=True,
        ),
        on_record_start=lambda: None,
        on_record_stop=lambda _session: None,
    )

    controller.start(keyboard)

    assert [
        (registration["hotkey"], registration["trigger_on_release"], registration["suppress"])
        for registration in keyboard.registrations
    ] == [
        ("ctrl+alt+space", False, True),
        ("ctrl+alt+space", True, True),
        ("ctrl+win", False, True),
        ("ctrl+win", True, True),
        ("esc", False, True),
    ]

    controller.stop()

    assert keyboard.removed == [
        "handle-0",
        "handle-1",
        "handle-2",
        "handle-3",
        "handle-4",
    ]


def test_duplicate_press_while_recording_does_not_start_twice():
    from voicetray.hotkeys import HotkeyConfig, HotkeyController

    starts = []
    controller = HotkeyController(
        HotkeyConfig(record_hotkey="f9", alternate_record_hotkey=None),
        on_record_start=lambda: starts.append("start"),
        on_record_stop=lambda _session: None,
    )
    keyboard = FakeKeyboard()
    controller.start(keyboard)

    keyboard.press("f9")
    keyboard.press("f9")

    assert starts == ["start"]


def test_force_stop_resets_recording_and_invokes_stop_callback():
    from voicetray.hotkeys import HotkeyConfig, HotkeyController

    clock = FakeClock()
    starts = []
    stops = []
    controller = HotkeyController(
        HotkeyConfig(record_hotkey="f9", alternate_record_hotkey=None),
        on_record_start=lambda: starts.append("start"),
        on_record_stop=stops.append,
        clock=clock.now,
    )
    keyboard = FakeKeyboard()
    controller.start(keyboard)

    keyboard.press("f9")
    clock.advance(600)
    session = controller.force_stop()

    assert starts == ["start"]
    assert stops == [session]
    assert session.duration_seconds == 600
    assert controller.is_recording is False


def test_hotkey_config_from_app_config_uses_configurable_keys():
    from voicetray.hotkeys import HotkeyConfig

    cfg = {
        "hotkeys": {
            "speech": "ctrl+alt+space",
            "speech_alternative": "ctrl+win",
            "cancel": "esc",
            "tap_lock_ms": 250,
        }
    }

    hotkeys = HotkeyConfig.from_app_config(cfg)

    assert hotkeys.record_hotkey == "ctrl+alt+space"
    assert hotkeys.alternate_record_hotkey == "ctrl+win"
    assert hotkeys.cancel_hotkey == "esc"
    assert hotkeys.tap_lock_ms == 250


def test_hotkey_controller_restarts_dead_keyboard_listener():
    from voicetray.hotkeys import HotkeyConfig, HotkeyController

    class DeadListener:
        listening = False

    keyboard = FakeKeyboard()
    keyboard._listener = DeadListener()
    controller = HotkeyController(
        HotkeyConfig(record_hotkey="f9", alternate_record_hotkey=None),
        on_record_start=lambda: None,
        on_record_stop=lambda _session: None,
    )
    controller.start(keyboard)

    assert controller.is_backend_alive() is False
    assert controller.restart_if_dead() is True

    assert keyboard.removed == ["handle-0", "handle-1", "handle-2"]
    assert len(keyboard.registrations) == 6
    assert controller.is_listening is True


def test_hotkey_controller_does_not_restart_live_keyboard_listener():
    from voicetray.hotkeys import HotkeyConfig, HotkeyController

    class LiveListener:
        listening = True

    keyboard = FakeKeyboard()
    keyboard._listener = LiveListener()
    controller = HotkeyController(
        HotkeyConfig(record_hotkey="f9", alternate_record_hotkey=None),
        on_record_start=lambda: None,
        on_record_stop=lambda _session: None,
    )
    controller.start(keyboard)

    assert controller.is_backend_alive() is True
    assert controller.restart_if_dead() is False
    assert keyboard.removed == []
