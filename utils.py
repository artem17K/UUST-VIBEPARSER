import os
import base64
import mimetypes
from datetime import date, timedelta
from config import JSON_DIR


SECOND_SEMESTER_START_WEEK = 24


def calculate_academic_week() -> int:
    today = date.today()
    if today.month >= 9:
        year_start_date = date(today.year, 9, 1)
    else:
        year_start_date = date(today.year - 1, 9, 1)
    start_of_semester = year_start_date - timedelta(days=year_start_date.weekday())
    days_passed = (today - start_of_semester).days
    return (days_passed // 7) + 1


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


def get_semester_start_week(week_number: int) -> int:
    return SECOND_SEMESTER_START_WEEK if week_number >= SECOND_SEMESTER_START_WEEK else 1


def image_to_base64_uri(filepath: str) -> str | None:
    if not os.path.exists(filepath):
        print(f"⚠️ Предупреждение: Файл изображения не найден: {filepath}")
        return None
    try:
        mime_type, _ = mimetypes.guess_type(filepath)
        if not mime_type or not mime_type.startswith('image'):
            return None
        with open(filepath, "rb") as image_file:
            encoded = base64.b64encode(image_file.read()).decode('utf-8')
            return f"data:{mime_type};base64,{encoded}"
    except Exception as e:
        print(f"⚠️ Не удалось загрузить изображение {filepath}: {e}")
        return None


def cleanup_old_files(directory: str, max_files: int, group_name: str):
    if not os.path.exists(directory):
        return
    prefix = f"schedule_{group_name}_"
    files = [f for f in os.listdir(directory) if f.startswith(prefix)]
    files.sort(key=lambda f: os.path.getmtime(os.path.join(directory, f)))
    to_delete = files[:-max_files] if max_files > 0 else files
    for filename in to_delete:
        try:
            os.remove(os.path.join(directory, filename))
        except OSError as e:
            print(f"    - ❌ Не удалось удалить {filename}: {e}")


def get_latest_schedule_file(group_name: str) -> str | None:
    if not os.path.exists(JSON_DIR):
        return None
    prefix = f"schedule_{group_name}_"
    group_files = [f for f in os.listdir(JSON_DIR) if f.startswith(prefix) and f.endswith(".json")]
    if not group_files:
        return None
    group_files.sort(key=lambda f: os.path.getmtime(os.path.join(JSON_DIR, f)))
    return os.path.join(JSON_DIR, group_files[-1])