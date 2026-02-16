import requests
import re
from bs4 import BeautifulSoup
from config import API_URL

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