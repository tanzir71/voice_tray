"""Deprecated compatibility entrypoint for VoiceTray.

New code should run ``python -m voicetray`` or import ``voicetray.main``.
"""

from voicetray.main import main


if __name__ == "__main__":
    raise SystemExit(main())
