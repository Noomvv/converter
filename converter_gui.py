#!/usr/bin/env python3
"""
Image Converter GUI — конвертация изображений в JPEG с GUI.
Запуск: python converter_gui.py
"""

import io
import os
import sys
import time
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path
from PIL import Image

# ── Константы ──────────────────────────────────────────────────────────────────
SUPPORTED_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".webp", ".bmp",
    ".tiff", ".tif", ".gif", ".heic", ".heif",
    ".avif", ".ico", ".ppm", ".pgm", ".pbm",
    ".cr2", ".cr3", ".nef", ".arw", ".dng",
    ".orf", ".rw2", ".raf", ".pef", ".srw",
}

# Конфигурация выходных форматов
OUTPUT_FORMATS = {
    "JPEG": {
        "ext": ".jpeg",
        "pil_format": "JPEG",
        "supports_alpha": False,
        "supports_quality": True,
    },
    "PNG": {
        "ext": ".png",
        "pil_format": "PNG",
        "supports_alpha": True,
        "supports_quality": False,
    },
    "WebP": {
        "ext": ".webp",
        "pil_format": "WEBP",
        "supports_alpha": True,
        "supports_quality": True,
    },
    "TIFF": {
        "ext": ".tiff",
        "pil_format": "TIFF",
        "supports_alpha": True,
        "supports_quality": False,
    },
}

DEFAULT_MAX_MB = 5

# ── Цветовая тема ───────────────────────────────────────────────────────────────
COLORS = {
    "bg":           "#1a1a2e",
    "surface":      "#16213e",
    "surface2":     "#0f3460",
    "accent":       "#e94560",
    "accent2":      "#533483",
    "text":         "#eaeaea",
    "text_muted":   "#8892a4",
    "success":      "#4ecca3",
    "warning":      "#f5a623",
    "error":        "#ff5c5c",
    "border":       "#2a2a4a",
    "progress_bg":  "#0d1117",
}

FONT_FAMILY = "SF Pro Display" if sys.platform == "darwin" else "Segoe UI"


# ── Вспомогательные функции ─────────────────────────────────────────────────────
def format_time(seconds: float) -> str:
    if seconds < 1:
        return "менее 1с"
    elif seconds < 60:
        return f"{int(seconds)}с"
    elif seconds < 3600:
        m, s = divmod(int(seconds), 60)
        return f"{m}м {s}с"
    else:
        h, rem = divmod(int(seconds), 3600)
        m, s = divmod(rem, 60)
        return f"{h}ч {m}м"


def format_size(size_bytes: int) -> str:
    if size_bytes < 1024:
        return f"{size_bytes} Б"
    elif size_bytes < 1024 ** 2:
        return f"{size_bytes / 1024:.1f} КБ"
    else:
        return f"{size_bytes / 1024 ** 2:.2f} МБ"


def collect_images(src_dir: Path) -> list[Path]:
    return sorted(
        f for f in src_dir.rglob("*")
        if f.is_file() and f.suffix.lower() in SUPPORTED_EXTENSIONS
    )


def prepare_image(img: Image.Image, supports_alpha: bool) -> Image.Image:
    """Приводит изображение к нужному цветовому режиму."""
    if not supports_alpha:
        if img.mode in ("RGBA", "LA", "P"):
            bg = Image.new("RGB", img.size, (255, 255, 255))
            if img.mode == "P":
                img = img.convert("RGBA")
            mask = img.split()[-1] if img.mode in ("RGBA", "LA") else None
            bg.paste(img, mask=mask)
            return bg
        elif img.mode != "RGB":
            return img.convert("RGB")
    else:
        if img.mode == "P":
            img = img.convert("RGBA")
        elif img.mode not in ("RGB", "RGBA", "L", "LA"):
            img = img.convert("RGBA" if img.mode == "PA" else "RGB")
    return img


def compress_to_limit(
    img: Image.Image,
    pil_format: str,
    limit_bytes: int,
    initial_quality: int = 90,
) -> tuple[bytes, int]:
    lo, hi = 10, initial_quality
    best_data, best_quality = None, lo
    while lo <= hi:
        mid = (lo + hi) // 2
        buf = io.BytesIO()
        img.save(buf, format=pil_format, quality=mid)
        data = buf.getvalue()
        if len(data) <= limit_bytes:
            best_data, best_quality = data, mid
            lo = mid + 1
        else:
            hi = mid - 1
    if best_data is None:
        buf = io.BytesIO()
        img.save(buf, format=pil_format, quality=10)
        best_data = buf.getvalue()
        best_quality = 10
    return best_data, best_quality


def convert_image(src_path: Path, dst_path: Path, fmt_key: str, max_bytes: int) -> dict:
    fmt = OUTPUT_FORMATS[fmt_key]
    result = {
        "status": "ok",
        "src_size": src_path.stat().st_size,
        "dst_size": 0,
        "quality": None,
        "compressed": False,
        "message": "",
    }
    try:
        img = Image.open(src_path)
        img.load()
        img = prepare_image(img, fmt["supports_alpha"])
        dst_path.parent.mkdir(parents=True, exist_ok=True)

        if fmt["supports_quality"]:
            buf = io.BytesIO()
            img.save(buf, format=fmt["pil_format"], quality=90)
            data = buf.getvalue()
            if len(data) > max_bytes:
                data, quality = compress_to_limit(img, fmt["pil_format"], max_bytes)
                result["compressed"] = True
                result["quality"] = quality
            else:
                result["quality"] = 90
        else:
            buf = io.BytesIO()
            if fmt["pil_format"] == "PNG":
                img.save(buf, format="PNG", optimize=True, compress_level=6)
            else:
                img.save(buf, format=fmt["pil_format"])
            data = buf.getvalue()
            if len(data) > max_bytes:
                result["message"] = (
                    f"⚠ {format_size(len(data))} > лимита "
                    f"(lossless, сжатие невозможно)"
                )

        dst_path.write_bytes(data)
        result["dst_size"] = len(data)
    except Exception as e:
        result["status"] = "error"
        result["message"] = str(e)
    return result


# ── Главное приложение ──────────────────────────────────────────────────────────
class ConverterApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Image Converter")
        self.geometry("820x680")
        self.minsize(700, 580)
        self.configure(bg=COLORS["bg"])
        self.resizable(True, True)

        # Состояние
        self._running = False
        self._cancel_flag = threading.Event()
        self._thread: threading.Thread | None = None

        self._build_ui()
        self._center_window()

    def _center_window(self):
        self.update_idletasks()
        w, h = self.winfo_width(), self.winfo_height()
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        self.geometry(f"{w}x{h}+{(sw-w)//2}+{(sh-h)//2}")

    # ── Построение UI ────────────────────────────────────────────────────────────
    def _build_ui(self):
        # Заголовок
        header = tk.Frame(self, bg=COLORS["surface"], pady=18)
        header.pack(fill="x")
        tk.Label(
            header, text="🖼  Image Converter",
            font=(FONT_FAMILY, 20, "bold"),
            bg=COLORS["surface"], fg=COLORS["text"],
        ).pack()
        tk.Label(
            header, text="Конвертация изображений в JPEG с автоматическим сжатием",
            font=(FONT_FAMILY, 11),
            bg=COLORS["surface"], fg=COLORS["text_muted"],
        ).pack(pady=(2, 0))

        # Контент
        content = tk.Frame(self, bg=COLORS["bg"], padx=28, pady=20)
        content.pack(fill="both", expand=True)

        self._build_path_section(content)
        self._build_settings_section(content)
        self._build_progress_section(content)
        self._build_log_section(content)
        self._build_buttons(content)

    def _card(self, parent, title: str) -> tk.Frame:
        """Создаёт карточку с заголовком."""
        wrapper = tk.Frame(parent, bg=COLORS["bg"])
        wrapper.pack(fill="x", pady=(0, 14))

        tk.Label(
            wrapper, text=title.upper(),
            font=(FONT_FAMILY, 9, "bold"),
            bg=COLORS["bg"], fg=COLORS["text_muted"],
        ).pack(anchor="w", pady=(0, 6))

        card = tk.Frame(
            wrapper, bg=COLORS["surface"],
            highlightbackground=COLORS["border"],
            highlightthickness=1,
            padx=16, pady=14,
        )
        card.pack(fill="x")
        return card

    def _build_path_section(self, parent):
        card = self._card(parent, "📁 Папки")

        # Входная папка
        self._build_folder_row(card, "Исходная папка:", "input_path")
        tk.Frame(card, bg=COLORS["border"], height=1).pack(fill="x", pady=8)
        # Выходная папка
        self._build_folder_row(card, "Папка вывода:", "output_path")

    def _build_folder_row(self, parent, label: str, attr: str):
        row = tk.Frame(parent, bg=COLORS["surface"])
        row.pack(fill="x")

        tk.Label(
            row, text=label, width=16, anchor="w",
            font=(FONT_FAMILY, 11),
            bg=COLORS["surface"], fg=COLORS["text_muted"],
        ).pack(side="left")

        var = tk.StringVar()
        setattr(self, attr, var)

        entry = tk.Entry(
            row, textvariable=var,
            font=(FONT_FAMILY, 11),
            bg=COLORS["surface2"], fg=COLORS["text"],
            insertbackground=COLORS["text"],
            relief="flat", bd=0,
            highlightbackground=COLORS["border"],
            highlightthickness=1,
        )
        entry.pack(side="left", fill="x", expand=True, ipady=6, padx=(0, 8))

        def browse(a=attr):
            path = filedialog.askdirectory(title="Выберите папку")
            if path:
                getattr(self, a).set(path)

        tk.Button(
            row, text="Обзор…",
            font=(FONT_FAMILY, 10),
            bg=COLORS["surface2"], fg=COLORS["text"],
            activebackground=COLORS["accent2"],
            activeforeground=COLORS["text"],
            relief="flat", bd=0, padx=12, pady=4,
            cursor="hand2",
            command=browse,
        ).pack(side="left")

    def _build_settings_section(self, parent):
        card = self._card(parent, "⚙️  Настройки")

        # ── Выбор формата ──
        fmt_row = tk.Frame(card, bg=COLORS["surface"])
        fmt_row.pack(fill="x", pady=(0, 10))

        tk.Label(
            fmt_row, text="Выходной формат:",
            font=(FONT_FAMILY, 11),
            bg=COLORS["surface"], fg=COLORS["text_muted"],
        ).pack(side="left")

        self.output_format = tk.StringVar(value="JPEG")

        fmt_btn_frame = tk.Frame(fmt_row, bg=COLORS["surface"])
        fmt_btn_frame.pack(side="left", padx=(12, 0))

        self._fmt_buttons = {}
        for fmt_name in OUTPUT_FORMATS:
            btn = tk.Button(
                fmt_btn_frame,
                text=fmt_name,
                font=(FONT_FAMILY, 10, "bold"),
                relief="flat", bd=0,
                padx=14, pady=5,
                cursor="hand2",
                command=lambda f=fmt_name: self._select_format(f),
            )
            btn.pack(side="left", padx=(0, 4))
            self._fmt_buttons[fmt_name] = btn

        # Описание формата
        self._fmt_desc = tk.Label(
            fmt_row, text="",
            font=(FONT_FAMILY, 9),
            bg=COLORS["surface"], fg=COLORS["text_muted"],
        )
        self._fmt_desc.pack(side="right")

        tk.Frame(card, bg=COLORS["border"], height=1).pack(fill="x", pady=(0, 10))

        # ── Лимит размера ──
        self._size_row = tk.Frame(card, bg=COLORS["surface"])
        self._size_row.pack(fill="x")

        tk.Label(
            self._size_row, text="Максимальный размер файла:",
            font=(FONT_FAMILY, 11),
            bg=COLORS["surface"], fg=COLORS["text_muted"],
        ).pack(side="left")

        self.max_mb = tk.DoubleVar(value=DEFAULT_MAX_MB)

        self._max_mb_label = tk.Label(
            self._size_row, text=f"{DEFAULT_MAX_MB:.0f} МБ",
            font=(FONT_FAMILY, 11, "bold"),
            bg=COLORS["surface"], fg=COLORS["accent"],
            width=7,
        )
        self._max_mb_label.pack(side="right")

        self._size_slider = ttk.Scale(
            self._size_row, from_=0.5, to=20, variable=self.max_mb,
            orient="horizontal",
            command=self._on_slider,
        )
        self._size_slider.pack(side="right", fill="x", expand=True, padx=(12, 8))

        # Стиль слайдера
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("TScale",
            background=COLORS["surface"],
            troughcolor=COLORS["surface2"],
            sliderlength=18,
        )

        # Инициализация внешнего вида кнопок
        self._select_format("JPEG")

    _FMT_DESCS = {
        "JPEG": "Лучший размер • без прозрачности",
        "PNG":  "Lossless • с прозрачностью",
        "WebP": "Современный • с прозрачностью",
        "TIFF": "Профессиональный • lossless",
    }

    def _select_format(self, fmt_name: str):
        self.output_format.set(fmt_name)
        fmt = OUTPUT_FORMATS[fmt_name]

        for name, btn in self._fmt_buttons.items():
            if name == fmt_name:
                btn.config(
                    bg=COLORS["accent"], fg="white",
                    activebackground="#c73652", activeforeground="white",
                )
            else:
                btn.config(
                    bg=COLORS["surface2"], fg=COLORS["text_muted"],
                    activebackground=COLORS["surface"], activeforeground=COLORS["text"],
                )

        self._fmt_desc.config(text=self._FMT_DESCS.get(fmt_name, ""))

        # Показываем/скрываем слайдер размера
        if fmt["supports_quality"]:
            self._size_row.pack(fill="x")
        else:
            self._size_row.pack_forget()

    def _on_slider(self, val):
        v = float(val)
        self._max_mb_label.config(text=f"{v:.1f} МБ")

    def _build_progress_section(self, parent):
        card = self._card(parent, "📊 Прогресс")

        # Прогресс-бар
        style = ttk.Style(self)
        style.configure("Custom.Horizontal.TProgressbar",
            troughcolor=COLORS["progress_bg"],
            background=COLORS["accent"],
            bordercolor=COLORS["border"],
            lightcolor=COLORS["accent"],
            darkcolor=COLORS["accent"],
            thickness=14,
        )
        self.progress_var = tk.DoubleVar(value=0)
        self.progress_bar = ttk.Progressbar(
            card, variable=self.progress_var,
            maximum=100, style="Custom.Horizontal.TProgressbar",
        )
        self.progress_bar.pack(fill="x", pady=(0, 10))

        # Статистика в 4 колонки
        stats_row = tk.Frame(card, bg=COLORS["surface"])
        stats_row.pack(fill="x")

        self._stat_done   = self._stat_box(stats_row, "Готово",     "0",  COLORS["success"])
        self._stat_total  = self._stat_box(stats_row, "Всего",      "0",  COLORS["text"])
        self._stat_errors = self._stat_box(stats_row, "Ошибок",     "0",  COLORS["error"])
        self._stat_eta    = self._stat_box(stats_row, "Осталось",   "—",  COLORS["warning"])
        self._stat_speed  = self._stat_box(stats_row, "Файлов/мин", "—",  COLORS["text_muted"])
        self._stat_file   = self._stat_box(stats_row, "Текущий файл", "—", COLORS["text_muted"], wide=True)

    def _stat_box(self, parent, label: str, value: str, color: str, wide=False) -> tk.Label:
        frame = tk.Frame(parent, bg=COLORS["surface2"], padx=10, pady=8)
        frame.pack(side="left", fill="x", expand=True, padx=(0, 6) if not wide else (6, 0))

        val_label = tk.Label(
            frame, text=value,
            font=(FONT_FAMILY, 16, "bold"),
            bg=COLORS["surface2"], fg=color,
        )
        val_label.pack()
        tk.Label(
            frame, text=label,
            font=(FONT_FAMILY, 9),
            bg=COLORS["surface2"], fg=COLORS["text_muted"],
        ).pack()
        return val_label

    def _build_log_section(self, parent):
        log_wrapper = tk.Frame(parent, bg=COLORS["bg"])
        log_wrapper.pack(fill="both", expand=True, pady=(0, 12))

        tk.Label(
            log_wrapper, text="ЛОГ",
            font=(FONT_FAMILY, 9, "bold"),
            bg=COLORS["bg"], fg=COLORS["text_muted"],
        ).pack(anchor="w", pady=(0, 6))

        frame = tk.Frame(
            log_wrapper, bg=COLORS["surface"],
            highlightbackground=COLORS["border"],
            highlightthickness=1,
        )
        frame.pack(fill="both", expand=True)

        scrollbar = tk.Scrollbar(frame, bg=COLORS["surface2"])
        scrollbar.pack(side="right", fill="y")

        self.log_text = tk.Text(
            frame,
            font=("Menlo" if sys.platform == "darwin" else "Consolas", 10),
            bg=COLORS["surface"], fg=COLORS["text"],
            insertbackground=COLORS["text"],
            relief="flat", bd=0,
            yscrollcommand=scrollbar.set,
            state="disabled",
            height=8,
            wrap="none",
        )
        self.log_text.pack(fill="both", expand=True, padx=6, pady=6)
        scrollbar.config(command=self.log_text.yview)

        # Цвета тегов
        self.log_text.tag_config("ok",       foreground=COLORS["success"])
        self.log_text.tag_config("compress",  foreground=COLORS["warning"])
        self.log_text.tag_config("error",     foreground=COLORS["error"])
        self.log_text.tag_config("info",      foreground=COLORS["text_muted"])
        self.log_text.tag_config("header",    foreground=COLORS["accent"])

    def _build_buttons(self, parent):
        btn_row = tk.Frame(parent, bg=COLORS["bg"])
        btn_row.pack(fill="x")

        self.btn_start = tk.Button(
            btn_row, text="▶  Начать конвертацию",
            font=(FONT_FAMILY, 12, "bold"),
            bg=COLORS["accent"], fg="white",
            activebackground="#c73652",
            activeforeground="white",
            relief="flat", bd=0,
            padx=24, pady=10,
            cursor="hand2",
            command=self._start,
        )
        self.btn_start.pack(side="left")

        self.btn_cancel = tk.Button(
            btn_row, text="⏹  Остановить",
            font=(FONT_FAMILY, 12),
            bg=COLORS["surface2"], fg=COLORS["text_muted"],
            activebackground=COLORS["surface"],
            activeforeground=COLORS["text"],
            relief="flat", bd=0,
            padx=20, pady=10,
            cursor="hand2",
            state="disabled",
            command=self._cancel,
        )
        self.btn_cancel.pack(side="left", padx=(10, 0))

        self.status_label = tk.Label(
            btn_row, text="",
            font=(FONT_FAMILY, 10),
            bg=COLORS["bg"], fg=COLORS["text_muted"],
        )
        self.status_label.pack(side="right")

    # ── Логика ──────────────────────────────────────────────────────────────────
    def _log(self, message: str, tag: str = "info"):
        self.log_text.config(state="normal")
        self.log_text.insert("end", message + "\n", tag)
        self.log_text.see("end")
        self.log_text.config(state="disabled")

    def _clear_log(self):
        self.log_text.config(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.config(state="disabled")

    def _update_stats(self, done, total, errors, start_time):
        pct = (done / total * 100) if total > 0 else 0
        self.progress_var.set(pct)
        self._stat_done.config(text=str(done))
        self._stat_total.config(text=str(total))
        self._stat_errors.config(text=str(errors))

        elapsed = time.time() - start_time
        if done > 0:
            eta = elapsed / done * (total - done)
            speed = done / elapsed * 60 if elapsed > 0 else 0
            self._stat_eta.config(text=format_time(eta))
            self._stat_speed.config(text=f"{speed:.1f}")
        else:
            self._stat_eta.config(text="—")
            self._stat_speed.config(text="—")

    def _start(self):
        src = self.input_path.get().strip()
        dst = self.output_path.get().strip()
        max_mb = self.max_mb.get()

        if not src:
            messagebox.showwarning("Нет папки", "Укажите исходную папку.")
            return
        if not dst:
            messagebox.showwarning("Нет папки", "Укажите папку для сохранения.")
            return
        src_path = Path(src)
        if not src_path.exists() or not src_path.is_dir():
            messagebox.showerror("Ошибка", f"Папка не существует:\n{src}")
            return

        self._cancel_flag.clear()
        self._running = True
        self.btn_start.config(state="disabled")
        self.btn_cancel.config(state="normal")
        self.status_label.config(text="Идёт конвертация…")
        self._clear_log()

        # Сбрасываем статистику
        self.progress_var.set(0)
        for lbl in (self._stat_done, self._stat_total, self._stat_errors):
            lbl.config(text="0")
        self._stat_eta.config(text="—")
        self._stat_speed.config(text="—")
        self._stat_file.config(text="—")

        fmt_key = self.output_format.get()
        max_bytes = int(max_mb * 1024 * 1024)
        self._thread = threading.Thread(
            target=self._run_conversion,
            args=(src_path, Path(dst), fmt_key, max_bytes),
            daemon=True,
        )
        self._thread.start()

    def _cancel(self):
        self._cancel_flag.set()
        self.status_label.config(text="Остановка…")
        self.btn_cancel.config(state="disabled")

    def _run_conversion(self, src_dir: Path, dst_dir: Path, fmt_key: str, max_bytes: int):
        fmt = OUTPUT_FORMATS[fmt_key]
        images = collect_images(src_dir)
        total = len(images)

        if total == 0:
            self.after(0, lambda: messagebox.showinfo(
                "Готово", "Поддерживаемые изображения не найдены."))
            self.after(0, self._reset_buttons)
            return

        size_info = format_size(max_bytes) if fmt["supports_quality"] else "не применяется"
        self.after(0, lambda: self._log(
            f"Найдено {total} файлов  •  Формат: {fmt_key}  •  Лимит: {size_info}", "header"))
        self.after(0, lambda: self._log("─" * 60, "info"))

        start_time = time.time()
        done = success = errors = skipped = 0

        for src_path in images:
            if self._cancel_flag.is_set():
                break

            rel = src_path.relative_to(src_dir)
            dst_path = dst_dir / rel.parent / rel.with_suffix(fmt["ext"]).name
            name = str(rel)

            self.after(0, lambda n=name: self._stat_file.config(text=n))

            result = convert_image(src_path, dst_path, fmt_key, max_bytes)
            done += 1

            if result["status"] == "ok":
                success += 1
                size_str = f"{format_size(result['src_size'])} → {format_size(result['dst_size'])}"
                warn = f"  {result['message']}" if result.get("message") else ""
                if result["compressed"]:
                    msg = f"🗜  {name}  {size_str}  [q={result['quality']}]{warn}"
                    self.after(0, lambda m=msg: self._log(m, "compress"))
                else:
                    q_info = f"  [q={result['quality']}]" if result["quality"] else "  [lossless]"
                    msg = f"✅  {name}  {size_str}{q_info}{warn}"
                    self.after(0, lambda m=msg: self._log(m, "ok"))
            else:
                errors += 1
                msg = f"❌  {name}  {result['message']}"
                self.after(0, lambda m=msg: self._log(m, "error"))

            # Обновляем UI
            _done, _total, _errors, _st = done, total, errors, start_time
            self.after(0, lambda d=_done, t=_total, e=_errors, s=_st:
                       self._update_stats(d, t, e, s))

        elapsed = time.time() - start_time
        cancelled = self._cancel_flag.is_set()

        def finish():
            self.after(0, lambda: self._log("─" * 60, "info"))
            self.after(0, lambda: self._log(
                f"{'⚠️  Остановлено' if cancelled else '🎉  Завершено'}  •  "
                f"✅ {success} успешно  •  ❌ {errors} ошибок  •  "
                f"⏱ {format_time(elapsed)}", "header"))
            self.after(0, lambda: self.status_label.config(
                text="Остановлено" if cancelled else f"Готово за {format_time(elapsed)}"))
            self.after(0, self._reset_buttons)
            self.after(0, lambda: self._stat_file.config(text="—"))
            if not cancelled:
                self.after(0, lambda: self.progress_var.set(100))

        self.after(0, finish)

    def _reset_buttons(self):
        self._running = False
        self.btn_start.config(state="normal")
        self.btn_cancel.config(state="disabled")


# ── Точка входа ─────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    try:
        from PIL import Image  # noqa: F401
    except ImportError:
        import subprocess
        subprocess.run([sys.executable, "-m", "pip", "install", "Pillow"], check=True)
        from PIL import Image  # noqa: F401

    app = ConverterApp()
    app.mainloop()
