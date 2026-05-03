#!/usr/bin/env python3
"""
Image Converter — конвертирует изображения в выбранный формат и сжимает до лимита.
"""

import io
import sys
import time
import argparse
from pathlib import Path
from PIL import Image

# Поддерживаемые входные форматы
SUPPORTED_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".webp", ".bmp",
    ".tiff", ".tif", ".gif", ".heic", ".heif",
    ".avif", ".ico", ".ppm", ".pgm", ".pbm",
    ".cr2", ".cr3", ".nef", ".arw", ".dng",
    ".orf", ".rw2", ".raf", ".pef", ".srw",
}

# Конфигурация выходных форматов
OUTPUT_FORMATS = {
    "jpeg": {
        "ext": ".jpeg",
        "pil_format": "JPEG",
        "supports_alpha": False,
        "supports_quality": True,
    },
    "png": {
        "ext": ".png",
        "pil_format": "PNG",
        "supports_alpha": True,
        "supports_quality": False,  # PNG lossless, только уровень сжатия
    },
    "webp": {
        "ext": ".webp",
        "pil_format": "WEBP",
        "supports_alpha": True,
        "supports_quality": True,
    },
    "tiff": {
        "ext": ".tiff",
        "pil_format": "TIFF",
        "supports_alpha": True,
        "supports_quality": False,
    },
}

MAX_SIZE_BYTES = 5 * 1024 * 1024  # 5 МБ


def format_time(seconds: float) -> str:
    """Форматирует секунды в читаемый вид."""
    if seconds < 60:
        return f"{int(seconds)}с"
    elif seconds < 3600:
        m, s = divmod(int(seconds), 60)
        return f"{m}м {s}с"
    else:
        h, rem = divmod(int(seconds), 3600)
        m, s = divmod(rem, 60)
        return f"{h}ч {m}м {s}с"


def format_size(size_bytes: int) -> str:
    """Форматирует байты в читаемый вид."""
    if size_bytes < 1024:
        return f"{size_bytes} Б"
    elif size_bytes < 1024 ** 2:
        return f"{size_bytes / 1024:.1f} КБ"
    else:
        return f"{size_bytes / 1024 ** 2:.2f} МБ"


def print_progress(
    done: int,
    total: int,
    current_file: str,
    start_time: float,
    success: int,
    skipped: int,
    errors: int,
):
    """Выводит строку прогресса."""
    elapsed = time.time() - start_time
    pct = done / total if total > 0 else 0

    if done > 0:
        eta = elapsed / done * (total - done)
        eta_str = format_time(eta)
    else:
        eta_str = "—"

    bar_len = 30
    filled = int(bar_len * pct)
    bar = "█" * filled + "░" * (bar_len - filled)

    name = Path(current_file).name
    if len(name) > 35:
        name = "…" + name[-33:]

    sys.stdout.write("\r\033[K")
    sys.stdout.write(
        f"[{bar}] {done}/{total} ({pct*100:.0f}%)  "
        f"✅{success} ⏭{skipped} ❌{errors}  "
        f"⏱ осталось: {eta_str}  📄 {name}"
    )
    sys.stdout.flush()


def prepare_image(img: Image.Image, supports_alpha: bool) -> Image.Image:
    """Приводит изображение к нужному цветовому режиму."""
    if not supports_alpha:
        # Форматы без альфа-канала (JPEG): заливаем белым фоном
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
        # Форматы с альфа-каналом: переводим в RGBA или RGB
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
    """Бинарный поиск оптимального quality для вписывания в limit_bytes."""
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
    """
    Конвертирует одно изображение в указанный формат.
    Возвращает словарь с результатом.
    """
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
            # JPEG / WebP — можно управлять качеством
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
            # PNG / TIFF — lossless, сохраняем как есть
            buf = io.BytesIO()
            if fmt["pil_format"] == "PNG":
                img.save(buf, format="PNG", optimize=True, compress_level=6)
            else:
                img.save(buf, format=fmt["pil_format"])
            data = buf.getvalue()

            if len(data) > max_bytes:
                result["message"] = (
                    f"⚠ Размер {format_size(len(data))} превышает лимит "
                    f"(lossless-формат, сжатие невозможно)"
                )

        dst_path.write_bytes(data)
        result["dst_size"] = len(data)

    except Exception as e:
        result["status"] = "error"
        result["message"] = str(e)

    return result


def collect_images(src_dir: Path) -> list[Path]:
    """Рекурсивно собирает все поддерживаемые изображения."""
    images = []
    for f in sorted(src_dir.rglob("*")):
        if f.is_file() and f.suffix.lower() in SUPPORTED_EXTENSIONS:
            images.append(f)
    return images


def run(src_dir: Path, dst_dir: Path, fmt_key: str, max_bytes: int):
    fmt = OUTPUT_FORMATS[fmt_key]
    print(f"\n📂 Исходная папка : {src_dir}")
    print(f"💾 Папка вывода   : {dst_dir}")
    print(f"🎨 Формат вывода  : {fmt['pil_format']} ({fmt['ext']})")
    if fmt["supports_quality"]:
        print(f"📏 Лимит размера  : {format_size(max_bytes)}\n")
    else:
        print(f"📏 Лимит размера  : не применяется (lossless)\n")

    images = collect_images(src_dir)
    total = len(images)

    if total == 0:
        print("⚠️  Поддерживаемые изображения не найдены.")
        return

    print(f"🔍 Найдено файлов : {total}\n")
    print("─" * 70)

    start_time = time.time()
    success = skipped = errors = 0
    log_lines = []

    for idx, src_path in enumerate(images, start=1):
        rel = src_path.relative_to(src_dir)
        dst_path = dst_dir / rel.parent / rel.with_suffix(fmt["ext"]).name

        print_progress(idx - 1, total, str(src_path), start_time, success, skipped, errors)

        result = convert_image(src_path, dst_path, fmt_key, max_bytes)

        if result["status"] == "ok":
            success += 1
            if result["compressed"]:
                flag, note = "🗜", f"q={result['quality']} (сжато)"
            else:
                flag = "✅"
                note = f"q={result['quality']}" if result["quality"] else "lossless"
            size_info = f"{format_size(result['src_size'])} → {format_size(result['dst_size'])}"
            warn = f"  {result['message']}" if result["message"] else ""
            log_lines.append(f"{flag} {rel}  {size_info}  [{note}]{warn}")
        elif result["status"] == "skipped":
            skipped += 1
            log_lines.append(f"⏭  {rel}  (пропущен)")
        else:
            errors += 1
            log_lines.append(f"❌ {rel}  ОШИБКА: {result['message']}")

    print_progress(total, total, "", start_time, success, skipped, errors)
    print()

    elapsed = time.time() - start_time
    print("\n" + "─" * 70)
    print(f"\n{'='*70}")
    print(f"  ✅ Успешно сконвертировано : {success}")
    print(f"  ⏭  Пропущено              : {skipped}")
    print(f"  ❌ Ошибок                 : {errors}")
    print(f"  ⏱  Общее время            : {format_time(elapsed)}")
    print(f"{'='*70}\n")

    print("📋 Подробный лог:")
    print("─" * 70)
    for line in log_lines:
        print(" ", line)
    print()


def main():
    fmt_choices = list(OUTPUT_FORMATS.keys())
    parser = argparse.ArgumentParser(
        description="Конвертирует изображения в выбранный формат.",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument(
        "-i", "--input",
        required=True,
        metavar="ПАПКА",
        help="Путь к папке с исходными изображениями",
    )
    parser.add_argument(
        "-o", "--output",
        required=True,
        metavar="ПАПКА",
        help="Путь к папке для сохранения результатов",
    )
    parser.add_argument(
        "-f", "--format",
        choices=fmt_choices,
        default="jpeg",
        metavar="ФОРМАТ",
        help=f"Выходной формат: {', '.join(fmt_choices)} (по умолчанию: jpeg)",
    )
    parser.add_argument(
        "--max-mb",
        type=float,
        default=5.0,
        metavar="МБ",
        help="Максимальный размер файла в МБ (по умолчанию: 5.0; только для JPEG/WebP)",
    )
    args = parser.parse_args()

    src_dir = Path(args.input).expanduser().resolve()
    dst_dir = Path(args.output).expanduser().resolve()
    max_bytes = int(args.max_mb * 1024 * 1024)

    if not src_dir.exists():
        print(f"❌ Исходная папка не существует: {src_dir}")
        sys.exit(1)
    if not src_dir.is_dir():
        print(f"❌ Указанный путь не является папкой: {src_dir}")
        sys.exit(1)

    run(src_dir, dst_dir, args.format, max_bytes)


if __name__ == "__main__":
    main()
