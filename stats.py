import re
import requests
from config import PLANNED_CLASSES, SUBJECTS_TO_ALTERNATE
from utils import calculate_academic_week, get_semester_start_week
from api import get_group_id, get_schedule_html
from parser import parse_schedule_from_js, get_subject_name, get_lesson_type


DAY_ORDER = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"]
_DAY_INDEX = {d: i for i, d in enumerate(DAY_ORDER)}

_FIELD_LABELS = [
    ('subject', 'предмет'),
    ('teacher', 'преподаватель'),
    ('room', 'аудитория'),
    ('specific_time', 'время'),
]


def _is_military(subject: str) -> bool:
    s = subject.lower()
    return 'военная подготовка' in s or 'военная кафедра' in s or 'вуц' in s


def _lesson_weight(time_lessons: list[dict]) -> float:
    if len(time_lessons) == 2:
        return 0.5
    if len(time_lessons) == 1 and time_lessons[0].get("subgroup"):
        return 0.5
    return 1.0


def _group_by_time(lessons: list[dict], skip_military: bool = False) -> dict[str, list[dict]]:
    result: dict[str, list[dict]] = {}
    for lesson in lessons:
        if skip_military and _is_military(lesson.get("subject", "")):
            continue
        result.setdefault(lesson.get("time", "N/A"), []).append(lesson)
    return result


def count_all_classes(group_name: str, session: requests.Session):
    print("🚀 Начинаю подсчет всех прошедших пар. Это может занять некоторое время...")
    group_id = get_group_id(group_name, session)
    if not group_id:
        return
    try:
        current_week = calculate_academic_week()
    except Exception as e:
        print(f"❌ Не удалось рассчитать номер текущей недели: {e}")
        return

    start_week = get_semester_start_week(current_week)
    class_counts: dict[str, dict[str, float]] = {}

    for week_num in range(start_week, current_week + 1):
        print(f"    - Обрабатываю неделю №{week_num} из {current_week}...")
        schedule_html = get_schedule_html(group_id, str(week_num), session)
        if not schedule_html:
            print(f"    ⚠️ Не удалось получить расписание для недели №{week_num}. Пропускаю.")
            continue
        try:
            parsed = parse_schedule_from_js(
                schedule_html, week_num, alternation_subjects=SUBJECTS_TO_ALTERNATE
            )
        except ValueError:
            print(f"    ℹ️ На неделе №{week_num} нет пар или не удалось ее распарсить.")
            continue

        weekly = parsed.days
        week_total = 0.0
        for day_lessons in weekly.values():
            for time_lessons in _group_by_time(day_lessons, skip_military=True).values():
                week_total += _lesson_weight(time_lessons)
        print(f"      ✓ Всего пар на неделе: {week_total}")

        for day_lessons in weekly.values():
            for time_lessons in _group_by_time(day_lessons).values():
                increment = _lesson_weight(time_lessons)
                for lesson in time_lessons:
                    subject = get_subject_name(lesson.get("subject", "N/A"))
                    ltype = get_lesson_type(lesson.get("subject", "N/A"))
                    bucket = class_counts.setdefault(subject, {
                        "Лекция": 0, "Практика": 0, "Лабораторная": 0, "Семинар": 0, "Другое": 0
                    })
                    if ltype in bucket:
                        bucket[ltype] += increment

    _print_stats_summary(class_counts)


def _print_stats_summary(class_counts: dict[str, dict[str, float]]):
    print("\n" + "=" * 60)
    print("📊 СТАТИСТИКА ПО ПРЕДМЕТАМ (СКОЛЬКО ПАР ОСТАЛОСЬ)")
    print("=" * 60)

    unplanned = {}
    for subject in sorted(PLANNED_CLASSES.keys() | class_counts.keys()):
        if subject not in PLANNED_CLASSES:
            unplanned[subject] = class_counts[subject]
            continue
        planned = PLANNED_CLASSES[subject]
        past = class_counts.get(subject, {"Лекция": 0, "Практика": 0, "Лабораторная": 0})
        total_planned, total_past = sum(planned.values()), sum(past.values())
        if total_planned == 0 and total_past == 0:
            continue
        print(f"\n🔹 {subject} [Прошло {total_past} из {total_planned}]")
        details = []
        for class_type, plural in [("Лекция", "Лекций"), ("Практика", "Практик"),
                                   ("Лабораторная", "Лабораторных")]:
            planned_count = planned.get(class_type, 0)
            if planned_count == 0:
                continue
            past_count = past.get(class_type, 0)
            details.append(
                f"{plural} осталось: {planned_count - past_count} "
                f"(прошло {past_count} из {planned_count})"
            )
        if details:
            print("    " + ", ".join(details))

    if unplanned:
        print("\n" + "=" * 60)
        print("⚠️ ОБНАРУЖЕНЫ ВНЕПЛАНОВЫЕ ЗАНЯТИЯ")
        print("Этих предметов не было в вашем списке `PLANNED_CLASSES`:")
        print("=" * 60)
        for subject, types in unplanned.items():
            details = [f"{k}: {v}" for k, v in types.items() if v > 0]
            print(f"\n🔹 {subject} (Всего прошло: {sum(types.values())})")
            print("    " + ", ".join(details))
    print("\n" + "=" * 60)


def _normalize_subgroup(value) -> int:
    if isinstance(value, int):
        return value
    if not value:
        return 0
    m = re.search(r'\d+', str(value))
    return int(m.group(0)) if m else 0


def _lesson_identity(lesson: dict) -> tuple:
    return (
        lesson.get('time', ''),
        lesson.get('subject_clean', '') or lesson.get('subject', ''),
        _normalize_subgroup(lesson.get('subgroup')),
    )


def _format_lesson_summary(lesson: dict) -> str:
    subject = lesson.get('subject', '')
    sg = _normalize_subgroup(lesson.get('subgroup'))
    sg_part = f" [подгруппа {sg}]" if sg else ""
    return f"{lesson.get('time', '')} {subject}{sg_part}"


def _field_diffs(old: dict, new: dict) -> list[str]:
    diffs = []
    for key, label in _FIELD_LABELS:
        a = old.get(key) or ''
        b = new.get(key) or ''
        if a != b:
            diffs.append(f"      {label}: {a or '—'} → {b or '—'}")
    return diffs


def compare_schedules(old_schedule: dict, new_schedule: dict) -> list[str]:
    lines = []
    all_days = sorted(
        set(old_schedule.keys()) | set(new_schedule.keys()),
        key=lambda d: _DAY_INDEX.get(d, 99),
    )

    for day in all_days:
        old_by_id = {_lesson_identity(l): l for l in old_schedule.get(day, [])}
        new_by_id = {_lesson_identity(l): l for l in new_schedule.get(day, [])}

        removed_ids = old_by_id.keys() - new_by_id.keys()
        added_ids = new_by_id.keys() - old_by_id.keys()
        common_ids = old_by_id.keys() & new_by_id.keys()

        day_lines = []
        for lid in sorted(removed_ids):
            day_lines.append(f"  ➖ Убрано: {_format_lesson_summary(old_by_id[lid])}")
        for lid in sorted(added_ids):
            day_lines.append(f"  ➕ Добавлено: {_format_lesson_summary(new_by_id[lid])}")
        for lid in sorted(common_ids):
            diffs = _field_diffs(old_by_id[lid], new_by_id[lid])
            if diffs:
                day_lines.append(f"  📝 Изменено: {_format_lesson_summary(new_by_id[lid])}")
                day_lines.extend(diffs)

        if day_lines:
            lines.append(f"\n🗓 {day}:")
            lines.extend(day_lines)

    return lines or ["\n✅ Расписание не изменилось."]