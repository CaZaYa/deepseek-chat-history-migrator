"""图形界面入口（打包后的 DeepSeek2Cherry.exe 运行的就是这里）。"""

from __future__ import annotations

import json
import os
import queue
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from .core import (
    APP_NAME,
    APP_VERSION,
    DEFAULT_CHUNK_SIZE,
    PRESETS,
    PROJECT_URL,
    ConversionError,
    Converter,
    Options,
    Report,
    run_directory,
)

SETTINGS_PATH = Path(os.environ.get("APPDATA") or Path.home()) / "DeepSeek2Cherry" / "settings.json"


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"{APP_NAME} {APP_VERSION}")
        self.geometry("760x640")
        self.minsize(700, 600)
        self._set_window_icon()

        self.zip_var = tk.StringVar()
        self.out_var = tk.StringVar()
        self.name_var = tk.StringVar()
        self.mode_var = tk.StringVar(value="full")
        self.thinking_var = tk.BooleanVar(value=True)
        self.attach_var = tk.BooleanVar(value=True)
        self.chunk_var = tk.StringVar(value=str(DEFAULT_CHUNK_SIZE))
        self.status_var = tk.StringVar(value="等待开始")

        self.events: queue.Queue = queue.Queue()
        self.running = False

        self._build()
        self._load_settings()
        self._on_mode_change()
        self.after(100, self._drain_events)

        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ---------- 窗口图标 ----------
    def _set_window_icon(self):
        try:
            root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2]))
            icon = root / "assets" / "icon.ico"
            if icon.is_file():
                self.iconbitmap(str(icon))
        except Exception:  # noqa: BLE001
            pass

    # ---------- 界面 ----------
    def _build(self):
        style = ttk.Style(self)
        style.configure("Title.TLabel", font=("Microsoft YaHei UI", 15, "bold"))
        style.configure("Hint.TLabel", foreground="#666666")

        outer = ttk.Frame(self, padding=(18, 14, 18, 10))
        outer.pack(fill="both", expand=True)

        header = ttk.Frame(outer)
        header.pack(fill="x")
        ttk.Label(header, text="DeepSeek 聊天记录 → Cherry Studio", style="Title.TLabel").pack(side="left")
        ttk.Button(header, text="关于", width=6, command=self._show_about).pack(side="right")

        ttk.Label(
            outer,
            text="把 DeepSeek 导出的聊天记录转换成 Cherry Studio 可以直接导入的格式。",
            style="Hint.TLabel",
        ).pack(fill="x", pady=(2, 12))

        files = ttk.LabelFrame(outer, text=" 1. 选择文件 ", padding=(12, 8, 12, 10))
        files.pack(fill="x")

        ttk.Label(files, text="DeepSeek 导出包").grid(row=0, column=0, sticky="w", pady=2)
        ttk.Entry(files, textvariable=self.zip_var).grid(row=0, column=1, sticky="ew", padx=8, pady=2)
        ttk.Button(files, text="浏览…", command=self._pick_zip, width=8).grid(row=0, column=2, pady=2)

        ttk.Label(files, text="输出目录").grid(row=1, column=0, sticky="w", pady=2)
        ttk.Entry(files, textvariable=self.out_var).grid(row=1, column=1, sticky="ew", padx=8, pady=2)
        ttk.Button(files, text="浏览…", command=self._pick_out, width=8).grid(row=1, column=2, pady=2)

        ttk.Label(files, text="本次子文件夹").grid(row=2, column=0, sticky="w", pady=2)
        ttk.Entry(files, textvariable=self.name_var).grid(row=2, column=1, sticky="ew", padx=8, pady=2)
        ttk.Label(files, text="留空 = 按时间自动命名").grid(row=2, column=2, sticky="w")
        files.columnconfigure(1, weight=1)

        modes = ttk.LabelFrame(outer, text=" 2. 转换内容 ", padding=(12, 8, 12, 10))
        modes.pack(fill="x", pady=(10, 0))

        for index, (preset_id, label, _thinking, _attachments) in enumerate(PRESETS):
            ttk.Radiobutton(
                modes, text=label, value=preset_id, variable=self.mode_var, command=self._on_mode_change
            ).grid(row=index, column=0, columnspan=2, sticky="w", pady=1)

        ttk.Radiobutton(
            modes, text="自定义", value="custom", variable=self.mode_var, command=self._on_mode_change
        ).grid(row=3, column=0, sticky="w", pady=(1, 4))

        self.thinking_check = ttk.Checkbutton(modes, text="包含思考过程", variable=self.thinking_var)
        self.thinking_check.grid(row=4, column=0, sticky="w", padx=(22, 0))
        self.attach_check = ttk.Checkbutton(
            modes, text="导出图片附件并在消息里标注路径", variable=self.attach_var
        )
        self.attach_check.grid(row=4, column=1, sticky="w", padx=(12, 0))

        advanced = ttk.Frame(modes)
        advanced.grid(row=5, column=0, columnspan=2, sticky="w", pady=(8, 0))
        ttk.Label(advanced, text="每个 JSON 文件包含会话数").pack(side="left")
        ttk.Spinbox(
            advanced, from_=0, to=5000, increment=50, width=6, textvariable=self.chunk_var
        ).pack(side="left", padx=6)
        ttk.Label(advanced, text="（0 = 不拆分，建议 200）", style="Hint.TLabel").pack(side="left")

        actions = ttk.Frame(outer)
        actions.pack(fill="x", pady=(12, 4))
        self.start_btn = ttk.Button(actions, text="开始转换", command=self._start)
        self.start_btn.pack(side="left")
        self.open_btn = ttk.Button(actions, text="打开输出目录", command=self._open_out, state="disabled")
        self.open_btn.pack(side="left", padx=(8, 0))
        ttk.Label(actions, textvariable=self.status_var, style="Hint.TLabel").pack(side="right")

        self.progress = ttk.Progressbar(outer, mode="determinate", maximum=100)
        self.progress.pack(fill="x", pady=(2, 10))

        log_frame = ttk.LabelFrame(outer, text=" 日志 ", padding=(8, 6, 8, 8))
        log_frame.pack(fill="both", expand=True)
        self.log_box = tk.Text(log_frame, height=9, wrap="word", state="disabled", relief="flat")
        self.log_box.pack(fill="both", expand=True)
        self._log(f"{APP_NAME} {APP_VERSION} 就绪")

    # ---------- 模式联动 ----------
    def _on_mode_change(self):
        mode = self.mode_var.get()
        custom = mode == "custom"
        if not custom:
            for preset_id, _label, thinking, attachments in PRESETS:
                if preset_id == mode:
                    self.thinking_var.set(thinking)
                    self.attach_var.set(attachments)
                    break
        state = "normal" if custom else "disabled"
        self.thinking_check.configure(state=state)
        self.attach_check.configure(state=state)

    # ---------- 选择路径 ----------
    def _pick_zip(self):
        path = filedialog.askopenfilename(title="选择 DeepSeek 导出包", filetypes=[("ZIP 压缩包", "*.zip")])
        if not path:
            return
        self.zip_var.set(path)
        if not self.out_var.get():
            self.out_var.set(str(Path(path).with_suffix("")) + "_cherry")

    def _pick_out(self):
        path = filedialog.askdirectory(title="选择输出目录")
        if path:
            self.out_var.set(path)

    def _open_out(self):
        target = self.out_var.get().strip()
        if target and Path(target).is_dir():
            os.startfile(target)  # noqa: S606

    # ---------- 日志与事件 ----------
    def _log(self, message: str):
        self.events.put(("log", message))

    def _drain_events(self):
        try:
            while True:
                kind, payload = self.events.get_nowait()
                if kind == "log":
                    self.log_box.configure(state="normal")
                    self.log_box.insert("end", payload + "\n")
                    self.log_box.see("end")
                    self.log_box.configure(state="disabled")
                elif kind == "progress":
                    done, total = payload
                    percent = 100 if not total else done * 100 / total
                    self.progress["value"] = percent
                    self.status_var.set(f"处理中 {done}/{total}")
                elif kind == "done":
                    self._finish(payload)
                elif kind == "error":
                    self._fail(payload)
        except queue.Empty:
            pass
        self.after(100, self._drain_events)

    # ---------- 转换 ----------
    def _start(self):
        if self.running:
            return
        zip_path = self.zip_var.get().strip()
        out_dir = self.out_var.get().strip()

        if not zip_path or not Path(zip_path).is_file():
            messagebox.showwarning(APP_NAME, "请先选择 DeepSeek 导出包（.zip）。")
            return
        if not out_dir:
            messagebox.showwarning(APP_NAME, "请先选择输出目录。")
            return
        try:
            chunk_size = int(self.chunk_var.get())
            if chunk_size < 0:
                raise ValueError
        except ValueError:
            messagebox.showwarning(APP_NAME, "「每个 JSON 文件包含会话数」必须是不小于 0 的整数。")
            return

        options = Options(
            with_thinking=self.thinking_var.get(),
            export_attachments=self.attach_var.get(),
            chunk_size=chunk_size,
        )

        try:
            target = run_directory(out_dir, self.name_var.get())
        except OSError as error:
            messagebox.showerror(APP_NAME, "无法创建输出文件夹：\n" + str(error))
            return

        self.running = True
        self.start_btn.configure(state="disabled")
        self.open_btn.configure(state="disabled")
        self.progress["value"] = 0
        self.status_var.set("准备中…")
        self._log(f"开始转换：{zip_path}")
        self._save_settings()

        threading.Thread(
            target=self._worker, args=(zip_path, target, options), daemon=True
        ).start()

    def _worker(self, zip_path: str, out_dir: str, options: Options):
        try:
            report = Converter(
                zip_path,
                options,
                log=self._log,
                progress=lambda done, total: self.events.put(("progress", (done, total))),
            ).run(out_dir)
            self.events.put(("done", report))
        except ConversionError as error:
            self.events.put(("error", error))
        except Exception as error:  # noqa: BLE001
            self.events.put(("error", error))

    def _finish(self, report: Report):
        self.running = False
        self.start_btn.configure(state="normal")
        self.open_btn.configure(state="normal")
        self.progress["value"] = 100
        self.status_var.set("完成")

        for warning in report.warnings:
            self._log(f"提示：{warning}")

        summary = (
            f"会话：{report.conversations} 个\n"
            f"消息：{report.messages} 条\n"
            f"图片附件：{report.files} 个\n"
        )
        if report.missing_files:
            summary += f"原件缺失：{report.missing_files} 个（多为 PDF 等非图片附件）\n"
        summary += f"\n输出目录：\n{report.output_dir}"

        if messagebox.askyesno(APP_NAME, summary + "\n\n现在打开输出目录吗？"):
            self._open_out()

    def _fail(self, error: Exception):
        self.running = False
        self.start_btn.configure(state="normal")
        self.status_var.set("失败")
        self._log(f"出错：{error}")
        messagebox.showerror(APP_NAME, f"转换失败：\n{error}")

    # ---------- 设置持久化 ----------
    def _load_settings(self):
        try:
            data = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        mode = data.get("mode")
        if mode in {preset[0] for preset in PRESETS} or mode == "custom":
            self.mode_var.set(mode)
            self.thinking_var.set(bool(data.get("with_thinking", True)))
            self.attach_var.set(bool(data.get("export_attachments", True)))
            self._on_mode_change()
            if mode == "custom":
                self.thinking_var.set(bool(data.get("with_thinking", True)))
                self.attach_var.set(bool(data.get("export_attachments", True)))

    def _save_settings(self):
        try:
            SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
            SETTINGS_PATH.write_text(
                json.dumps(
                    {
                        "mode": self.mode_var.get(),
                        "with_thinking": self.thinking_var.get(),
                        "export_attachments": self.attach_var.get(),
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
        except OSError:
            pass

    # ---------- 其他 ----------
    def _show_about(self):
        messagebox.showinfo(
            f"关于 {APP_NAME}",
            f"{APP_NAME} {APP_VERSION}\n\n"
            "把 DeepSeek 网页版导出的聊天记录转换成 Cherry Studio 可导入的格式。\n"
            "本地运行，不上传任何数据。\n\n"
            f"{PROJECT_URL}",
        )

    def _on_close(self):
        if self.running and not messagebox.askyesno(APP_NAME, "正在转换，确定要退出吗？"):
            return
        self._save_settings()
        self.destroy()


def main() -> None:
    App().mainloop()


if __name__ == "__main__":
    main()
