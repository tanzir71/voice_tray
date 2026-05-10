import threading
import time
import speech_recognition as sr
import pystray
from pystray import MenuItem as item
from PIL import Image, ImageDraw
import keyboard
import pyautogui
import sys
import os
import atexit
import json
import vosk
import sounddevice as sd
import queue
import re
from difflib import SequenceMatcher
from datetime import datetime
import tkinter as tk
from tkinter import ttk, scrolledtext
import subprocess

from dictation import DictationConfig, DictationContext, DictationPipeline
from dictation.llm_local import LocalLLMConfig

class VoiceTrayApp:
    def __init__(self):
        self.recognizer = sr.Recognizer()
        self.microphone = sr.Microphone()
        self.is_listening = False
        self.is_recording = False
        self.hotkey = 'f9'  # Default hotkey - F9 key
        self.save_hotkey = 'f10'
        self.icon = None
        self.running = True
        self.last_recognized_text = ""
        
        # Initialize Vosk for offline recognition
        model_path = "models/vosk-model-small-en-us-0.15"
        if os.path.exists(model_path):
            self.vosk_model = vosk.Model(model_path)
            self.vosk_rec = vosk.KaldiRecognizer(self.vosk_model, 16000)
            self.audio_queue = queue.Queue()
            self.use_offline = True
            print("Offline speech recognition initialized")
        else:
            self.use_offline = False
            print("Vosk model not found, using online recognition")
            # Adjust for ambient noise for online recognition
            with self.microphone as source:
                self.recognizer.adjust_for_ambient_noise(source)
        
        # Store recent text for repetition detection
        self.recent_texts = []
        self.max_recent_texts = 5
        
        # Load settings from file
        self.load_settings()
        
        # Initialize text files
        self.init_text_files()
        
        # Load snippets from file
        self.load_snippets_from_file()

        self.load_app_profiles()
        self.init_dictation_pipeline()
        self.prompt_llm_setup_if_needed()
    
    def create_icon_image(self):
        """Create a simple icon for the system tray"""
        # Create a 64x64 image with a microphone-like icon
        image = Image.new('RGB', (64, 64), color='white')
        draw = ImageDraw.Draw(image)
        
        # Draw a simple microphone icon
        # Microphone body
        draw.rectangle([20, 15, 44, 35], fill='black')
        # Microphone stand
        draw.rectangle([30, 35, 34, 50], fill='black')
        # Base
        draw.rectangle([25, 50, 39, 55], fill='black')
        
        return image
    
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
    
    def process_text(self, raw_text):
        """Process text to remove repetitions and apply grammar checking"""
        if not raw_text:
            return None
        
        # Check if too similar to recent texts
        if self.check_similarity_with_recent(raw_text):
            print("Skipping similar text to avoid repetition")
            return None

        context = self.select_dictation_context()
        final_text = self.dictation_pipeline.process_transcript(raw_text, context)
        final_text = self.expand_snippets(final_text)
        
        # Store in recent texts for future comparison
        self.recent_texts.append(final_text)
        if len(self.recent_texts) > self.max_recent_texts:
            self.recent_texts.pop(0)
        
        return final_text
    
    def load_settings(self):
        """Load settings from settings.txt file"""
        try:
            self.auto_start_listening = True
            self.notification_duration = 3
            self.dictation_mode = 'balanced'
            self.format_profile = 'general'
            self.glossary_path = os.path.join(os.path.dirname(__file__), 'glossary.json')
            self.app_profiles_path = os.path.join(os.path.dirname(__file__), 'app_profiles.json')

            self.llm_enabled = False
            self.llm_model_path = os.path.join(os.path.dirname(__file__), 'models', 'llm', 'model.gguf')
            self.llm_n_ctx = 2048
            self.llm_max_tokens = 256
            self.llm_temperature = 0.05
            self.llm_top_p = 0.9
            self.llm_threads = None
            self.llm_gpu_layers = None

            settings_path = os.path.join(os.path.dirname(__file__), 'settings.txt')
            if os.path.exists(settings_path):
                with open(settings_path, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith('#') and '=' in line:
                            key, value = line.split('=', 1)
                            key = key.strip()
                            value = value.strip()
                            
                            if key == 'speech_hotkey':
                                self.hotkey = value
                            elif key == 'save_hotkey':
                                self.save_hotkey = value
                            elif key == 'auto_start_listening':
                                self.auto_start_listening = value.lower() == 'true'
                            elif key == 'notification_duration':
                                self.notification_duration = int(value)
                            elif key == 'dictation_mode':
                                self.dictation_mode = value.lower()
                            elif key == 'format_profile':
                                self.format_profile = value.lower()
                            elif key == 'glossary_path':
                                self.glossary_path = value
                            elif key == 'app_profiles_path':
                                self.app_profiles_path = value
                            elif key == 'llm_enabled':
                                self.llm_enabled = value.lower() == 'true'
                            elif key == 'llm_model_path':
                                self.llm_model_path = value
                            elif key == 'llm_n_ctx':
                                self.llm_n_ctx = int(value)
                            elif key == 'llm_max_tokens':
                                self.llm_max_tokens = int(value)
                            elif key == 'llm_temperature':
                                self.llm_temperature = float(value)
                            elif key == 'llm_top_p':
                                self.llm_top_p = float(value)
                            elif key == 'llm_threads':
                                self.llm_threads = int(value)
                            elif key == 'llm_gpu_layers':
                                self.llm_gpu_layers = int(value)
                                
            print(f"Settings loaded: speech_hotkey={self.hotkey}, save_hotkey={self.save_hotkey}")
        except Exception as e:
            print(f"Error loading settings: {e}")
            # Use defaults if settings file doesn't exist or has errors
            self.auto_start_listening = True
            self.notification_duration = 3
    
    def init_text_files(self):
        """Initialize text files if they don't exist"""
        try:
            # Ensure saved_texts.txt exists
            saved_texts_path = os.path.join(os.path.dirname(__file__), 'saved_texts.txt')
            if not os.path.exists(saved_texts_path):
                with open(saved_texts_path, 'w', encoding='utf-8') as f:
                    f.write("# SAVED TEXTS (entries appear below this line):\n\n")
            
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
                    
            print("Text files initialized successfully")
        except Exception as e:
            print(f"Error initializing text files: {e}")

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

    def launch_settings_gui(self, initial_tab=None):
        try:
            gui_path = os.path.join(os.path.dirname(__file__), 'voicetray_settings_gui.py')
            if not os.path.exists(gui_path):
                return False
            args = [sys.executable, gui_path]
            if initial_tab:
                args.extend(['--tab', initial_tab])

            if sys.platform == 'win32':
                DETACHED_PROCESS = 0x00000008
                CREATE_NEW_PROCESS_GROUP = 0x00000200
                subprocess.Popen(
                    args,
                    cwd=os.path.dirname(__file__),
                    creationflags=DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP,
                )
            else:
                subprocess.Popen(args, cwd=os.path.dirname(__file__))
            return True
        except Exception as e:
            print(f"Could not launch settings GUI: {e}")
            return False

    def prompt_llm_setup_if_needed(self):
        ok, reason = self.llm_setup_status()
        if ok:
            return
        try:
            threading.Timer(1.0, lambda: self.launch_settings_gui('llm')).start()
        except Exception:
            pass

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
            print(f"Error loading app profiles: {e}")

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
    
    def save_text_to_file(self, text):
        """Save recognized text to saved_texts.txt file"""
        try:
            saved_texts_path = os.path.join(os.path.dirname(__file__), 'saved_texts.txt')
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            
            with open(saved_texts_path, 'a', encoding='utf-8') as f:
                f.write(f"[{timestamp}] speech_recognition: {text}\n")
            
            print(f"Text saved to file: {text[:50]}...")
            self.show_minimal_save_feedback(text)
            return True
        except Exception as e:
            print(f"Error saving to file: {e}")
            return False
    
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
            
            print(f"Loaded {len(self.snippets)} snippets from file")
            
        except Exception as e:
            print(f"Error loading snippets from file: {e}")
    
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
            print(f"Error expanding snippets: {e}")
            return text
    

    

     
    def speech_to_text(self):
        """Convert speech to text and insert into active field"""
        if self.use_offline:
            return self.speech_to_text_offline()
        else:
            return self.speech_to_text_online()
    
    def speech_to_text_offline(self):
        """Convert speech to text using Vosk offline recognition"""
        try:
            # Record audio for 3 seconds
            duration = 3
            sample_rate = 16000
            
            print("Listening...")
            audio_data = sd.rec(int(duration * sample_rate), samplerate=sample_rate, channels=1, dtype='int16')
            sd.wait()  # Wait until recording is finished
            
            # Convert to bytes
            audio_bytes = audio_data.tobytes()
            
            # Process with Vosk
            if self.vosk_rec.AcceptWaveform(audio_bytes):
                result = json.loads(self.vosk_rec.Result())
                raw_text = result.get('text', '').strip()
            else:
                result = json.loads(self.vosk_rec.PartialResult())
                raw_text = result.get('partial', '').strip()
            
            if raw_text:
                # Process text to remove repetitions and apply grammar checking
                processed_text = self.process_text(raw_text)
                if processed_text:
                    # Store the last recognized text
                    self.last_recognized_text = processed_text
                    # Insert text at current cursor position
                    pyautogui.typewrite(processed_text)
                    print(f"Original: {raw_text}")
                    print(f"Processed: {processed_text}")
                    return processed_text
        
        except Exception as e:
            print(f"Offline recognition error: {e}")
        
        return None
    
    def speech_to_text_online(self):
        """Convert speech to text using Google's online service"""
        try:
            with self.microphone as source:
                # Listen for audio with timeout
                audio = self.recognizer.listen(source, timeout=1, phrase_time_limit=5)
            
            # Recognize speech using Google's service
            raw_text = self.recognizer.recognize_google(audio)
            
            if raw_text:
                # Process text to remove repetitions and apply grammar checking
                processed_text = self.process_text(raw_text)
                if processed_text:
                    # Store the last recognized text
                    self.last_recognized_text = processed_text
                    # Insert text at current cursor position
                    pyautogui.typewrite(processed_text)
                    print(f"Original: {raw_text}")
                    print(f"Processed: {processed_text}")
                    return processed_text
        
        except sr.WaitTimeoutError:
            pass  # No speech detected
        except sr.UnknownValueError:
            pass  # Could not understand audio
        except sr.RequestError as e:
            print(f"Error with speech recognition service: {e}")
        except Exception as e:
            print(f"Unexpected error: {e}")
        
        return None
    
    def on_hotkey_press(self):
        """Handle hotkey press event"""
        if not self.is_recording:
            self.is_recording = True
            # Start recording in a separate thread
            threading.Thread(target=self.record_and_convert, daemon=True).start()
    
    def on_save_hotkey_press(self):
        """Handle save hotkey press event (F10) - Record and save directly to text file"""
        if not self.is_recording:
            self.is_recording = True
            # Start recording and saving in a separate thread
            threading.Thread(target=self.record_and_save_to_file, daemon=True).start()
    
    def record_and_convert(self):
        """Record audio and convert to text"""
        try:
            result = self.speech_to_text()
            if result:
                print(f"Converted: {result}")
        finally:
            self.is_recording = False
    
    def record_and_save_to_file(self):
        """Record audio, convert to text, and save directly to text file"""
        try:
            result = self.speech_to_text_for_saving()
            if result:
                success = self.save_text_to_file(result)
                if success:
                    print(f"✓ Saved to file: {result}")
                else:
                    print("✗ Failed to save text to file")
            else:
                print("No speech detected for saving")
        finally:
            self.is_recording = False
    
    def speech_to_text_for_saving(self):
        """Convert speech to text for saving (without typing to screen)"""
        try:
            if self.use_offline and self.vosk_model:
                return self.speech_to_text_offline_for_saving()
            else:
                return self.speech_to_text_online_for_saving()
        except Exception as e:
            print(f"Error in speech recognition for saving: {e}")
            return None
    
    def speech_to_text_offline_for_saving(self):
        """Convert speech to text using offline Vosk (for saving only)"""
        try:
            # Record audio for 3 seconds
            duration = 3
            sample_rate = 16000
            audio_data = sd.rec(int(duration * sample_rate), samplerate=sample_rate, channels=1, dtype='int16')
            sd.wait()  # Wait for recording to complete
            
            # Convert to bytes
            audio_bytes = audio_data.tobytes()
            
            # Process with Vosk
            if self.vosk_rec.AcceptWaveform(audio_bytes):
                result = json.loads(self.vosk_rec.Result())
                raw_text = result.get('text', '').strip()
            else:
                result = json.loads(self.vosk_rec.FinalResult())
                raw_text = result.get('text', '').strip()
            
            if raw_text:
                # Process text to remove repetitions and apply grammar checking
                processed_text = self.process_text(raw_text)
                return processed_text
        
        except Exception as e:
            print(f"Error in offline speech recognition for saving: {e}")
        
        return None
    
    def speech_to_text_online_for_saving(self):
        """Convert speech to text using Google's online service (for saving only)"""
        try:
            with self.microphone as source:
                # Listen for audio with timeout
                audio = self.recognizer.listen(source, timeout=1, phrase_time_limit=5)
            
            # Recognize speech using Google's service
            raw_text = self.recognizer.recognize_google(audio)
            
            if raw_text:
                # Process text to remove repetitions and apply grammar checking
                processed_text = self.process_text(raw_text)
                return processed_text
        
        except sr.WaitTimeoutError:
            pass  # No speech detected
        except sr.UnknownValueError:
            pass  # Could not understand audio
        except sr.RequestError as e:
            print(f"Error with speech recognition service: {e}")
        except Exception as e:
            print(f"Unexpected error: {e}")
        
        return None
    

    

    
    def start_listening(self, icon=None, item=None):
        """Start the speech recognition service"""
        if not self.is_listening:
            self.is_listening = True
            # Register global hotkeys
            keyboard.add_hotkey(self.hotkey, self.on_hotkey_press)
            keyboard.add_hotkey(self.save_hotkey, self.on_save_hotkey_press)
            if self.icon:
                self.icon.title = "Speech-to-Text (Active)"
            print(f"VoiceTray is ready. Press {self.hotkey} to record and type, {self.save_hotkey} to record and save.")
    
    def stop_listening(self, icon=None, item=None):
        """Stop the speech recognition service"""
        if self.is_listening:
            self.is_listening = False
            # Unregister hotkeys
            try:
                keyboard.remove_hotkey(self.hotkey)
                keyboard.remove_hotkey(self.save_hotkey)
            except:
                pass
            if self.icon:
                self.icon.title = "Speech-to-Text (Inactive)"
            print("Speech-to-text stopped.")
    
    def quit_app(self, icon=None, item=None):
        """Quit the application"""
        self.stop_listening()
        self.running = False
        if self.icon:
            self.icon.stop()
    
    def show_minimal_save_feedback(self, text):
        """Show minimal GUI feedback when text is saved"""
        try:
            # Create a simple notification window
            feedback_window = tk.Tk()
            feedback_window.title("Text Saved")
            feedback_window.resizable(False, False)
            
            # Set window size
            width = 300
            height = 100
            
            # Center the window on screen
            feedback_window.withdraw()
            feedback_window.update_idletasks()
            
            screen_width = feedback_window.winfo_screenwidth()
            screen_height = feedback_window.winfo_screenheight()
            
            x = (screen_width - width) // 2
            y = (screen_height - height) // 2
            
            feedback_window.geometry(f"{width}x{height}+{x}+{y}")
            feedback_window.deiconify()
            
            # Create label with saved text preview
            preview_text = text[:40] + "..." if len(text) > 40 else text
            label = tk.Label(
                feedback_window,
                text=f"✓ Saved: {preview_text}",
                font=('Arial', 10),
                wraplength=280,
                justify='center'
            )
            label.pack(expand=True, pady=10)
            
            # Auto-close after 2 seconds
            feedback_window.after(2000, feedback_window.destroy)
            
            # Make window stay on top briefly
            feedback_window.attributes('-topmost', True)
            feedback_window.focus_force()
            
            # Start the GUI event loop
            feedback_window.mainloop()
            
        except Exception as e:
            print(f"Could not show save feedback: {e}")
    
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
                
            print(f"Opened application folder: {app_directory}")
            
        except Exception as e:
            print(f"Could not open application folder: {e}")
    
    def show_instructions(self, icon=None, item=None):
        """Show instructions for configuring VoiceTray"""
        instructions = """VoiceTray Configuration Files:

• settings.txt - Configure hotkeys and startup options
  - speech_hotkey: Key to record and type (default: f9)
  - save_hotkey: Key to record and save (default: f10)
  - auto_start_listening: Auto-start on launch (default: true)
  - notification_duration: Notification time in seconds (default: 3)

  Dictation intelligence:
  - dictation_mode: raw | balanced | aggressive (default: balanced)
  - format_profile: general | email | chat | notes | code/comments (default: general)
  - glossary_path: Path to glossary.json (default: glossary.json)
  - app_profiles_path: Path to app_profiles.json (default: app_profiles.json)
  - llm_enabled: true/false (default: false)
  - llm_model_path: Path to local GGUF model
  - llm_n_ctx: Context size (default: 2048)
  - llm_max_tokens: Output limit (default: 256)
  - llm_temperature: Keep near zero (default: 0.05)
  - llm_top_p: Sampling control (default: 0.9)
  - llm_threads: Optional int
  - llm_gpu_layers: Optional int

• snippets.txt - Add text expansion shortcuts
  - Format: trigger=expansion_text
  - Example: addr=123 Main Street, City, State

• glossary.json - Personal dictionary and protected terms
  - user_terms: preferred terms (kept stable)
  - protected_terms: never rewrite
  - replacements: common misrecognitions to replace

• app_profiles.json - Per-app mode/profile overrides
  - Example entry: {"match": "Visual Studio Code", "profile": "code/comments", "mode": "raw"}

• saved_texts.txt - View your saved recordings
  - Contains timestamped speech recordings from F10
  - Format: [timestamp] source: text

Edit these files with any text editor to customize VoiceTray.

IMPORTANT: You must restart the application after making changes to any configuration files (settings.txt, snippets.txt) for the new changes to take effect."""
        
        # Create a proper instructions window
        try:
            # Create the main window
            window = tk.Tk()
            window.title("VoiceTray Instructions")
            window.resizable(True, True)
            
            # Set window size
            width = 600
            height = 500
            
            # Center the window on screen
            window.withdraw()  # Hide window while calculating position
            window.update_idletasks()  # Ensure window is fully initialized
            
            # Get screen dimensions
            screen_width = window.winfo_screenwidth()
            screen_height = window.winfo_screenheight()
            
            # Calculate center position
            x = (screen_width - width) // 2
            y = (screen_height - height) // 2
            
            # Set geometry and show window
            window.geometry(f"{width}x{height}+{x}+{y}")
            window.deiconify()  # Show the window
            
            # Create text area with scrollbar
            text_area = scrolledtext.ScrolledText(
                window, 
                wrap=tk.WORD, 
                width=70, 
                height=25,
                font=('Consolas', 10),
                padx=10,
                pady=10
            )
            text_area.pack(expand=True, fill='both', padx=10, pady=(10, 5))
            text_area.insert('1.0', instructions)
            text_area.config(state='disabled')  # Make it read-only
            
            # Create button frame
            button_frame = tk.Frame(window)
            button_frame.pack(pady=(5, 10))
            
            # Create OK button
            ok_button = tk.Button(
                button_frame, 
                text="OK", 
                command=window.destroy,
                width=10,
                font=('Arial', 10)
            )
            ok_button.pack(side=tk.RIGHT, padx=5)
            
            # Handle window close button
            window.protocol("WM_DELETE_WINDOW", window.destroy)
            
            # Make window modal and bring to front
            window.lift()
            window.attributes('-topmost', True)
            window.focus_force()
            
            # Start the GUI event loop
            window.mainloop()
            
        except Exception as e:
            # Fallback to console output
            print(f"Could not show GUI instructions: {e}")
            print(instructions)
    
    def create_menu(self):
        """Create the system tray menu"""
        return pystray.Menu(
            item('Start Listening', self.start_listening, enabled=lambda _item: not self.is_listening),
            item('Stop Listening', self.stop_listening, enabled=lambda _item: self.is_listening),
            pystray.Menu.SEPARATOR,
            item('Settings', lambda icon, item: self.launch_settings_gui(None), default=True),
            item('LLM Setup', lambda icon, item: self.launch_settings_gui('llm')),
            item('Instructions', lambda icon, item: self.launch_settings_gui('help')),
            pystray.Menu.SEPARATOR,
            item('Open Folder', self.open_app_folder),
            item('Quit', self.quit_app)
        )
    
    def run(self):
        """Run the application"""
        # Create system tray icon
        icon_image = self.create_icon_image()
        self.icon = pystray.Icon(
            "SpeechToText",
            icon_image,
            "Speech-to-Text (Inactive)",
            self.create_menu()
        )
        
        print("VoiceTray started - Expand your words, save your thoughts.")
        print(f"Auto-starting speech recognition...")
        print(f"Press {self.hotkey} to record speech.")
        print("Application is now running in the background. Close this window safely.")
        
        if getattr(self, 'auto_start_listening', True):
            self.start_listening()
        
        # Register cleanup function
        atexit.register(self.cleanup)
        
        # Start the system tray icon (this blocks until quit)
        self.icon.run()
    
    def cleanup(self):
        """Cleanup function called on exit"""
        self.stop_listening()
        if self.icon:
            self.icon.stop()

def main():
    """Main entry point"""
    try:
        # Hide console window after startup (Windows only)
        if sys.platform == "win32":
            import ctypes
            # Give user time to see startup messages
            threading.Timer(3.0, lambda: ctypes.windll.user32.ShowWindow(
                ctypes.windll.kernel32.GetConsoleWindow(), 0)).start()
        
        app = VoiceTrayApp()
        app.run()
    except KeyboardInterrupt:
        print("\nApplication interrupted by user.")
    except Exception as e:
        print(f"Error starting application: {e}")
        # Don't wait for input in background mode
        sys.exit(1)

if __name__ == "__main__":
    main()
