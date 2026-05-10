from __future__ import annotations

import os
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import filedialog, ttk

from voicetray_config import load_settings, write_setting


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

        self._build_dictation_tab()
        self._build_llm_tab()
        self._build_status_bar()

        if initial_tab == "llm":
            self.notebook.select(self.llm_tab)

        self.refresh_status()

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

    def _build_status_bar(self):
        self.status_var = tk.StringVar(value="")
        bar = ttk.Label(self.root, textvariable=self.status_var, anchor="w")
        bar.pack(fill="x", padx=10, pady=(0, 8))

    def log(self, msg: str):
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
            self.refresh_status()

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

