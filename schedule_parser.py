import os
import json
import re
import requests
import imgkit
from bs4 import BeautifulSoup
from datetime import datetime, date, timedelta
import base64
import mimetypes

# --- Настройки ---

GROUP_NAME = "" # ВВЕДИТЕ НАЗВАНИЕ ГРУППЫ например "ПИ-101Б"
API_URL = "https://isu.uust.ru/module/schedule/schedule_2024_script.php" # если поменяется надо будет поменять (надеюсь не поменяется)
BASE_URL = "https://isu.uust.ru/schedule_2024/"

# ОПЦИОНАЛЬНО
# Укажите свой учебный план (необязательно, только для функции подсчёта оставшихся часов)
PLANNED_CLASSES = {
    "Базы данных": {"Лекция": 18, "Практика": 0, "Лабораторная": 18},
    "Интернет-программирование": {"Лекция": 9, "Практика": 0, "Лабораторная": 18},
    "Математические методы принятия решений": {"Лекция": 9, "Практика": 0, "Лабораторная": 9},
    "Нечеткая логика": {"Лекция": 9, "Практика": 0, "Лабораторная": 9},
    "Разработка Web-приложений": {"Лекция": 9, "Практика": 0, "Лабораторная": 9},
    "Численные методы решения экстремальных задач": {"Лекция": 9, "Практика": 0, "Лабораторная": 9},
    "Комплексный и функциональный анализ": {"Лекция": 18, "Практика": 0, "Лабораторная": 18},
    "Теория вероятностей и математическая статистика": {"Лекция": 9, "Практика": 9, "Лабораторная": 18},
    "Программная инженерия": {"Лекция": 9, "Практика": 0, "Лабораторная": 9},
    "Проектирование информационных систем": {"Лекция": 9, "Практика": 0, "Лабораторная": 18},
    "Вычислительные методы и программирование": {"Лекция": 9, "Практика": 0, "Лабораторная": 9},
    "Информационная безопасность": {"Лекция": 6, "Практика": 0, "Лабораторная": 12},
    "Информационное право": {"Лекция": 9, "Практика": 9, "Лабораторная": 0},
    "Общая физическая подготовка": {"Лекция": 0, "Практика": 11, "Лабораторная": 0},
    "Военная подготовка": {"Практика": 36, "Лекция": 0, "Лабораторная": 0},
}

# Настройки хранения файлов
SCHEDULE_DIR = "schedules"
JSON_DIR = os.path.join(SCHEDULE_DIR, "json")
PNG_DIR = os.path.join(SCHEDULE_DIR, "png")
MAX_FILES_TO_KEEP = 2

# ВАЖНО: Укажите здесь СВОЙ путь к wkhtmltoimage.exe
WKHTMLTOIMAGE_PATH = r"C:\Program Files\wkhtmltopdf\bin\wkhtmltoimage.exe"

# ОПЦИОНАЛЬНО
# Указать путь к картинке, которая вставится поверх дня с военной кафедрой
# Например: MILITARY_DAY_IMAGE_PATH = r"C:\Program Files\cat.jpg"
MILITARY_DAY_IMAGE_PATH = None


# -----------------

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


def choose_week_interaction() -> str | None:
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
                if custom_week.isdigit() and int(custom_week) > 0:
                    return custom_week
                print("❗️Введите корректное число.")
        else:
            print("❗️Неверный ввод. Пожалуйста, введите 1, 2 или 3.")


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


def get_group_id(group_name: str, session: requests.Session) -> str | None:
    payload = {'text_search_group': group_name.lower(), 'week': '1', 'funct': 'filter_group'}
    try:
        response = session.post(API_URL, data=payload)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        for button in soup.find_all('button', class_='link-button'):
            if button.get_text(strip=True) == group_name:
                match = re.search(r'link_group\((\d+),', button.get('onclick', ''))
                if match: return match.group(1)
        raise ValueError(f"Группа '{group_name}' не найдена.")
    except (requests.RequestException, ValueError) as e:
        print(f"❌ Ошибка при поиске ID группы: {e}")
        return None


def get_schedule_html(group_id: str, week_id: str, session: requests.Session) -> str | None:
    payload = {'group_id': group_id, 'week': week_id, 'funct': 'group', 'show_temp': '0'}
    try:
        response = session.post(API_URL, data=payload)
        response.raise_for_status()
        if not response.text.strip(): raise ValueError("Сервер вернул пустой ответ.")
        return response.text
    except (requests.RequestException, ValueError) as e:
        print(f"❌ Ошибка при загрузке расписания для недели №{week_id}: {e}")
        return None


def find_military_day(schedule_data: dict) -> str | None:
    military_keywords = ["военная подготовка", "военная кафедра", "вуц"]
    for day, lessons in schedule_data.items():
        for lesson in lessons:
            subject_lower = lesson.get("subject", "").lower()
            if any(keyword in subject_lower for keyword in military_keywords):
                return day
    return None


def parse_schedule_from_js(html_content: str) -> tuple[dict, dict]:
    soup = BeautifulSoup(html_content, "html.parser")
    temp_schedule_data = {}
    schedule_table = soup.find("table", class_="table table-bordered")
    if not schedule_table: raise ValueError("Таблица расписания не найдена в HTML.")

    headers = schedule_table.find("thead").find_all("th")

    days = []
    day_date_map = {}

    for th in headers[2:]:
        raw_text = th.get_text(strip=True)
        match = re.match(r'([А-Яа-я]+).*?(\d{2}\.\d{2})', raw_text)
        if match:
            day_name, date_short = match.groups()
            days.append(day_name)
            day_date_map[day_name] = date_short
        else:
            day_name = raw_text.split('(')[0].strip()
            days.append(day_name)
            day_date_map[day_name] = ""

    time_map = {c[0].get_text(strip=True): c[1].get_text(strip=True)
                for r in schedule_table.find_all("tr") if
                (c := r.find_all("td")) and len(c) > 1 and c[0].get_text(strip=True).isdigit()}

    pattern = re.compile(r"\$\('#(\d+_\d+_group)'\)\.append\('(.*?)'\);", re.DOTALL)

    for script in soup.find_all("script"):
        if not script.string: continue
        for match in pattern.finditer(script.string):
            cell_id, content_html = match.groups()
            content_html = content_html.replace('\\/', '/')
            pair_num_str, day_idx_str, _ = cell_id.split('_')
            day_idx = int(day_idx_str) - 1

            if day_idx < len(days) and pair_num_str in time_map:
                day_name = days[day_idx]
                lesson_soup = BeautifulSoup(content_html, "html.parser")
                lines = [line for line in lesson_soup.get_text(separator='\n', strip=True).split('\n') if line]
                if not lines: continue

                specific_time = lines.pop() if lines and re.match(r'^В \d{1,2}:\d{2}$', lines[-1].strip()) else None
                subject = lines.pop(0) if lines else ""
                teacher = lines.pop(0) if lines else ""
                room_raw = " ".join(lines).strip()

                lesson = {
                    "time": time_map[pair_num_str],
                    "subject": subject,
                    "teacher": teacher,
                    "room": room_raw,
                    "specific_time": specific_time
                }
                if 'дистант' in lesson_soup.get_text().lower(): lesson['room'] = 'Дистант'
                temp_schedule_data.setdefault(day_name, []).append(lesson)

    DAYS_ORDER = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"]
    final_schedule = {day: sorted(temp_schedule_data.get(day, []), key=lambda x: x['time']) for day in DAYS_ORDER if
                      day in temp_schedule_data or day in day_date_map}

    return final_schedule, day_date_map


def create_schedule_image(schedule_data, day_date_map, image_filename, military_day_info=None):
    TIME_COL_WIDTH, DAY_COL_WIDTH = "80px", "325px"
    TOTAL_IMAGE_WIDTH = (int(TIME_COL_WIDTH.replace('px', '')) + int(DAY_COL_WIDTH.replace('px', ''))) * 3

    html_style = f"""<style>
        body{{font-family:'Tahoma',serif;background-color:#fff;margin:0}}
        .multi-day-table{{width:100%;border-collapse:collapse;table-layout:fixed}}
        .multi-day-table th,.multi-day-table td{{border:1px solid #000;padding:5px;text-align:center;vertical-align:top;font-size:13pt}}
        .multi-day-table .time-cell {{ font-size: 16pt; vertical-align:middle; }}
        .room-text {{ font-size: 15pt; }}
        .subject-text {{ font-size: 15pt; }}
        .lesson-type-text {{ font-size: 15pt; }}
        .specific-time {{ font-size: 14pt; font-weight: bold; color: #cc0000; margin-top: 5px; margin-bottom: 2px; }}
        .lesson-cell {{ position: relative; padding-bottom: 30px !important; }}
        .teacher-name {{ position: absolute; bottom: 5px; left: 0; right: 0; width: 100%; font-size: 13pt; color: #444; }}
        .day-header {{ font-weight:700; position: relative; }}
        .date-badge {{ position: absolute; top: 6px; right: 5px; font-size: 12pt; font-weight: 700; background-color: rgba(255,255,255,0.7); padding: 0 3px; border-radius: 4px; }}
        .multi-day-table td.multi-lesson{{padding:0}}
        .nested-table{{width:100%;height:100%;border-collapse:collapse}}
        .nested-table td{{border:none;padding:5px;vertical-align:middle}}
        .nested-row{{border-bottom:1px solid #000}}
        .multi-day-table.thick-border-bottom{{border-bottom:1px solid #000}}
        .multi-day-table .day-header,.multi-day-table .date-pair-header{{border-bottom:2px solid #000}}
        .multi-day-table .thick-border-right{{border-right:2px solid #000}}
        .lesson-row{{height:136px}}
        .lecture-bg{{background-color:#DDEBF7}}
        .practice-bg{{background-color:#FCE4D6}}
        .lab-bg{{background-color:#CCCCFF}}
        .exam-bg{{background-color:#FFD5D5}}
        .default-bg{{background-color:#fff}}
        .military-day-bg {{ background-color: #e2f0d9; vertical-align: middle; font-size: 24pt; font-weight: bold; color: #000; }}
        .military-lesson-bg {{ background-color: #e2f0d9; vertical-align: top; }}
        .image-cell{{padding:0;background-size:cover;background-position:center;background-repeat:no-repeat}}
    </style>"""

    all_times = sorted(list(set(l['time'] for day in schedule_data.values() for l in day)))
    military_day_name = military_day_info.get('day') if military_day_info else None
    military_day_image_uri = military_day_info.get('image_uri') if military_day_info else None

    def get_lesson_color_class(s):
        s = s.lower()
        if 'военная подготовка' in s: return 'military-lesson-bg'
        if 'зачёт' in s or 'зачет' in s: return 'exam-bg'
        if 'лекция' in s: return 'lecture-bg'
        if 'практика' in s or 'семинар' in s: return 'practice-bg'
        if 'лабораторная' in s: return 'lab-bg'
        return 'default-bg'

    def format_room_text(s):
        if not s or s == "N/A": return ""
        s_lower = s.lower()
        if 'дистант' in s_lower: return 'Дистант'
        if 'спорткомплекс' in s_lower: return 'Спорткомплекс'
        s = re.sub(r'подгруппа\s*\d+', '', s, flags=re.IGNORECASE)
        s = re.sub(r'[\s-]*уточняется', '', s, flags=re.IGNORECASE)
        if 'заки валиди 32/1' in s_lower:
            n = re.findall(r'\d+[а-яА-Я]?', s)
            return f"Ауд. {n[-1]}" if n else "Физмат"
        s = s.replace('(', ' ').replace(')', ' ')
        if '-' in s:
            parts = s.rsplit('-', 1)
            address, room = parts[0].strip(), parts[1].strip()
            if re.match(r'^\d+[а-яА-Я]?$', room): return f"{' '.join(address.split())} ауд. {room}"
        return " ".join(s.split())

    def get_lesson_type_formatted(type_str):
        type_str_lower = type_str.lower()
        if 'зачёт' in type_str_lower or 'зачет' in type_str_lower: return "(Зачёт)"
        if 'лекция' in type_str_lower: return "(Лекция)"
        if 'практика' in type_str_lower: return "(Практика)"
        if 'семинар' in type_str_lower: return "(Семинар)"
        if 'лабораторная' in type_str_lower: return "(Лаба)"
        return ""

    def generate_lesson_cell_html(lessons):
        def format_lesson_content(l):
            if 'военная подготовка' in l['subject'].lower():
                return f"<div style='padding-top: 20px; color: #000;'><span class='subject-text'><strong>Военная подготовка</strong></span></div>"

            m = re.match(r'(.+?)\s*\((.+)\)', l['subject'])
            subject_name, subject_type_raw = m.groups() if m else (l['subject'], '')
            type_html = f"<br><span class='lesson-type-text'>{get_lesson_type_formatted(subject_type_raw)}</span>" if subject_type_raw else ""
            room = format_room_text(l['room'])
            specific_time_html = f"<div class='specific-time'>{l['specific_time']}</div>" if l.get(
                'specific_time') else ""
            room_html = f"<span class='room-text'>{room}</span>" if room else ""
            main_content_html = f"<br><span class='subject-text'><strong>{subject_name.strip()}</strong></span>{type_html}{specific_time_html}{'' if specific_time_html else '<br>'}{room_html}"
            teacher_html = f"<div class='teacher-name'>{l['teacher']}</div>" if l.get('teacher') and l[
                'teacher'].strip() not in ('N/A', '') else ""
            return main_content_html + teacher_html

        if not lessons: return ''
        if len(lessons) == 1: return format_lesson_content(lessons[0])
        h = '<table class="nested-table">'
        t, b = lessons[0], lessons[1]
        h += f'<tr class="nested-row {get_lesson_color_class(t["subject"])}"><td>{format_lesson_content(t)}</td></tr>'
        h += f'<tr class="{get_lesson_color_class(b["subject"])}"><td>{format_lesson_content(b)}</td></tr>'
        h += '</table>'
        return h

    def get_visible_times_for_days(days, times, data):
        idx = -1
        for i in range(len(times) - 1, -1, -1):
            current_time = times[i]
            has_lesson = False
            for d in days:
                if d in data:
                    for lesson in data[d]:
                        if lesson['time'] == current_time:
                            has_lesson = True
                            break
                if has_lesson: break

            if has_lesson:
                idx = i
                break

        if idx == -1: return []
        return times[:idx + 1]

    def generate_days_row_html(days, data, times, is_top, tw, dw):
        h = f'<table class="{"multi-day-table thick-border-bottom" if is_top else "multi-day-table"}"><thead><tr>'
        for i, d in enumerate(days):
            header_content = f"{d}<div class='date-badge'>{day_date_map.get(d, '')}</div>"
            h += f'<th class="date-pair-header" style="width:{tw};"><strong>Время</strong></th>'
            h += f'<th class="{"day-header thick-border-right" if i < len(days) - 1 else "day-header"}" style="width:{dw};">{header_content}</th>'
        h += '</tr></thead><tbody>'

        has_content_in_days = any(data.get(d) for d in days)
        if not has_content_in_days:
            h += f'<tr><td colspan="{len(days) * 2}" style="height:100px;vertical-align:middle;">Пар нет</td></tr>'
            h += "</tbody></table>"
            return h

        mil_day_cell_added = False
        for t in times:
            h += '<tr class="lesson-row">'
            for i, d in enumerate(days):
                if d == military_day_name and military_day_image_uri:
                    if not mil_day_cell_added:
                        rowspan = len(times) if times else 1
                        border_class = "thick-border-right" if i < len(days) - 1 else ""
                        h += f'<td colspan="2" rowspan="{rowspan}" class="image-cell {border_class}" style="background-image:url({military_day_image_uri});"></td>'
                        mil_day_cell_added = True
                    continue

                h += f'<td class="time-cell">{t.replace("-", "<br>-<br>")}</td>'
                ls = [l for l in data.get(d, []) if l['time'] == t]
                cls = ["lesson-cell"]
                cls.append("thick-border-right" if i < len(days) - 1 else "")
                cls.append(
                    "multi-lesson" if len(ls) > 1 else get_lesson_color_class(ls[0]['subject']) if ls else "default-bg")
                h += f'<td class="{" ".join(cls)}">{generate_lesson_cell_html(ls)}</td>'
            h += '</tr>'
        h += "</tbody></table>"
        return h

    top_days, bottom_days = ["Понедельник", "Вторник", "Среда"], ["Четверг", "Пятница", "Суббота"]
    visible_top = get_visible_times_for_days(top_days, all_times, schedule_data)
    visible_bottom = get_visible_times_for_days(bottom_days, all_times, schedule_data)
    html_body = generate_days_row_html(top_days, schedule_data, visible_top, True, TIME_COL_WIDTH, DAY_COL_WIDTH)
    html_body += generate_days_row_html(bottom_days, schedule_data, visible_bottom, False, TIME_COL_WIDTH,
                                        DAY_COL_WIDTH)
    full_html = f"<!DOCTYPE html><html><head><meta charset='UTF-8'>{html_style}</head><body>{html_body}</body></html>"
    try:
        config = imgkit.config(wkhtmltoimage=WKHTMLTOIMAGE_PATH)
        options = {'width': TOTAL_IMAGE_WIDTH, 'encoding': "UTF-8", 'disable-smart-width': '', 'quiet': ''}
        imgkit.from_string(full_html, image_filename, options=options, config=config)
    except Exception as e:
        print(f"❌ Ошибка при создании изображения: {e}\n    Убедись, что путь в WKHTMLTOIMAGE_PATH указан верно.")


def get_latest_schedule_file(group_name: str) -> str | None:
    if not os.path.exists(JSON_DIR): return None
    group_files = [f for f in os.listdir(JSON_DIR) if f.startswith(f"schedule_{group_name}_") and f.endswith(".json")]
    return os.path.join(JSON_DIR, sorted(group_files)[-1]) if group_files else None


def compare_schedules(old_schedule: dict, new_schedule: dict) -> list[str]:
    changes = []
    all_days = sorted(list(set(old_schedule.keys()) | set(new_schedule.keys())),
                      key=["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"].index)
    for day in all_days:
        old_set = {tuple(sorted(d.items())) for d in old_schedule.get(day, [])}
        new_set = {tuple(sorted(d.items())) for d in new_schedule.get(day, [])}
        if old_set != new_set:
            day_changes, added, removed = [], new_set - old_set, old_set - new_set
            if added: day_changes.extend(f"  [+] Добавлено: {dict(l)['time']} - {dict(l)['subject']}" for l in added)
            if removed: day_changes.extend(f"  [-] Убрано: {dict(l)['time']} - {dict(l)['subject']}" for l in removed)
            if day_changes: changes.extend([f"\nИзменения на {day}:", *sorted(day_changes)])
    return changes or ["\n✅ Расписание не изменилось.\n"]


def cleanup_old_files(directory: str, max_files: int, group_name: str):
    if not os.path.exists(directory): return
    files = sorted([f for f in os.listdir(directory) if f.startswith(f"schedule_{group_name}_")])
    if len(files) > max_files:
        for filename in files[:-max_files]:
            try:
                os.remove(os.path.join(directory, filename))
            except OSError as e:
                print(f"    - ❌ Не удалось удалить {filename}: {e}")


def count_all_classes(group_name: str, session: requests.Session):
    print("🚀 Начинаю подсчет всех прошедших пар. Это может занять некоторое время...")
    group_id = get_group_id(group_name, session)
    if not group_id: return
    try:
        current_week = calculate_academic_week()
    except Exception as e:
        print(f"❌ Не удалось рассчитать номер текущей недели: {e}"); return

    class_counts = {}

    def get_lesson_type(subject_str):
        s = subject_str.lower()
        if 'военная подготовка' in s or 'вуц' in s: return "Практика"
        if 'лекция' in s or 'лек.' in s: return "Лекция"
        if 'практика' in s or 'прак.' in s: return "Практика"
        if 'семинар' in s: return "Семинар"
        if 'лабораторная' in s or 'лаб.' in s: return "Лабораторная"
        return "Другое"

    def get_subject_name(subject_full):
        s_lower = subject_full.lower()
        if 'военная подготовка' in s_lower or 'вуц' in s_lower:
            return "Военная подготовка"
        match = re.match(r'(.+?)\s*\(.+\)', subject_full)
        return match.groups()[0].strip() if match else subject_full.strip()

    for week_num in range(1, current_week + 1):
        print(f"    - Обрабатываю неделю №{week_num} из {current_week}...")
        schedule_html = get_schedule_html(group_id, str(week_num), session)
        if not schedule_html:
            print(f"    ⚠️ Не удалось получить расписание для недели №{week_num}. Пропускаю.");
            continue
        try:
            weekly_schedule, _ = parse_schedule_from_js(schedule_html)
        except ValueError:
            print(f"    ℹ️ На неделе №{week_num} нет пар или не удалось ее распарсить.");
            continue

        for day, lessons in weekly_schedule.items():
            for lesson in lessons:
                subject_name = get_subject_name(lesson.get("subject", "N/A"))
                lesson_type = get_lesson_type(lesson.get("subject", "N/A"))
                if subject_name not in class_counts:
                    class_counts[subject_name] = {"Лекция": 0, "Практика": 0, "Лабораторная": 0, "Семинар": 0,
                                                  "Другое": 0}
                if lesson_type in class_counts[subject_name]:
                    class_counts[subject_name][lesson_type] += 1

    print("\n" + "=" * 60);
    print("📊 СТАТИСТИКА ПО ПРЕДМЕТАМ (СКОЛЬКО ПАР ОСТАЛОСЬ)");
    print("=" * 60)
    unplanned_subjects = {}
    all_subject_names = sorted(list(PLANNED_CLASSES.keys() | class_counts.keys()))

    for subject in all_subject_names:
        if subject not in PLANNED_CLASSES:
            unplanned_subjects[subject] = class_counts[subject];
            continue
        planned = PLANNED_CLASSES[subject]
        past = class_counts.get(subject, {"Лекция": 0, "Практика": 0, "Лабораторная": 0})
        total_planned, total_past = sum(planned.values()), sum(past.values())
        if total_planned == 0 and total_past == 0: continue
        print(f"\n🔹 {subject} [Прошло {total_past} из {total_planned}]")
        details = []
        for class_type, type_name_plural in [("Лекция", "Лекций"), ("Практика", "Практик"),
                                             ("Лабораторная", "Лабораторных")]:
            planned_count = planned.get(class_type, 0)
            if planned_count == 0: continue
            remaining_count = planned_count - past.get(class_type, 0)
            details.append(
                f"{type_name_plural} осталось: {remaining_count} (прошло {past.get(class_type, 0)} из {planned_count})")
        if details: print("    " + ", ".join(details))
    if unplanned_subjects:
        print("\n" + "=" * 60);
        print("⚠️ ОБНАРУЖЕНЫ ВНЕПЛАНОВЫЕ ЗАНЯТИЯ");
        print("Этих предметов не было в вашем списке `PLANNED_CLASSES`:");
        print("=" * 60)
        for subject, types in unplanned_subjects.items():
            details = [f"{k}: {v}" for k, v in types.items() if v > 0]
            print(f"\n🔹 {subject} (Всего прошло: {sum(types.values())})");
            print("    " + ", ".join(details))
    print("\n" + "=" * 60)


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
                current_schedule, date_map = parse_schedule_from_js(schedule_html)
                print("📊 Расписание успешно собрано.")
            except ValueError as e:
                print(f"❌ Ошибка парсинга: {e}"); break

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
                        print("⚠️ Не удалось загрузить изображение. День будет отображен стандартно (парами).")
                        military_day_info['image_uri'] = None
                else:
                    print("ℹ️ День военной кафедры будет отображен в виде отдельных пар. Картинка не указана.")
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
                    print("⚠️ Не удалось прочитать старый файл. Сравнение пропущено.")
            else:
                print("📜 Предыдущих версий не найдено. Это первый запуск.")

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
                create_schedule_image(current_schedule, date_map, image_filename, military_day_info=military_day_info)
                print(f"🖼️ Изображение расписания сохранено в: {image_filename}")
            else:
                print("🖼️ Расписание пустое, изображение не создано.")
            print("\n" + "=" * 40);
            cleanup_old_files(JSON_DIR, MAX_FILES_TO_KEEP, GROUP_NAME);
            cleanup_old_files(PNG_DIR, MAX_FILES_TO_KEEP, GROUP_NAME);
            print("=" * 40)
            break
        elif choice == '2':
            count_all_classes(GROUP_NAME, session); break
        else:
            print("❗️Неверный ввод. Пожалуйста, введите 1 или 2.")
    print("\n🎉 Работа завершена!")


if __name__ == "__main__":
    main()