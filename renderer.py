import imgkit
import re
from config import WKHTMLTOIMAGE_PATH

def create_schedule_image(schedule_data, day_date_map, image_filename, military_day_info=None, pair_num_to_time=None):
    TIME_COL_WIDTH, DAY_COL_WIDTH = "80px", "550px"
    TOTAL_IMAGE_WIDTH = (int(TIME_COL_WIDTH.replace('px', '')) + int(DAY_COL_WIDTH.replace('px', ''))) * 3 + 2  # +2 чтобы правая граница не обрезалась

    html_style = f"""<style>
        body{{font-family:'Tahoma',serif;background-color:#fff;margin:0;padding:0}}
        .multi-day-table{{width:100%;border-collapse:collapse;table-layout:fixed}}
        .multi-day-table th,.multi-day-table td{{border:1px solid #000;padding:5px;text-align:center;vertical-align:middle;e:15pt;}}
        .multi-day-table .time-cell {{ font-size: 16pt; vertical-align:middle; }}
        .room-text {{ font-size: 16pt; }}
        .subject-text {{ font-size: 16pt; }}
        .lesson-type-text {{ font-size: 16pt; }}
        .specific-time {{ font-size: 15pt; font-weight: bold; color: #cc0000; margin-top: 5px; margin-bottom: 2px; }}
        .lesson-cell {{ position: relative; padding-bottom: 30px !important; }}
        .teacher-name {{ position: absolute; bottom: 5px; left: 0; right: 0; width: 100%; font-size: 13pt; color: #444; }}
        .day-header {{ font-weight:700; position: relative; }}
        .date-badge {{ position: absolute; top: 6px; right: 5px; font-size: 13pt; font-weight: 700; background-color: rgba(255,255,255,0.7); padding: 0 3px; border-radius: 4px; }}
        .multi-day-table td.split-lesson {{ padding: 0 !important; margin: 0; height: 136px; }}
        .split-cell-table {{ width: 100%; height: 100%; border-collapse: collapse; table-layout: fixed; margin: 0; padding: 0; border: none; border-spacing: 0; display: table; }}
        .split-cell-table tr {{ height: 100%; }}
        .subgroup-cell {{ width: 50%; padding: 5px; padding-bottom: 30px !important; vertical-align: middle; position: relative; border: none !important; margin: 0; box-sizing: border-box; height: 100%; }}
        .sg-left {{ border-right: 1px solid #000 !important; }}
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

    if pair_num_to_time:
        all_times = [pair_num_to_time[k] for k in sorted(pair_num_to_time, key=lambda x: int(x))]
    else:
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

    def format_lesson_content(l):
        if 'военная подготовка' in l['subject'].lower():
            return f"<div style='padding-top: 20px; color: #000;'><span class='subject-text'><strong>Военная подготовка</strong></span></div>"
        m = re.match(r'(.+?)\s*\((.+)\)', l['subject'])
        subject_name, subject_type_raw = m.groups() if m else (l['subject'], '')
        type_html = f"<br><span class='lesson-type-text'>{get_lesson_type_formatted(subject_type_raw)}</span>" if subject_type_raw else ""
        room = format_room_text(l['room'])
        specific_time_html = f"<div class='specific-time'>{l['specific_time']}</div>" if l.get('specific_time') else ""
        room_html = f"<span class='room-text'>{room}</span>" if room else ""
        separator = "" if (specific_time_html) else "<br>"
        main_content_html = (
            f"<br><span class='subject-text'><strong>{subject_name.strip()}</strong></span>"
            f"{type_html}{specific_time_html}{separator}{room_html}"
        )
        teacher_html = f"<div class='teacher-name'>{l['teacher']}</div>" if l.get('teacher') and l['teacher'].strip() not in ('N/A', '') else ""
        return main_content_html + teacher_html

    def generate_lesson_cell_html(lessons):
        lesson_sg1 = next((l for l in lessons if 'подгруппа 1' in l.get('subgroup', '')), None)
        lesson_sg2 = next((l for l in lessons if 'подгруппа 2' in l.get('subgroup', '')), None)
        if not lesson_sg1 and not lesson_sg2:
            if not lessons: return ''
            return format_lesson_content(lessons[0])
        html = '<table class="split-cell-table"><tr>'
        if lesson_sg1:
            bg_class = get_lesson_color_class(lesson_sg1['subject'])
            content = format_lesson_content(lesson_sg1)
            html += f'<td class="subgroup-cell sg-left {bg_class}">{content}</td>'
        else:
            html += '<td class="subgroup-cell sg-left default-bg"></td>'
        if lesson_sg2:
            bg_class = get_lesson_color_class(lesson_sg2['subject'])
            content = format_lesson_content(lesson_sg2)
            html += f'<td class="subgroup-cell {bg_class}">{content}</td>'
        else:
            html += '<td class="subgroup-cell default-bg"></td>'
        html += '</tr></table>'
        return html

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
                ls.sort(key=lambda x: x.get('subgroup', ''))
                cls = ["lesson-cell"]
                cls.append("thick-border-right" if i < len(days) - 1 else "")
                has_subgroups = any('подгруппа' in l.get('subgroup', '') for l in ls)
                if has_subgroups: cls.append("split-lesson")
                elif ls: cls.append(get_lesson_color_class(ls[0]['subject']))
                else: cls.append("default-bg")
                h += f'<td class="{" ".join(cls)}">{generate_lesson_cell_html(ls)}</td>'
            h += '</tr>'
        h += "</tbody></table>"
        return h

    top_days, bottom_days = ["Понедельник", "Вторник", "Среда"], ["Четверг", "Пятница", "Суббота"]
    visible_top = get_visible_times_for_days(top_days, all_times, schedule_data)
    visible_bottom = get_visible_times_for_days(bottom_days, all_times, schedule_data)
    html_body = generate_days_row_html(top_days, schedule_data, visible_top, True, TIME_COL_WIDTH, DAY_COL_WIDTH)
    html_body += generate_days_row_html(bottom_days, schedule_data, visible_bottom, False, TIME_COL_WIDTH, DAY_COL_WIDTH)
    full_html = f"<!DOCTYPE html><html><head><meta charset='UTF-8'>{html_style}</head><body>{html_body}</body></html>"
    try:
        config = imgkit.config(wkhtmltoimage=WKHTMLTOIMAGE_PATH)
        options = {'width': TOTAL_IMAGE_WIDTH, 'encoding': "UTF-8", 'disable-smart-width': '', 'quiet': ''}
        imgkit.from_string(full_html, image_filename, options=options, config=config)
    except Exception as e:
        print(f"❌ Ошибка при создании изображения: {e}\n    Убедись, что путь в WKHTMLTOIMAGE_PATH указан верно.")