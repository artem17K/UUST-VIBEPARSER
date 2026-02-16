import re
from bs4 import BeautifulSoup
from config import SUBJECTS_TO_ALTERNATE


def find_military_day(schedule_data: dict) -> str | None:
    military_keywords = ["военная подготовка", "военная кафедра", "вуц"]
    for day, lessons in schedule_data.items():
        for lesson in lessons:
            subject_lower = lesson.get("subject", "").lower()
            if any(keyword in subject_lower for keyword in military_keywords):
                return day
    return None


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

def apply_lab_alternation(final_schedule, current_week_number: int):
    def get_sg_num(lesson):
        sg_str = lesson.get('subgroup', '').lower()
        if 'подгруппа 1' in sg_str: return 1
        if 'подгруппа 2' in sg_str: return 2
        return 0  # Нет подгруппы (или обе)

    for day, lessons in final_schedule.items():
        if len(lessons) < 2:
            continue

        sequence_counter = 0

        i = 0
        while i < len(lessons) - 1:
            curr = lessons[i]
            next_l = lessons[i + 1]

            if (curr['subject_clean'] != next_l['subject_clean'] or
                    curr['subject_clean'] not in SUBJECTS_TO_ALTERNATE):
                i += 1
                continue

            if 'лаб' not in curr['subject'].lower() or 'лаб' not in next_l['subject'].lower():
                i += 1
                continue

            sg1 = get_sg_num(curr)
            sg2 = get_sg_num(next_l)

            if sg1 == 0 and sg2 == 0:
                parity = (current_week_number + sequence_counter) % 2
                start_sg = 1 if parity != 0 else 2

                curr['subgroup'] = f'подгруппа {start_sg}'
                next_l['subgroup'] = f'подгруппа {3 - start_sg}'

                sequence_counter += 1
            elif sg1 != 0 and sg2 == 0:
                next_l['subgroup'] = f'подгруппа {3 - sg1}'

            elif sg1 == 0 and sg2 != 0:
                curr['subgroup'] = f'подгруппа {3 - sg2}'
            i += 1

    return final_schedule

def parse_schedule_from_js(html_content: str, current_week_number: int = 1) -> tuple[dict, dict]:
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

    pair_num_to_time = {}
    time_to_pair_num = {}

    rows = schedule_table.find_all("tr")
    for r in rows:
        cols = r.find_all("td")
        if len(cols) > 1 and cols[0].get_text(strip=True).isdigit():
            p_num = int(cols[0].get_text(strip=True))
            p_time = cols[1].get_text(strip=True)
            pair_num_to_time[str(p_num)] = p_time
            time_to_pair_num[p_time] = p_num

    pattern = re.compile(r"\$\('#(\d+_\d+_group)'\)\.append\('(.*?)'\);", re.DOTALL)

    for script in soup.find_all("script"):
        if not script.string: continue
        for match in pattern.finditer(script.string):
            cell_id, content_html = match.groups()
            content_html = content_html.replace('\\/', '/')
            pair_num_str, day_idx_str, _ = cell_id.split('_')
            day_idx = int(day_idx_str) - 1

            if day_idx < len(days) and pair_num_str in pair_num_to_time:
                day_name = days[day_idx]
                lesson_soup = BeautifulSoup(content_html, "html.parser")

                lines = [line for line in lesson_soup.get_text(separator='\n', strip=True).split('\n') if line]
                if not lines: continue

                specific_time = None
                if lines and re.match(r'^В \d{1,2}:\d{2}$', lines[-1].strip()):
                    specific_time = lines.pop().strip()

                subgroup = ""
                cleaned_lines = []
                for line in lines:
                    if re.search(r'подгруппа\s*\d+', line, re.IGNORECASE):
                        subgroup = line.strip().lower()
                    else:
                        cleaned_lines.append(line)
                lines = cleaned_lines

                raw_subject = lines.pop(0) if lines else ""
                m = re.match(r'(.+?)\s*\(.+\)', raw_subject)
                subject_clean_name = m.groups()[0].strip() if m else raw_subject.strip()

                teacher = lines.pop(0) if lines else ""
                room_raw = " ".join(lines).strip()

                lesson = {
                    "time": pair_num_to_time[pair_num_str],
                    "subject": raw_subject,
                    "subject_clean": subject_clean_name,
                    "teacher": teacher,
                    "room": room_raw,
                    "specific_time": specific_time,
                    "subgroup": subgroup
                }

                if 'дистант' in lesson_soup.get_text().lower():
                    lesson['room'] = 'Дистант'

                temp_schedule_data.setdefault(day_name, []).append(lesson)

    for day in temp_schedule_data:
        lessons_by_time = {}
        for l in temp_schedule_data[day]:
            lessons_by_time.setdefault(l['time'], []).append(l)

        sorted_times = sorted(lessons_by_time.keys(), key=lambda t: time_to_pair_num.get(t, 0))

        daily_subject_assignments = {}
        split_counter = 0

        for t in sorted_times:
            lessons = lessons_by_time[t]
            if len(lessons) == 2 and not lessons[0]['subgroup'] and not lessons[1]['subgroup']:
                split_counter += 1
                lessons.sort(key=lambda x: x['subject_clean'])
                sub1, sub2 = lessons[0], lessons[1]
                sub1_prev_sg = daily_subject_assignments.get(sub1['subject_clean'])
                sub2_prev_sg = daily_subject_assignments.get(sub2['subject_clean'])
                first_subject_sg = -1

                if sub1_prev_sg:
                    first_subject_sg = 3 - sub1_prev_sg
                elif sub2_prev_sg:
                    first_subject_sg = sub2_prev_sg
                else:
                    parity = (int(current_week_number) + split_counter) % 2
                    first_subject_sg = 1 if parity == 0 else 2
                sub1['subgroup'] = f"подгруппа {first_subject_sg}"
                sub2['subgroup'] = f"подгруппа {3 - first_subject_sg}"

                daily_subject_assignments[sub1['subject_clean']] = first_subject_sg
                daily_subject_assignments[sub2['subject_clean']] = 3 - first_subject_sg

    DAYS_ORDER = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"]
    final_schedule = {day: sorted(temp_schedule_data.get(day, []), key=lambda x: x['time']) for day in DAYS_ORDER if
                      day in temp_schedule_data or day in day_date_map}

    final_schedule = apply_lab_alternation(final_schedule, int(current_week_number))

    return final_schedule, day_date_map