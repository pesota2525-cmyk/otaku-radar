
import json, re, html, time, hashlib
from pathlib import Path
from datetime import datetime, timezone, timedelta
from urllib.parse import quote_plus, urljoin, urlparse
import requests
import feedparser
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
CFG = json.loads((ROOT/"config/sources.json").read_text(encoding="utf-8"))
OUT = ROOT/"data/items.json"
JST = timezone(timedelta(hours=9))
UA = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/151 Safari/537.36",
    "Accept-Language": "ja,en-US;q=0.7,en;q=0.5"
}
SESSION = requests.Session()
SESSION.headers.update(UA)

PHOTO_POSITIVE = [
    "撮影会","水着","コスプレ","グラビア","女性モデル","モデル","アイドル","女優",
    "私服","浴衣","着エロ","個撮","団体撮影"
]
MINOR_TERMS = [
    "中学生","高校生","小学生","未成年","17歳","１６歳","16歳","１５歳","15歳",
    "１４歳","14歳","１３歳","13歳","12歳","１１歳","11歳"
]
BAD_IMAGE_PARTS = [
    "news.google.com","gstatic.com","googleusercontent.com",
    "logo","favicon","icon","header","common/logo","bnr_side"
]

def now_utc():
    return datetime.now(timezone.utc)

def stable_id(*parts):
    raw = "||".join(str(x or "") for x in parts)
    return hashlib.sha1(raw.encode("utf-8", "ignore")).hexdigest()[:20]

def clean_text(s):
    if not s:
        return ""
    s = BeautifulSoup(str(s), "html.parser").get_text(" ", strip=True)
    return re.sub(r"\s+", " ", html.unescape(s)).strip()

def fetch(url, timeout=None):
    timeout = timeout or CFG["settings"].get("request_timeout_seconds", 10)
    try:
        r = SESSION.get(url, timeout=timeout, allow_redirects=True)
        r.raise_for_status()
        if not r.encoding or r.encoding.lower() == "iso-8859-1":
            r.encoding = r.apparent_encoding or "utf-8"
        return r
    except Exception as e:
        print("FETCH FAIL", url, type(e).__name__, e)
        return None

def soup_for(url):
    r = fetch(url)
    if not r:
        return None, url
    return BeautifulSoup(r.text, "html.parser"), r.url

def valid_image(url):
    if not url:
        return False
    low = url.lower()
    return not any(x in low for x in BAD_IMAGE_PARTS)

def pick_image(soup, base):
    if not soup:
        return ""
    for sel, attr in [
        ('meta[property="og:image"]',"content"),
        ('meta[name="twitter:image"]',"content"),
        ('meta[property="twitter:image"]',"content")
    ]:
        tag = soup.select_one(sel)
        if tag and tag.get(attr):
            u = urljoin(base, tag.get(attr).strip())
            if valid_image(u):
                return u

    candidates = []
    for img in soup.find_all("img"):
        src = img.get("data-src") or img.get("data-original") or img.get("src") or ""
        if not src:
            continue
        u = urljoin(base, src)
        if not valid_image(u):
            continue
        alt = clean_text(img.get("alt",""))
        width = str(img.get("width",""))
        height = str(img.get("height",""))
        score = 0
        if alt: score += 1
        if any(k in alt for k in ["商品","イベント","ポップアップ","撮影","特典","画像"]): score += 4
        try:
            if int(re.sub(r"\D","",width) or "0") >= 300: score += 2
            if int(re.sub(r"\D","",height) or "0") >= 180: score += 2
        except:
            pass
        candidates.append((score, u))
    if candidates:
        candidates.sort(reverse=True)
        return candidates[0][1]
    return ""

def page_title(soup):
    if not soup: return ""
    tag = soup.select_one('meta[property="og:title"]')
    if tag and tag.get("content"):
        return clean_text(tag["content"])
    h1 = soup.find("h1")
    if h1:
        return clean_text(h1.get_text(" ", strip=True))
    if soup.title:
        return clean_text(soup.title.get_text(" ", strip=True))
    return ""

def page_description(soup):
    if not soup: return ""
    for sel in ['meta[property="og:description"]','meta[name="description"]']:
        tag = soup.select_one(sel)
        if tag and tag.get("content"):
            return clean_text(tag["content"])
    return ""

def detect_published(text, soup=None):
    if soup:
        for sel in ['meta[property="article:published_time"]','time[datetime]']:
            tag = soup.select_one(sel)
            val = tag.get("content") if tag and tag.has_attr("content") else (tag.get("datetime") if tag else None)
            if val:
                try:
                    return datetime.fromisoformat(val.replace("Z","+00:00")).astimezone(timezone.utc)
                except:
                    pass
    patterns = [
        r"(20\d{2})年\s*(\d{1,2})月\s*(\d{1,2})日(?:\s*公開)?",
        r"(20\d{2})[./-](\d{1,2})[./-](\d{1,2})"
    ]
    for p in patterns:
        m = re.search(p, text or "")
        if m:
            try:
                return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)), tzinfo=JST).astimezone(timezone.utc)
            except:
                pass
    return None

def extract_meta_line(text):
    text = clean_text(text)
    keys = ["開催期間","開催日","発売日","予約締切","予約期間","受付開始","販売期間"]
    for k in keys:
        i = text.find(k)
        if i >= 0:
            chunk = text[i:i+110]
            return chunk.split("。")[0].strip()
    return ""

def score_item(title, text, category, direct=False, image=""):
    hay = f"{title} {text}".lower()
    score = 2 if direct else 0
    if image: score += 2
    for k in ["予約開始","予約受付中","抽選","限定","完売","品薄","再販","新作","発売","開催","特典","描き下ろし"]:
        if k.lower() in hay:
            score += 1
    if category == "gamers": score += 2
    if category == "eroge" and ("特典" in hay or "描き下ろし" in hay): score += 3
    if category == "photo" and any(k in hay for k in ["水着","コスプレ","グラビア","女優"]): score += 2
    return min(score, 15)

def is_photo_allowed(text):
    t = clean_text(text)
    if CFG["settings"].get("photo_only_adults", True):
        if any(k in t for k in MINOR_TERMS):
            return False
    return any(k in t for k in PHOTO_POSITIVE)

def passes(text, src):
    t = clean_text(text)
    must_all = src.get("must_all", [])
    must_any = src.get("must_any", [])
    if must_all and not all(k.lower() in t.lower() for k in must_all):
        return False
    if must_any and not any(k.lower() in t.lower() for k in must_any):
        return False
    if src.get("female_photo") and not is_photo_allowed(t):
        return False
    return True

def gnews_url(q):
    return f"https://news.google.com/rss/search?q={quote_plus(q)}&hl=ja&gl=JP&ceid=JP:ja"

def dt_from_feed(e):
    st = getattr(e, "published_parsed", None) or getattr(e, "updated_parsed", None)
    if st:
        return datetime(*st[:6], tzinfo=timezone.utc)
    return now_utc()

def read_previous():
    if not OUT.exists():
        return {}
    try:
        data = json.loads(OUT.read_text(encoding="utf-8"))
        return {x.get("url"): x for x in data.get("items", []) if x.get("url")}
    except:
        return {}

def add_item(items, previous, *, title, url, category, source_name, store="", text="", image="",
             published=None, adult=False, direct=False, meta_line="", source_type=""):
    title = clean_text(title)
    text = clean_text(text)
    if not title or not url:
        return
    old = previous.get(url, {})
    if published is None:
        if old.get("published_at"):
            try:
                published = datetime.fromisoformat(old["published_at"]).astimezone(timezone.utc)
            except:
                published = now_utc()
        else:
            published = now_utc()
    if not image:
        image = old.get("image","")
    item = {
        "id": stable_id(url, title),
        "title": title[:240],
        "url": url,
        "image": image,
        "category": category,
        "feed_name": source_name,
        "publisher": store or source_name,
        "published_at": published.astimezone(JST).isoformat(),
        "score": score_item(title, text, category, direct=direct, image=image),
        "adult": bool(adult),
        "direct": bool(direct),
        "meta": clean_text(meta_line)[:150],
        "source_type": source_type
    }
    items.append(item)

def parse_google_news_feed(query):
    url = gnews_url(query)
    r = fetch(url, timeout=CFG["settings"].get("google_news_timeout_seconds", 12))
    if not r:
        return []
    try:
        feed = feedparser.parse(r.content)
        return list(feed.entries or [])
    except Exception as e:
        print("GNEWS PARSE FAIL", query, repr(e))
        return []

def collect_google_news(items, previous, lookback):
    """
    V3.3:
    - Fetch Google News RSS with requests (instead of letting feedparser do network I/O).
    - Try multiple progressively broader queries per category.
    - If a category still has too few fresh results, allow up to 90 days as a fallback.
    """
    for src in CFG.get("google_news", []):
        queries = [q for q in src.get("queries", []) if q]
        if not queries and src.get("query"):
            queries = [src["query"]]

        min_items = src.get("min_items", 12)
        max_items = src.get("max_items", 35)
        fallback_days = src.get("fallback_lookback_days", 90)
        fallback_cutoff = now_utc() - timedelta(days=fallback_days)

        seen_urls = set()
        accepted = 0

        for query in queries:
            entries = parse_google_news_feed(query)
            print("GNEWS", src["category"], "query=", query, "entries=", len(entries))

            # First pass: requested lookback window.
            for e in entries:
                if accepted >= max_items:
                    break
                dt = dt_from_feed(e)
                if dt < lookback:
                    continue

                title = clean_text(getattr(e, "title", ""))
                link = getattr(e, "link", "")
                if not title or not link or link in seen_urls:
                    continue
                if src["category"] == "photo" and not is_photo_allowed(title):
                    continue

                try:
                    publisher = clean_text(e.source.title)
                except:
                    publisher = src["name"]

                add_item(
                    items, previous,
                    title=title, url=link, category=src["category"],
                    source_name=src["name"], store=publisher, text=title,
                    image="", published=dt, direct=False,
                    source_type="google_news"
                )
                seen_urls.add(link)
                accepted += 1

            if accepted >= min_items:
                break

        # Second pass: widen to 90 days only when the category is still sparse.
        if accepted < min_items:
            for query in queries:
                entries = parse_google_news_feed(query)
                for e in entries:
                    if accepted >= max_items:
                        break
                    dt = dt_from_feed(e)
                    if dt < fallback_cutoff:
                        continue

                    title = clean_text(getattr(e, "title", ""))
                    link = getattr(e, "link", "")
                    if not title or not link or link in seen_urls:
                        continue
                    if src["category"] == "photo" and not is_photo_allowed(title):
                        continue

                    try:
                        publisher = clean_text(e.source.title)
                    except:
                        publisher = src["name"]

                    add_item(
                        items, previous,
                        title=title, url=link, category=src["category"],
                        source_name=src["name"], store=publisher, text=title,
                        image="", published=dt, direct=False,
                        source_type="google_news"
                    )
                    seen_urls.add(link)
                    accepted += 1

                if accepted >= min_items:
                    break

        print("GNEWS CATEGORY TOTAL", src["category"], accepted)

def nearest_context(a):
    node = a
    best = clean_text(a.get_text(" ", strip=True))
    for _ in range(5):
        node = node.parent
        if not node:
            break
        txt = clean_text(node.get_text(" ", strip=True))
        if 20 <= len(txt) <= 1200:
            best = txt
        if getattr(node, "name", "") in ["li","article","tr"]:
            break
    return best

def collect_direct_source(src, items, previous, lookback):
    seen_links = set()
    max_links = min(src.get("max_links", 30), CFG["settings"].get("max_detail_fetches_per_source", 35) + 25)
    candidates = []
    link_re = re.compile(src["link_regex"])

    for seed in src["seed_urls"]:
        soup, final = soup_for(seed)
        if not soup:
            continue
        for a in soup.find_all("a", href=True):
            href = urljoin(final, a["href"])
            if href in seen_links or not link_re.search(href):
                continue
            ctx = nearest_context(a)
            ckeys = src.get("context_any", [])
            if ckeys and not any(k.lower() in ctx.lower() for k in ckeys):
                # Don't reject Gamers POPUP links just because link context is terse.
                if src.get("category") != "gamers":
                    continue
            seen_links.add(href)
            candidates.append((href, ctx))
            if len(candidates) >= max_links:
                break
        if len(candidates) >= max_links:
            break

    detail_cap = CFG["settings"].get("max_detail_fetches_per_source", 35)
    for href, ctx in candidates[:detail_cap]:
        soup, final = soup_for(href)
        if not soup:
            continue
        text = clean_text(soup.get_text(" ", strip=True))
        combined = f"{ctx} {text}"
        if not passes(combined, src):
            continue
        title = page_title(soup)
        if not title or len(title) < 4:
            title = ctx[:180]
        image = pick_image(soup, final)
        published = detect_published(text, soup)
        if published and published < lookback and src.get("category") not in ("gamers","eroge","bookbonus","doujin"):
            continue
        meta = extract_meta_line(text)
        add_item(
            items, previous, title=title, url=final, category=src["category"],
            source_name=src["name"], store=src.get("store",""), text=combined,
            image=image, published=published, adult=src.get("adult",False),
            direct=True, meta_line=meta, source_type="direct"
        )
        time.sleep(0.05)

def collect_page_card(src, items, previous, lookback):
    soup, final = soup_for(src["url"])
    if not soup:
        return
    text = clean_text(soup.get_text(" ", strip=True))
    if not passes(text, src):
        return
    title = page_title(soup) or src["name"]
    # For schedule pages, prepend current/newest date snippet if available.
    date_match = re.search(r"20\d{2}年\s*\d{1,2}月\s*\d{1,2}日[^。]{0,80}", text)
    if date_match:
        title = f"{src['name']}｜{date_match.group(0)[:90]}"
    image = pick_image(soup, final)
    published = detect_published(text, soup)
    meta = extract_meta_line(text)
    add_item(
        items, previous, title=title, url=final, category=src["category"],
        source_name=src["name"], store=src.get("store",""), text=text,
        image=image, published=published, adult=src.get("adult",False),
        direct=True, meta_line=meta, source_type="page"
    )

def collect_external_antenna(src, items, previous, lookback):
    soup, final = soup_for(src["url"])
    if not soup:
        return
    candidates = []
    seen = set()
    for a in soup.find_all("a", href=True):
        href = urljoin(final, a["href"])
        dom = urlparse(href).netloc
        if not dom or "hatena.ne.jp" in dom:
            continue
        ctx = nearest_context(a)
        if not any(k.lower() in ctx.lower() for k in src.get("context_any", [])):
            continue
        if src.get("female_photo") and not is_photo_allowed(ctx):
            continue
        if href in seen:
            continue
        seen.add(href)
        candidates.append((href, ctx))
        if len(candidates) >= src.get("max_links", 30):
            break

    for href, ctx in candidates[:25]:
        soup2, final2 = soup_for(href)
        if soup2:
            text = clean_text(soup2.get_text(" ", strip=True))
            combined = f"{ctx} {text}"
            if src.get("female_photo") and not is_photo_allowed(combined):
                continue
            title = page_title(soup2) or clean_text(a.get_text(" ", strip=True)) or ctx[:180]
            image = pick_image(soup2, final2)
            published = detect_published(text, soup2)
            meta = extract_meta_line(text)
        else:
            title = ctx[:180]
            image = ""
            published = None
            meta = extract_meta_line(ctx)
        add_item(
            items, previous, title=title, url=final2 if soup2 else href,
            category=src["category"], source_name=src["name"], store=urlparse(href).netloc.replace("www.",""),
            text=combined if soup2 else ctx, image=image, published=published,
            adult=src.get("adult",False), direct=True, meta_line=meta, source_type="antenna"
        )
        time.sleep(0.05)

def dedupe(items):
    # Prefer direct cards and cards with images when titles collide.
    def norm(t):
        t = re.sub(r"\s+","", t.lower())
        t = re.sub(r"[「」『』【】\[\]（）()・\-_|｜:：!！?？]","", t)
        return t[:110]
    best = {}
    for x in items:
        key = norm(x["title"])
        quality = (5 if x.get("direct") else 0) + (3 if x.get("image") else 0) + x.get("score",0)
        if key not in best or quality > best[key][0]:
            best[key] = (quality, x)
    return [v[1] for v in best.values()]

def main():
    previous = read_previous()
    items = []
    lookback = now_utc() - timedelta(days=CFG["settings"].get("lookback_days", 30))

    print("Collecting Google News...")
    collect_google_news(items, previous, lookback)

    print("Collecting direct sources...")
    for src in CFG.get("direct_sources", []):
        print(" ->", src["name"])
        try:
            collect_direct_source(src, items, previous, lookback)
        except Exception as e:
            print("SOURCE FAIL", src["name"], repr(e))

    print("Collecting schedule pages...")
    for src in CFG.get("page_cards", []):
        try:
            collect_page_card(src, items, previous, lookback)
        except Exception as e:
            print("PAGE FAIL", src["name"], repr(e))

    print("Collecting photo antenna...")
    for src in CFG.get("external_antenna", []):
        try:
            collect_external_antenna(src, items, previous, lookback)
        except Exception as e:
            print("ANTENNA FAIL", src["name"], repr(e))

    items = dedupe(items)

    # V3.2: Balance categories BEFORE applying the global cap.
    # V3 direct sources (especially Gamers) can generate enough cards to push
    # Google News categories out of the final dataset if we only sort globally.
    def item_sort_key(x):
        return (
            1 if x.get("direct") else 0,
            1 if x.get("image") else 0,
            x.get("score",0),
            x.get("published_at","")
        )

    by_cat = {}
    for x in items:
        by_cat.setdefault(x.get("category","other"), []).append(x)

    category_limits = CFG["settings"].get("category_limits", {})
    balanced = []
    leftovers = []

    for category, rows in by_cat.items():
        rows.sort(key=item_sort_key, reverse=True)
        limit = category_limits.get(category, 60)
        balanced.extend(rows[:limit])
        leftovers.extend(rows[limit:])

    balanced.sort(key=item_sort_key, reverse=True)
    leftovers.sort(key=item_sort_key, reverse=True)

    max_total = CFG["settings"].get("max_total_items", 520)
    if len(balanced) < max_total:
        balanced.extend(leftovers[:max_total-len(balanced)])

    items = balanced[:max_total]

    counts = {}
    for x in items:
        counts[x.get("category","other")] = counts.get(x.get("category","other"), 0) + 1
    print("Category counts:", counts)

    payload = {
        "version": 3.3,
        "generated_at": datetime.now(JST).isoformat(),
        "count": len(items),
        "items": items
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {len(items)} items")

if __name__ == "__main__":
    main()
