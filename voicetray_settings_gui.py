from __future__ import annotations

import os
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import urllib.request

from voicetray_config import load_settings, write_setting


RECOMMENDED_MODELS = [
    {
        "label": "Qwen2.5 0.5B Instruct (Q4_K_M, ~0.40GB)",
        "url": "https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct-GGUF/resolve/main/qwen2.5-0.5b-instruct-q4_k_m.gguf",
    },
    {
        "label": "Qwen2.5 0.5B Instruct (Q5_K_M, ~0.42GB)",
        "url": "https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct-GGUF/resolve/main/qwen2.5-0.5b-instruct-q5_k_m.gguf",
    },
]


class SettingsGUI:
    def __init__(self, settings_path: str, initial_tab: str | None = None):
        self.settings_path = settings_path
        self.settings_dir = os.path.dirname(os.path.abspath(settings_path))
        self.settings = load_settings(settings_path)

        self.root = tk.Tk()
        self.root.title("VoiceTray Settings")
        self.root.resizable(True, True)
        self.root.geometry("720x520")

        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(expand=True, fill="both")

        self._build_general_tab()
        self._build_dictation_tab()
        self._build_llm_tab()
        self._build_help_tab()
        self._build_status_bar()
        self._build_bottom_buttons()

        if initial_tab == "llm":
            self.notebook.select(self.llm_tab)
        elif initial_tab == "dictation":
            self.notebook.select(self.dictation_tab)
        elif initial_tab == "general":
            self.notebook.select(self.general_tab)
        elif initial_tab == "help":
            self.notebook.select(self.help_tab)

        self.refresh_status()

    def ui(self, fn):
        try:
            self.root.after(0, fn)
        except Exception:
            pass

    def _build_general_tab(self):
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text="General")

        pad = {"padx": 12, "pady": 8}
        row = 0

        ttk.Label(tab, text="Speech hotkey (dictate + type)").grid(row=row, column=0, sticky="w", **pad)
        self.speech_hotkey_var = tk.StringVar(value=self.settings.speech_hotkey)
        ttk.Entry(tab, textvariable=self.speech_hotkey_var).grid(row=row, column=1, sticky="ew", **pad)
        row += 1

        ttk.Label(tab, text="Save hotkey (dictate + save)").grid(row=row, column=0, sticky="w", **pad)
        self.save_hotkey_var = tk.StringVar(value=self.settings.save_hotkey)
        ttk.Entry(tab, textvariable=self.save_hotkey_var).grid(row=row, column=1, sticky="ew", **pad)
        row += 1

        self.auto_listen_var = tk.BooleanVar(value=bool(self.settings.auto_start_listening))
        ttk.Checkbutton(tab, text="Auto-start listening on launch", variable=self.auto_listen_var).grid(
            row=row, column=0, columnspan=2, sticky="w", **pad
        )
        row += 1

        ttk.Label(tab, text="Notification duration (seconds)").grid(row=row, column=0, sticky="w", **pad)
        self.notification_seconds_var = tk.StringVar(value=str(self.settings.notification_duration))
        ttk.Entry(tab, textvariable=self.notification_seconds_var).grid(row=row, column=1, sticky="ew", **pad)
        row += 1

        btns = ttk.Frame(tab)
        btns.grid(row=row, column=0, columnspan=2, sticky="ew", **pad)
        ttk.Button(btns, text="Save", command=self.save_general).pack(side="left")
        ttk.Button(btns, text="Open app folder", command=self.open_app_folder).pack(side="left", padx=8)

        tab.columnconfigure(1, weight=1)
        self.general_tab = tab

    def _build_dictation_tab(self):
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text="Dictation")

        pad = {"padx": 12, "pady": 8}
        row = 0

        ttk.Label(tab, text="Cleanup mode").grid(row=row, column=0, sticky="w", **pad)
        self.mode_var = tk.StringVar(value=self.settings.dictation_mode)
        self.mode_combo = ttk.Combobox(tab, textvariable=self.mode_var, state="readonly")
        self.mode_combo["values"] = ("raw", "balanced", "aggressive")
        self.mode_combo.grid(row=row, column=1, sticky="ew", **pad)
        row += 1

        ttk.Label(tab, text="Formatting profile").grid(row=row, column=0, sticky="w", **pad)
        self.profile_var = tk.StringVar(value=self.settings.format_profile)
        self.profile_combo = ttk.Combobox(tab, textvariable=self.profile_var, state="readonly")
        self.profile_combo["values"] = ("general", "email", "chat", "notes", "code/comments")
        self.profile_combo.grid(row=row, column=1, sticky="ew", **pad)
        row += 1

        ttk.Label(tab, text="Glossary file").grid(row=row, column=0, sticky="w", **pad)
        self.glossary_var = tk.StringVar(value=self.settings.glossary_path)
        glossary_entry = ttk.Entry(tab, textvariable=self.glossary_var)
        glossary_entry.grid(row=row, column=1, sticky="ew", **pad)
        ttk.Button(tab, text="Browse", command=self.browse_glossary).grid(row=row, column=2, sticky="e", **pad)
        row += 1

        ttk.Label(tab, text="Per-app profiles").grid(row=row, column=0, sticky="w", **pad)
        self.app_profiles_var = tk.StringVar(value=self.settings.app_profiles_path)
        app_entry = ttk.Entry(tab, textvariable=self.app_profiles_var)
        app_entry.grid(row=row, column=1, sticky="ew", **pad)
        ttk.Button(tab, text="Browse", command=self.browse_app_profiles).grid(row=row, column=2, sticky="e", **pad)
        row += 1

        btns = ttk.Frame(tab)
        btns.grid(row=row, column=0, columnspan=3, sticky="ew", **pad)
        ttk.Button(btns, text="Save", command=self.save_dictation).pack(side="left")
        ttk.Button(btns, text="Open app folder", command=self.open_app_folder).pack(side="left", padx=8)

        tab.columnconfigure(1, weight=1)
        self.dictation_tab = tab

    def _build_llm_tab(self):
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text="Local LLM")

        pad = {"padx": 12, "pady": 8}
        row = 0

        self.llm_enabled_var = tk.BooleanVar(value=bool(self.settings.llm_enabled))
        enabled_chk = ttk.Checkbutton(tab, text="Enable local LLM cleanup", variable=self.llm_enabled_var)
        enabled_chk.grid(row=row, column=0, columnspan=3, sticky="w", **pad)
        row += 1

        ttk.Label(tab, text="GGUF model path").grid(row=row, column=0, sticky="w", **pad)
        self.model_path_var = tk.StringVar(value=self.settings.llm_model_path)
        model_entry = ttk.Entry(tab, textvariable=self.model_path_var)
        model_entry.grid(row=row, column=1, sticky="ew", **pad)
        ttk.Button(tab, text="Browse", command=self.browse_model).grid(row=row, column=2, sticky="e", **pad)
        row += 1

        ttk.Label(tab, text="Download model").grid(row=row, column=0, sticky="w", **pad)
        self.recommended_model_var = tk.StringVar(value=RECOMMENDED_MODELS[0]["label"])
        self.recommended_combo = ttk.Combobox(tab, textvariable=self.recommended_model_var, state="readonly")
        self.recommended_combo["values"] = tuple([m["label"] for m in RECOMMENDED_MODELS])
        self.recommended_combo.grid(row=row, column=1, sticky="ew", **pad)
        ttk.Button(tab, text="Download", command=self.download_recommended_model).grid(row=row, column=2, sticky="e", **pad)
        row += 1

        self.download_progress_var = tk.DoubleVar(value=0.0)
        self.download_progress = ttk.Progressbar(tab, variable=self.download_progress_var, maximum=100.0)
        self.download_progress.grid(row=row, column=1, sticky="ew", **pad)
        ttk.Button(tab, text="Open model folder", command=self.open_model_folder).grid(row=row, column=2, sticky="e", **pad)
        row += 1

        ttk.Label(tab, text="Context (n_ctx)").grid(row=row, column=0, sticky="w", **pad)
        self.n_ctx_var = tk.StringVar(value=str(self.settings.llm_n_ctx))
        ttk.Entry(tab, textvariable=self.n_ctx_var).grid(row=row, column=1, sticky="ew", **pad)
        row += 1

        ttk.Label(tab, text="Max output tokens").grid(row=row, column=0, sticky="w", **pad)
        self.max_tokens_var = tk.StringVar(value=str(self.settings.llm_max_tokens))
        ttk.Entry(tab, textvariable=self.max_tokens_var).grid(row=row, column=1, sticky="ew", **pad)
        row += 1

        ttk.Label(tab, text="Temperature").grid(row=row, column=0, sticky="w", **pad)
        self.temp_var = tk.StringVar(value=str(self.settings.llm_temperature))
        ttk.Entry(tab, textvariable=self.temp_var).grid(row=row, column=1, sticky="ew", **pad)
        row += 1

        install_frame = ttk.Frame(tab)
        install_frame.grid(row=row, column=0, columnspan=3, sticky="ew", **pad)
        ttk.Button(install_frame, text="Install LLM runtime", command=self.install_runtime).pack(side="left")
        ttk.Button(install_frame, text="Save", command=self.save_llm).pack(side="left", padx=8)
        ttk.Button(install_frame, text="Refresh status", command=self.refresh_status).pack(side="left")
        row += 1

        self.output = tk.Text(tab, height=10, wrap="word")
        self.output.grid(row=row, column=0, columnspan=3, sticky="nsew", **pad)
        self.output.configure(state="disabled")
        row += 1

        tab.columnconfigure(1, weight=1)
        tab.rowconfigure(row - 1, weight=1)
        self.llm_tab = tab

    def _build_help_tab(self):
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text="Help")

        pad = {"padx": 12, "pady": 10}
        text = tk.Text(tab, height=18, wrap="word")
        text.pack(expand=True, fill="both", padx=12, pady=12)
        text.insert(
            "1.0",
            "VoiceTray quick help\n\n"
            "Hotkeys\n"
            "- Speech hotkey: records and types into the active app\n"
            "- Save hotkey: records and saves to saved_texts.txt\n\n"
            "Local LLM cleanup (optional)\n"
            "- Use the Local LLM tab to install the runtime and download a model into models/llm/\n"
            "- Keep temperature near zero for conservative cleanup\n"
            "- Restart VoiceTray after saving settings\n\n"
            "Files\n"
            "- settings.txt: app settings\n"
            "- snippets.txt: snippet expansion\n"
            "- glossary.json: protected terms + replacements\n"
            "- app_profiles.json: per-app cleanup/profile overrides\n",
        )
        text.configure(state="disabled")
        self.help_tab = tab

    def _build_status_bar(self):
        self.status_var = tk.StringVar(value="")
        bar = ttk.Label(self.root, textvariable=self.status_var, anchor="w")
        bar.pack(fill="x", padx=10, pady=(0, 8))

    def _build_bottom_buttons(self):
        frame = ttk.Frame(self.root)
        frame.pack(fill="x", padx=10, pady=(0, 10))
        ttk.Button(frame, text="Close", command=self.root.destroy).pack(side="right")

    def log(self, msg: str):
        if threading.current_thread() is not threading.main_thread():
            self.ui(lambda: self.log(msg))
            return
        self.output.configure(state="normal")
        self.output.insert("end", msg + "\n")
        self.output.see("end")
        self.output.configure(state="disabled")

    def refresh_status(self):
        enabled = bool(self.llm_enabled_var.get())
        model_path = self._resolve_path(self.model_path_var.get())
        model_ok = bool(model_path) and os.path.exists(model_path)
        runtime_ok = False
        try:
            import llama_cpp  # noqa: F401

            runtime_ok = True
        except Exception:
            runtime_ok = False

        if not enabled:
            self.status_var.set("Local LLM: disabled")
        else:
            parts = []
            parts.append("runtime OK" if runtime_ok else "runtime missing")
            parts.append("model OK" if model_ok else "model missing")
            self.status_var.set("Local LLM: enabled (" + ", ".join(parts) + ")")

    def _resolve_path(self, p: str) -> str:
        p = (p or "").strip()
        if not p:
            return ""
        if os.path.isabs(p):
            return p
        return os.path.join(self.settings_dir, p)

    def open_app_folder(self):
        try:
            if sys.platform == "win32":
                os.startfile(self.settings_dir)
            elif sys.platform == "darwin":
                subprocess.Popen(["open", self.settings_dir])
            else:
                subprocess.Popen(["xdg-open", self.settings_dir])
        except Exception:
            pass

    def browse_model(self):
        path = filedialog.askopenfilename(
            title="Select a GGUF model",
            filetypes=[("GGUF model", "*.gguf"), ("All files", "*")],
        )
        if path:
            self.model_path_var.set(path)
            self.refresh_status()

    def open_model_folder(self):
        model_path = self._resolve_path(self.model_path_var.get())
        folder = os.path.dirname(model_path) if model_path else os.path.join(self.settings_dir, "models", "llm")
        try:
            os.makedirs(folder, exist_ok=True)
        except Exception:
            pass
        try:
            if sys.platform == "win32":
                os.startfile(folder)
            elif sys.platform == "darwin":
                subprocess.Popen(["open", folder])
            else:
                subprocess.Popen(["xdg-open", folder])
        except Exception:
            pass

    def browse_glossary(self):
        path = filedialog.askopenfilename(
            title="Select glossary.json",
            filetypes=[("JSON", "*.json"), ("All files", "*")],
        )
        if path:
            self.glossary_var.set(path)

    def browse_app_profiles(self):
        path = filedialog.askopenfilename(
            title="Select app_profiles.json",
            filetypes=[("JSON", "*.json"), ("All files", "*")],
        )
        if path:
            self.app_profiles_var.set(path)

    def save_general(self):
        speech_hotkey = (self.speech_hotkey_var.get() or "").strip()
        save_hotkey = (self.save_hotkey_var.get() or "").strip()

        if not speech_hotkey or not save_hotkey:
            messagebox.showerror("Invalid hotkeys", "Hotkeys cannot be empty.")
            return

        write_setting(self.settings_path, "speech_hotkey", speech_hotkey)
        write_setting(self.settings_path, "save_hotkey", save_hotkey)
        write_setting(self.settings_path, "auto_start_listening", "true" if self.auto_listen_var.get() else "false")
        write_setting(self.settings_path, "notification_duration", self.notification_seconds_var.get())
        self.settings = load_settings(self.settings_path)
        self.log("Saved general settings. Restart VoiceTray to apply.")

    def save_dictation(self):
        write_setting(self.settings_path, "dictation_mode", self.mode_var.get())
        write_setting(self.settings_path, "format_profile", self.profile_var.get())
        write_setting(self.settings_path, "glossary_path", self.glossary_var.get())
        write_setting(self.settings_path, "app_profiles_path", self.app_profiles_var.get())
        self.settings = load_settings(self.settings_path)
        self.log("Saved dictation settings. Restart VoiceTray to apply.")

    def save_llm(self):
        write_setting(self.settings_path, "llm_enabled", "true" if self.llm_enabled_var.get() else "false")
        write_setting(self.settings_path, "llm_model_path", self.model_path_var.get())
        write_setting(self.settings_path, "llm_n_ctx", self.n_ctx_var.get())
        write_setting(self.settings_path, "llm_max_tokens", self.max_tokens_var.get())
        write_setting(self.settings_path, "llm_temperature", self.temp_var.get())
        self.settings = load_settings(self.settings_path)
        self.log("Saved local LLM settings. Restart VoiceTray to apply.")
        self.refresh_status()

    def _selected_model_url(self) -> str:
        label = self.recommended_model_var.get()
        for m in RECOMMENDED_MODELS:
            if m["label"] == label:
                return m["url"]
        return RECOMMENDED_MODELS[0]["url"]

    def download_recommended_model(self):
        url = self._selected_model_url()
        raw_path = (self.model_path_var.get() or "").strip()
        if not raw_path:
            raw_path = "models/llm/model.gguf"
            self.model_path_var.set(raw_path)

        dest = self._resolve_path(raw_path)
        if not dest.lower().endswith(".gguf"):
            dest = os.path.join(dest, "model.gguf")

        if os.path.exists(dest):
            overwrite = messagebox.askyesno("Model exists", "A model file already exists at the target path. Overwrite it?")
            if not overwrite:
                return

        dest_dir = os.path.dirname(dest)
        try:
            os.makedirs(dest_dir, exist_ok=True)
        except Exception as e:
            messagebox.showerror("Download failed", f"Could not create folder:\n{dest_dir}\n\n{type(e).__name__}")
            return

        self.download_progress_var.set(0.0)
        self.log(f"Downloading model to:\n{dest}")
        self.log(f"URL:\n{url}")

        def set_progress(pct: float):
            try:
                self.download_progress_var.set(pct)
            except Exception:
                pass

        def worker():
            part_path = dest + ".part"
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "VoiceTray/1.0"})
                with urllib.request.urlopen(req, timeout=60) as resp:
                    total = resp.headers.get("Content-Length")
                    total_bytes = int(total) if total and total.isdigit() else None
                    downloaded = 0

                    with open(part_path, "wb") as f:
                        while True:
                            chunk = resp.read(1024 * 1024)
                            if not chunk:
                                break
                            f.write(chunk)
                            downloaded += len(chunk)
                            if total_bytes:
                                pct = (downloaded / total_bytes) * 100.0
                                self.root.after(0, lambda v=pct: set_progress(v))

                try:
                    if os.path.exists(dest):
                        os.remove(dest)
                except Exception:
                    pass
                os.replace(part_path, dest)

                self.root.after(0, lambda: set_progress(100.0))
                self.root.after(0, lambda: self.log("Download complete."))
                self.root.after(0, self.refresh_status)
            except Exception as e:
                try:
                    if os.path.exists(part_path):
                        os.remove(part_path)
                except Exception:
                    pass
                self.root.after(0, lambda: self.log(f"Download failed: {type(e).__name__}"))
                self.root.after(
                    0,
                    lambda: messagebox.showerror(
                        "Download failed",
                        f"{type(e).__name__}\n\nIf this persists, try again or choose a different model.",
                    ),
                )

        threading.Thread(target=worker, daemon=True).start()

    def install_runtime(self):
        def worker():
            self.log("Installing llama-cpp-python...")
            try:
                cmd = [sys.executable, "-m", "pip", "install", "--upgrade", "llama-cpp-python"]
                p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
                if p.stdout:
                    for line in p.stdout:
                        self.log(line.rstrip("\n"))
                p.wait()
                if p.returncode == 0:
                    self.log("Install completed.")
                else:
                    self.log(f"Install failed (exit {p.returncode}).")
            except Exception as e:
                self.log(f"Install failed: {type(e).__name__}")
            self.ui(self.refresh_status)

        threading.Thread(target=worker, daemon=True).start()

    def run(self):
        self.root.mainloop()


def main(argv: list[str]):
    base_dir = os.path.dirname(os.path.abspath(__file__))
    settings_path = os.path.join(base_dir, "settings.txt")
    initial_tab = None
    if "--tab" in argv:
        idx = argv.index("--tab")
        if idx + 1 < len(argv):
            initial_tab = argv[idx + 1]
    app = SettingsGUI(settings_path=settings_path, initial_tab=initial_tab)
    app.run()


if __name__ == "__main__":
    main(sys.argv[1:])

