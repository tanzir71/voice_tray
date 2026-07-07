import threading
import time
import logging
import keyboard
import sys
import os
import atexit
import json
import re
from difflib import SequenceMatcher

from voicetray.audio.recorder import AudioRecorder, NoInputDeviceError
from voicetray.config import load_config
from voicetray.dictation import DictationConfig, DictationContext, DictationPipeline
from voicetray.dictation.llm_local import LocalLLMConfig
from voicetray.history import DictationHistoryStore, HistoryEntry
from voicetray.hotkeys import HotkeyConfig, HotkeyController
from voicetray.insert.inserter import Inserter
from voicetray.stt.whisper_engine import WhisperEngine, WhisperEngineConfig

logger = logging.getLogger(__name__)

PERFORMANCE_STAGES = ("record", "vad", "stt", "rules", "llm", "insert")
PROCESSING_STAGES = ("vad", "stt", "rules", "llm", "insert")
SMALL_MODEL_SLOW_NOTIFICATION = "Small model is running slowly; try the base model in Settings > Models."

class VoiceTrayApp:
    def __init__(self):
        self.is_listening = False
        self.is_recording = False
        self.hotkey = 'f9'  # Default hotkey - F9 key
        self.alternate_hotkey = 'ctrl+win'
        self.save_hotkey = 'f10'
        self.cancel_hotkey = 'esc'
        self.tap_lock_ms = 300
        self.icon = None
        self.running = True
        self.last_recognized_text = ""
        self.legacy_record_seconds = 3.0
        self.recording_focus_token = None
        self.recording_max_seconds = 600
        self.recording_warning_seconds = 540
        self.recording_warning_timer = None
        self.recording_cap_timer = None
        self.timer_factory = threading.Timer
        self.hotkey_watchdog_interval_seconds = 5.0
        self.hotkey_watchdog_thread = None
        self.hotkey_watchdog_stop_event = None
        self.performance_clock = time.perf_counter
        self.small_model_budget_seconds = 1.5
        self.llm_budget_seconds = 3.0
        self._small_model_suggestion_shown = False
        self.audio_level_callback = None
        self.recording_started_callback = None
        self.recording_stopped_callback = None
        self.processing_started_callback = None
        self.processing_finished_callback = None
        self.error_callback = None
        self.audio_recorder = AudioRecorder(level_callback=self.on_audio_level)
        self.stt_engine = None
        self.stt_config = WhisperEngineConfig()
        
        # Store recent text for repetition detection
        self.recent_texts = []
        self.max_recent_texts = 5
        
        # Load settings from file
        self.load_settings()
        
        # Initialize local support files
        self.init_support_files()
        
        # Load snippets from file
        self.load_snippets_from_file()

        self.load_app_profiles()
        self.init_inserter()
        self.init_history_store()
        self.init_dictation_pipeline()
        self.init_speech_engine()
        self.init_hotkey_controller()
        self.prompt_llm_setup_if_needed()
    
    def create_icon_image(self):
        """Reserved for the dedicated Qt tray implementation."""
        return None
    
    def remove_repetitions(self, text):
        """Remove repetitive words and phrases from text"""
        if not text:
            return text
        
        # Split into words
        words = text.split()
        if len(words) <= 1:
            return text
        
        # Remove consecutive duplicate words
        cleaned_words = [words[0]]
        for i in range(1, len(words)):
            if words[i].lower() != words[i-1].lower():
                cleaned_words.append(words[i])
        
        # Remove repetitive phrases (2-3 word sequences)
        final_text = ' '.join(cleaned_words)
        
        # Check for phrase repetitions
        for phrase_len in [3, 2]:
            words = final_text.split()
            if len(words) < phrase_len * 2:
                continue
            
            cleaned = []
            i = 0
            while i < len(words):
                if i + phrase_len * 2 <= len(words):
                    phrase1 = ' '.join(words[i:i+phrase_len])
                    phrase2 = ' '.join(words[i+phrase_len:i+phrase_len*2])
                    
                    if phrase1.lower() == phrase2.lower():
                        cleaned.extend(words[i:i+phrase_len])
                        i += phrase_len * 2
                    else:
                        cleaned.append(words[i])
                        i += 1
                else:
                    cleaned.append(words[i])
                    i += 1
            
            final_text = ' '.join(cleaned)
        
        return final_text
    
    def check_similarity_with_recent(self, text):
        """Check if text is too similar to recently processed text"""
        if not text or not self.recent_texts:
            return False
        
        for recent_text in self.recent_texts:
            similarity = SequenceMatcher(None, text.lower(), recent_text.lower()).ratio()
            if similarity > 0.8:  # 80% similarity threshold
                return True
        return False
    
    def basic_grammar_check(self, text):
        """Apply basic grammar corrections"""
        if not text:
            return text
        
        # Capitalize first letter
        text = text.strip()
        if text:
            text = text[0].upper() + text[1:]
        
        # Fix common grammar issues
        # Fix double spaces
        text = re.sub(r'\s+', ' ', text)
        
        # Fix spacing around punctuation
        text = re.sub(r'\s+([,.!?;:])', r'\1', text)
        text = re.sub(r'([,.!?;:])([a-zA-Z])', r'\1 \2', text)
        
        # Common word corrections
        corrections = {
            r'\bi\b': 'I',
            r'\bim\b': "I'm",
            r'\bive\b': "I've",
            r'\bill\b': "I'll",
            r'\bwont\b': "won't",
            r'\bcant\b': "can't",
            r'\bdont\b': "don't",
            r'\bisnt\b': "isn't",
            r'\barent\b': "aren't",
            r'\bwasnt\b': "wasn't",
            r'\bwerent\b': "weren't",
            r'\bhasnt\b': "hasn't",
            r'\bhavent\b': "haven't",
            r'\bhadnt\b': "hadn't",
            r'\bwont\b': "won't",
            r'\bwouldnt\b': "wouldn't",
            r'\bcouldnt\b': "couldn't",
            r'\bshouldnt\b': "shouldn't"
        }
        
        for pattern, replacement in corrections.items():
            text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
        
        return text
    
    def process_text(self, raw_text, context=None, timings=None):
        """Process text to remove repetitions and apply grammar checking"""
        if not raw_text:
            return None
        
        # Check if too similar to recent texts
        if self.check_similarity_with_recent(raw_text):
            logger.info("Skipping similar text to avoid repetition")
            return None

        if context is None:
            context = self.select_dictation_context()
        final_text = self.dictation_pipeline.process_transcript(raw_text, context)
        self._merge_component_timings(timings, getattr(self.dictation_pipeline, 'last_timings', None))
        final_text = self.expand_snippets(final_text)
        
        # Store in recent texts for future comparison
        self.recent_texts.append(final_text)
        if len(self.recent_texts) > self.max_recent_texts:
            self.recent_texts.pop(0)
        
        return final_text
    
    def resolve_project_path(self, value):
        if not value or os.path.isabs(value):
            return value
        return os.path.join(os.path.dirname(os.path.dirname(__file__)), value)

    def load_settings(self):
        """Load settings from the JSON config."""
        try:
            cfg = load_config()
            hotkey_cfg = HotkeyConfig.from_app_config(cfg)
            hotkeys = cfg.get('hotkeys', {})
            app = cfg.get('app', {})
            recording = cfg.get('recording', {})
            dictation = cfg.get('dictation', {})
            llm = cfg.get('llm', {})

            self.hotkey = hotkey_cfg.record_hotkey
            self.alternate_hotkey = hotkey_cfg.alternate_record_hotkey
            self.save_hotkey = hotkeys.get('save', self.save_hotkey)
            self.cancel_hotkey = hotkey_cfg.cancel_hotkey
            self.tap_lock_ms = hotkey_cfg.tap_lock_ms
            self.auto_start_listening = bool(app.get('auto_start_listening', True))
            self.notification_duration = int(app.get('notification_duration', 3))
            self.recording_max_seconds = int(recording.get('max_seconds', 600))
            self.recording_warning_seconds = int(recording.get('warning_seconds', 540))
            self.dictation_mode = str(dictation.get('mode', 'balanced')).lower()
            self.format_profile = str(dictation.get('profile', 'general')).lower()
            self.glossary_path = self.resolve_project_path(
                str(dictation.get('glossary_path', 'glossary.json'))
            )
            self.app_profiles_path = self.resolve_project_path(
                str(dictation.get('app_profiles_path', 'app_profiles.json'))
            )

            self.llm_enabled = bool(llm.get('enabled', False))
            self.llm_model_path = self.resolve_project_path(
                str(llm.get('model_path', 'models/llm/model.gguf'))
            )
            self.llm_n_ctx = int(llm.get('n_ctx', 2048))
            self.llm_max_tokens = int(llm.get('max_tokens', 256))
            self.llm_temperature = float(llm.get('temperature', 0.05))
            self.llm_top_p = float(llm.get('top_p', 0.9))
            self.llm_threads = llm.get('threads')
            self.llm_gpu_layers = llm.get('gpu_layers')
            self.stt_config = WhisperEngineConfig.from_app_config(cfg)

            logger.info(
                "Settings loaded: speech_hotkey=%s, save_hotkey=%s",
                self.hotkey,
                self.save_hotkey,
            )
        except Exception:
            logger.exception("Error loading settings")
            self.auto_start_listening = True
            self.notification_duration = 3
            self.dictation_mode = 'balanced'
            self.format_profile = 'general'
            self.alternate_hotkey = 'ctrl+win'
            self.cancel_hotkey = 'esc'
            self.tap_lock_ms = 300
            self.recording_max_seconds = 600
            self.recording_warning_seconds = 540
            self.glossary_path = self.resolve_project_path('glossary.json')
            self.app_profiles_path = self.resolve_project_path('app_profiles.json')
            self.llm_enabled = False
            self.llm_model_path = self.resolve_project_path('models/llm/model.gguf')
            self.llm_n_ctx = 2048
            self.llm_max_tokens = 256
            self.llm_temperature = 0.05
            self.llm_top_p = 0.9
            self.llm_threads = None
            self.llm_gpu_layers = None
            self.stt_config = WhisperEngineConfig()
    
    def init_support_files(self):
        """Initialize editable support files if they don't exist."""
        try:
            # Ensure snippets.txt exists
            snippets_path = os.path.join(os.path.dirname(__file__), 'snippets.txt')
            if not os.path.exists(snippets_path):
                with open(snippets_path, 'w', encoding='utf-8') as f:
                    f.write("# YOUR SNIPPETS (add below this line):\n\n")

            glossary_path = os.path.join(os.path.dirname(__file__), 'glossary.json')
            if not os.path.exists(glossary_path):
                with open(glossary_path, 'w', encoding='utf-8') as f:
                    json.dump({"user_terms": [], "protected_terms": [], "replacements": {}}, f, indent=2)

            app_profiles_path = os.path.join(os.path.dirname(__file__), 'app_profiles.json')
            if not os.path.exists(app_profiles_path):
                with open(app_profiles_path, 'w', encoding='utf-8') as f:
                    json.dump([], f, indent=2)
                    
            logger.info("Support files initialized successfully")
        except Exception as e:
            logger.exception("Error initializing support files")

    def init_dictation_pipeline(self):
        llm_cfg = LocalLLMConfig(
            enabled=bool(self.llm_enabled),
            model_path=self.llm_model_path,
            n_ctx=int(self.llm_n_ctx),
            max_tokens=int(self.llm_max_tokens),
            temperature=float(self.llm_temperature),
            top_p=float(self.llm_top_p),
            n_threads=self.llm_threads,
            n_gpu_layers=self.llm_gpu_layers,
        )
        cfg = DictationConfig(glossary_path=self.glossary_path, llm=llm_cfg)
        self.dictation_pipeline = DictationPipeline(cfg)

    def init_speech_engine(self):
        self.audio_recorder = AudioRecorder(
            max_seconds=self.recording_max_seconds,
            level_callback=self.on_audio_level,
        )
        self.stt_engine = WhisperEngine(self.stt_config, state_callback=self.on_stt_state)
        logger.info(
            "Local STT engine configured: model=%s device=%s compute_type=%s",
            self.stt_config.model_size,
            self.stt_config.device,
            self.stt_config.compute_type,
        )

    def init_hotkey_controller(self):
        self.hotkey_config = HotkeyConfig(
            record_hotkey=self.hotkey,
            alternate_record_hotkey=self.alternate_hotkey,
            cancel_hotkey=self.cancel_hotkey,
            tap_lock_ms=self.tap_lock_ms,
        )
        self.hotkey_controller = HotkeyController(
            self.hotkey_config,
            on_record_start=self.start_hotkey_recording,
            on_record_stop=self.finish_hotkey_recording,
        )
        self.save_hotkey_handle = None

    def start_hotkey_watchdog(self):
        interval = float(getattr(self, 'hotkey_watchdog_interval_seconds', 5.0) or 0.0)
        if interval <= 0:
            return
        thread = getattr(self, 'hotkey_watchdog_thread', None)
        if thread is not None and thread.is_alive():
            return
        stop_event = threading.Event()
        self.hotkey_watchdog_stop_event = stop_event
        self.hotkey_watchdog_thread = threading.Thread(
            target=self.hotkey_watchdog_loop,
            args=(stop_event,),
            daemon=True,
        )
        self.hotkey_watchdog_thread.start()

    def stop_hotkey_watchdog(self):
        stop_event = getattr(self, 'hotkey_watchdog_stop_event', None)
        if stop_event is not None:
            stop_event.set()
        self.hotkey_watchdog_stop_event = None

    def hotkey_watchdog_loop(self, stop_event):
        interval = float(getattr(self, 'hotkey_watchdog_interval_seconds', 5.0) or 5.0)
        while not stop_event.wait(interval):
            self.restart_dead_hotkey_listener()

    def restart_dead_hotkey_listener(self):
        if not getattr(self, 'is_listening', False):
            return False
        controller = getattr(self, 'hotkey_controller', None)
        if controller is None or not hasattr(controller, 'restart_if_dead'):
            return False
        try:
            restarted = bool(controller.restart_if_dead())
        except Exception:
            logger.exception("Could not check hotkey listener health")
            return False
        if not restarted:
            return False

        old_handle = getattr(self, 'save_hotkey_handle', None)
        if old_handle is not None:
            try:
                keyboard.remove_hotkey(old_handle)
            except Exception:
                logger.debug("Could not remove stale save hotkey handle", exc_info=True)
        self.save_hotkey_handle = keyboard.add_hotkey(self.save_hotkey, self.on_save_hotkey_press)
        self.show_tray_notification("VoiceTray restarted hotkeys after a listener error.")
        return True

    def on_stt_state(self, state):
        logger.debug("STT state: %s", state)

    def on_audio_level(self, rms):
        callback = getattr(self, 'audio_level_callback', None)
        if callback is None:
            return
        try:
            callback(float(rms))
        except Exception:
            logger.debug("Could not emit audio level", exc_info=True)

    def emit_ui_callback(self, attr, *args):
        callback = getattr(self, attr, None)
        if callback is None:
            return
        try:
            callback(*args)
        except Exception:
            logger.debug("Could not emit %s", attr, exc_info=True)

    def _performance_now(self):
        return getattr(self, 'performance_clock', time.perf_counter)()

    def _elapsed_since(self, started):
        return max(0.0, self._performance_now() - started)

    def _merge_component_timings(self, timings, source):
        if timings is None or not isinstance(source, dict):
            return
        for stage in ("vad", "stt", "rules", "llm"):
            if stage in source:
                timings[stage] = float(source.get(stage) or 0.0)

    def _processing_total_seconds(self, timings):
        return sum(float(timings.get(stage, 0.0) or 0.0) for stage in PROCESSING_STAGES)

    def report_dictation_performance(self, timings):
        timings = timings or {}
        for stage in PERFORMANCE_STAGES:
            timings.setdefault(stage, 0.0)
        total = self._processing_total_seconds(timings)
        model_size = str(getattr(getattr(self, 'stt_config', None), 'model_size', 'unknown'))
        logger.info(
            "Dictation timings: record=%.3fs vad=%.3fs stt=%.3fs rules=%.3fs llm=%.3fs insert=%.3fs total=%.3fs model=%s",
            float(timings["record"] or 0.0),
            float(timings["vad"] or 0.0),
            float(timings["stt"] or 0.0),
            float(timings["rules"] or 0.0),
            float(timings["llm"] or 0.0),
            float(timings["insert"] or 0.0),
            total,
            model_size,
        )
        budget = (
            float(getattr(self, 'llm_budget_seconds', 3.0))
            if getattr(self, 'llm_enabled', False)
            else float(getattr(self, 'small_model_budget_seconds', 1.5))
        )
        if (
            model_size.lower() == "small"
            and total > budget
            and not getattr(self, '_small_model_suggestion_shown', False)
        ):
            self._small_model_suggestion_shown = True
            self.show_tray_notification(SMALL_MODEL_SLOW_NOTIFICATION)

    def llm_setup_status(self):
        if not getattr(self, 'llm_enabled', False):
            return True, 'disabled'
        model_path = getattr(self, 'llm_model_path', '')
        if not model_path:
            return False, 'missing_model_path'
        if not os.path.exists(model_path):
            return False, 'model_not_found'
        if not getattr(self, 'dictation_pipeline', None):
            return False, 'pipeline_not_ready'
        if not self.dictation_pipeline.llm.available():
            return False, 'llama_cpp_missing'
        return True, 'ok'

    def prompt_llm_setup_if_needed(self):
        ok, reason = self.llm_setup_status()
        if ok:
            return
        self.show_tray_notification(
            "Local LLM setup needs attention; open Settings from the tray."
        )

    def load_app_profiles(self):
        self.app_profiles = []
        try:
            path = getattr(self, 'app_profiles_path', os.path.join(os.path.dirname(__file__), 'app_profiles.json'))
            if not path or not os.path.exists(path):
                return
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            if isinstance(data, list):
                self.app_profiles = [d for d in data if isinstance(d, dict)]
        except Exception as e:
            logger.exception("Error loading app profiles")

    def init_inserter(self):
        self.inserter = Inserter(
            focus_provider=self.get_active_window_identity,
            profiles=getattr(self, 'app_profiles', []),
        )

    def init_history_store(self):
        self.history_store = DictationHistoryStore()

    def get_active_window_title(self):
        if sys.platform != "win32":
            return None
        try:
            import ctypes

            user32 = ctypes.windll.user32
            hwnd = user32.GetForegroundWindow()
            length = user32.GetWindowTextLengthW(hwnd)
            buf = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buf, length + 1)
            title = buf.value
            return title or None
        except Exception:
            return None

    def get_active_window_identity(self):
        if sys.platform != "win32":
            return self.get_active_window_title()
        try:
            import ctypes

            return int(ctypes.windll.user32.GetForegroundWindow())
        except Exception:
            return self.get_active_window_title()

    def select_dictation_context(self):
        title = self.get_active_window_title()
        mode = self.dictation_mode
        profile = self.format_profile
        if title and getattr(self, 'app_profiles', None):
            lowered = title.lower()
            for entry in self.app_profiles:
                match = entry.get('match')
                if isinstance(match, str) and match and match.lower() in lowered:
                    entry_mode = entry.get('mode')
                    entry_profile = entry.get('profile')
                    if isinstance(entry_mode, str) and entry_mode:
                        mode = entry_mode.lower()
                    if isinstance(entry_profile, str) and entry_profile:
                        profile = entry_profile.lower()
                    break
        if mode not in ('raw', 'balanced', 'aggressive'):
            mode = 'balanced'
        if profile not in ('general', 'email', 'chat', 'notes', 'code/comments'):
            profile = 'general'
        return DictationContext(mode=mode, profile=profile, app_title=title)
    
    def load_snippets_from_file(self):
        """Load snippets from snippets.txt file into memory"""
        try:
            snippets_path = os.path.join(os.path.dirname(__file__), 'snippets.txt')
            self.snippets = {}
            
            if os.path.exists(snippets_path):
                with open(snippets_path, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith('#') and '=' in line:
                            trigger_word, expansion_text = line.split('=', 1)
                            trigger_word = trigger_word.strip().lower()
                            expansion_text = expansion_text.strip()
                            self.snippets[trigger_word] = expansion_text
            
            logger.info("Loaded %s snippets from file", len(self.snippets))
            
        except Exception as e:
            logger.exception("Error loading snippets from file")
    
    def expand_snippets(self, text):
        """Expand any snippets found in the text"""
        try:
            if not hasattr(self, 'snippets') or not self.snippets:
                return text
            
            expanded_text = text
            words = text.lower().split()
            
            for trigger_word, expansion_text in self.snippets.items():
                # Check if trigger word exists as a whole word
                if trigger_word in words:
                    # Replace the trigger word with expansion text (case insensitive)
                    pattern = r'\b' + re.escape(trigger_word) + r'\b'
                    expanded_text = re.sub(pattern, expansion_text, expanded_text, flags=re.IGNORECASE)
            
            return expanded_text
        except Exception as e:
            logger.exception("Error expanding snippets")
            return text
    

    

     
    def record_legacy_audio(self, timings=None):
        """Record a short clip until the hold-to-talk controller lands in M2."""
        logger.info("Listening")
        started = self._performance_now()
        self.audio_recorder.start()
        try:
            time.sleep(self.legacy_record_seconds)
        finally:
            audio = self.audio_recorder.stop()
            if timings is not None:
                timings["record"] = self._elapsed_since(started)
        return audio

    def transcribe_legacy_recording(self, timings=None):
        audio = self.record_legacy_audio(timings=timings)
        return self.transcribe_audio_to_text(audio, timings=timings)

    def transcribe_audio_to_text(self, audio, timings=None):
        if self.stt_engine is None:
            self.init_speech_engine()
        if getattr(audio, "size", 0) == 0:
            return None
        raw_text = self.stt_engine.transcribe(audio).strip()
        self._merge_component_timings(timings, getattr(self.stt_engine, 'last_timings', None))
        return raw_text or None

    def process_raw_transcript(self, raw_text, *, insert_text, duration_seconds=None, timings=None):
        if not raw_text:
            return None
        timings = timings if timings is not None else {}

        context = self.select_dictation_context()
        processed_text = self.process_text(raw_text, context=context, timings=timings)
        if not processed_text:
            return None

        app_title = getattr(context, 'app_title', None) or self.get_active_window_title()
        self.record_history_entry(raw_text, processed_text, context, duration_seconds, app_title)
        self.last_recognized_text = processed_text
        if insert_text:
            insert_started = self._performance_now()
            result = self.inserter.insert_text(
                processed_text,
                start_focus=getattr(self, 'recording_focus_token', None),
                app_title=app_title,
            )
            timings["insert"] = self._elapsed_since(insert_started)
            if result.status == "skipped_focus_changed":
                self.show_tray_notification("Copied to history; focus changed before insertion.")
            elif result.status != "inserted":
                logger.warning("Text insertion skipped: %s", result.reason or result.status)
        else:
            timings.setdefault("insert", 0.0)
        logger.info("Original: %s", raw_text)
        logger.info("Processed: %s", processed_text)
        self.report_dictation_performance(timings)
        return processed_text

    def record_history_entry(self, raw_text, cleaned_text, context, duration_seconds, app_title):
        try:
            entry = HistoryEntry(
                app_name=app_title,
                raw_text=raw_text,
                cleaned_text=cleaned_text,
                mode=context.mode,
                profile=context.profile,
                duration_seconds=duration_seconds,
                model=getattr(self.stt_config, 'model_size', 'unknown'),
            )
            self.history_store.append(entry)
        except Exception:
            logger.exception("Could not append dictation history")

    def speech_to_text(self):
        """Convert local audio to text and insert it into the active field."""
        try:
            timings = {}
            raw_text = self.transcribe_legacy_recording(timings=timings)
            return self.process_raw_transcript(raw_text, insert_text=True, timings=timings)
        except Exception:
            logger.exception("Local dictation error")
            return None

    def start_hotkey_recording(self):
        """Start recording immediately for hold-to-talk hotkeys."""
        if self.is_recording:
            return
        try:
            self.is_recording = True
            self.recording_focus_token = self.get_active_window_identity()
            logger.info("Recording started")
            self.audio_recorder.start()
            self.emit_ui_callback('recording_started_callback')
            self.schedule_recording_limit_timers()
        except NoInputDeviceError:
            self.is_recording = False
            self.emit_ui_callback('error_callback', "No microphone")
            logger.exception("No microphone available")
        except Exception:
            self.is_recording = False
            self.emit_ui_callback('error_callback', "Could not start recording")
            logger.exception("Could not start recording")

    def schedule_recording_limit_timers(self):
        self.cancel_recording_limit_timers()
        warning_seconds = getattr(self, 'recording_warning_seconds', 540)
        max_seconds = getattr(self, 'recording_max_seconds', 600)
        timer_factory = getattr(self, 'timer_factory', threading.Timer)

        if warning_seconds and 0 < warning_seconds < max_seconds:
            self.recording_warning_timer = timer_factory(warning_seconds, self.warn_recording_limit)
            self.recording_warning_timer.start()

        self.recording_cap_timer = timer_factory(max_seconds, self.stop_recording_at_soft_cap)
        self.recording_cap_timer.start()

    def cancel_recording_limit_timers(self):
        for attr in ('recording_warning_timer', 'recording_cap_timer'):
            timer = getattr(self, attr, None)
            if timer is not None:
                try:
                    timer.cancel()
                except Exception:
                    logger.debug("Could not cancel %s", attr, exc_info=True)
            setattr(self, attr, None)

    def warn_recording_limit(self):
        if self.is_recording:
            self.show_tray_notification("Recording will stop at 10:00. Finish up soon.")

    def stop_recording_at_soft_cap(self):
        if not self.is_recording:
            return
        self.show_tray_notification("Recording stopped at the 10-minute limit.")
        controller = getattr(self, 'hotkey_controller', None)
        if controller is not None and hasattr(controller, 'force_stop'):
            session = controller.force_stop()
            if session is not None or not self.is_recording:
                return

        if self.is_recording:
            from types import SimpleNamespace

            self.finish_hotkey_recording(
                SimpleNamespace(duration_seconds=self.recording_max_seconds, locked=True)
            )

    def finish_hotkey_recording(self, session):
        """Stop recording and process the captured utterance."""
        if not self.is_recording:
            return
        self.cancel_recording_limit_timers()
        self.last_recording_duration_seconds = getattr(session, "duration_seconds", None)
        try:
            audio = self.audio_recorder.stop()
            logger.info(
                "Recording stopped after %.2fs%s",
                getattr(session, "duration_seconds", 0.0),
                " (lock mode)" if getattr(session, "locked", False) else "",
            )
        except Exception:
            self.is_recording = False
            self.emit_ui_callback('error_callback', "Could not stop recording")
            logger.exception("Could not stop recording")
            return
        self.emit_ui_callback(
            'recording_stopped_callback',
            float(getattr(session, "duration_seconds", 0.0) or 0.0),
        )

        threading.Thread(
            target=self.process_recorded_audio,
            args=(audio, True),
            daemon=True,
        ).start()

    def process_recorded_audio(self, audio, insert_text=True):
        try:
            self.emit_ui_callback('processing_started_callback')
            timings = {"record": float(getattr(self, 'last_recording_duration_seconds', None) or 0.0)}
            raw_text = self.transcribe_audio_to_text(audio, timings=timings)
            result = self.process_raw_transcript(
                raw_text,
                insert_text=insert_text,
                duration_seconds=getattr(self, 'last_recording_duration_seconds', None),
                timings=timings,
            )
            if result:
                logger.info("Converted: %s", result)
            self.emit_ui_callback('processing_finished_callback', result or "")
            return result
        except Exception as exc:
            logger.exception("Could not process recorded audio")
            self.emit_ui_callback('error_callback', str(exc) or type(exc).__name__)
            return None
        finally:
            self.is_recording = False
            self.recording_focus_token = None
            self.last_recording_duration_seconds = None
    
    def on_hotkey_press(self):
        """Handle hotkey press event"""
        if not self.is_recording:
            self.is_recording = True
            # Start recording in a separate thread
            threading.Thread(target=self.record_and_convert, daemon=True).start()
    
    def on_save_hotkey_press(self):
        """Handle save hotkey press event (F10) without typing into the active app."""
        if not self.is_recording:
            self.is_recording = True
            threading.Thread(target=self.record_and_save_to_history, daemon=True).start()
    
    def record_and_convert(self):
        """Record audio and convert to text"""
        try:
            result = self.speech_to_text()
            if result:
                logger.info("Converted: %s", result)
        finally:
            self.is_recording = False
    
    def record_and_save_to_history(self):
        """Record audio, convert to text, and keep it in local history only."""
        try:
            result = self.speech_to_text_for_saving()
            if result:
                logger.info("Saved to history without insertion: %s", result)
                self.show_minimal_save_feedback(result)
            else:
                logger.info("No speech detected for saving")
        finally:
            self.is_recording = False
    
    def speech_to_text_for_saving(self):
        """Convert speech to text for history-only saving."""
        try:
            timings = {}
            raw_text = self.transcribe_legacy_recording(timings=timings)
            return self.process_raw_transcript(raw_text, insert_text=False, timings=timings)
        except Exception:
            logger.exception("Error in local dictation for saving")
            return None
    

    

    
    def start_listening(self, icon=None, item=None):
        """Start the speech recognition service"""
        if not self.is_listening:
            self.is_listening = True
            self.hotkey_controller.start(keyboard)
            self.save_hotkey_handle = keyboard.add_hotkey(self.save_hotkey, self.on_save_hotkey_press)
            self.start_hotkey_watchdog()
            if self.icon:
                self.icon.title = "Speech-to-Text (Active)"
            logger.info(
                "VoiceTray is ready. Hold %s to record, tap it to lock, or use %s as an alternative. Press %s to record without inserting.",
                self.hotkey,
                self.alternate_hotkey,
                self.save_hotkey,
            )
    
    def stop_listening(self, icon=None, item=None):
        """Stop the speech recognition service"""
        if self.is_listening:
            self.is_listening = False
            self.stop_hotkey_watchdog()
            self.hotkey_controller.stop()
            try:
                if self.save_hotkey_handle is not None:
                    keyboard.remove_hotkey(self.save_hotkey_handle)
                    self.save_hotkey_handle = None
            except:
                pass
            if self.icon:
                self.icon.title = "Speech-to-Text (Inactive)"
            logger.info("Speech-to-text stopped")
    
    def quit_app(self, icon=None, item=None):
        """Quit the application"""
        self.stop_listening()
        self.running = False
    
    def show_minimal_save_feedback(self, text):
        """Report saved text through the app notification channel."""
        try:
            preview_text = text[:40] + "..." if len(text) > 40 else text
            self.show_tray_notification(f"Saved: {preview_text}")
        except Exception:
            logger.exception("Could not report save feedback")
    
    def open_app_folder(self, icon=None, item=None):
        """Open the application folder in file explorer"""
        try:
            # Get the directory where the script is located
            app_directory = os.path.dirname(os.path.abspath(__file__))
            
            # Open the folder in the default file manager
            if sys.platform == "win32":
                os.startfile(app_directory)
            elif sys.platform == "darwin":  # macOS
                os.system(f"open '{app_directory}'")
            else:  # Linux and other Unix-like systems
                os.system(f"xdg-open '{app_directory}'")
                
            logger.info("Opened application folder: %s", app_directory)
            
        except Exception as e:
            logger.exception("Could not open application folder")
    
    def show_instructions(self, icon=None, item=None):
        """Log configuration guidance until the Qt help surface lands."""
        instructions = """VoiceTray configuration files:

- config.json: hotkeys, startup, recording limits, dictation mode, profile, STT, and LLM settings.
- snippets.txt: text expansion shortcuts in trigger=expansion_text format.
- glossary.json: preferred terms, protected terms, and replacements.
- app_profiles.json: per-app mode/profile overrides.

These files can be edited in Settings or with a text editor while VoiceTray is stopped.
"""
        logger.info("VoiceTray instructions:\n%s", instructions)
    
    def create_menu(self):
        """Reserved for the dedicated Qt tray implementation."""
        return ()

    def start_second_launch_notification_watcher(self):
        threading.Thread(target=self.second_launch_notification_loop, daemon=True).start()

    def second_launch_notification_loop(self):
        from .single_instance import consume_existing_instance_notification, default_lock_path

        lock_path = default_lock_path()
        while self.running:
            payload = consume_existing_instance_notification(lock_path)
            if payload:
                message = payload.get("message", "VoiceTray is already running")
                self.show_tray_notification(str(message))
            time.sleep(0.5)

    def show_tray_notification(self, message):
        callback = getattr(self, "notification_callback", None)
        if callback is None:
            logger.info("Notification requested: %s", message)
            return
        try:
            callback(message)
        except Exception:
            logger.exception("Could not dispatch notification")
    
    def run(self):
        """Run the application"""
        self.start_second_launch_notification_watcher()
        
        logger.info("VoiceTray started - Expand your words, save your thoughts.")
        logger.info("Auto-starting speech recognition")
        logger.info("Press %s to record speech", self.hotkey)
        logger.info("Application is now running in the background")
        
        if getattr(self, 'auto_start_listening', True):
            self.start_listening()
        
        # Register cleanup function
        atexit.register(self.cleanup)
        
        while self.running:
            time.sleep(0.2)
    
    def cleanup(self):
        """Cleanup function called on exit"""
        self.stop_listening()

def main():
    """Main entry point"""
    try:
        from .logging_config import configure_logging

        configure_logging()

        # Hide console window after startup (Windows only)
        if sys.platform == "win32":
            import ctypes
            # Give user time to see startup messages
            threading.Timer(3.0, lambda: ctypes.windll.user32.ShowWindow(
                ctypes.windll.kernel32.GetConsoleWindow(), 0)).start()
        
        app = VoiceTrayApp()
        app.run()
    except KeyboardInterrupt:
        logger.info("Application interrupted by user")
    except Exception as e:
        logger.exception("Error starting application")
        # Don't wait for input in background mode
        sys.exit(1)

if __name__ == "__main__":
    main()
