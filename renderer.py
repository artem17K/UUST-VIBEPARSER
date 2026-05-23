import re
import imgkit
from config import WKHTMLTOIMAGE_PATH
from parser import split_subject_and_type


STYLE = """<style>
    body{font-family:'Tahoma',sans-serif;background-color:#fff;margin:0;padding:0}
    .multi-day-table{width:100%;border-collapse:collapse;table-layout:fixed}
    .multi-day-table th,.multi-day-table td{border:1px solid #000;padding:5px;text-align:center;vertical-align:middle;}
    .multi-day-table .time-cell { font-size: 16pt; vertical-align:middle; }
    .room-text { font-size: 16pt; }
    .subject-text { font-size: 16pt; }
    .lesson-type-text { font-size: 16pt; }
    .specific-time { font-size: 15pt; font-weight: bold; color: #cc0000; margin-top: 5px; margin-bottom: 2px; }
    .lesson-cell { position: relative; padding-bottom: 30px !important; }
    .teacher-name { position: absolute; bottom: 5px; left: 0; right: 0; width: 100%; font-size: 13pt; color: #444; }
    .day-header { font-weight:700; position: relative; }
    .date-badge { position: absolute; top: 6px; right: 5px; font-size: 13pt; font-weight: 700; background-color: rgba(255,255,255,0.7); padding: 0 3px; border-radius: 4px; }
    .multi-day-table td.split-lesson { padding: 0 !important; margin: 0; height: 136px; }
    .split-cell-table { width: 100%; height: 100%; border-collapse: collapse; table-layout: fixed; margin: 0; padding: 0; border: none; border-spacing: 0; display: table; }
    .split-cell-table tr { height: 100%; }
    .subgroup-cell { width: 50%; padding: 5px; padding-bottom: 30px !important; vertical-align: middle; position: relative; border: none !important; margin: 0; box-sizing: border-box; height: 100%; }
    .sg-left { border-right: 1px solid #000 !important; }
    .multi-day-table.thick-border-bottom{border-bottom:1px solid #000}
    .multi-day-table .day-header,.multi-day-table .date-pair-header{border-bottom:2px solid #000}
    .multi-day-table .thick-border-right{border-right:2px solid #000}
    .lesson-row{height:136px}
    .lecture-bg{background-color:#DDEBF7}
    .practice-bg{background-color:#FCE4D6}
    .lab-bg{background-color:#CCCCFF}
    .exam-bg{background-color:#FFD5D5}
    .default-bg{background-color:#fff}
    .military-day-bg { background-color: #e2f0d9; vertical-align: middle; font-size: 24pt; font-weight: bold; color: #000; }
    .military-lesson-bg { background-color: #e2f0d9; vertical-align: top; }
    .image-cell{padding:0;background-size:cover;background-position:center;background-repeat:no-repeat}
</style>"""

_EXAM_KEYWORDS = ('зачёт', 'зачет', 'экзамен', 'защита', 'консультация', 'к/р', 'ргр')


def _lesson_subgroup(lesson: dict) -> int:
    sg = lesson.get('subgroup', 0)
    if isinstance(sg, int):
        return sg
    m = re.search(r'\d+', str(sg))
    return int(m.group(0)) if m else 0


def _get_lesson_color_class(subject: str) -> str:
    s_lower = (subject or "").lower()
    _, type_str = split_subject_and_type(subject or "")
    t = type_str.lower()
    if 'военная подготовка' in s_lower:
        return 'military-lesson-bg'
    if any(k in t for k in _EXAM_KEYWORDS):
        return 'exam-bg'
    if 'лекция' in t:
        return 'lecture-bg'
    if 'практика' in t or 'семинар' in t:
        return 'practice-bg'
    if 'лабораторная' in t or 'лаб.' in t:
        return 'lab-bg'
    return 'default-bg'


def _format_room_text(s: str) -> str:
    if not s or s == "N/A":
        return ""
    s_lower = s.lower()
    if 'дистант' in s_lower:
        return 'Дистант'
    if 'спорткомплекс' in s_lower:
        return 'Спорткомплекс'
    s = re.sub(r'подгруппа\s*\d+', '', s, flags=re.IGNORECASE)
    s = re.sub(r'[\s-]*уточняется', '', s, flags=re.IGNORECASE)
    if 'заки валиди 32/1' in s_lower:
        n = re.findall(r'\d+[а-яА-Я]?', s)
        return f"Ауд. {n[-1]}" if n else "Физмат"
    s = s.replace('(', ' ').replace(')', ' ')
    if '-' in s:
        parts = s.rsplit('-', 1)
        address, room = parts[0].strip(), parts[1].strip()
        if re.match(r'^\d+[а-яА-Я]?$', room):
            return f"{' '.join(address.split())} ауд. {room}"
    return " ".join(s.split())


def _format_lesson_type(type_str: str) -> str:
    if not type_str:
        return ""
    s = type_str.strip()
    if s.lower() in ('лабораторная', 'лабораторная работа'):
        return "(Лаба)"
    return f"({s})"


def _format_lesson_content(lesson: dict) -> str:
    if 'военная подготовка' in lesson['subject'].lower():
        return ("<div style='padding-top: 20px; color: #000;'>"
                "<span class='subject-text'><strong>Военная подготовка</strong></span></div>")
    subject_name, type_raw = split_subject_and_type(lesson['subject'])
    type_html = (f"<br><span class='lesson-type-text'>{_format_lesson_type(type_raw)}</span>"
                 if type_raw else "")
    room = _format_room_text(lesson['room'])
    specific_time_html = (f"<div class='specific-time'>{lesson['specific_time']}</div>"
                          if lesson.get('specific_time') else "")
    room_html = f"<span class='room-text'>{room}</span>" if room else ""
    separator = "" if specific_time_html else "<br>"
    display_name = subject_name.strip() or lesson['subject']
    main = (f"<br><span class='subject-text'><strong>{display_name}</strong></span>"
            f"{type_html}{specific_time_html}{separator}{room_html}")
    teacher = (lesson.get('teacher') or '').strip()
    teacher_html = f"<div class='teacher-name'>{teacher}</div>" if teacher and teacher != 'N/A' else ""
    return main + teacher_html


def _generate_lesson_cell(lessons: list[dict]) -> str:
    sg1 = next((l for l in lessons if _lesson_subgroup(l) == 1), None)
    sg2 = next((l for l in lessons if _lesson_subgroup(l) == 2), None)
    if not sg1 and not sg2:
        return _format_lesson_content(lessons[0]) if lessons else ''
    parts = ['<table class="split-cell-table"><tr>']
    if sg1:
        parts.append(f'<td class="subgroup-cell sg-left {_get_lesson_color_class(sg1["subject"])}">'
                     f'{_format_lesson_content(sg1)}</td>')
    else:
        parts.append('<td class="subgroup-cell sg-left default-bg"></td>')
    if sg2:
        parts.append(f'<td class="subgroup-cell {_get_lesson_color_class(sg2["subject"])}">'
                     f'{_format_lesson_content(sg2)}</td>')
    else:
        parts.append('<td class="subgroup-cell default-bg"></td>')
    parts.append('</tr></table>')
    return ''.join(parts)


def _visible_times(days: list[str], times: list[str], data: dict) -> list[str]:
    last = -1
    for i, t in enumerate(times):
        if any(l['time'] == t for d in days for l in data.get(d, [])):
            last = i
    return times[:last + 1] if last >= 0 else []


def _generate_days_row(days, data, times, is_top, date_map, military_day, military_uri, time_w, day_w):
    cls = "multi-day-table thick-border-bottom" if is_top else "multi-day-table"
    parts = [f'<table class="{cls}"><thead><tr>']
    for i, d in enumerate(days):
        header = f"{d}<div class='date-badge'>{date_map.get(d, '')}</div>"
        parts.append(f'<th class="date-pair-header" style="width:{time_w};"><strong>Время</strong></th>')
        border = "day-header thick-border-right" if i < len(days) - 1 else "day-header"
        parts.append(f'<th class="{border}" style="width:{day_w};">{header}</th>')
    parts.append('</tr></thead><tbody>')

    if not any(data.get(d) for d in days):
        parts.append(f'<tr><td colspan="{len(days) * 2}" style="height:100px;vertical-align:middle;">Пар нет</td></tr>')
        parts.append("</tbody></table>")
        return ''.join(parts)

    mil_added = False
    for t in times:
        parts.append('<tr class="lesson-row">')
        for i, d in enumerate(days):
            if d == military_day and military_uri:
                if not mil_added:
                    rowspan = len(times) if times else 1
                    border = "thick-border-right" if i < len(days) - 1 else ""
                    parts.append(f'<td colspan="2" rowspan="{rowspan}" class="image-cell {border}" '
                                 f'style="background-image:url({military_uri});"></td>')
                    mil_added = True
                continue
            parts.append(f'<td class="time-cell">{t.replace("-", "<br>-<br>")}</td>')
            ls = [l for l in data.get(d, []) if l['time'] == t]
            ls.sort(key=_lesson_subgroup)
            cell_cls = ["lesson-cell"]
            if i < len(days) - 1:
                cell_cls.append("thick-border-right")
            has_sub = any(_lesson_subgroup(l) for l in ls)
            if has_sub:
                cell_cls.append("split-lesson")
            elif ls:
                cell_cls.append(_get_lesson_color_class(ls[0]['subject']))
            else:
                cell_cls.append("default-bg")
            parts.append(f'<td class="{" ".join(cell_cls)}">{_generate_lesson_cell(ls)}</td>')
        parts.append('</tr>')
    parts.append("</tbody></table>")
    return ''.join(parts)


def create_schedule_image(schedule_data, day_date_map, image_filename,
                          military_day_info=None, pair_num_to_time=None):
    time_w, day_w = "80px", "550px"
    total_width = (int(time_w.replace('px', '')) + int(day_w.replace('px', ''))) * 3 + 2

    if pair_num_to_time:
        all_times = [pair_num_to_time[k] for k in sorted(pair_num_to_time, key=lambda x: int(x))]
    else:
        all_times = sorted({l['time'] for day in schedule_data.values() for l in day})

    mil_day = military_day_info.get('day') if military_day_info else None
    mil_uri = military_day_info.get('image_uri') if military_day_info else None

    top, bottom = ["Понедельник", "Вторник", "Среда"], ["Четверг", "Пятница", "Суббота"]
    vis_top = _visible_times(top, all_times, schedule_data)
    vis_bot = _visible_times(bottom, all_times, schedule_data)

    body = (
        _generate_days_row(top, schedule_data, vis_top, True, day_date_map, mil_day, mil_uri, time_w, day_w)
        + _generate_days_row(bottom, schedule_data, vis_bot, False, day_date_map, mil_day, mil_uri, time_w, day_w)
    )
    full = f"<!DOCTYPE html><html><head><meta charset='UTF-8'>{STYLE}</head><body>{body}</body></html>"

    try:
        cfg = imgkit.config(wkhtmltoimage=WKHTMLTOIMAGE_PATH)
        opts = {'width': total_width, 'encoding': "UTF-8", 'disable-smart-width': '', 'quiet': ''}
        imgkit.from_string(full, image_filename, options=opts, config=cfg)
    except Exception as e:
        print(f"❌ Ошибка при создании изображения: {e}\n"
              f"    Убедись, что путь в WKHTMLTOIMAGE_PATH указан верно.")