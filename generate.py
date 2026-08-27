#!/usr/bin/env python3
"""
Генератор страницы опен-коллов.

  python3 generate.py            # собрать, обработать через Claude, отрендерить public/index.html
  python3 generate.py --dry      # без обращения к Claude: показать, что собралось
  python3 generate.py --no-llm   # отрендерить страницу из архива, ничего не собирая

Архив храним в data/items.json: каналы удаляют посты после дедлайна, и без архива
раздел «приём закрыт» опустеет. Каждая запись обрабатывается Claude ровно один раз.
"""
import html as H
import json, os, re, sys
from datetime import date, datetime, timezone, timedelta

import collect

HERE = os.path.dirname(os.path.abspath(__file__))
STORE = os.path.join(HERE, "data", "items.json")
OUT = os.path.join(HERE, "public", "index.html")
MODEL = os.environ.get("OPENCALL_MODEL", "claude-opus-5")
BATCH = 12

# ---------------------------------------------------------------- критерии отбора
CRITERIA_YES = "живопись, графика, коллаж (аналоговый и цифровой), смешанные техники, " \
               "а также опен-коллы без ограничений по медиуму"
CRITERIA_NO = "VR, медиаарт, science-art, цифровое кино, проекты про ИИ и нейроинтерфейсы"

SYSTEM = f"""Ты — редактор каталога опен-коллов для художников.

Оставляй запись (relevant=true), если выполнено всё:
1. Это действующий или прошедший приём заявок: опен-колл, резиденция, грант, конкурс,
   набор в выставку, ярмарка. Не анонс выставки без приёма заявок и не реклама курсов.
2. Подать заявку можно из России — российский организатор или приём открыт авторам из РФ.
3. Медиум подходит: {CRITERIA_YES}.

Отклоняй (relevant=false): {CRITERIA_NO}; литературу, театр, вокал, кино, фотоконкурсы;
детские и школьные конкурсы; гранты вне искусства; служебные посты каналов и рекламу.
В reject_reason коротко укажи причину: "медиум исключён", "не про искусство",
"нет приёма заявок", "реклама", "детский конкурс".

Поля заполняй по тексту, ничего не выдумывая. Пустое значение — пустая строка.
deadline — строго ГГГГ-ММ-ДД, если год не указан, бери ближайший будущий.
summary — 2–3 предложения по-русски: что за проект, что подать, что получает участник.
theme — одна строка: тема или фокус отбора.
apply_url — прямая ссылка на условия или форму заявки, если она есть в тексте.
techniques — техники и медиумы, которые принимают.
provides — что даёт участие: гонорар, грант, проживание, продакшн-бюджет, публикация."""

SCHEMA = {
    "type": "object",
    "properties": {"items": {"type": "array", "items": {
        "type": "object",
        "properties": {
            "id": {"type": "integer"},
            "relevant": {"type": "boolean"},
            "reject_reason": {"type": "string"},
            "title": {"type": "string"},
            "org": {"type": "string"},
            "city": {"type": "string"},
            "theme": {"type": "string"},
            "summary": {"type": "string"},
            "deadline": {"type": "string"},
            "period": {"type": "string"},
            "who": {"type": "string"},
            "techniques": {"type": "string"},
            "provides": {"type": "string"},
            "contact": {"type": "string"},
            "apply_url": {"type": "string"},
        },
        "required": ["id", "relevant", "reject_reason", "title", "org", "city", "theme",
                     "summary", "deadline", "period", "who", "techniques", "provides",
                     "contact", "apply_url"],
        "additionalProperties": False}}},
    "required": ["items"], "additionalProperties": False,
}


def log(*a):
    print(*a, file=sys.stderr, flush=True)


# ---------------------------------------------------------------- хранилище
def load_store():
    if os.path.exists(STORE):
        with open(STORE, encoding="utf-8") as f:
            return json.load(f)
    return {"items": {}, "rejected": {}}


def save_store(store):
    os.makedirs(os.path.dirname(STORE), exist_ok=True)
    with open(STORE, "w", encoding="utf-8") as f:
        json.dump(store, f, ensure_ascii=False, indent=1, sort_keys=True)


# ---------------------------------------------------------------- Claude
def enrich(raw, model=MODEL):
    """Классификация и резюмирование пачками. Возвращает список разборов."""
    import anthropic
    client = anthropic.Anthropic()
    today = date.today().isoformat()
    result = []
    for start in range(0, len(raw), BATCH):
        chunk = raw[start:start + BATCH]
        payload = [{"id": i, "source": it["source"], "url": it["source_url"],
                    "text": it["text"][:3500]} for i, it in enumerate(chunk)]
        resp = client.messages.create(
            model=model, max_tokens=16000, system=SYSTEM,
            output_config={"effort": "low", "format": {"type": "json_schema", "schema": SCHEMA}},
            messages=[{"role": "user", "content": "Сегодня %s. Разбери записи:\n\n%s"
                       % (today, json.dumps(payload, ensure_ascii=False))}],
        )
        text = next(b.text for b in resp.content if b.type == "text")
        parsed = json.loads(text)["items"]
        for p in parsed:
            if 0 <= p["id"] < len(chunk):
                result.append((chunk[p["id"]], p))
        log("  обработано %d/%d" % (min(start + BATCH, len(raw)), len(raw)))
    return result


# ---------------------------------------------------------------- рендер
def esc(s):
    return H.escape(s or "", quote=True)


def days_word(n):
    if 11 <= n % 100 <= 14: return "дней"
    return {1: "день", 2: "дня", 3: "дня", 4: "дня"}.get(n % 10, "дней")


def parse_iso(s):
    try:
        return date.fromisoformat(s)
    except (ValueError, TypeError):
        return None


def fmt_ru(d):
    m = ["января", "февраля", "марта", "апреля", "мая", "июня", "июля",
         "августа", "сентября", "октября", "ноября", "декабря"][d.month - 1]
    return "%d %s %d" % (d.day, m, d.year)


def link_row(it):
    out = []
    apply_url = it.get("apply_url") or it["source_url"]
    out.append('<a class="apply" target="_blank" rel="noopener" href="%s">Условия и заявка</a>' % esc(apply_url))
    src = it["source_url"]
    if src != apply_url:
        cls = "plain tg" if "t.me/" in src else "plain"
        label = "Пост в Telegram" if "t.me/" in src else "Источник"
        out.append('<a class="%s" target="_blank" rel="noopener" href="%s">%s</a>' % (cls, esc(src), label))
    return '<div class="links">%s</div>' % "".join(out)


def card(it, today):
    d = parse_iso(it.get("deadline", ""))
    if d:
        left = (d - today).days
        chip = '<div class="chip %s">%d %s</div>' % ("hot" if left <= 7 else "calm", left, days_word(left))
        datebox = "до %02d.%02d" % (d.day, d.month)
    else:
        chip = '<div class="chip off">без дедлайна</div>'
        datebox = "бессрочно"
    meta = []
    for label, value in (("Приём заявок", fmt_ru(d) if d else "бессрочно"),
                         ("Проведение", it.get("period")),
                         ("Кто может подать", it.get("who")),
                         ("Техники", it.get("techniques")),
                         ("Что даёт", it.get("provides")),
                         ("Контакт", it.get("contact"))):
        if value:
            meta.append('<div class="pair"><dt>%s</dt><dd>%s</dd></div>' % (esc(label), esc(value)))
    theme = ('<div class="theme"><span>Тема</span>%s</div>' % esc(it["theme"])) if it.get("theme") else ""
    org = " · ".join(x for x in (it.get("org"), it.get("city")) if x)
    return f"""<article class="item">
  <div class="reg"><div class="date">{datebox}</div>{chip}<div class="eyebrow">{esc(it['source'])}</div></div>
  <div class="body">
    <h3>{esc(it['title'])}</h3>
    {'<p class="org">%s</p>' % esc(org) if org else ''}
    {theme}
    <p class="desc">{esc(it['summary'])}</p>
    <dl class="meta">{''.join(meta)}</dl>
    {link_row(it)}
  </div>
</article>"""


def row(it):
    d = parse_iso(it.get("deadline", ""))
    org = " · ".join(x for x in (it.get("org"), it.get("city")) if x)
    apply_url = it.get("apply_url") or it["source_url"]
    return f"""<div class="row">
  <div class="date">закрыт {('%02d.%02d' % (d.day, d.month)) if d else '—'}</div>
  <div>
    <h3>{esc(it['title'])}</h3>
    {'<p class="place">%s</p>' % esc(org) if org else ''}
    <p>{esc(it['summary'])}</p>
    {'<p class="tech">%s</p>' % esc(it['techniques']) if it.get('techniques') else ''}
    <p class="go"><a class="plain" target="_blank" rel="noopener" href="{esc(apply_url)}">Страница организатора</a></p>
  </div>
</div>"""


def render(store, stamp):
    today = date.today()
    items = list(store["items"].values())
    open_, closed = [], []
    for it in items:
        d = parse_iso(it.get("deadline", ""))
        (closed if (d and d < today) else open_).append(it)
    open_.sort(key=lambda i: parse_iso(i.get("deadline", "")) or date(2099, 1, 1))
    closed.sort(key=lambda i: parse_iso(i.get("deadline", "")) or date(1970, 1, 1), reverse=True)

    reasons = {}
    for r in store["rejected"].values():
        reasons[r] = reasons.get(r, 0) + 1
    rejected_html = "".join(
        '<li><b>%d</b><span>%s</span></li>' % (n, esc(k))
        for k, n in sorted(reasons.items(), key=lambda kv: -kv[1]))

    css = open(os.path.join(HERE, "style.css"), encoding="utf-8").read()
    first = ' first' if open_ else ''
    cards = "".join(card(i, today) for i in open_).replace('class="item"', 'class="item%s"' % first, 1)
    rows = "".join(row(i) for i in closed).replace('class="row"', 'class="row first"', 1)

    return f"""<!doctype html>
<html lang="ru"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Каталог опен-коллов</title>
<meta name="robots" content="noindex, nofollow">
<meta name="description" content="Опен-коллы для художников: живопись, графика, коллаж, смешанные техники. Обновляется автоматически.">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Unbounded:wght@400;600;700&family=Golos+Text:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500&display=swap">
<style>{css}</style>
</head><body>
<div class="wrap">
<header class="masthead">
  <div class="eyebrow">Обновлено {stamp} · Россия</div>
  <h1>Каталог опен-коллов</h1>
  <p class="sub">Страница пересобирается автоматически. Закрытые приёмы остаются в архиве: почти всё это ежегодные конкурсы, резиденции и ярмарки, и по ним видно, когда готовить заявку в следующий раз.</p>
  <div class="criteria">
    <span class="tag">живопись</span><span class="tag">графика</span>
    <span class="tag">коллаж аналоговый и цифровой</span><span class="tag">смешанные техники</span>
    <span class="tag no">VR</span><span class="tag no">медиаарт</span>
  </div>
  <div class="stats">
    <span>Всего в каталоге <b>{len(items)}</b></span>
    <span>Приём открыт <b>{len(open_)}</b></span>
    <span>Приём закрыт <b>{len(closed)}</b></span>
    <span>Отсеяно <b>{len(store['rejected'])}</b></span>
  </div>
</header>

<h2 class="sec">Приём заявок открыт</h2>
<p class="sec-note">Отсортировано по дедлайну — от ближайшего.</p>
{cards or '<p class="sec-note">Сейчас открытых приёмов нет.</p>'}

<h2 class="sec">Приём закрыт</h2>
<p class="sec-note">Архив: ориентир по срокам на следующий сезон.</p>
{rows or '<p class="sec-note">Архив пока пуст.</p>'}

<h2 class="sec">Отсеяно</h2>
<section class="report">
  <div class="eyebrow">Не прошло фильтр</div>
  <h3>Всего {len(store['rejected'])} записей</h3>
  <ul>{rejected_html or '<li><b>0</b><span>пока ничего</span></li>'}</ul>
</section>

<p class="foot">Источники: телеграм-каналы «Где выставка» и «Арт опен-коллы», RSS агрегатора vsekonkursy.ru, каталог ewert.ru и сайты организаторов. Условия и суммы уточняйте на странице организатора. Страница обновлена {stamp}.</p>
</div>
</body></html>"""


# ---------------------------------------------------------------- главный проход
def main():
    dry = "--dry" in sys.argv
    skip_llm = "--no-llm" in sys.argv
    store = load_store()
    seen = set(store["items"]) | set(store["rejected"])

    if not skip_llm and not os.environ.get("ANTHROPIC_API_KEY"):
        log("ANTHROPIC_API_KEY не задан — пропускаю сбор, пересобираю страницу из архива")
        skip_llm = True

    if not skip_llm:
        raw = collect.collect(seen, log)
        fresh = [it for it in raw if it["source_url"] not in seen]
        log("новых записей: %d" % len(fresh))
        if dry:
            for it in fresh:
                log("  •", it["title"][:90])
            return
        if fresh:
            for src, p in enrich(fresh):
                url = src["source_url"]
                if not p["relevant"]:
                    store["rejected"][url] = p["reject_reason"] or "не подошло"
                    continue
                store["items"][url] = {
                    "source": src["source"], "source_url": url,
                    "apply_url": p["apply_url"] or src.get("apply_url") or url,
                    "title": p["title"] or src["title"], "org": p["org"], "city": p["city"],
                    "theme": p["theme"], "summary": p["summary"], "deadline": p["deadline"],
                    "period": p["period"], "who": p["who"], "techniques": p["techniques"],
                    "provides": p["provides"], "contact": p["contact"],
                    "first_seen": store["items"].get(url, {}).get(
                        "first_seen", date.today().isoformat()),
                }
            save_store(store)
            log("в каталоге: %d, отсеяно всего: %d" % (len(store["items"]), len(store["rejected"])))

    msk = timezone(timedelta(hours=3))
    stamp = datetime.now(msk).strftime("%d.%m.%Y, %H:%M МСК")
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(render(store, stamp))
    log("страница записана: %s" % OUT)


if __name__ == "__main__":
    main()
