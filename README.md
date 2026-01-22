# Stock Delta Analyzer

Приложение для ежедневного анализа Excel-файлов по остаткам автотоваров. Оптимизировано под большие загрузки: хранит только снимок остатков и дневные изменения.

## Архитектура

**Таблицы**
- `daily_snapshot`: снимок остатков на день (по ключу `date + warehouse + sku + manufacturer`).
- `daily_delta`: дневные изменения (sold/replenished) + цена за день.

**Индексы**
- `date + warehouse + sku` для быстрых диапазонных запросов.
- отдельные индексы для фильтров (`warehouse`, `sku`, `manufacturer`, `nomenclature`).

**Поток загрузки**
1. Загрузка Excel (`/upload`).
2. Проверка колонок и нормализация.
3. Аггрегация внутри дня (последняя цена, последний остаток).
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
4. В Railway откройте Settings → Pre-deploy Command и задайте:
   `python -m alembic upgrade head`
   Railway Pre-deploy Command = python -m alembic upgrade head
5. После pre-deploy Railway запускает приложение обычной командой из Dockerfile
   (через `uvicorn`), отдельный доступ к Shell не требуется.

Railway Pre-deploy Command = python -m alembic upgrade head

## API

- `POST /upload` — загрузка Excel.
  - `upload_date` (YYYY-MM-DD)
  - `mode`: `reject` (по умолчанию), `merge` или `replace`
- `GET /series?sku=&warehouse=&manufacturer=&date_from=&date_to=` — временной ряд (поле `price` вместо `price_start_day`)
- `GET /filters/suggestions?field=sku&q=` — подсказки для фильтров
- `GET /top?company=&date_from=&date_to=&limit=` — топ продаж
  - пустые параметры следует опускать из запроса
  - `company` нормализуется к нижнему регистру
  - примеры:
    - `curl ".../top?company=Alliance&date_from=2025-10-24&date_to=2026-01-21&limit=100"`
    - `curl ".../top?company=alliance&date_from=2025-10-24&date_to=2026-01-21"`

## Manual verification

```bash
curl ".../top?company=Alliance&date_from=2025-09-07&date_to=2025-09-08&limit=10&warehouse=Варшавка"
```
