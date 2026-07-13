from pathlib import Path

required = [Path("index.html"), Path("demo/index.html"), Path("llms.txt"), Path(".nojekyll")]
for path in required:
    if not path.exists():
        raise SystemExit(f"Missing site file: {path}")

landing = required[0].read_text(encoding="utf-8")
demo = required[1].read_text(encoding="utf-8")
checks = [
    'property="og:title"' in landing,
    'data-copy="agent"' in landing,
    "100% offline. $0/month." in landing,
    "Simulated demo" in demo,
    "no microphone permission" in demo,
    'id="run"' in demo,
]
if not all(checks):
    raise SystemExit("VoiceTray site contract failed")
print(f"Verified VoiceTray site: {len(checks)} contracts.")
