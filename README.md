# Каталог опен-коллов

Страница со списком опен-коллов для художников. Пересобирается сама раз в сутки,
адрес страницы не меняется.

## Как устроено

    collect.py     сбор: телеграм-каналы, RSS, каталоги-агрегаторы, сайты организаторов
    generate.py    отбор и резюме через Claude, сборка HTML
    style.css      оформление страницы
    data/items.json  архив: каталоги удаляют объявления после дедлайна, архив их держит
    public/index.html  готовая страница, её раздаёт хостинг

Каждое объявление проходит через Claude ровно один раз — при первой встрече.
Дальше оно живёт в архиве, поэтому ежедневный прогон стоит копейки.

## Запуск руками

    pip install anthropic
    export ANTHROPIC_API_KEY=sk-ant-...
    python generate.py

    python generate.py --dry     # что собралось, без обращения к Claude
    python generate.py --no-llm  # пересобрать страницу из архива

## Автообновление

`.github/workflows/update.yml` запускается ежедневно в 09:00 МСК и после каждого
пуша кнопкой в разделе Actions. Нужен один секрет репозитория:

    Settings → Secrets and variables → Actions → New repository secret
    имя: ANTHROPIC_API_KEY

## Что менять

Источники — `TELEGRAM`, `RSS`, `INDEXES` в начале `collect.py`.
Критерии отбора — `CRITERIA_YES` и `CRITERIA_NO` в начале `generate.py`.
Расписание — строка `cron` в воркфлоу.
