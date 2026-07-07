import numpy as np


class FakeInputStream:
    instances = []

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.callback = kwargs["callback"]
        self.started = False
        self.stopped = False
        self.closed = False
        FakeInputStream.instances.append(self)

    def start(self):
        self.started = True

    def stop(self):
        self.stopped = True

    def close(self):
        self.closed = True

    def emit(self, samples):
        data = np.asarray(samples)
        self.callback(data, len(data), None, None)


class FailingInputStream:
    def __init__(self, **_kwargs):
        raise RuntimeError("no default input")


def test_recorder_starts_sounddevice_stream_and_returns_mono_float32_audio():
    from voicetray.audio.recorder import AudioRecorder

    FakeInputStream.instances.clear()
    recorder = AudioRecorder(stream_factory=FakeInputStream)

    recorder.start()
    stream = FakeInputStream.instances[-1]
    stream.emit([[0.25], [-0.5], [1.0]])
    audio = recorder.stop()

    assert stream.kwargs["samplerate"] == 16000
    assert stream.kwargs["channels"] == 1
    assert stream.kwargs["dtype"] == "float32"
    assert stream.started is True
    assert stream.stopped is True
    assert stream.closed is True
    assert audio.dtype == np.float32
    assert audio.shape == (3,)
    np.testing.assert_allclose(audio, np.array([0.25, -0.5, 1.0], dtype=np.float32))


def test_recorder_mixes_multichannel_input_to_mono():
    from voicetray.audio.recorder import AudioRecorder

    FakeInputStream.instances.clear()
    recorder = AudioRecorder(stream_factory=FakeInputStream)

    recorder.start()
    FakeInputStream.instances[-1].emit([[0.0, 1.0], [1.0, -1.0]])
    audio = recorder.stop()

    np.testing.assert_allclose(audio, np.array([0.5, 0.0], dtype=np.float32))


def test_recorder_ring_buffer_keeps_only_recent_audio():
    from voicetray.audio.recorder import AudioRecorder

    FakeInputStream.instances.clear()
    recorder = AudioRecorder(
        sample_rate=10,
        max_seconds=0.3,
        stream_factory=FakeInputStream,
    )

    recorder.start()
    stream = FakeInputStream.instances[-1]
    stream.emit([[0.0], [1.0]])
    stream.emit([[2.0], [3.0], [4.0]])
    audio = recorder.stop()

    np.testing.assert_allclose(audio, np.array([2.0, 3.0, 4.0], dtype=np.float32))


def test_recorder_emits_rms_level_at_configured_rate():
    from voicetray.audio.recorder import AudioRecorder

    FakeInputStream.instances.clear()
    current_time = [0.0]
    levels = []
    recorder = AudioRecorder(
        stream_factory=FakeInputStream,
        level_callback=levels.append,
        level_hz=30,
        clock=lambda: current_time[0],
    )

    recorder.start()
    stream = FakeInputStream.instances[-1]
    stream.emit([[0.5], [-0.5]])
    current_time[0] = 0.01
    stream.emit([[1.0], [1.0]])
    current_time[0] = 0.04
    stream.emit([[1.0], [1.0]])
    recorder.stop()

    assert len(levels) == 2
    np.testing.assert_allclose(levels, [0.5, 1.0])


def test_stop_without_start_returns_empty_float32_audio():
    from voicetray.audio.recorder import AudioRecorder

    recorder = AudioRecorder(stream_factory=FakeInputStream)

    audio = recorder.stop()

    assert audio.dtype == np.float32
    assert audio.shape == (0,)


def test_recorder_default_ring_buffer_limit_is_ten_minutes():
    from voicetray.audio.recorder import AudioRecorder

    recorder = AudioRecorder(stream_factory=FakeInputStream)

    assert recorder.max_seconds == 600.0


def test_recorder_retries_default_input_stream_after_open_failure():
    from voicetray.audio.recorder import AudioRecorder

    FakeInputStream.instances.clear()
    calls = []

    def stream_factory(**kwargs):
        calls.append(kwargs)
        if len(calls) == 1:
            raise RuntimeError("stale default input")
        return FakeInputStream(**kwargs)

    recorder = AudioRecorder(stream_factory=stream_factory, device=None)

    recorder.start()
    audio = recorder.stop()

    assert len(calls) == 2
    assert calls[0]["device"] is None
    assert calls[1]["device"] is None
    assert audio.dtype == np.float32


def test_recorder_raises_no_input_device_error_when_default_input_unavailable():
    from voicetray.audio.recorder import AudioRecorder, NoInputDeviceError

    recorder = AudioRecorder(stream_factory=FailingInputStream, device=None)

    try:
        recorder.start()
    except NoInputDeviceError as exc:
        assert str(exc) == "No microphone"
    else:
        raise AssertionError("expected NoInputDeviceError")

    assert recorder.is_recording is False
