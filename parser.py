import re
from dataclasses import dataclass, asdict
from bs4 import BeautifulSoup

DAYS_ORDER = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"]

_TIME_PREFIXED_RE = re.compile(r'^[Вв]\s+(\d{1,2}:\d{2})$')
_TIME_BARE_RE = re.compile(r'^(\d{1,2}:\d{2})$')
_SUBGROUP_RE = re.compile(r'подгруппа\s*(\d+)', re.IGNORECASE)
_APPEND_RE = re.compile(r"\$\('#(\d+_\d+_group)'\)\.append\('(.*?)'\);", re.DOTALL)
_DAY_HEADER_RE = re.compile(r'([А-Яа-я]+).*?(\d{2}\.\d{2})')


@dataclass
class Lesson:
    time: str
    subject: str
    subject_clean: str
    teacher: str
    room: str
    specific_time: str | None = None
    subgroup: int = 0

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ParsedSchedule:
    days: dict
    date_map: dict
    pair_num_to_time: dict


def split_subject_and_type(raw: str) -> tuple[str, str]:
    s = (raw or "").strip()
    if not s:
        return s, ''

    end_idx = s.rfind(')')
    if end_idx == -1:
        return s, ''

    depth = 0
    for i in range(end_idx, -1, -1):
        ch = s[i]
        if ch == ')':
            depth += 1
        elif ch == '(':
            depth -= 1
            if depth == 0:
                name = s[:i].strip()
                type_str = s[i + 1:end_idx].strip()
                trailing = s[end_idx + 1:].strip()

                if not name:
                    return s, ''
                if trailing:
                    name += " " + trailing

                return name, type_str

    return s, ''


def find_military_day(schedule_data: dict) -> str | None:
    keywords = ("военная подготовка", "военная кафедра", "вуц")
    for day, lessons in schedule_data.items():
        for lesson in lessons:
            subject_lower = lesson.get("subject", "").lower()
            if any(k in subject_lower for k in keywords):
                return day
    return None


def get_lesson_type(subject_str: str) -> str:
    s = (subject_str or "").lower()
    if 'военная подготовка' in s or 'вуц' in s:
        return "Практика"
    _, type_str = split_subject_and_type(subject_str)
    t = type_str.lower()
    if 'лекция' in t or 'лек.' in t:
        return "Лекция"
    if 'практика' in t or 'прак.' in t:
        return "Практика"
    if 'семинар' in t:
        return "Семинар"
    if 'лабораторная' in t or 'лаб.' in t:
        return "Лабораторная"
    return "Другое"


def get_subject_name(subject_full: str) -> str:
    s_lower = (subject_full or "").lower()
    if 'военная подготовка' in s_lower or 'вуц' in s_lower:
        return "Военная подготовка"
    name, _ = split_subject_and_type(subject_full)
    return name


def _extract_days(table) -> tuple[list[str], dict[str, str]]:
    headers = table.find("thead").find_all("th")
    days = []
    date_map = {}
    for th in headers[2:]:
        raw = th.get_text(strip=True)
        m = _DAY_HEADER_RE.match(raw)
        if m:
            day_name, date_short = m.groups()
            days.append(day_name)
            date_map[day_name] = date_short
        else:
            day_name = raw.split('(')[0].strip()
            days.append(day_name)
            date_map[day_name] = ""
    return days, date_map


def _extract_pair_times(table) -> tuple[dict[str, str], dict[str, int]]:
    pair_num_to_time = {}
    time_to_pair_num = {}
    for row in table.find_all("tr"):
        cols = row.find_all("td")
        if len(cols) > 1 and cols[0].get_text(strip=True).isdigit():
            p_num = int(cols[0].get_text(strip=True))
            p_time = cols[1].get_text(strip=True)
            pair_num_to_time[str(p_num)] = p_time
            time_to_pair_num[p_time] = p_num
    return pair_num_to_time, time_to_pair_num


def _extract_specific_time(lines: list[str]) -> str | None:
    if not lines:
        return None
    last = lines[-1].strip().rstrip('.')
    m_pref = _TIME_PREFIXED_RE.match(last)
    if m_pref:
        lines.pop()
        return f"В {m_pref.group(1)}"
    m_bare = _TIME_BARE_RE.match(last)
    if m_bare:
        lines.pop()
        return f"В {m_bare.group(1)}"
    return None


def _extract_subgroup(lines: list[str]) -> tuple[int, list[str]]:
    subgroup = 0
    cleaned = []
    for line in lines:
        m = _SUBGROUP_RE.search(line)
        if m:
            subgroup = int(m.group(1))
        else:
            cleaned.append(line)
    return subgroup, cleaned


def _parse_lesson_block(content_html: str, time_str: str) -> Lesson | None:
    soup = BeautifulSoup(content_html, "html.parser")

    teacher = ""
    room = ""
    for button in soup.find_all('button', class_='link-button'):
        onclick = button.get('onclick', '')
        btn_text = button.get_text(strip=True)
        if 'link_teacher' in onclick:
            teacher = btn_text
        elif 'link_class' in onclick:
            room = btn_text
            if "Уточняется" in room:
                room = "Уточняется"
        button.extract()

    lines = [ln for ln in soup.get_text(separator='\n', strip=True).split('\n') if ln.strip()]
    if not lines:
        return None

    specific_time = _extract_specific_time(lines)
    subgroup, lines = _extract_subgroup(lines)

    lines = [ln for ln in lines if ln.lower() not in ('дистанционно', 'дистант')]

    raw_subject = lines.pop(0) if lines else ""
    subject_clean, _ = split_subject_and_type(raw_subject)

    if lines:
        raw_subject += " " + " ".join(lines)

    return Lesson(
        time=time_str,
        subject=raw_subject,
        subject_clean=subject_clean,
        teacher=teacher,
        room=room,
        specific_time=specific_time,
        subgroup=subgroup,
    )


def _assign_split_subgroups(temp: dict[str, list[Lesson]],
                            time_to_pair_num: dict[str, int],
                            current_week: int) -> None:
    for day, lessons in temp.items():
        by_time: dict[str, list[Lesson]] = {}
        for l in lessons:
            by_time.setdefault(l.time, []).append(l)

        sorted_times = sorted(by_time.keys(), key=lambda t: time_to_pair_num.get(t, 0))
        daily_assigned: dict[str, int] = {}
        split_counter = 0

        for t in sorted_times:
            pair_lessons = by_time[t]
            if len(pair_lessons) != 2:
                continue
            if pair_lessons[0].subgroup or pair_lessons[1].subgroup:
                continue

            split_counter += 1
            pair_lessons.sort(key=lambda x: x.subject_clean)
            a, b = pair_lessons
            prev_a = daily_assigned.get(a.subject_clean)
            prev_b = daily_assigned.get(b.subject_clean)

            if prev_a:
                first = 3 - prev_a
            elif prev_b:
                first = prev_b
            else:
                first = 1 if (current_week + split_counter) % 2 == 0 else 2

            a.subgroup = first
            b.subgroup = 3 - first
            daily_assigned[a.subject_clean] = first
            daily_assigned[b.subject_clean] = 3 - first


def _apply_lab_alternation(schedule: dict[str, list[Lesson]],
                           current_week: int,
                           alternation_subjects: list[str]) -> None:
    if not alternation_subjects:
        return
    alt_set = set(alternation_subjects)
    for day, lessons in schedule.items():
        if len(lessons) < 2:
            continue
        seq = 0
        i = 0
        while i < len(lessons) - 1:
            curr, nxt = lessons[i], lessons[i + 1]
            same_subject = (curr.subject_clean == nxt.subject_clean
                            and curr.subject_clean in alt_set)
            both_lab = 'лаб' in curr.subject.lower() and 'лаб' in nxt.subject.lower()
            if not (same_subject and both_lab):
                i += 1
                continue

            sg1, sg2 = curr.subgroup, nxt.subgroup
            if sg1 == 0 and sg2 == 0:
                first = 1 if (current_week + seq) % 2 != 0 else 2
                curr.subgroup = first
                nxt.subgroup = 3 - first
                seq += 1
            elif sg1 and not sg2:
                nxt.subgroup = 3 - sg1
            elif sg2 and not sg1:
                curr.subgroup = 3 - sg2
            i += 1


def parse_schedule_from_js(
        html_content: str,
        current_week_number: int = 1,
        alternation_subjects: list[str] | None = None,
) -> ParsedSchedule:
    soup = BeautifulSoup(html_content, "html.parser")
    table = soup.find("table", class_="table table-bordered")
    if not table:
        raise ValueError("Таблица расписания не найдена в HTML.")

    days, date_map = _extract_days(table)
    pair_num_to_time, time_to_pair_num = _extract_pair_times(table)

    temp: dict[str, list[Lesson]] = {}
    for script in soup.find_all("script"):
        if not script.string:
            continue
        for m in _APPEND_RE.finditer(script.string):
            cell_id, content_html = m.groups()
            content_html = content_html.replace('\\/', '/')
            pair_num_str, day_idx_str, _ = cell_id.split('_')
            day_idx = int(day_idx_str) - 1
            if day_idx >= len(days) or pair_num_str not in pair_num_to_time:
                continue
            lesson = _parse_lesson_block(content_html, pair_num_to_time[pair_num_str])
            if lesson:
                temp.setdefault(days[day_idx], []).append(lesson)

    week = int(current_week_number)
    _assign_split_subgroups(temp, time_to_pair_num, week)

    final: dict[str, list[Lesson]] = {
        day: sorted(temp.get(day, []), key=lambda x: time_to_pair_num.get(x.time, 0))
        for day in DAYS_ORDER
        if day in temp or day in date_map
    }
    _apply_lab_alternation(final, week, alternation_subjects or [])

    days_as_dicts = {day: [l.to_dict() for l in lessons] for day, lessons in final.items()}
    return ParsedSchedule(days=days_as_dicts, date_map=date_map, pair_num_to_time=pair_num_to_time)