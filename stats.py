import requests
from config import PLANNED_CLASSES
from utils import calculate_academic_week
from api import get_group_id, get_schedule_html
from parser import parse_schedule_from_js, get_subject_name, get_lesson_type


def count_all_classes(group_name: str, session: requests.Session):
    print("🚀 Начинаю подсчет всех прошедших пар. Это может занять некоторое время...")
    group_id = get_group_id(group_name, session)
    if not group_id: return
    try:
        current_week = calculate_academic_week()
        # Если нужно жестко задать неделю для отладки, раскомментируй следующую строку:
        # current_week = 39
    except Exception as e:
        print(f"❌ Не удалось рассчитать номер текущей недели: {e}")
        return

    class_counts = {}
    DEBUG_TARGET = "Теория вероятностей и математическая статистика"  # Или любой другой для отладки

    for week_num in range(24, current_week + 1):
        print(f"    - Обрабатываю неделю №{week_num} из {current_week}...")
        schedule_html = get_schedule_html(group_id, str(week_num), session)
        if not schedule_html:
            print(f"    ⚠️ Не удалось получить расписание для недели №{week_num}. Пропускаю.")
            continue
        try:
            weekly_schedule, _ = parse_schedule_from_js(schedule_html, week_num)
        except ValueError:
            print(f"    ℹ️ На неделе №{week_num} нет пар или не удалось ее распарсить.")
            continue

        # --- Подсчет общего количества пар на неделе ---
        week_total = 0
        for day, lessons in weekly_schedule.items():
            lessons_by_time = {}
            for lesson in lessons:
                subject_lower = lesson.get("subject", "").lower()
                if 'военная подготовка' in subject_lower or 'военная кафедра' in subject_lower or 'вуц' in subject_lower:
                    continue
                time = lesson.get("time", "N/A")
                lessons_by_time.setdefault(time, []).append(lesson)

            for time, time_lessons in lessons_by_time.items():
                if len(time_lessons) == 2:
                    week_total += 1.0  # Две пары по 0.5 = 1.0
                elif len(time_lessons) == 1 and time_lessons[0].get("subgroup", ""):
                    week_total += 0.5
                else:
                    week_total += 1.0

        print(f"      ✓ Всего пар на неделе: {week_total}")

        # --- Подсчет статистики по предметам (ТВОЯ ОРИГИНАЛЬНАЯ ЛОГИКА) ---
        for day, lessons in weekly_schedule.items():
            lessons_by_time = {}
            for lesson in lessons:
                time = lesson.get("time", "N/A")
                lessons_by_time.setdefault(time, []).append(lesson)

            for time, time_lessons in lessons_by_time.items():
                # Логика определения веса пары
                if len(time_lessons) == 2:
                    increment = 0.5
                elif len(time_lessons) == 1 and time_lessons[0].get("subgroup", ""):
                    increment = 0.5
                else:
                    increment = 1.0

                for lesson in time_lessons:
                    subject_name = get_subject_name(lesson.get("subject", "N/A"))
                    lesson_type = get_lesson_type(lesson.get("subject", "N/A"))

                    # Отладочный вывод
                    if DEBUG_TARGET.lower() in subject_name.lower():
                        print(
                            f"🐞 DEBUG: Неделя {week_num:<2} | {day:<11} | {time} | {lesson_type:<10} | +{increment} | {subject_name}")

                    if subject_name not in class_counts:
                        class_counts[subject_name] = {"Лекция": 0, "Практика": 0, "Лабораторная": 0, "Семинар": 0,
                                                      "Другое": 0}

                    if lesson_type in class_counts[subject_name]:
                        class_counts[subject_name][lesson_type] += increment

    print("\n" + "=" * 60)
    print("📊 СТАТИСТИКА ПО ПРЕДМЕТАМ (СКОЛЬКО ПАР ОСТАЛОСЬ)")
    print("=" * 60)
    unplanned_subjects = {}
    all_subject_names = sorted(list(PLANNED_CLASSES.keys() | class_counts.keys()))

    for subject in all_subject_names:
        if subject not in PLANNED_CLASSES:
            unplanned_subjects[subject] = class_counts[subject]
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
        print("\n" + "=" * 60)
        print("⚠️ ОБНАРУЖЕНЫ ВНЕПЛАНОВЫЕ ЗАНЯТИЯ")
        print("Этих предметов не было в вашем списке `PLANNED_CLASSES`:")
        print("=" * 60)
        for subject, types in unplanned_subjects.items():
            details = [f"{k}: {v}" for k, v in types.items() if v > 0]
            print(f"\n🔹 {subject} (Всего прошло: {sum(types.values())})")
            print("    " + ", ".join(details))
    print("\n" + "=" * 60)


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