# Stock Delta Analyzer

Приложение для ежедневного анализа Excel-файлов по остаткам автотоваров. Оптимизировано под большие загрузки: хранит только снимок остатков и дневные изменения.

## Архитектура

**Таблицы**
- `daily_snapshot`: снимок остатков на день (по ключу `date + warehouse + sku + manufacturer`).
- `daily_delta`: дневные изменения (sold/replenished) + цена старта/конца дня.

**Индексы**
- `date + warehouse + sku` для быстрых диапазонных запросов.
- отдельные индексы для фильтров (`warehouse`, `sku`, `manufacturer`, `nomenclature`).

**Поток загрузки**
1. Загрузка Excel (`/upload`).
2. Проверка колонок и нормализация.
3. Аггрегация внутри дня (первая цена/последняя цена, последний остаток).
4. Сравнение только с предыдущим днём.
5. Запись `daily_snapshot` и `daily_delta`.

## Быстрый старт

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export DATABASE_URL="postgresql+psycopg2://user:pass@localhost:5432/dbname"
alembic upgrade head
uvicorn app.main:app --reload
```

Откройте `http://localhost:8000`.

## Деплой на Railway

1. Создайте новый проект и добавьте Postgres плагин.
2. Скопируйте `DATABASE_URL` в переменные окружения сервиса.
3. Залейте репозиторий в Railway — сборка идёт через Dockerfile.
4. Выполните миграции через Railway Shell:

```bash
alembic upgrade head
```

## API

- `POST /upload` — загрузка Excel.
  - `upload_date` (YYYY-MM-DD)
  - `mode`: `reject` (по умолчанию), `merge` или `replace`
- `GET /series?sku=&warehouse=&manufacturer=&date_from=&date_to=` — временной ряд
- `GET /filters/suggestions?field=sku&q=` — подсказки для фильтров
