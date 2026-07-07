# VoiceTray Test Checklist

## Automated Verification

Run these before manual acceptance:

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'; $env:QT_QPA_PLATFORM='offscreen'; python -B -m pytest tests\ -q
$env:PYTHONDONTWRITEBYTECODE='1'; python -B -m voicetray.eval
$env:PYTHONDONTWRITEBYTECODE='1'; python -B tools\soak.py --cycles 50 --target synthetic
```

Expected current result:

- Pytest: 188 passed, 1 skipped
- Eval harness: 42/42 passed
- Soak: 50 cycles, 0 failures, 0 UI freezes, RSS growth below 10%

## Manual App Matrix

Use the packaged app or `run_app.bat`, complete onboarding if prompted, and keep the History window available for raw/cleaned comparison.

- Notepad: hold F9, dictate two paragraphs with fillers, a self-correction, and a spoken numbered list. Confirm cleaned text inserts, raw text appears in History, and the pill returns to hidden.
- VS Code: repeat the same dictation in an editor tab. Confirm code/comment profile behavior still avoids aggressive punctuation changes when configured.
- Chrome textarea: dictate into a web textarea. Confirm clipboard paste insertion succeeds and the original clipboard content is restored.
- Slack: dictate into the message composer. Confirm chat-style cleanup, no duplicate send, and History copy/re-insert actions work.
- Terminal fallback: configure a terminal app profile with typing fallback, dictate a short command-like sentence, and confirm it types rather than pastes.
- RDP focus-change: start dictation in one field, move focus before release, and confirm insertion is skipped with the focus-change notification while the cleaned text remains in History.

## Reliability Checks

- Unplug and replug the default microphone, then start a new dictation without restarting VoiceTray.
- Start with no microphone available and confirm the tray tooltip shows "No microphone" and the pill shows the error state.
- Kill and relaunch VoiceTray, then confirm no duplicate tray icons remain and the single-instance notification appears on a second launch.
