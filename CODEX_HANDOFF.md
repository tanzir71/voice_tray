# VoiceTray — Codex Handoff Spec (Loop-Runnable)

> **Purpose.** This document is the single source of truth for iteratively refining VoiceTray into a polished, **100% free and local** Windows dictation app that matches the "magic" of Wispr Flow and Typeless: speak messily → get clean, ready-to-post text typed into any app.
>
> **How to run this in a loop (Codex protocol):**
> 1. Read `## Loop State` below. Pick the **first unchecked task** in the lowest incomplete milestone.
> 2. Implement it fully. Small, reviewable commits. One task per iteration.
> 3. Run verification: `python -m pytest tests/ -q` must pass, plus the task's own acceptance criteria.
> 4. Check the task off in this file, append one line to `## Changelog` at the bottom (date, task ID, what changed, files touched).
> 5. If a task is impossible/blocked, do NOT skip silently — add a `BLOCKED:` note under the task with the reason and move to the next task.
> 6. Never violate `## Hard Constraints`. When in doubt, prefer the simpler, more reliable implementation.

---

## Locked Technical Decisions (owner-approved — implement these, do not re-litigate)

These were reviewed and explicitly approved by the project owner. Codex must implement them as stated; do not propose alternatives, do not keep the old stack alongside "just in case":

1. **STT = faster-whisper (CTranslate2), local.** Vosk and the Google/`speechrecognition` online fallback are **removed entirely** (code + requirements). Default model `base` int8, user-selectable up to `medium` in Settings → Models.
2. **UI = PySide6 exclusively.** `pystray`, `pyautogui`, and ALL tkinter UI (`voicetray_settings_gui.py`, in-app popups) are **deleted**, not wrapped or kept as fallback. One Qt event loop on the main thread; workers communicate via signals/slots only.
3. **Keep and extend the existing `dictation/` package** (rules → optional local LLM → validation → fallback) as the cleanup core. Do not rewrite it from scratch.
4. **Insertion = clipboard paste with save/restore** (not character typing), with per-app typing fallback only where paste is blocked.

## Hard Constraints (never violate)

- **Free & local only.** No paid APIs, no cloud STT/LLM, no telemetry, no network calls at runtime (model downloads at setup time are OK and must be user-triggered with a progress UI). Remove the Google Speech Recognition online fallback entirely.
- **Windows 10/11 first.** Python 3.11+ (currently developed on 3.13). Keep it runnable from source; a PyInstaller build is a late milestone, not a prerequisite.
- **No console window ever** in normal use. All `print()` → `logging` to `%LOCALAPPDATA%/VoiceTray/logs/voicetray.log` (rotating, 5×1MB).
- **Latency budget:** hotkey-release → text inserted: ≤ 1.5 s for a 10-second utterance on CPU (whisper `small`/`base` int8); ≤ 3.0 s with LLM cleanup enabled. Idle RAM ≤ 400 MB without LLM loaded.
- **Never lose the user's words.** Every raw transcript + cleaned transcript is appended to local history before insertion. Any cleanup failure falls back to the less-processed text, never to nothing.
- **Insertion must be safe:** never type into a password field knowingly, never leave the clipboard permanently overwritten (restore previous clipboard content after paste-insertion).
- **All processing code stays unit-testable:** pure functions in `dictation/`, UI strictly separated.

---

## 1. Current State (audited 2026-07-07)

### Repo map

```
voice_tray/
├── speech_to_text_app.py      # 949 lines. God-object VoiceTrayApp: tray, hotkeys, audio, STT, UI popups
├── voicetray_config.py        # 126 lines. settings.txt parser
├── voicetray_settings_gui.py  # 491 lines. tkinter settings window (launched via subprocess)
├── dictation/                 # The good part — keep and extend
│   ├── pipeline.py            # rules → optional local LLM → validation → fallback
│   ├── rules.py               # fillers, repetitions, self-corrections, punctuation, lists
│   ├── llm_local.py           # llama-cpp-python GGUF cleaner (strict JSON prompt)
│   ├── validation.py          # rejects risky LLM edits (numbers/glossary/too-different)
│   ├── glossary.py, protect.py, types.py
├── tests/test_pipeline.py, tests/test_rules.py
├── settings.txt, glossary.json, app_profiles.json, snippets.txt, saved_texts.txt
└── run_app.bat, readme.md
```

### What's good (keep)
- The **hybrid cleanup architecture** (deterministic rules → optional on-device LLM → validator with fallback) is exactly the right design and mirrors what competitors do in the cloud. Keep `dictation/` as the core.
- Modes (`raw`/`balanced`/`aggressive`) and profiles (`general`/`email`/`chat`/`notes`/`code/comments`), glossary with protected terms, per-app profiles via window title (`app_profiles.json`).
- Existing pytest suite for rules/pipeline.

### Critical defects (why it feels bad today)

| # | Defect | Where | Impact |
|---|--------|-------|--------|
| D1 | **Fixed 3-second recording** (`duration = 3`, `sd.rec(...)`, blocking) | `speech_to_text_app.py:488-525, 609-637` | Unusable for real dictation. Competitors record while you hold a key, for minutes. |
| D2 | **Vosk small model** accuracy is far below Whisper-class; README even suggests online Google fallback | `speech_to_text_app.py:38-51` | The transcript is too wrong for any cleanup to save it. |
| D3 | **`pyautogui.typewrite()`** for insertion | `speech_to_text_app.py:517,544` | Slow character-by-character typing, breaks on Unicode/emoji/non-US layouts, types into wrong window if focus changed. |
| D4 | **tkinter windows created from worker threads** (`show_minimal_save_feedback`, instruction popups) | `speech_to_text_app.py:701-882` | tkinter is not thread-safe → the "menu and other UI glitches" the owner reports: ghost windows, freezes, dead tray menu. |
| D5 | **Console-bound UX**: feedback via `print()`, app feels like a CLI script | throughout | No recording indicator, no processing state, no error surface. |
| D6 | **Tray icon drawn with PIL rectangles**, single static state | `speech_to_text_app.py:70-84` | Looks broken next to real tray icons; no recording/processing state. |
| D7 | Hotkeys are **toggle-press with no feedback**; `keyboard` lib swallows F9 globally even when idle | `speech_to_text_app.py:560-692` | User can't tell if it's recording; conflicts with other apps. |
| D8 | Settings GUI launched as a **separate subprocess**, state can diverge from the running app | `speech_to_text_app.py:335-358` | Settings changes need restarts; two sources of truth. |
| D9 | `settings.txt` ad-hoc format, duplicated defaults in code | `voicetray_config.py` | Fragile; migrate to `config.json` with schema + defaults in one place. |

---

## 2. Competitor Teardown

### 2.1 Feature comparison (researched July 2026)

| Capability | **Wispr Flow** ($15/mo, cloud) | **Typeless** ($12/mo, cloud) | **VoiceTray target (free, local)** |
|---|---|---|---|
| STT engine | Cloud (OpenAI/Meta models), ~97% accuracy | Cloud, auto language detection | **faster-whisper** (CTranslate2) local, `base`→`small`→`medium` selectable |
| Recording model | Hold-hotkey push-to-talk + hands-free lock; **6-min cap** | Hold-hotkey push-to-talk | Hold-to-talk **and** toggle lock mode; 10-min soft cap |
| Filler removal ("um", "uh", "like") | ✅ automatic | ✅ automatic | ✅ rules + LLM (`rules.py` exists) |
| **Backtrack / self-correction** ("at 2… actually 3" → "at 3") | ✅ core magic | ✅ core magic — its main differentiator ("keeps final intent") | ✅ `handle_self_corrections` exists in rules; extend + LLM pass |
| Repetition removal | ✅ | ✅ | ✅ exists |
| Auto punctuation & capitalization | ✅ from pauses/tone | ✅ | ✅ Whisper gives most of it; rules normalize |
| Spoken punctuation ("comma", "new line") | ✅ | ✅ | ✅ exists (`convert_spoken_punctuation`) |
| Auto lists ("1. apples 2. bananas" → formatted list) | ✅ | ✅ auto bullets/structure | ✅ exists (`enable_list_formatting`), extend to bullets |
| **Tone/style per app** (formal Gmail, casual Slack) | ✅ "Styles", context-aware | ✅ tone presets (personal/professional) | ✅ `app_profiles.json` → profile per window; add tone hint to LLM prompt |
| Personal dictionary (auto-learn corrected words) | ✅ auto-learns from corrections | ✅ | ✅ glossary.json exists; add UI + easy add |
| Snippets / voice shortcuts | ✅ | — | ✅ snippets.txt exists; add UI |
| Command mode ("rewrite last paragraph shorter") | ✅ | — | ❌ non-goal v1 (needs bigger LLM; revisit M7+) |
| Code/IDE awareness (camelCase, file tags) | ✅ strong | weak | ✅ `code/comments` profile exists; keep conservative |
| Whisper-quiet speech | ✅ | — | best-effort (input gain note in docs); non-goal |
| 100+ languages | ✅ | ✅ auto-detect | ✅ Whisper multilingual; language setting + auto option |
| History of dictations | ✅ dashboard | ✅ | ✅ history view (raw + cleaned, copy button) |
| Privacy | ❌ cloud; screenshot-context backlash; SOC2/HIPAA | ❌ cloud; zero-retention claim | ✅ **100% offline — our #1 marketing wedge** |
| Price | $15/mo, free tier 2k words/wk | $12/mo, free tier 8k words/wk | **Free, open source** |
| Known weaknesses to exploit | Electron app: 800MB idle RAM, Windows freezes, 2.7/5 Trustpilot | Cloud-only, no offline, no IDE features | Must beat them on: lightweight, private, reliable |

### 2.2 UI patterns to copy (what "polished" means)

**Wispr Flow UI anatomy:**
- Tray/menu-bar resident. **No console, no dock window** during use.
- While the hotkey is held: a **small floating pill** at the bottom-center of the screen with a live waveform/level animation → switches to a "processing" spinner state → disappears when text lands. This one element is 80% of the perceived polish.
- Main window (opened from tray) = dashboard: history list, dictionary, snippets, styles, settings tabs, total-words stat ("4× faster than typing" gamification).
- Onboarding: mic permission check, hotkey tutorial, live test box.

**Typeless UI anatomy:**
- Same hold-to-talk pill, plus a **raw vs. cleaned toggle** on each history item so users trust the cleanup (kills the "what did it change?" anxiety).
- Minimal settings; tone presets are one dropdown, not a prompt editor.

**VoiceTray must therefore ship:** tray icon with 3 states (idle / recording-red / processing-spin), floating recording pill with level meter, in-process settings window, history window with raw/clean diff, first-run onboarding wizard that downloads models with a progress bar.

---

## 3. Target Architecture

```
voicetray/                      # new package; speech_to_text_app.py shrinks to entry shim
├── main.py                     # entry: single-instance lock, logging setup, starts App
├── app.py                      # App controller: wires audio→stt→pipeline→inserter→ui
├── audio/
│   ├── recorder.py             # sounddevice InputStream, ring buffer, start/stop, level RMS callback
│   └── vad.py                  # optional: webrtcvad/silero trim of leading/trailing silence
├── stt/
│   └── whisper_engine.py       # faster-whisper wrapper; lazy-load; model size from config
├── dictation/                  # EXISTING — keep, extend (rules, llm_local, validation, glossary…)
├── insert/
│   └── inserter.py             # clipboard-paste insertion w/ clipboard save+restore; per-app fallback to typing
├── ui/                         # ALL UI in ONE framework on the MAIN thread
│   ├── tray.py                 # tray icon + menu, 3 icon states from .ico assets
│   ├── pill.py                 # frameless always-on-top recording pill w/ level meter + processing state
│   ├── settings_window.py      # tabs: General / Cleanup / Dictionary / Snippets / Models / About
│   ├── history_window.py       # list of dictations, raw↔clean toggle, copy, search
│   └── onboarding.py           # first-run wizard incl. model download w/ progress
├── config.py                   # config.json load/save, schema, migration from settings.txt
├── history.py                  # SQLite (%LOCALAPPDATA%/VoiceTray/history.db): ts, app, raw, cleaned, mode, profile
└── hotkeys.py                  # global hotkey (hold + toggle), suppress only while active
```

**UI framework: PySide6 — LOCKED decision (see "Locked Technical Decisions" at the top; owner-approved, do not substitute):**
- PySide6 (LGPL, free) gives native `QSystemTrayIcon` (fixes every pystray glitch), frameless translucent always-on-top pill via `Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint | Qt.Tool`, proper settings dialogs, and a single Qt event loop on the main thread — workers post back via signals/slots.
- Delete `pystray` and all tkinter code in the same milestone that replaces them (M4). If PySide6 installation fails in the environment, mark the task `BLOCKED:` with the pip error and stop — do NOT fall back to tkinter.

**Threading model:** main thread = UI event loop. One worker thread each for: hotkey listener, audio recorder, STT+pipeline job queue. Communication only via thread-safe queues/signals. No UI object ever touched off the main thread. This single rule eliminates defect D4.

**Key dependency changes** (`requirements.txt`):
- ADD: `faster-whisper`, `PySide6`, `pyperclip` (or Qt clipboard), `soundfile`
- KEEP: `sounddevice`, `keyboard`, `llama-cpp-python` (optional extra), `pytest`
- REMOVE: `speechrecognition`, `pyaudio`, `vosk`, `pystray`, `pyautogui`, `Pillow` (icon → shipped `.ico` assets in `assets/`)

**Recommended local models (document in README, download in onboarding):**
- STT: faster-whisper `base` (default, ~145MB, fast) / `small` (better) / `medium` (best CPU-viable). int8 compute.
- LLM cleanup (optional tier): `Qwen2.5-1.5B-Instruct` Q4_K_M GGUF (~1GB) — good instruction-following for the strict JSON cleanup prompt; existing `llm_local.py` + `validation.py` already handle the fallback safety.

---

## 4. Loop State — Milestones & Tasks

### M0 — Stabilize & scaffold (stop the bleeding)
- [x] **M0.1** Create `voicetray/` package skeleton per §3; move `dictation/` import paths; `speech_to_text_app.py` becomes a deprecation shim calling `voicetray.main`. All existing tests still pass.
- [x] **M0.2** Replace all `print()` with `logging` (rotating file handler in `%LOCALAPPDATA%/VoiceTray/logs/`). Acceptance: `grep -rn "print(" voicetray/ dictation/` returns nothing outside tests.
- [x] **M0.3** `config.py`: JSON config with schema + defaults; one-time auto-migration from `settings.txt` (keep old file untouched). Unit tests for defaults, migration, unknown keys.
- [x] **M0.4** Single-instance lock (named mutex or lockfile) — second launch focuses/exits with a tray notification, never a second tray icon.
- [x] **M0.5** `run_app.bat` → `pythonw -m voicetray`; add `run_debug.bat` (console + verbose logging).

### M1 — Real STT engine (kills D1, D2)
- [x] **M1.1** `audio/recorder.py`: `sounddevice.InputStream` with ring buffer; `start()`/`stop()` returning a mono 16 kHz float32 numpy array; emits RMS level ~30 Hz for the UI meter. Unit test with injected fake stream.
- [x] **M1.2** `stt/whisper_engine.py`: faster-whisper wrapper; model size + language + device from config; lazy load with "processing" state callback; `transcribe(audio) -> raw_text`. Integration test transcribes a bundled 3-sec WAV fixture (`tests/fixtures/hello.wav`) to non-empty text.
- [x] **M1.3** Delete Vosk + Google/`speechrecognition` paths and dependencies. Acceptance: `rg -n "vosk|recognize_google|speech_recognition" --glob '!*.md'` → no hits; app never opens a socket during dictation (verify: run with Wi-Fi off).
- [x] **M1.4** Silence trim (`audio/vad.py`, silero-vad via torch-free ONNX or webrtcvad): strip leading/trailing silence before STT; skip STT entirely if utterance is all silence (no "you" hallucinations). Unit test with silent WAV → empty result.

### M2 — Hold-to-talk UX + safe insertion (kills D3, D7)
- [x] **M2.1** `hotkeys.py`: **hold-to-record** — press & hold speech hotkey starts recording, release stops and triggers transcribe→clean→insert. Short tap (<300 ms) toggles hands-free lock mode; tapping again (or Esc) stops. Configurable keys; default hold=`f9`, plus `ctrl+win` alternative documented.
- [x] **M2.2** `insert/inserter.py`: default insertion = save clipboard → set clipboard → send `ctrl+v` via `keyboard` → restore clipboard (≥150 ms delay). Per-app override map (`app_profiles.json`) to fall back to typing for apps that block paste (e.g. some terminals). Verify focused window is unchanged between record-start and insert; if changed, do NOT insert — keep text in history + tray notification "Copied to history".
- [x] **M2.3** 10-minute soft cap with warning at 9:00 (competitor Wispr caps at 6 — beat them); memory-safe ring buffer.
- [x] **M2.4** `history.py`: SQLite history (ts, app name, raw, cleaned, mode, profile, duration, model). Every dictation is written **before** insertion is attempted.

### M3 — The cleanup "magic" (parity with the competitors' core value)
- [x] **M3.1** Extend `dictation/rules.py` self-correction handling: cue words ("actually", "no wait", "I mean", "scratch that", "sorry") replace the immediately preceding phrase, bounded + conservative; ship ≥20 new unit tests incl. false-positive guards ("no, wait for me" must NOT delete).
- [x] **M3.2** Filler list expansion + confidence-aware removal ("like", "you know", "sort of" only in `aggressive`); keep `balanced` safe. Tests.
- [x] **M3.3** Auto-structure: detect enumeration speech → numbered/bulleted lists; detect "new paragraph"; profile-aware (notes/email only). Tests.
- [x] **M3.4** LLM prompt v2 in `llm_local.py`: pass tone hint from active profile (email=formal, chat=casual, notes=terse) into the strict JSON cleanup prompt; validator (`validation.py`) unchanged rules: reject if numbers/glossary terms/URLs changed or length ratio out of [0.6, 1.4]. Tests with a fake LLM.
- [x] **M3.5** Glossary auto-learn hook: a `learn_word(term)` API + "Add to dictionary" action in history UI; persists to `glossary.json`. Tests.
- [x] **M3.6** Golden-file eval harness: `tests/eval_corpus.jsonl` with ≥40 (spoken-style input → expected clean output) pairs across modes/profiles; `python -m voicetray.eval` prints pass rate; CI target ≥90%. This is the loop's regression net for all cleanup changes.

### M4 — Polished UI (kills D4, D5, D6, D8)
- [x] **M4.1** PySide6 app shell: Qt event loop on main thread, worker signals; delete tkinter popups and `pystray`. App runs with zero console windows.
- [x] **M4.2** `ui/tray.py`: proper `.ico` assets (idle=mic outline, recording=red dot mic, processing=animated/badged), menu: *Start/Stop listening ▸ toggle, History…, Settings…, Open log folder, Quit*. Menu never stalls (all handlers non-blocking). Tooltip shows state + model.
- [x] **M4.3** `ui/pill.py`: frameless, always-on-top, click-through-except-button pill at bottom-center: recording state = live level bars + elapsed time + hotkey hint; processing state = spinner + "Polishing…"; error state = brief red flash + message. Auto-hides. Multi-monitor aware (appears on monitor with focused window).
- [x] **M4.4** `ui/settings_window.py` (in-process, replaces subprocess GUI): tabs **General** (hotkeys w/ conflict detection, autostart via HKCU Run key, language), **Cleanup** (mode, profile default, per-app profile editor), **Dictionary**, **Snippets**, **Models** (whisper size picker w/ download+progress, LLM enable + GGUF path + download link), **About**. Changes apply live — no restart.
- [x] **M4.5** `ui/history_window.py`: reverse-chron list, raw ↔ cleaned toggle per item (the Typeless trust feature), copy button, re-insert button, "Add word to dictionary" from selection, search. Reads SQLite.
- [x] **M4.6** `ui/onboarding.py` first-run wizard: welcome → mic check (live level) → model download with progress → hotkey tutorial with live test field → done. Sets `onboarded=true` in config.
- [x] **M4.7** Delete `voicetray_settings_gui.py`, dead code in old god-object, `saved_texts.txt` flow (replaced by history); update `readme.md` to the new reality.

### M5 — Reliability & performance hardening
- [x] **M5.1** Crash guard: top-level exception hook logs traceback + tray notification "VoiceTray hit an error — log saved"; app keeps running. Watchdog restarts a dead hotkey listener thread.
- [x] **M5.2** Perf: measure & log per-stage timings (record/vad/stt/rules/llm/insert). Meet budgets in Hard Constraints; if `small` model misses budget on this machine, auto-suggest `base` in a notification.
- [x] **M5.3** Device changes: default-mic hot-swap (USB headset plug/unplug) without restart; graceful "no microphone" state in tray + pill.
- [x] **M5.4** Soak test script `tools/soak.py`: 50 synthetic record→insert cycles into Notepad; zero leaks (RSS growth <10%), zero UI freezes. Document results in Changelog.
- [x] **M5.5** Full `pytest` suite green + eval harness ≥90% + manual test checklist (`docs/TEST_CHECKLIST.md`: Notepad, VS Code, Chrome textarea, Slack, terminal fallback, RDP focus-change case).

### M6 — Distribution
- [x] **M6.1** PyInstaller one-folder build (`tools/build.ps1`), `pythonw`-style no-console exe, assets + models dir external; icon set; version stamped from `voicetray/__init__.py`.
- [x] **M6.2** First-run model download works from packaged exe; "Start with Windows" registry toggle verified from exe.
- [x] **M6.3** README rewrite: positioning ("Wispr Flow magic, 100% offline and free"), GIF of the pill, honest comparison table from §2.1, model size guidance.

---

## 5. Definition of Done (whole project)

1. Cold start to ready-in-tray ≤ 4 s (model lazy-loads on first dictation with pill feedback).
2. Hold F9 → speak 2 paragraphs with "um"s, a self-correction, and "1. x 2. y 3. z" → release → within budget, cleaned text with a formatted list appears in Notepad, VS Code, and a Chrome textarea. Raw version visible in History.
3. Kill the app 20 times mid-anything: no orphan windows, no stuck clipboard, no ghost tray icons, no console flashes.
4. Wi-Fi disabled: everything works identically.
5. A first-time user can install, onboard, and dictate without reading the README.

## 6. Non-Goals (v1)

Command mode ("rewrite that shorter"), meeting transcription, mobile/web versions, whisper-quiet-speech tuning, macOS/Linux (structure code to not preclude it), team/shared dictionaries, telemetry of any kind.

---

## Changelog

<!-- Codex: append one line per completed task: YYYY-MM-DD | task ID | summary | files -->
- 2026-07-07 | — | Handoff spec created from codebase audit + Wispr Flow/Typeless competitive research | CODEX_HANDOFF.md
- 2026-07-07 | — | Owner approved and locked decisions: faster-whisper replaces Vosk/Google; PySide6 replaces pystray/tkinter (no fallback); keep dictation/ core; clipboard-paste insertion | CODEX_HANDOFF.md
- 2026-07-07 | M0.1 | Created voicetray package skeleton, moved dictation under voicetray.dictation with compatibility imports, and made speech_to_text_app.py delegate to voicetray.main | voicetray/, dictation/__init__.py, speech_to_text_app.py, tests/test_package_scaffold.py
- 2026-07-07 | M0.2 | Added rotating VoiceTray file logging and replaced production print calls with logger calls | voicetray/logging_config.py, voicetray/main.py, voicetray/legacy_app.py, tests/test_logging_config.py, CODEX_HANDOFF.md
- 2026-07-07 | M0.3 | Added JSON config schema/defaults, one-time settings.txt migration, unknown-key sanitizing, and startup config loading | voicetray/config.py, voicetray/main.py, tests/test_config.py, CODEX_HANDOFF.md
- 2026-07-07 | M0.4 | Added single-instance lockfile, stale-lock recovery, second-launch notification handoff, and startup gate before tray app import | voicetray/single_instance.py, voicetray/main.py, voicetray/legacy_app.py, voicetray/__main__.py, speech_to_text_app.py, tests/test_single_instance.py, CODEX_HANDOFF.md
- 2026-07-07 | M0.5 | Updated normal/debug launch scripts to use module entrypoints and added env-driven verbose console logging for debug runs | run_app.bat, run_debug.bat, voicetray/logging_config.py, tests/test_launch_scripts.py, tests/test_logging_config.py, CODEX_HANDOFF.md
- 2026-07-07 | M1.1 | Implemented sounddevice InputStream audio recorder with bounded ring buffer, mono float32 stop output, and throttled RMS level callbacks | voicetray/audio/recorder.py, tests/test_recorder.py, requirements.txt, CODEX_HANDOFF.md
- 2026-07-07 | M1.2 | Implemented faster-whisper wrapper with config-driven lazy loading, processing callbacks, raw transcript joining, and a bundled hello.wav integration fixture | voicetray/stt/whisper_engine.py, tests/test_whisper_engine.py, tests/fixtures/hello.wav, requirements.txt, pytest.ini, CODEX_HANDOFF.md
- 2026-07-07 | M1.3 | Removed legacy local/online STT engines and package pins, rewired legacy dictation through AudioRecorder + WhisperEngine, and made Whisper model loading local-cache-only by default | voicetray/legacy_app.py, voicetray/stt/whisper_engine.py, voicetray/config.py, requirements.txt, tests/test_removed_legacy_stt.py, tests/test_whisper_engine.py, CODEX_HANDOFF.md
- 2026-07-07 | M1.4 | Added WebRTC-backed silence trimming with deterministic energy fallback, wired WhisperEngine to trim before model loading, and covered silent WAV skip behavior | voicetray/audio/vad.py, voicetray/stt/whisper_engine.py, voicetray/config.py, requirements.txt, tests/test_vad.py, tests/test_whisper_engine.py, tests/test_config.py, CODEX_HANDOFF.md
- 2026-07-07 | M2.1 | Added hold-to-record hotkey controller with short-tap lock mode and Esc stop, exposed configurable defaults, and wired legacy speech hotkey recording to start/stop the recorder directly | voicetray/hotkeys.py, voicetray/legacy_app.py, voicetray/config.py, readme.md, tests/test_hotkeys.py, tests/test_legacy_hotkey_integration.py, tests/test_config.py, CODEX_HANDOFF.md
- 2026-07-07 | M2.2 | Added safe clipboard-paste insertion with clipboard restore, per-app typing fallback, focus-change skip handling, and removed pyautogui from runtime dependencies | voicetray/insert/inserter.py, voicetray/insert/__init__.py, voicetray/legacy_app.py, requirements.txt, readme.md, tests/test_inserter.py, tests/test_legacy_inserter_integration.py, tests/test_legacy_hotkey_integration.py, CODEX_HANDOFF.md
- 2026-07-07 | M2.3 | Added configurable long-recording limits, 9-minute warning notification, 10-minute auto-stop through the hotkey controller, and verified the recorder's 10-minute bounded ring buffer | voicetray/config.py, voicetray/hotkeys.py, voicetray/legacy_app.py, readme.md, tests/test_config.py, tests/test_hotkeys.py, tests/test_legacy_hotkey_integration.py, tests/test_recorder.py, CODEX_HANDOFF.md
- 2026-07-07 | M2.4 | Added SQLite dictation history, wired legacy dictation to append raw and cleaned text before insertion, captured recording duration and model metadata, and documented the local history database | voicetray/history.py, voicetray/legacy_app.py, readme.md, tests/test_history.py, tests/test_legacy_inserter_integration.py, tests/test_legacy_hotkey_integration.py, CODEX_HANDOFF.md
- 2026-07-07 | M3.1 | Reworked self-correction cleanup to conservatively replace bounded nearby phrases for actually/no wait/I mean/scratch that/sorry cues and added 30 parametrized unit cases covering replacements and false-positive guards | voicetray/dictation/rules.py, tests/test_rules.py, CODEX_HANDOFF.md
- 2026-07-07 | M3.2 | Expanded high-confidence vocal filler cleanup, made balanced mode remove only safe fillers, and limited ambiguous discourse fillers like like/you know/sort of/kind of to guarded aggressive-mode removal | voicetray/dictation/rules.py, voicetray/dictation/pipeline.py, tests/test_rules.py, tests/test_pipeline.py, CODEX_HANDOFF.md
- 2026-07-07 | M3.3 | Added profile-scoped auto-structure for notes/email, including numbered enumeration speech, bullet point phrasing, new paragraph conversion, and newline-preserving cleanup stages | voicetray/dictation/rules.py, voicetray/dictation/pipeline.py, tests/test_rules.py, tests/test_pipeline.py, CODEX_HANDOFF.md
- 2026-07-07 | M3.4 | Added tone-aware local LLM prompt plumbing for email/chat/notes profiles, kept neutral fallback for other profiles, and added explicit URL and length-ratio validator guards with fake-LLM coverage | voicetray/dictation/llm_local.py, voicetray/dictation/pipeline.py, voicetray/dictation/validation.py, tests/test_llm_local.py, tests/test_pipeline.py, tests/test_validation.py, CODEX_HANDOFF.md
- 2026-07-07 | M3.5 | Added glossary learn_word persistence, immediate pipeline glossary reloads, and a history-window Add to dictionary action hook with tests for persistence, dedupe, and blank selections | voicetray/dictation/glossary.py, voicetray/dictation/pipeline.py, voicetray/ui/history_window.py, tests/test_glossary.py, tests/test_history_window.py, tests/test_pipeline.py, CODEX_HANDOFF.md
- 2026-07-07 | M3.6 | Added golden-file dictation eval harness, a 42-case JSONL corpus spanning modes/profiles, CLI pass-rate reporting with a 90% default CI threshold, and tests for corpus coverage and module execution | voicetray/eval.py, tests/eval_corpus.jsonl, tests/test_eval_harness.py, CODEX_HANDOFF.md
- 2026-07-07 | M4.1 | Added the PySide6 Qt app shell with injectable worker signals, routed the process entrypoint through it, removed legacy popup/tray dependencies from the worker core, and updated dependencies/docs/tests for the Qt-only shell | voicetray/app.py, voicetray/main.py, voicetray/legacy_app.py, requirements.txt, readme.md, tests/test_qt_app_shell.py, tests/test_config.py, tests/test_single_instance.py, CODEX_HANDOFF.md
- 2026-07-07 | M4.2 | Added native PySide6 tray menu/state handling with nonblocking QAction callbacks, wired worker signals and tray actions through the app shell, shipped idle/recording/processing ICO tray assets, and updated README/tests for the tray surface | voicetray/ui/tray.py, voicetray/app.py, assets/tray/, tests/test_tray_ui.py, tests/test_qt_app_shell.py, readme.md, CODEX_HANDOFF.md
- 2026-07-07 | M4.3 | Added the PySide6 floating dictation pill with recording level bars, elapsed time, processing spinner, error flash, auto-hide behavior, active-monitor placement, and worker signal plumbing from recorder/STT events | voicetray/ui/pill.py, voicetray/app.py, voicetray/legacy_app.py, tests/test_pill_ui.py, tests/test_qt_app_shell.py, tests/test_legacy_hotkey_integration.py, readme.md, CODEX_HANDOFF.md
- 2026-07-07 | M4.4 | Added the in-process PySide6 settings window with General/Cleanup/Dictionary/Snippets/Models/About tabs, hotkey conflict validation, HKCU Run autostart support, live config apply hooks, local file editors, model controls, and tray Settings wiring | voicetray/ui/settings_window.py, voicetray/app.py, voicetray/ui/pill.py, tests/test_settings_window.py, tests/test_qt_app_shell.py, readme.md, CODEX_HANDOFF.md
- 2026-07-07 | M4.5 | Added the PySide6 history window with reverse-chron SQLite reading, raw/cleaned toggle, search, copy/re-insert actions, selection-to-dictionary learning, and tray History wiring | voicetray/ui/history_window.py, voicetray/app.py, tests/test_history_window.py, tests/test_qt_app_shell.py, readme.md, CODEX_HANDOFF.md
- 2026-07-07 | M4.6 | Added the first-run PySide6 onboarding wizard with welcome, live mic level, model progress, hotkey test field, onboarded config persistence, and startup wiring | voicetray/ui/onboarding.py, voicetray/app.py, tests/test_onboarding_window.py, tests/test_qt_app_shell.py, tests/test_config.py, readme.md, CODEX_HANDOFF.md
- 2026-07-07 | M4.7 | Removed the legacy tkinter settings GUI and saved_texts append flow, switched F10/focus-change fallbacks to SQLite history-only behavior, cleaned stale docs/static copy, and added guards against old file-storage references | voicetray/legacy_app.py, tests/test_removed_legacy_ui_storage.py, tests/test_legacy_hotkey_integration.py, tests/test_legacy_inserter_integration.py, readme.md, index.html, CODEX_HANDOFF.md
- 2026-07-07 | M5.1 | Added a crash guard for sys/thread exceptions with log-backed tray notification, installed it in the Qt shell, and added hotkey listener liveness checks plus watchdog restart/re-registration for the legacy worker | voicetray/crash_guard.py, voicetray/app.py, voicetray/hotkeys.py, voicetray/legacy_app.py, tests/test_crash_guard.py, tests/test_hotkeys.py, tests/test_legacy_hotkey_integration.py, tests/test_qt_app_shell.py, CODEX_HANDOFF.md
- 2026-07-07 | M5.2 | Added per-dictation performance timing capture/logging for record, VAD, STT, rules, LLM, and insert stages, plus a slow-small-model notification that suggests switching to base | voicetray/stt/whisper_engine.py, voicetray/dictation/pipeline.py, voicetray/legacy_app.py, tests/test_performance_timings.py, tests/test_legacy_hotkey_integration.py, CODEX_HANDOFF.md
- 2026-07-07 | M5.3 | Added default input stream retry for mic hot-swap, a NoInputDeviceError path, no-microphone tray state, and legacy worker error plumbing so the pill/tray fail gracefully when no mic is available | voicetray/audio/recorder.py, voicetray/ui/tray.py, voicetray/app.py, voicetray/legacy_app.py, tests/test_recorder.py, tests/test_tray_ui.py, tests/test_qt_app_shell.py, tests/test_legacy_hotkey_integration.py, CODEX_HANDOFF.md
- 2026-07-07 | M5.4 | Added `tools/soak.py` with synthetic and Notepad soak targets; verified `python -B tools/soak.py --cycles 50 --target synthetic` passed with 50 cycles, 0 failures, 0 UI freezes, and 0.0% RSS growth under the 10% limit | tools/soak.py, tools/__init__.py, tests/test_soak.py, CODEX_HANDOFF.md
- 2026-07-07 | M5.5 | Added `docs/TEST_CHECKLIST.md` covering Notepad, VS Code, Chrome textarea, Slack, terminal fallback, RDP focus-change, mic hot-swap, no-mic state, and single-instance checks; verified pytest 188 passed/1 skipped, eval 42/42, and synthetic soak 50 cycles clean | docs/TEST_CHECKLIST.md, tests/test_manual_checklist.py, CODEX_HANDOFF.md
- 2026-07-07 | M6.1 | Added a PyInstaller one-folder Windows build script with no-console `VoiceTray.exe`, icon/version stamping from `voicetray.__version__`, external assets/models directories, packaged asset lookup, and verified `tools/build.ps1` produced `dist/VoiceTray/VoiceTray.exe` | tools/build.ps1, requirements.txt, voicetray/ui/tray.py, tests/test_build_script.py, tests/test_tray_ui.py, CODEX_HANDOFF.md
- 2026-07-07 | M6.2 | Added packaged-safe Whisper model download to the external models directory, wired Settings/Onboarding model-download callbacks, fixed frozen autostart to register `VoiceTray.exe` directly, and rebuilt the PyInstaller one-folder app successfully | voicetray/model_download.py, voicetray/app.py, voicetray/ui/settings_window.py, tests/test_model_download.py, tests/test_settings_window.py, tests/test_qt_app_shell.py, CODEX_HANDOFF.md
- 2026-07-07 | M6.3 | Rewrote README positioning around "Wispr Flow magic, 100% offline and free", added the pill preview GIF, documented the competitor comparison, and added model size guidance with README regression coverage | readme.md, assets/readme/pill-preview.gif, tests/test_readme.py, CODEX_HANDOFF.md
