
import json, re, html, time
from pathlib import Path
from datetime import datetime, timezone, timedelta
from urllib.parse import quote_plus, urlparse
import requests
import feedparser
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
CFG = json.loads((ROOT/"config/sources.json").read_text(encoding="utf-8"))
OUT = ROOT/"data/items.json"

UA = {"User-Agent": "Mozilla/5.0 (compatible; OtakuRadar/1.0; +https://github.com/)"}
JST = timezone(timedelta(hours=9))

def gnews_url(q):
    return f"https://news.google.com/rss/search?q={quote_plus(q)}&hl=ja&gl=JP&ceid=JP:ja"

def clean_text(s):
    s = BeautifulSoup(s or "", "html.parser").get_text(" ", strip=True)
    return re.sub(r"\s+", " ", html.unescape(s)).strip()

def dt_from_entry(e):
    st = getattr(e, "published_parsed", None) or getattr(e, "updated_parsed", None)
    if st:
        return datetime(*st[:6], tzinfo=timezone.utc)
    return datetime.now(timezone.utc)

def resolve_and_og(link, timeout=8):
    """Best effort only. If a site blocks requests, we simply keep the card without an image."""
    try:
        r = requests.get(link, headers=UA, timeout=timeout, allow_redirects=True)
        final = r.url
        if "text/html" not in r.headers.get("content-type",""):
            return final, ""
        soup = BeautifulSoup(r.text[:900000], "html.parser")
        for sel, attr in [
            ('meta[property="og:image"]',"content"),
            ('meta[name="twitter:image"]',"content"),
            ('meta[property="twitter:image"]',"content")
        ]:
            tag = soup.select_one(sel)
            if tag and tag.get(attr):
                return final, tag.get(attr)
        return final, ""
    except Exception:
        return link, ""

def score_item(title, category):
    t = title.lower()
    score = 0
    hot = ["予約開始","抽選","限定","完売","品薄","再販","新作","発売","登場","開催決定","受付開始"]
    for k in hot:
        if k.lower() in t:
            score += 2
    if category == "trend":
        for k in ["抽選","完売","品薄","再販","限定","予約終了"]:
            if k in title:
                score += 3
    return min(score, 10)

def main():
    now = datetime.now(timezone.utc)
    lookback = now - timedelta(days=CFG["settings"].get("lookback_days", 14))
    items, seen = [], set()
    timeout = CFG["settings"].get("request_timeout_seconds", 8)
    max_per = CFG["settings"].get("max_items_per_source", 25)
    fetch_images = CFG["settings"].get("fetch_og_images", True)

    for src in CFG["sources"]:
        if src["type"] != "google_news":
            continue
        feed = feedparser.parse(gnews_url(src["query"]), request_headers=UA)
        count = 0
        for e in feed.entries:
            if count >= max_per:
                break
            published = dt_from_entry(e)
            if published < lookback:
                continue
            title = clean_text(getattr(e, "title", ""))
            link = getattr(e, "link", "")
            if not title or not link:
                continue
            key = re.sub(r"\W+", "", title.lower())[:120]
            if key in seen:
                continue
            seen.add(key)
            final_link, image = (link, "")
            if fetch_images:
                final_link, image = resolve_and_og(link, timeout)
                time.sleep(0.08)
            source_name = clean_text(getattr(getattr(e, "source", {}), "title", "")) if getattr(e, "source", None) else src["name"]
            domain = urlparse(final_link).netloc.replace("www.","")
            items.append({
                "id": str(abs(hash(title + final_link))),
                "title": title,
                "url": final_link,
                "image": image,
                "category": src["category"],
                "feed_name": src["name"],
                "publisher": source_name or domain,
                "published_at": published.astimezone(JST).isoformat(),
                "score": score_item(title, src["category"])
            })
            count += 1

    items.sort(key=lambda x: (x["score"], x["published_at"]), reverse=True)
    items = items[:CFG["settings"].get("max_total_items", 160)]
    payload = {
        "generated_at": datetime.now(JST).isoformat(),
        "count": len(items),
        "items": items
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {len(items)} items to {OUT}")

if __name__ == "__main__":
    main()
