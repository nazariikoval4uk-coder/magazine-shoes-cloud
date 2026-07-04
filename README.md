# Magazine Shoes — хмарна версія (тільки код)

Цей репозиторій містить **лише код** дашборду, без даних клієнтів.
Дані (`data/raw`, `data/processed`, `data/manual`) завантажуються на сервер
окремо, вручну, після розгортання коду — щоб персональні дані клієнтів
(телефони, імена) ніколи не потрапляли в git.

## Розгортання на PythonAnywhere

1. Клонувати цей репозиторій у Bash-консолі PythonAnywhere:
   `git clone <URL цього репозиторію> magazine-shoes-cloud`
2. Встановити залежності:
   `pip install --user -r magazine-shoes-cloud/requirements.txt`
3. Створити `dashboard/instance/auth.json` (пароль на вхід) — див. нижче.
4. Завантажити реальні дані (`data/raw`, `data/processed`, `data/manual`)
   через вкладку Files на PythonAnywhere — окремо від коду.
5. Налаштувати Web-застосунок (Manual configuration, Flask) з WSGI-файлом,
   що імпортує `dashboard.app:app` як `application`.

## Створення auth.json (пароль на вхід)

```
python3 -c "
import json, secrets
from werkzeug.security import generate_password_hash
config = {'secret_key': secrets.token_hex(32), 'password_hash': generate_password_hash('ВАШ_ПАРОЛЬ')}
with open('dashboard/instance/auth.json', 'w', encoding='utf-8') as f:
    json.dump(config, f, indent=2)
"
```
