import os
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk

import stego_core


C_BG      = "#1e1e2e"
C_SURFACE = "#313244"
C_MANTLE  = "#181825"
C_FG      = "#cdd6f4"
C_ACCENT  = "#89b4fa"
C_GREEN   = "#a6e3a1"
C_YELLOW  = "#f9e2af"
C_RED     = "#f38ba8"
C_SUBTEXT = "#a6adc8"


class StegoApp(tk.Tk):

    def __init__(self) -> None:
        super().__init__()
        self.title("StegoCAS  —  Esteganografia DCT resistente a JPEG")
        self.geometry("760x660")
        self.minsize(680, 580)
        self.configure(bg=C_BG)
        self._setup_ttk_style()

        self.notebook = ttk.Notebook(self, style="App.TNotebook")
        self.notebook.pack(fill="both", expand=True, padx=12, pady=(10, 4))

        self._build_embed_tab()
        self._build_extract_tab()

        self._status_var = tk.StringVar(value="Listo.")
        self._status_bar = tk.Label(
            self, textvariable=self._status_var,
            bg=C_MANTLE, fg=C_SUBTEXT, anchor="w", padx=10,
            font=("Consolas", 9),
        )
        self._status_bar.pack(fill="x", side="bottom", ipady=4)

    def _setup_ttk_style(self) -> None:
        s = ttk.Style(self)
        s.theme_use("clam")

        s.configure("App.TNotebook", background=C_BG, borderwidth=0, tabmargins=[2, 4, 2, 0])
        s.configure("App.TNotebook.Tab", background=C_SURFACE, foreground=C_FG,
                    padding=[16, 7], font=("Segoe UI", 10, "bold"))
        s.map("App.TNotebook.Tab",
              background=[("selected", C_ACCENT)],
              foreground=[("selected", C_BG)])

        s.configure("TFrame", background=C_BG)
        s.configure("TLabel", background=C_BG, foreground=C_FG, font=("Segoe UI", 10))
        s.configure("Dim.TLabel", background=C_BG, foreground=C_SUBTEXT, font=("Segoe UI", 9))
        s.configure("TEntry", fieldbackground=C_SURFACE, foreground=C_FG,
                    insertcolor=C_FG, borderwidth=0, relief="flat")
        s.map("TEntry", fieldbackground=[("focus", "#3d3f5c")])
        s.configure("Accent.TButton", background=C_ACCENT, foreground=C_BG,
                    font=("Segoe UI", 10, "bold"), padding=[12, 7],
                    borderwidth=0, relief="flat")
        s.map("Accent.TButton",
              background=[("active", "#74c7ec"), ("disabled", C_SURFACE)],
              foreground=[("disabled", C_SUBTEXT)])
        s.configure("TProgressbar", troughcolor=C_SURFACE, background=C_ACCENT,
                    thickness=5, borderwidth=0)
        s.configure("TSeparator", background=C_SURFACE)

    def _build_embed_tab(self) -> None:
        frame = ttk.Frame(self.notebook, style="TFrame")
        self.notebook.add(frame, text="  Ocultar mensaje  ")
        p = {"padx": 14, "pady": 5}

        ttk.Label(frame, text="Imagen de origen:").grid(row=0, column=0, sticky="w", **p)
        self._embed_src = tk.StringVar()
        ttk.Entry(frame, textvariable=self._embed_src, width=52).grid(row=0, column=1, sticky="ew", **p)
        ttk.Button(frame, text="...", width=3, command=self._browse_embed_source).grid(row=0, column=2, padx=(0, 14), pady=5)

        ttk.Label(frame, text="Guardar como:").grid(row=1, column=0, sticky="w", **p)
        self._embed_dst = tk.StringVar()
        ttk.Entry(frame, textvariable=self._embed_dst, width=52).grid(row=1, column=1, sticky="ew", **p)
        ttk.Button(frame, text="...", width=3, command=self._browse_embed_output).grid(row=1, column=2, padx=(0, 14), pady=5)

        ttk.Label(frame, text="Contrasena:").grid(row=2, column=0, sticky="w", **p)
        self._embed_pwd  = tk.StringVar()
        self._embed_show = tk.BooleanVar(value=False)
        self._embed_pwd_entry, _ = self._make_password_row(frame, 2, 1, self._embed_pwd, self._embed_show)

        ttk.Separator(frame, orient="horizontal").grid(row=3, column=0, columnspan=3, sticky="ew", padx=14, pady=6)

        ttk.Label(frame, text="Texto a ocultar:").grid(row=4, column=0, sticky="nw", padx=14, pady=(5, 2))
        self._embed_text = scrolledtext.ScrolledText(
            frame, height=8, wrap="word",
            bg=C_SURFACE, fg=C_FG, insertbackground=C_FG,
            font=("Consolas", 10), relief="flat", padx=6, pady=4,
            selectbackground=C_ACCENT, selectforeground=C_BG)
        self._embed_text.grid(row=4, column=1, columnspan=2, sticky="nsew", padx=14, pady=(5, 2))

        self._embed_char_count = tk.StringVar(value="0 caracteres")
        ttk.Label(frame, textvariable=self._embed_char_count, style="Dim.TLabel").grid(row=5, column=1, sticky="e", padx=14)
        self._embed_text.bind("<KeyRelease>", self._update_char_count)

        self._embed_btn = ttk.Button(frame, text="Ocultar mensaje", style="Accent.TButton", command=self._run_embed)
        self._embed_btn.grid(row=6, column=1, sticky="e", padx=14, pady=(6, 4))

        self._embed_progress = ttk.Progressbar(frame, mode="indeterminate", style="TProgressbar")
        self._embed_progress.grid(row=7, column=0, columnspan=3, sticky="ew", padx=14, pady=(0, 4))

        self._embed_result = scrolledtext.ScrolledText(
            frame, height=5, wrap="word", state="disabled",
            bg=C_MANTLE, fg=C_FG, font=("Consolas", 9), relief="flat", padx=6, pady=4)
        self._embed_result.grid(row=8, column=0, columnspan=3, sticky="nsew", padx=14, pady=(4, 10))

        frame.columnconfigure(1, weight=1)
        frame.rowconfigure(4, weight=1)

    def _build_extract_tab(self) -> None:
        frame = ttk.Frame(self.notebook, style="TFrame")
        self.notebook.add(frame, text="  Extraer mensaje  ")
        p = {"padx": 14, "pady": 5}

        ttk.Label(frame, text="Imagen con mensaje:").grid(row=0, column=0, sticky="w", **p)
        self._extract_src = tk.StringVar()
        ttk.Entry(frame, textvariable=self._extract_src, width=52).grid(row=0, column=1, sticky="ew", **p)
        ttk.Button(frame, text="...", width=3, command=self._browse_extract).grid(row=0, column=2, padx=(0, 14), pady=5)

        ttk.Label(frame, text="Contrasena:").grid(row=1, column=0, sticky="w", **p)
        self._extract_pwd  = tk.StringVar()
        self._extract_show = tk.BooleanVar(value=False)
        self._extract_pwd_entry, _ = self._make_password_row(frame, 1, 1, self._extract_pwd, self._extract_show)

        ttk.Separator(frame, orient="horizontal").grid(row=2, column=0, columnspan=3, sticky="ew", padx=14, pady=6)

        self._extract_btn = ttk.Button(frame, text="Extraer y descifrar", style="Accent.TButton", command=self._run_extract)
        self._extract_btn.grid(row=3, column=1, sticky="e", padx=14, pady=(6, 4))

        self._extract_progress = ttk.Progressbar(frame, mode="indeterminate", style="TProgressbar")
        self._extract_progress.grid(row=4, column=0, columnspan=3, sticky="ew", padx=14, pady=(0, 4))

        ttk.Label(frame, text="Mensaje extraido:").grid(row=5, column=0, sticky="nw", **p)
        self._extract_result = scrolledtext.ScrolledText(
            frame, height=14, wrap="word",
            bg=C_SURFACE, fg=C_GREEN, font=("Consolas", 11), relief="flat", padx=8, pady=6,
            selectbackground=C_ACCENT, selectforeground=C_BG)
        self._extract_result.grid(row=5, column=1, columnspan=2, sticky="nsew", padx=14, pady=(5, 4))

        ttk.Button(frame, text="Copiar al portapapeles", command=self._copy_result).grid(
            row=6, column=1, sticky="e", padx=14, pady=(0, 10))

        self._extract_status = scrolledtext.ScrolledText(
            frame, height=4, wrap="word", state="disabled",
            bg=C_MANTLE, fg=C_FG, font=("Consolas", 9), relief="flat", padx=6, pady=4)
        self._extract_status.grid(row=7, column=0, columnspan=3, sticky="nsew", padx=14, pady=(0, 10))

        frame.columnconfigure(1, weight=1)
        frame.rowconfigure(5, weight=1)

    def _make_password_row(self, parent, row, col, pwd_var, show_var):
        container = ttk.Frame(parent, style="TFrame")
        container.grid(row=row, column=col, columnspan=2, sticky="ew", padx=14, pady=5)
        entry = ttk.Entry(container, textvariable=pwd_var, show="*", width=48)
        entry.pack(side="left", fill="x", expand=True)

        def _toggle():
            entry.config(show="" if show_var.get() else "*")

        chk = tk.Checkbutton(
            container, text="Mostrar", variable=show_var, command=_toggle,
            bg=C_BG, fg=C_SUBTEXT, selectcolor=C_SURFACE,
            activebackground=C_BG, activeforeground=C_ACCENT,
            font=("Segoe UI", 9), cursor="hand2",
        )
        chk.pack(side="left", padx=(8, 0))
        return entry, chk

    def _browse_embed_source(self) -> None:
        path = filedialog.askopenfilename(
            title="Seleccionar imagen de origen",
            filetypes=[("Imagenes", "*.jpg *.jpeg *.png *.bmp *.tiff *.webp"), ("Todos", "*.*")],
        )
        if path:
            self._embed_src.set(path)
            base, _ = os.path.splitext(path)
            current  = self._embed_dst.get()
            if not current or current.endswith("_stego.jpg"):
                self._embed_dst.set(base + "_stego.jpg")

    def _browse_embed_output(self) -> None:
        path = filedialog.asksaveasfilename(
            title="Guardar como",
            defaultextension=".jpg",
            filetypes=[("JPEG", "*.jpg *.jpeg"), ("PNG", "*.png"), ("Todos", "*.*")],
        )
        if path:
            self._embed_dst.set(path)

    def _browse_extract(self) -> None:
        path = filedialog.askopenfilename(
            title="Seleccionar imagen con mensaje",
            filetypes=[("Imagenes", "*.jpg *.jpeg *.png *.bmp *.tiff"), ("Todos", "*.*")],
        )
        if path:
            self._extract_src.set(path)

    def _update_char_count(self, _event=None) -> None:
        n = len(self._embed_text.get("1.0", "end-1c"))
        self._embed_char_count.set(f"{n} caracteres")

    def _copy_result(self) -> None:
        text = self._extract_result.get("1.0", "end-1c").strip()
        if text:
            self.clipboard_clear()
            self.clipboard_append(text)
            self._set_status("Texto copiado al portapapeles.", "ok")
        else:
            self._set_status("No hay texto para copiar.", "info")

    def _set_status(self, msg: str, level: str = "info") -> None:
        colors = {"ok": C_GREEN, "warn": C_YELLOW, "error": C_RED, "info": C_SUBTEXT}
        self._status_var.set(msg)
        self._status_bar.config(fg=colors.get(level, C_SUBTEXT))

    def _write_to_textbox(self, widget, text: str, color: str) -> None:
        widget.config(state="normal")
        widget.delete("1.0", "end")
        widget.insert("end", text)
        widget.config(fg=color, state="disabled")

    def _run_embed(self) -> None:
        src      = self._embed_src.get().strip()
        dst      = self._embed_dst.get().strip()
        password = self._embed_pwd.get()
        text     = self._embed_text.get("1.0", "end-1c").strip()

        if not src:
            messagebox.showwarning("Campo vacio", "Selecciona una imagen de origen."); return
        if not os.path.isfile(src):
            messagebox.showerror("Archivo no encontrado", f"No se encuentra:\n{src}"); return
        if not dst:
            messagebox.showwarning("Campo vacio", "Indica donde guardar la imagen."); return
        if not password:
            messagebox.showwarning("Campo vacio", "Introduce una contrasena."); return
        if not text:
            messagebox.showwarning("Campo vacio", "Escribe el texto a ocultar."); return

        self._embed_btn.state(["disabled"])
        self._embed_progress.start(12)
        self._set_status("Procesando...", "info")
        self._write_to_textbox(self._embed_result, "Procesando...", C_SUBTEXT)

        threading.Thread(target=self._embed_worker, args=(src, text, password, dst), daemon=True).start()

    def _embed_worker(self, src, text, password, dst) -> None:
        try:
            result = stego_core.embed(src, text, password, dst)
        except Exception as exc:
            result = {"success": False, "message": f"Error inesperado: {exc}", "warning": ""}
        self.after(0, self._embed_done, result)

    def _embed_done(self, result: dict) -> None:
        self._embed_progress.stop()
        self._embed_btn.state(["!disabled"])
        parts = [p for p in [result.get("warning"), result["message"]] if p]
        output = "\n\n".join(parts)
        if result["success"]:
            self._write_to_textbox(self._embed_result, output, C_GREEN)
            self._set_status("Mensaje ocultado con exito.", "ok")
        else:
            self._write_to_textbox(self._embed_result, output, C_RED)
            self._set_status("Error al ocultar el mensaje.", "error")

    def _run_extract(self) -> None:
        src      = self._extract_src.get().strip()
        password = self._extract_pwd.get()

        if not src:
            messagebox.showwarning("Campo vacio", "Selecciona una imagen."); return
        if not os.path.isfile(src):
            messagebox.showerror("Archivo no encontrado", f"No se encuentra:\n{src}"); return
        if not password:
            messagebox.showwarning("Campo vacio", "Introduce la contrasena."); return

        self._extract_btn.state(["disabled"])
        self._extract_progress.start(12)
        self._set_status("Extrayendo y descifrando...", "info")
        self._extract_result.config(state="normal")
        self._extract_result.delete("1.0", "end")
        self._extract_result.config(fg=C_GREEN, state="disabled")
        self._write_to_textbox(self._extract_status, "Procesando...", C_SUBTEXT)

        threading.Thread(target=self._extract_worker, args=(src, password), daemon=True).start()

    def _extract_worker(self, src, password) -> None:
        try:
            result = stego_core.extract(src, password)
        except Exception as exc:
            result = {"success": False, "message": f"Error inesperado: {exc}", "text": ""}
        self.after(0, self._extract_done, result)

    def _extract_done(self, result: dict) -> None:
        self._extract_progress.stop()
        self._extract_btn.state(["!disabled"])
        if result["success"]:
            self._extract_result.config(state="normal")
            self._extract_result.delete("1.0", "end")
            self._extract_result.insert("end", result["text"])
            self._extract_result.config(fg=C_GREEN, state="disabled")
            self._write_to_textbox(self._extract_status, result["message"], C_GREEN)
            self._set_status("Mensaje extraido y descifrado con exito.", "ok")
        else:
            self._write_to_textbox(self._extract_status, result["message"], C_RED)
            self._set_status(result["message"].splitlines()[0][:70], "error")


if __name__ == "__main__":
    app = StegoApp()
    app.mainloop()
