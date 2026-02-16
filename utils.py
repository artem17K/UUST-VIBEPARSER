import os
import base64
import mimetypes
import json
from datetime import date, timedelta
from config import JSON_DIR

def calculate_academic_week() -> int:
    today = date.today()
    if today.month >= 9:
        year_start_date = date(today.year, 9, 1)
    else:
        year_start_date = date(today.year - 1, 9, 1)
    start_of_semester = year_start_date - timedelta(days=year_start_date.weekday())
    days_passed = (today - start_of_semester).days
    week_number = (days_passed // 7) + 1
    return week_number

def get_week_date_range(week_number: int) -> str:
    today = date.today()
    if today.month >= 9:
        year_start_date = date(today.year, 9, 1)
    else:
        year_start_date = date(today.year - 1, 9, 1)
    semester_start_monday = year_start_date - timedelta(days=year_start_date.weekday())
    target_monday = semester_start_monday + timedelta(weeks=week_number - 1)
    target_sunday = target_monday + timedelta(days=6)
    return f"{target_monday.strftime('%d.%m.%Y')} - {target_sunday.strftime('%d.%m.%Y')}"

def image_to_base64_uri(filepath: str) -> str | None:
    if not os.path.exists(filepath):
        print(f"⚠️ Предупреждение: Файл изображения не найден: {filepath}")
        return None
    try:
        mime_type, _ = mimetypes.guess_type(filepath)
        if not mime_type or not mime_type.startswith('image'): return None
        with open(filepath, "rb") as image_file:
            encoded_string = base64.b64encode(image_file.read()).decode('utf-8')
            return f"data:{mime_type};base64,{encoded_string}"
    except Exception:
        return None

def cleanup_old_files(directory: str, max_files: int, group_name: str):
    if not os.path.exists(directory): return
    files = sorted([f for f in os.listdir(directory) if f.startswith(f"schedule_{group_name}_")])
    if len(files) > max_files:
        for filename in files[:-max_files]:
            try:
                os.remove(os.path.join(directory, filename))
            except OSError as e:
                print(f"    - ❌ Не удалось удалить {filename}: {e}")

def get_latest_schedule_file(group_name: str) -> str | None:
    if not os.path.exists(JSON_DIR): return None
    group_files = [f for f in os.listdir(JSON_DIR) if f.startswith(f"schedule_{group_name}_") and f.endswith(".json")]
    return os.path.join(JSON_DIR, sorted(group_files)[-1]) if group_files else None