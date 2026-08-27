"""Сбор объявлений из источников. Только stdlib."""
import gzip, html, io, re, urllib.request
from datetime import datetime

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/124 Safari/537.36"

TELEGRAM = ["gdeart", "artopencall"]

RSS = [
    ("vsekonkursy.ru", "https://vsekonkursy.ru/feed"),
    ("artdeadline.com", "https://www.artdeadline.com/feed/"),
]

# индексы-каталоги: со страницы-списка берём ссылки по шаблону и заходим в каждую.
# limit — сколько новых карточек открывать за один прогон, чтобы не разгонять счёт.
INDEXES = [
    ("ewert.ru", "https://ewert.ru/opportunities/",
     r"https://ewert\.ru/competitions/[^\"']+", 25),
    ("resartis.org", "https://resartis.org/open-calls/",
     r"https://resartis\.org/open-call/[^\"'#]+", 20),
]


def get(url, timeout=25):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "ru,en;q=0.8"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read()
    if raw[:2] == b"\x1f\x8b":
        raw = gzip.GzipFile(fileobj=io.BytesIO(raw)).read()
    return raw.decode("utf-8", "replace")


def strip_tags(s):
    s = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", s)
    s = re.sub(r"<br\s*/?>", "\n", s)
    s = re.sub(r"(?i)</(p|div|li|h\d)>", "\n", s)
    s = re.sub(r"<[^>]+>", " ", s)
    s = html.unescape(s)
    return re.sub(r"[ \t]{2,}", " ", re.sub(r"\n{3,}", "\n\n", s)).strip()


def from_telegram(channel, log):
    """Публичное веб-превью канала: до 20 последних постов, без Bot API и без ключей."""
    out = []
    try:
        h = get("https://t.me/s/" + channel)
    except Exception as e:
        log("telegram/%s недоступен: %s" % (channel, e)); return out
    for c in h.split('class="tgme_widget_message ')[1:]:
        pid = re.search(r'data-post="([^"]+)"', c)
        body = re.search(r'<div class="tgme_widget_message_text[^"]*"[^>]*>(.*?)</div>\s*'
                         r'(?:<div class="tgme_widget_message_(?:footer|reply_markup)|</div>)', c, re.S)
        if not (pid and body):
            continue
        text = strip_tags(body.group(1))
        if len(text) < 60:
            continue
        ext = [l for l in re.findall(r'href="(https?://[^"]+)"', body.group(1)) if "t.me" not in l]
        out.append(dict(source="t.me/" + channel, source_url="https://t.me/" + pid.group(1),
                        apply_url=ext[0] if ext else None,
                        title=text.split("\n")[0][:180], text=text))
    log("t.me/%s — %d постов" % (channel, len(out)))
    return out


def from_rss(name, url, log):
    out = []
    try:
        x = get(url)
    except Exception as e:
        log("rss/%s недоступен: %s" % (name, e)); return out
    for it in re.findall(r"<item>(.*?)</item>", x, re.S):
        def field(tag):
            m = re.search(r"<%s>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</%s>" % (tag, tag), it, re.S)
            return html.unescape(m.group(1)).strip() if m else ""
        title, link = field("title"), field("link")
        if not title:
            continue
        out.append(dict(source=name, source_url=link, apply_url=link,
                        title=title, text=title + "\n" + strip_tags(field("description"))[:2500]))
    log("rss/%s — %d записей" % (name, len(out)))
    return out


def from_index(name, url, pattern, limit, seen_urls, log):
    """Каталог: собираем ссылки на карточки и открываем те, которых ещё не видели."""
    out = []
    try:
        h = get(url)
    except Exception as e:
        log("index/%s недоступен: %s" % (name, e)); return out
    links, order = set(), []
    for m in re.finditer(pattern, h):
        u = m.group(0).rstrip("\"'")
        if u not in links:
            links.add(u); order.append(u)
    fresh = [u for u in order if u not in seen_urls][:limit]
    log("index/%s — %d карточек, из них новых %d" % (name, len(order), len(fresh)))
    for u in fresh:
        try:
            page = strip_tags(get(u))
        except Exception as e:
            log("  не открылась %s: %s" % (u, e)); continue
        title = page.split("\n")[0][:180]
        out.append(dict(source=name, source_url=u, apply_url=u, title=title, text=page[:4000]))
    return out


def collect(seen_urls, log=print):
    items = []
    for ch in TELEGRAM:
        items += from_telegram(ch, log)
    for name, url in RSS:
        items += from_rss(name, url, log)
    for name, url, pattern, limit in INDEXES:
        items += from_index(name, url, pattern, limit, seen_urls, log)
    log("собрано записей: %d" % len(items))
    return items
