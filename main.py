import os
import json
import requests
from datetime import datetime
from config import GROUP_NAME, BASE_URL, MILITARY_DAY_IMAGE_PATH, JSON_DIR, PNG_DIR, MAX_FILES_TO_KEEP
from utils import calculate_academic_week, get_week_date_range, image_to_base64_uri, cleanup_old_files, \
    get_latest_schedule_file
from api import get_group_id, get_schedule_html
from parser import parse_schedule_from_js, find_military_day
from renderer import create_schedule_image
from stats import count_all_classes, compare_schedules


def choose_week_interaction():
    try:
        current_week_num = calculate_academic_week()
    except Exception as e:
        print(f"❌ Не удалось рассчитать номер текущей недели: {e}")
        return None

    next_week_num = current_week_num + 1
    current_week_dates = get_week_date_range(current_week_num)
    next_week_dates = get_week_date_range(next_week_num)

    print("\n" + "=" * 50)
    print(f"🗓️  Сейчас идет {current_week_num}-я неделя")
    print("=" * 50)
    print("Выберите неделю для загрузки:")
    print(f"  1. Текущая неделя (№ {current_week_num}) [{current_week_dates}]")
    print(f"  2. Следующая неделя (№ {next_week_num}) [{next_week_dates}]")
    print(f"  3. Выбрать конкретную неделю (из списка)")
    print("=" * 50)

    while True:
        choice = input("Введите номер (1, 2 или 3): ").strip()
        if choice == '1':
            return str(current_week_num)
        elif choice == '2':
            return str(next_week_num)
        elif choice == '3':
            print("\n📋 Список учебных недель:")
            print("-" * 40)
            max_week_show = 26 if current_week_num < 24 else 52
            for w in range(1, max_week_show + 1):
                d_range = get_week_date_range(w)
                marker = "👉" if w == current_week_num else "  "
                print(f"{marker} Неделя {w:<2} : {d_range}")
            print("-" * 40)
            while True:
                custom_week = input("Введите номер нужной недели: ").strip()
                if custom_week.isdigit() and int(custom_week) > 0: return custom_week
                print("❗️Введите корректное число.")
        else:
            print("❗️Неверный ввод. Пожалуйста, введите 1, 2 или 3.")


def main():
    session = requests.Session()
    session.headers.update({
        'User-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Referer': BASE_URL, 'X-Requested-With': 'XMLHttpRequest',
        'Origin': 'https://isu.uust.ru'})

    print("\n" + "=" * 40);
    print("Выберите действие:");
    print("  1. Получить расписание на определенную неделю");
    print("  2. Посчитать, сколько пар осталось по плану");
    print("=" * 40)

    while True:
        choice = input("Введите номер (1 или 2): ")
        if choice == '1':
            selected_week_id = choose_week_interaction()
            if not selected_week_id: break
            group_id = get_group_id(GROUP_NAME, session)
            if not group_id: break
            schedule_html = get_schedule_html(group_id, selected_week_id, session)
            if not schedule_html: break
            try:
                current_schedule, date_map, pair_num_to_time = parse_schedule_from_js(schedule_html, int(selected_week_id))
                print("📊 Расписание успешно собрано.")
            except ValueError as e:
                print(f"❌ Ошибка парсинга: {e}");
                break

            military_day_info = {}
            military_day_name = find_military_day(current_schedule)
            if military_day_name:
                print(f"✔️ Обнаружен день военной кафедры: {military_day_name}")
                military_day_info['day'] = military_day_name
                if MILITARY_DAY_IMAGE_PATH:
                    uri = image_to_base64_uri(MILITARY_DAY_IMAGE_PATH)
                    if uri:
                        print("🖼️ Используется изображение для дня военной кафедры.")
                        military_day_info['image_uri'] = uri
                        current_schedule[military_day_name] = []
                    else:
                        print("⚠️ Не удалось загрузить изображение.")
                        military_day_info['image_uri'] = None
                else:
                    military_day_info['image_uri'] = None
            else:
                print("ℹ️ День военной кафедры на этой неделе не найден.")

            latest_file = get_latest_schedule_file(GROUP_NAME)
            if latest_file:
                print(f"⚖️ Сравниваю с последней версией: {os.path.basename(latest_file)}")
                try:
                    with open(latest_file, 'r', encoding='utf-8') as f:
                        previous_schedule = json.load(f)
                    print("\n".join(compare_schedules(previous_schedule, current_schedule)))
                except (json.JSONDecodeError, FileNotFoundError):
                    print("⚠️ Не удалось прочитать старый файл.")
            else:
                print("📜 Предыдущих версий не найдено.")

            os.makedirs(JSON_DIR, exist_ok=True);
            os.makedirs(PNG_DIR, exist_ok=True)
            timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            base_filename = f"schedule_{GROUP_NAME}_{timestamp}"
            json_filename = os.path.join(JSON_DIR, f"{base_filename}.json")
            image_filename = os.path.join(PNG_DIR, f"{base_filename}.png")

            with open(json_filename, 'w', encoding='utf-8') as f:
                json.dump(current_schedule, f, ensure_ascii=False, indent=4)
            print(f"\n💾 Расписание сохранено в: {json_filename}")

            if any(current_schedule.values()):
                create_schedule_image(current_schedule, date_map, image_filename, military_day_info=military_day_info, pair_num_to_time=pair_num_to_time)
                print(f"🖼️ Изображение расписания сохранено в: {image_filename}")
            else:
                print("🖼️ Расписание пустое.")

            print("\n" + "=" * 40);
            cleanup_old_files(JSON_DIR, MAX_FILES_TO_KEEP, GROUP_NAME);
            cleanup_old_files(PNG_DIR, MAX_FILES_TO_KEEP, GROUP_NAME);
            print("=" * 40)
            break

        elif choice == '2':
            count_all_classes(GROUP_NAME, session);
            break
        else:
            print("❗️Неверный ввод.")

    print("\n🎉 Работа завершена!")


if __name__ == "__main__":
    main()