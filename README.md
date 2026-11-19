# LifeOS

Личная система управления жизнью. Первый модуль — **LifeOS RPG**: XP за реальные
действия, уровни, характеристики, квесты.

## Статус

| Часть | Состояние |
|---|---|
| Фаза 1 — ядро: профиль, XP Ledger, уровни | готово |
| Фаза 2 — квесты: daily / weekly / personal / challenge / milestone | готово |
| Авторизация: JWT + refresh-токены с ротацией, Argon2id | готово |
| Клиент (PWA: React + TypeScript + Vite): главная, квесты, профиль | готово |
| Фаза 3 — достижения и стрики | дальше |
| Фазы 4–6 — циклы, Adaptive Engine, аналитика | дальше |

Принятые решения по ТЗ и отклонения от него — в [docs/decisions.md](docs/decisions.md).

## Структура

```
backend/
  app/domain/      правила игры без БД: уровни, награды, локальные даты
  app/services/    сценарии: XP Ledger, квесты, профиль, авторизация
  app/routers/     HTTP API /api/v1
  migrations/      миграции Alembic
  tests/           тесты на настоящем PostgreSQL
web/
  src/api/         клиент API: токены, повторы, Idempotency-Key, типы из OpenAPI
  src/pages/       экраны: вход, главная, квесты, карточка квеста, профиль
  src/components/  интерфейс Premium Dark
  src/i18n/        тексты RU и EN
scripts/devdb.ps1  локальный PostgreSQL для разработки
docs/              решения и документация
```

## Запуск на Windows

Нужны Python 3.14, PostgreSQL 18 (достаточно бинарников) и Git.

```powershell
# 1. База данных: первый раз — init, после перезагрузки — start
powershell -ExecutionPolicy Bypass -File .\scripts\devdb.ps1 init

# 2. Зависимости бэкенда
cd backend
py -3.14 -m venv .venv
.\.venv\Scripts\python -m pip install -e ".[dev]"

# 3. Схема базы
.\.venv\Scripts\alembic upgrade head

# 4. Сервер: документация API на http://127.0.0.1:8000/docs
.\.venv\Scripts\uvicorn app.main:create_app --factory --reload

# 5. Тесты (база lifeos_test пересоздаётся при каждом запуске)
.\.venv\Scripts\python -m pytest
```

Клиент (нужен Node.js 22+; сервер API из шага 4 должен работать):

```powershell
cd web
npm install
npm run dev        # http://localhost:5173, запросы /api уходят на :8000
npm test           # тесты API-клиента
npm run build      # проверка типов и сборка PWA в web/dist
```

**С телефона.** Запусти `npm run dev:lan` и открой на телефоне `http://<IP компьютера>:5173`.
Телефон и компьютер должны быть в одной сети Wi-Fi. При первом запуске Windows может
спросить, разрешить ли Node.js доступ к частной сети — разреши. Так приложение работает
как сайт. Чтобы установить его на главный экран и получать уведомления, нужен HTTPS:
это даст Tailscale или сервер, и этим займёмся на этапе деплоя.

**Типы API.** После изменения бэкенда обнови типы клиента:
`backend\.venv\Scripts\python backend\scripts\export_openapi.py`, затем `npm run api:types` в `web`.

`devdb.ps1 init` создаёт кластер в `%LOCALAPPDATA%\LifeOS\pgdata`, роль `lifeos`
и базы `lifeos` и `lifeos_test`. Случайные пароли он записывает в `backend/.env`,
файл в git не попадает. Служба Windows и права администратора не нужны.

Почему не используется служба из установщика: штатный установщик PostgreSQL
запускает `initdb` с системной локалью `Russian_Russia.1251`. В итоге он падает с
ошибкой `invalid byte sequence for encoding "UTF8"`, и кластер не создаётся.
`devdb.ps1` создаёт кластер с локалью `C` и встроенным провайдером сортировки
`C.UTF-8`, такой кластер не зависит от языка Windows.

## API

Все пути начинаются с `/api/v1`, полная схема — в `/docs`.

| Метод и путь | Что делает |
|---|---|
| `POST /auth/register`, `/auth/login` | регистрация и вход, ответ — пара токенов |
| `POST /auth/refresh`, `/auth/logout` | ротация и отзыв refresh-токена |
| `POST /account/delete` | удаление аккаунта со всеми данными |
| `GET/PATCH /player/profile` | профиль, уровень, прогресс, часовой пояс |
| `GET /player/attributes` | характеристики с динамикой за 7 и 30 дней |
| `GET /player/xp-history` | журнал XP, новые записи сверху |
| `GET /player/statistics` | XP по дням и характеристикам за период |
| `GET/POST /quests`, `GET/PATCH/DELETE /quests/{id}` | квесты (`?scope=today` — квесты на сегодня) |
| `POST /quests/{id}/complete`, `/skip`, `/undo` | выполнить, пропустить, отменить до конца дня |
| `GET /config/levels`, `/config/rewards` | таблица уровней и награды с сервера |

POST-запросы принимают заголовок `Idempotency-Key`. Повтор с тем же ключом
возвращает первый ответ и не выполняет действие заново.

## Как начисляется XP

- Награду всегда считает сервер: она зависит от типа, активности и сложности
  квеста и фиксируется при создании квеста.
- Каждое начисление — запись в неизменяемом журнале `xp_ledger`. Ключ записи
  детерминированный, поэтому одно событие не может дать XP дважды.
- Профиль и характеристики обновляются в той же транзакции. Строка профиля
  блокируется, поэтому параллельные запросы не теряют XP.
- Пропуск квеста XP не снимает. Отмена ошибочного выполнения добавляет
  компенсирующую запись в журнал и доступна до конца того же дня.
