import os
import json
import requests
from datetime import datetime
from config import (
    GROUP_NAME, MILITARY_DAY_IMAGE_PATH, JSON_DIR, PNG_DIR,
    MAX_FILES_TO_KEEP, SUBJECTS_TO_ALTERNATE,
)
from utils import (
    calculate_academic_week, get_week_date_range, image_to_base64_uri,
    cleanup_old_files, get_latest_schedule_file,
    get_current_academic_year_start, get_academic_year_start
)
from api import get_group_id, get_schedule_html, make_session
from parser import parse_schedule_from_js, find_military_day
from renderer import create_schedule_image
from stats import count_all_classes, compare_schedules


def choose_week_interaction() -> str | None:
    try:
        current = calculate_academic_week()
        year_start = get_current_academic_year_start()
        next_year_start = get_academic_year_start(year_start.year + 1)
        total_weeks = (next_year_start - year_start).days // 7

    except Exception as e:
        print(f"❌ Не удалось рассчитать номер текущей недели: {e}")
        return None

    nxt = current + 1
    nxt_year_offset = 0
    if nxt > total_weeks:
        nxt = 1
        nxt_year_offset = 1

    print("\n" + "=" * 50)
    print(f"🗓️  Сейчас идет {current}-я неделя")
    print("=" * 50)
    print("Выберите неделю для загрузки:")
    print(f"  1. Текущая неделя (№ {current}) [{get_week_date_range(current)}]")
    print(f"  2. Следующая неделя (№ {nxt}) [{get_week_date_range(nxt, nxt_year_offset)}]")
    print(f"  3. Выбрать конкретную неделю (из списка)")
    print("=" * 50)

    while True:
        choice = input("Введите номер (1, 2 или 3): ").strip()
        if choice == '1':
            return str(current)
        if choice == '2':
            return str(nxt)
        if choice == '3':
            return _pick_specific_week(current, total_weeks)
        print("❗️Неверный ввод. Пожалуйста, введите 1, 2 или 3.")


def _pick_specific_week(current_week: int, total_weeks: int) -> str:
    print("\n📋 Список учебных недель:")
    print("-" * 40)
    max_show = 26 if current_week < 24 else total_weeks
    for w in range(1, max_show + 1):
        marker = "👉" if w == current_week else "  "
        print(f"{marker} Неделя {w:<2} : {get_week_date_range(w)}")
    print("-" * 40)
    while True:
        custom = input("Введите номер нужной недели: ").strip()
        if custom.isdigit() and int(custom) > 0:
            return custom
        print("❗️Введите корректное число.")


def _prepare_military_info(schedule: dict) -> dict:
    info = {}
    day = find_military_day(schedule)
    if not day:
        print("ℹ️ День военной кафедры на этой неделе не найден.")
        return info

    print(f"✔️ Обнаружен день военной кафедры: {day}")
    info['day'] = day

    if not MILITARY_DAY_IMAGE_PATH:
        info['image_uri'] = None
        return info

    uri = image_to_base64_uri(MILITARY_DAY_IMAGE_PATH)
    if uri:
        print("🖼️ Используется изображение для дня военной кафедры.")
        info['image_uri'] = uri
    else:
        print("⚠️ Не удалось загрузить изображение.")
        info['image_uri'] = None
    return info


def _compare_with_previous(group_name: str, current_schedule: dict):
    latest = get_latest_schedule_file(group_name)
    if not latest:
        print("📜 Предыдущих версий не найдено.")
        return
    print(f"⚖️ Сравниваю с последней версией: {os.path.basename(latest)}")
    try:
        with open(latest, 'r', encoding='utf-8') as f:
            previous = json.load(f)
        print("\n".join(compare_schedules(previous, current_schedule)))
    except (json.JSONDecodeError, OSError):
        print("⚠️ Не удалось прочитать старый файл.")


def _save_schedule(group_name: str, schedule: dict, date_map: dict,
                   military_info: dict, pair_num_to_time: dict):
    os.makedirs(JSON_DIR, exist_ok=True)
    os.makedirs(PNG_DIR, exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    base = f"schedule_{group_name}_{timestamp}"
    json_path = os.path.join(JSON_DIR, f"{base}.json")
    png_path = os.path.join(PNG_DIR, f"{base}.png")

    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(schedule, f, ensure_ascii=False, indent=4)
    print(f"\n💾 Расписание сохранено в: {json_path}")

    if any(schedule.values()):
        create_schedule_image(
            schedule, date_map, png_path,
            military_day_info=military_info,
            pair_num_to_time=pair_num_to_time,
        )
        print(f"🖼️ Изображение расписания сохранено в: {png_path}")
    else:
        print("🖼️ Расписание пустое.")


def run_for_week(group_name: str, week_id: str, session: requests.Session) -> bool:
    group_id = get_group_id(group_name, session)
    if not group_id:
        return False
    html = get_schedule_html(group_id, week_id, session)
    if not html:
        return False
    try:
        parsed = parse_schedule_from_js(
            html, int(week_id), alternation_subjects=SUBJECTS_TO_ALTERNATE
        )
    except ValueError as e:
        print(f"❌ Ошибка парсинга: {e}")
        return False
    print("📊 Расписание успешно собрано.")

    schedule = parsed.days
    military_info = _prepare_military_info(schedule)
    _compare_with_previous(group_name, schedule)
    _save_schedule(group_name, schedule, parsed.date_map, military_info, parsed.pair_num_to_time)

    print("\n" + "=" * 40)
    cleanup_old_files(JSON_DIR, MAX_FILES_TO_KEEP, group_name)
    cleanup_old_files(PNG_DIR, MAX_FILES_TO_KEEP, group_name)
    print("=" * 40)
    return True


def main():
    session = make_session()

    print("\n" + "=" * 40)
    print("Выберите действие:")
    print("  1. Получить расписание на определенную неделю")
    print("  2. Посчитать, сколько пар осталось по плану")
    print("=" * 40)

    while True:
        choice = input("Введите номер (1 или 2): ").strip()
        if choice == '1':
            week_id = choose_week_interaction()
            if week_id:
                run_for_week(GROUP_NAME, week_id, session)
            break
        if choice == '2':
            count_all_classes(GROUP_NAME, session)
            break
        print("❗️Неверный ввод.")

    print("\n🎉 Работа завершена!")


if __name__ == "__main__":
    main()