# ==============================================================================
# 【EAT MAP】究極の幹事サポート・No-Exit全画面マップ 完全統合版 (前半)
# ==============================================================================
import os, urllib.request, urllib.parse, json, re, time, gzip, html, base64, socket, math, concurrent.futures
from collections import defaultdict
from flask import Flask, request, render_template_string, jsonify, Response

# IPv6遅延対策
_orig_gai = socket.getaddrinfo
socket.getaddrinfo = lambda *args, **kwargs: [r for r in _orig_gai(*args, **kwargs) if r[0] == socket.AF_INET] or _orig_gai(*args, **kwargs)

app = Flask(__name__)

# --- APIキーの設定 ---
HOTPEPPER_API_KEY     = os.environ.get("HOTPEPPER_API_KEY", "").strip() or "16ba3d78b920bccf"
GROQ_API_KEY          = os.environ.get("GROQ_API_KEY", "").strip()
GEMINI_API_KEY        = os.environ.get("GEMINI_API_KEY", "").strip()
GOOGLE_PLACES_API_KEY = os.environ.get("GOOGLE_PLACES_API_KEY", "").strip() or "AIzaSyDpVErGY32EqC5_jArZs0RnA52Vz5pLMLs"
YAHOO_CLIENT_ID       = os.environ.get("YAHOO_CLIENT_ID", "").strip() or "dmVyPTIwMjUwNyZpZD1raW1RS01WREM4Jmhhc2g9TURKbU5EWmtZVFJoTkdJeFpERTJZdw"
RAKUTEN_APP_ID        = os.environ.get("RAKUTEN_APP_ID", "").strip() or "2bb90f1a-6eac-4ffe-acdd-9b59c82d20cf"

if not GEMINI_API_KEY:
    for k, v in os.environ.items():
        if "GEMINI" in k.upper() or "EAT" in k.upper():
            if v.startswith("AQ."):
                GEMINI_API_KEY = v.strip()
                break
if not GEMINI_API_KEY:
    GEMINI_API_KEY = base64.b64decode("QVEuQWI4Uk42S1EzbGtWSjctSVowSWFfNjEtdUpQaF9zT0tFUzFqNjV3WGg2bVZqc1o1bnc=").decode('utf-8')

# ================= 1. 安全対策・キャッシュ・セキュリティ =================
IP_LOG = defaultdict(list)
AI_CACHE, PLACES_CACHE, SEARCH_CACHE, RECIPE_CACHE = {}, {}, {}, {}

@app.before_request
def firewall():
    if request.path == '/ping': return None
    forwarded = request.headers.get('X-Forwarded-For')
    ip = forwarded.split(',')[0].strip() if forwarded else (request.remote_addr or '127.0.0.1')
    now = time.time()
    IP_LOG[ip] = [t for t in IP_LOG[ip] if now - t < 60]
    if len(IP_LOG) > 2000:
        for k in list(IP_LOG.keys()):
            if not IP_LOG[k]: del IP_LOG[k]
    if len(IP_LOG[ip]) >= 150:
        return "アクセス過多です。", 429
    IP_LOG[ip].append(now)

@app.after_request
def apply_security_and_compress(res):
    res.headers['X-Content-Type-Options'] = 'nosniff'
    res.headers['X-Frame-Options'] = 'DENY'
    res.headers['X-XSS-Protection'] = '1; mode=block'
    res.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    res.headers['Content-Security-Policy'] = (
        "default-src 'self' 'unsafe-inline' 'unsafe-eval' https: data:; "
        "img-src 'self' https: data: blob:; "
        "font-src 'self' https: data:; "
        "connect-src 'self' https://api.open-meteo.com https://generativelanguage.googleapis.com https://api.groq.com https://*.openstreetmap.org https://tile.openstreetmap.jp https://cyberjapandata.gsi.go.jp https://router.project-osrm.org https://places.googleapis.com https://maps.googleapis.com https://map.yahooapis.jp https://app.rakuten.co.jp https://vision.googleapis.com https://www.googleapis.com;"
    )
    if res.content_type and 'text/html' in res.content_type:
        res.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    if 'gzip' in request.headers.get('Accept-Encoding', '').lower() and 200 <= res.status_code < 300 and not res.headers.get('Content-Encoding'):
        data = res.get_data()
        if len(data) >= 500:
            c = gzip.compress(data)
            res.set_data(c)
            res.headers['Content-Encoding'] = 'gzip'
            res.headers['Content-Length'] = str(len(c))
    return res

# ================= 2. 各種API連携エンジン =================

def fetch_google_places_direct(query_str, lat=None, lng=None):
    if not GOOGLE_PLACES_API_KEY or not query_str: return []
    cache_key = f"g_direct_{query_str}_{lat}_{lng}"
    if cache_key in PLACES_CACHE: return PLACES_CACHE[cache_key]

    url = "https://places.googleapis.com/v1/places:searchText"
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": GOOGLE_PLACES_API_KEY,
        "X-Goog-FieldMask": "places.displayName,places.formattedAddress,places.location,places.rating,places.userRatingCount,places.nationalPhoneNumber,places.regularOpeningHours,places.primaryTypeDisplayName,places.websiteUri"
    }
    body_data = {
        "textQuery": f"{query_str} 飲食店 グルメ レストラン".strip(),
        "maxResultCount": 20,
        "languageCode": "ja"
    }
    if lat and lng:
        body_data["locationBias"] = {"circle": {"center": {"latitude": lat, "longitude": lng}, "radius": 5000.0}}

    g_shops = []
    try:
        req = urllib.request.Request(url, data=json.dumps(body_data).encode("utf-8"), headers=headers)
        with urllib.request.urlopen(req, timeout=3.5) as res:
            places = json.loads(res.read().decode("utf-8")).get("places", [])
            for p in places:
                loc = p.get("location", {})
                hours = p.get("regularOpeningHours", {}).get("weekdayDescriptions", [])
                genre = (p.get("primaryTypeDisplayName") or {}).get("text", "グルメ")
                g_shops.append({
                    "name": (p.get("displayName") or {}).get("text", "店舗名不明"),
                    "genre": genre,
                    "address": p.get("formattedAddress", "").replace("日本、", ""),
                    "budget": "要確認", "lat": loc.get("latitude"), "lng": loc.get("longitude"),
                    "tel": p.get("nationalPhoneNumber", "要確認"),
                    "open": "、".join(hours[:2]) if hours else "要確認", "close": "要確認",
                    "has_private": False, "smoking_info": "🚬/🚭 要確認",
                    "photo": "https://images.unsplash.com/photo-1517248135467-4c7edcad34c4?w=600",
                    "google_rating": p.get("rating"), "google_reviews_count": p.get("userRatingCount", 0),
                    "url": p.get("websiteUri", ""), "source": "google"
                })
        PLACES_CACHE[cache_key] = g_shops
        return g_shops
    except Exception: return []

def fetch_yahoo_local_task(keyword, lat, lng):
    if not YAHOO_CLIENT_ID: return []
    params = {"appid": YAHOO_CLIENT_ID, "output": "json", "results": 30, "gc": "01"}
    if keyword: params["query"] = keyword
    if lat and lng:
        params["lat"], params["lon"], params["dist"] = lat, lng, 3
        if not keyword: params["query"] = "飲食店"
    try:
        req = urllib.request.Request(f"https://map.yahooapis.jp/search/local/V1/localSearch?{urllib.parse.urlencode(params)}", headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=2.5) as res:
            features = json.loads(res.read().decode('utf-8')).get("Feature", [])
            y_shops = []
            for f in features:
                prop = f.get("Property", {})
                geom = f.get("Geometry", {}).get("Coordinates", "")
                lng_str, lat_str = geom.split(",") if geom and "," in geom else (None, None)
                cat = prop.get("Genre", [])
                y_shops.append({
                    "name": f.get("Name", "店舗名不明"),
                    "genre": cat[0].get("Name", "グルメ") if cat else "グルメ",
                    "address": prop.get("Address", ""), "budget": "要確認",
                    "lat": float(lat_str) if lat_str else None, "lng": float(lng_str) if lng_str else None,
                    "tel": prop.get("Tel1", "要確認"), "open": "要確認", "close": "要確認",
                    "photo": prop.get("Detail", {}).get("Image1", ""),
                    "google_rating": None, "source": "yahoo", "url": ""
                })
            return y_shops
    except Exception: return []

def fetch_hotpepper_task(keyword, area, lat, lng, start_idx=1, is_rain=False):
    if not HOTPEPPER_API_KEY: return []
    params = {"key": HOTPEPPER_API_KEY, "count": 100, "start": start_idx, "format": "json"}
    parts = [p for p in [area, keyword] if p]
    if lat and lng:
        params.update({"lat": lat, "lng": lng, "range": 3 if is_rain else 5})
        if parts: params["keyword"] = " ".join(parts)
    else: params["keyword"] = " ".join(parts) if parts else "居酒屋 グルメ"

    results = []
    try:
        req = urllib.request.Request(f"https://webservice.recruit.co.jp/hotpepper/gourmet/v1/?{urllib.parse.urlencode(params)}", headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=3.5) as res:
            data = json.loads(res.read().decode('utf-8'))
            for s in data.get("results", {}).get("shop", []):
                non_sm = s.get("non_smoking", "")
                if "全面禁煙" in non_sm: sm = "🚭 全面禁煙"
                elif "一部禁煙" in non_sm or "分煙" in non_sm: sm = "🚬 分煙"
                else: sm = "🚬 喫煙可"
                results.append({
                    "name": s.get("name", ""), "genre": (s.get("genre") or {}).get("name", "グルメ"),
                    "address": s.get("address", ""), "budget": (s.get("budget") or {}).get("name", "要確認"),
                    "lat": s.get("lat"), "lng": s.get("lng"), "tel": s.get("tel", "要確認"),
                    "open": s.get("open", "要確認"), "close": s.get("close", "不定休"),
                    "has_private": bool(s.get("private_room") and "あり" in s.get("private_room")),
                    "smoking_info": sm, "photo": ((s.get("photo") or {}).get("pc") or {}).get("l", ""),
                    "google_rating": None, "source": "hotpepper", "url": (s.get("urls") or {}).get("pc", "")
                })
    except Exception: pass
    return results

def fetch_rakuten_recipes(keyword):
    if not RAKUTEN_APP_ID or not keyword: return []
    clean_kw = re.sub(r'[^a-zA-Z0-9\u3040-\u309F\u30A0-\u30FA\u4E00-\u9FFF]', ' ', keyword).strip()
    first_word = clean_kw.split()[0] if clean_kw else "肉"
    if first_word in RECIPE_CACHE: return RECIPE_CACHE[first_word]

    try:
        req = urllib.request.Request(f"https://app.rakuten.co.jp/services/api/Recipe/CategoryRanking/20170426?applicationId={RAKUTEN_APP_ID}", headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=2.5) as res:
            d = json.loads(res.read().decode('utf-8'))
            recipes = [{"title": r.get("recipeTitle"), "url": r.get("recipeUrl"), "photo": r.get("foodImageUrl"), "cost": r.get("recipeCost"), "time": r.get("recipeIndication")} for r in d.get("result", [])[:4]]
            RECIPE_CACHE[first_word] = recipes
            return recipes
    except Exception: return []

def fetch_all_shops_massive(keyword="", area="", lat=None, lng=None, is_rain=False):
    cache_key = f"{keyword}_{area}_{lat}_{lng}_{is_rain}"
    if cache_key in SEARCH_CACHE: return SEARCH_CACHE[cache_key]

    query_str = " ".join([p for p in [area, keyword] if p]) or "グルメ"
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        f_goog = executor.submit(fetch_google_places_direct, query_str, lat, lng)
        f_hp1  = executor.submit(fetch_hotpepper_task, keyword, area, lat, lng, 1, is_rain)
        f_hp2  = executor.submit(fetch_hotpepper_task, keyword, area, lat, lng, 101, is_rain)
        f_yh   = executor.submit(fetch_yahoo_local_task, query_str, lat, lng)
        goog, hp1, hp2, yh = f_goog.result(), f_hp1.result(), f_hp2.result(), f_yh.result()

    all_raw = goog + hp1 + hp2 + yh
    results, existing = [], set()
    for s in all_raw:
        clean_n = re.sub(r'\s+', '', s["name"])
        if clean_n not in existing:
            results.append(s)
            existing.add(clean_n)

    if len(SEARCH_CACHE) > 50: SEARCH_CACHE.clear()
    SEARCH_CACHE[cache_key] = results
    return results

def fetch_single_google_rating(name, address):
    if not GOOGLE_PLACES_API_KEY: return None, 0
    try:
        url = "https://places.googleapis.com/v1/places:searchText"
        headers = {"Content-Type": "application/json", "X-Goog-Api-Key": GOOGLE_PLACES_API_KEY, "X-Goog-FieldMask": "places.rating,places.userRatingCount"}
        body = json.dumps({"textQuery": f"{name} {address}".strip(), "maxResultCount": 1}).encode("utf-8")
        req = urllib.request.Request(url, data=body, headers=headers)
        with urllib.request.urlopen(req, timeout=2.0) as res:
            p = json.loads(res.read().decode("utf-8")).get("places", [])
            if p: return p[0].get("rating"), p[0].get("userRatingCount", 0)
    except: pass
    return None, 0

# ================= 3. HTMLテンプレート =================
LAYOUT_HTML = """<!DOCTYPE html>
<html lang="ja">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no, viewport-fit=cover">
    <link rel="icon" href="data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 100 100%22><text y=%22.9em%22 font-size=%2290%22>🍽️</text></svg>">
    <title>EAT MAP</title>
    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
    <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
    <script>
        const savedTheme = localStorage.getItem('eatmap_theme') || (window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
        document.documentElement.setAttribute('data-theme', savedTheme);
        function doVibrate(ms=30){ try{ if('vibrate' in navigator) navigator.vibrate(ms); }catch(e){} }
        function showAppAlert(title, message) {
            doVibrate([200, 100, 200]);
            const box = document.createElement('div');
            box.style.position = 'fixed'; box.style.top = '20px'; box.style.left = '50%';
            box.style.transform = 'translateX(-50%)'; box.style.background = 'var(--primary)';
            box.style.color = '#fff'; box.style.padding = '16px'; box.style.borderRadius = '16px';
            box.style.boxShadow = '0 6px 20px rgba(0,0,0,0.2)'; box.style.zIndex = '99999';
            box.style.width = '90%'; box.style.maxWidth = '400px'; box.style.textAlign = 'center';
            box.innerHTML = `<div style="font-size:16px; font-weight:900; margin-bottom:8px;">${title}</div><div style="font-size:13px; font-weight:700;">${message}</div><button onclick="this.parentElement.remove()" style="margin-top:12px; width:100%; padding:10px; background:rgba(255,255,255,0.25); border:none; border-radius:10px; color:#fff; font-weight:900; cursor:pointer;">OK</button>`;
            document.body.appendChild(box);
        }
        function shareToLine(text) { window.open(`https://line.me/R/msg/text/?${encodeURIComponent(text)}`, '_blank'); }
    </script>
    <style>
        :root {
            --bg:#f8fafc; --card:#ffffff; --border:#e2e8f0; --text:#1e293b; --muted:#64748b;
            --primary:#ff5252; --primary-light:#fff1f2; --yellow:#f59e0b; --green:#10b981; --blue:#3b82f6; --purple:#8b5cf6;
            --line:#06c755; --shadow:0 2px 10px rgba(15,23,42,0.06);
        }
        [data-theme="dark"] {
            --bg:#0f172a; --card:#1e293b; --border:#334155; --text:#f8fafc; --muted:#94a3b8;
            --primary:#ff6b6b; --primary-light:#2c2125; --yellow:#fbbf24; --green:#34d399; --blue:#60a5fa; --purple:#a78bfa;
            --line:#06c755; --input:#0f172a; --tag:#283347; --shadow:0 2px 12px rgba(0,0,0,0.25);
        }
        * { box-sizing:border-box; -webkit-tap-highlight-color:transparent; }
        body { background:var(--bg); color:var(--text); font-family:-apple-system,BlinkMacSystemFont,sans-serif; margin:0; padding:0 0 70px 0; min-height:100vh; }
        .max-w { max-width:480px; margin:0 auto; padding:14px; }
        .card { background:var(--card); border:1.5px solid var(--border); border-radius:16px; padding:14px; margin-bottom:12px; box-shadow:var(--shadow); position:relative; }
        .top-bar { display:flex; justify-content:space-between; align-items:center; margin-bottom:12px; }
        .brand { font-size:21px; font-weight:900; color:var(--primary); text-decoration:none; }
        .btn-sm { cursor:pointer; border-radius:10px; display:inline-flex; align-items:center; justify-content:center; font-weight:800; border:1.5px solid var(--border); padding:8px 12px; font-size:12px; background:var(--card); color:var(--text); text-decoration:none; }
        .btn-block { width:100%; min-height:46px; border-radius:10px; font-size:14px; font-weight:800; border:none; cursor:pointer; display:inline-flex; align-items:center; justify-content:center; gap:6px; margin-bottom:8px; box-shadow:var(--shadow); }
        .btn-primary { background:var(--primary); color:#fff; } .btn-green { background:var(--green); color:#fff; } .btn-line { background:var(--line); color:#fff; } .btn-sub { background:var(--card); color:var(--text); border:1.5px solid var(--border); }
        .input-group { margin-bottom:10px; }
        .input-group input, .input-group textarea { width:100%; padding:12px 14px; border:1.5px solid var(--border); border-radius:10px; font-size:14px; outline:none; font-weight:700; background:var(--card); color:var(--text); font-family:inherit; }
        .badge { display:inline-flex; align-items:center; gap:3px; font-size:10.5px; font-weight:800; padding:3px 6px; border-radius:6px; background:#f1f5f9; color:var(--text); }
        .bottom-nav { position:fixed; bottom:0; left:0; width:100%; background:var(--card); border-top:1.5px solid var(--border); display:flex; justify-content:space-around; padding:6px 0 calc(6px + env(safe-area-inset-bottom)); z-index:9000; }
        .bottom-nav a { color:var(--muted); text-decoration:none; font-size:10px; display:flex; flex-direction:column; align-items:center; gap:2px; font-weight:800; width:20%; }
        .bottom-nav a.active { color:var(--primary); }
        .bottom-nav span.icon { font-size:20px; }

        /* 超見やすいカプセル型ピン（Google風） */
        .pill-pin { background:#fff; border:1.5px solid var(--primary); border-radius:20px; padding:3px 8px; box-shadow:0 3px 6px rgba(0,0,0,0.3); font-weight:900; color:var(--primary); font-size:12px; display:flex; align-items:center; gap:4px; white-space:nowrap; cursor:pointer; transition:transform 0.2s; position:relative; }
        .pill-pin:active { transform:scale(0.9); }
        .pill-pin::after { content:''; position:absolute; bottom:-6px; left:50%; transform:translateX(-50%); border-width:6px 5px 0; border-style:solid; border-color:var(--primary) transparent transparent transparent; }
        /* GPSパルス */
        .gps-pulse-marker { position:relative; width:22px; height:22px; }
        .gps-dot { width:16px; height:16px; background:#2563eb; border:2.5px solid #fff; border-radius:50%; box-shadow:0 0 5px rgba(0,0,0,0.4); position:absolute; top:3px; left:3px; z-index:2; }
        .gps-ring { width:22px; height:22px; background:rgba(37,99,235,0.4); border-radius:50%; position:absolute; top:0; left:0; animation:pulseRadar 1.5s infinite ease-out; }
        @keyframes pulseRadar { 0% { transform:scale(0.6); opacity:1; } 100% { transform:scale(2.4); opacity:0; } }

        #loading-overlay { position:fixed; top:0; left:0; width:100vw; height:100vh; background:rgba(0,0,0,0.65); display:none; justify-content:center; align-items:center; flex-direction:column; z-index:99999; backdrop-filter:blur(4px); }
        .spinner { width:36px; height:36px; border:4px solid rgba(255,255,255,0.25); border-top-color:#fff; border-radius:50%; animation:spin .7s linear infinite; margin-bottom:12px; }
        @keyframes spin { 100% { transform:rotate(360deg); } }
    </style>
</head>
<body>
    <div id="loading-overlay"><div class="spinner"></div><div id="loading-msg" style="color:#fff; font-size:13.5px; font-weight:800;">処理中...</div></div>
    {{ content | safe }}
    <div class="bottom-nav">
        <a href="/" id="nav-home"><span class="icon">🔍</span><span>探す</span></a>
        <a href="/favorites" id="nav-fav"><span class="icon">📋</span><span>記録</span></a>
        <a href="/tools" id="nav-tools"><span class="icon">🧮</span><span>幹事</span></a>
        <a href="/chat" id="nav-chat"><span class="icon">💬</span><span>相談</span></a>
        <a href="/about" id="nav-about"><span class="icon">📖</span><span>ガイド</span></a>
    </div>
    <script>
        const p = window.location.pathname;
        const navMap = {'/':'nav-home','/chat':'nav-chat','/favorites':'nav-fav','/tools':'nav-tools','/about':'nav-about'};
        if(navMap[p] && document.getElementById(navMap[p])) document.getElementById(navMap[p]).classList.add('active');
        function toggleTheme(){
            const c = document.documentElement.getAttribute('data-theme')==='dark'?'light':'dark';
            document.documentElement.setAttribute('data-theme', c);
            localStorage.setItem('eatmap_theme', c);
            document.querySelectorAll('.theme-btn').forEach(b => b.innerText = c==='dark'?'☀️':'🌙');
        }
        window.addEventListener('DOMContentLoaded', ()=>{
            const isDark = document.documentElement.getAttribute('data-theme')==='dark';
            document.querySelectorAll('.theme-btn').forEach(b => b.innerText = isDark?'☀️':'🌙');
        });
    </script>
</body>
</html>"""

def render_page(inner_content):
    return render_template_string(LAYOUT_HTML, content=inner_content)

# ================= 4. 各画面コンテンツ =================

# --- ホーム画面 ---
HOME_CONTENT = """
<div class="max-w">
<div class="top-bar">
    <a href="/" class="brand">🍽️ EAT MAP</a>
    <div style="display:flex; gap:6px;">
        <button class="btn-sm theme-btn" style="width:36px;height:36px;padding:0;" onclick="toggleTheme()">🌙</button>
        <button class="btn-sm" style="width:36px;height:36px;padding:0;" onclick="window.location.reload(true)">🔄</button>
    </div>
</div>
<div id="weather-banner" style="display:none; background:#dbeafe; color:#1e3a8a; padding:10px; border-radius:10px; font-size:12px; font-weight:800; margin-bottom:12px; text-align:center;">☔ 現在雨のため、駅近・アーケード沿いを優先表示します</div>

<div style="display:grid; grid-template-columns:1fr 1fr; gap:8px; margin-bottom:12px;">
    <button class="btn-block btn-green" onclick="searchLoc()">📍 現在地周辺</button>
    <button class="btn-block btn-primary" style="background:var(--yellow); color:#493800;" onclick="window.location.href='/tools'">🧮 幹事ツール</button>
</div>

<div class="card">
    <div style="font-size:12px; font-weight:800; color:var(--muted); margin-bottom:10px;">⭐ 人気ジャンル一発検索</div>
    <div style="display:grid; grid-template-columns:repeat(4,1fr); gap:6px; margin-bottom:14px;">
        <button class="btn-sm" style="background:#fee2e2; border-color:#fca5a5; color:#991b1b;" onclick="quick('居酒屋 個室')">🍺 居酒屋</button>
        <button class="btn-sm" style="background:#fef3c7; border-color:#fde047; color:#854d0e;" onclick="quick('焼肉')">🍖 焼肉</button>
        <button class="btn-sm" style="background:#dcfce7; border-color:#86efac; color:#166534;" onclick="quick('カフェ')">☕ カフェ</button>
        <button class="btn-sm" style="background:#e0f2fe; border-color:#7dd3fc; color:#075985;" onclick="quick('ラーメン')">🍜 麺類</button>
    </div>

    <form action="/search" method="GET" id="s-form" onsubmit="showLoad()">
        <input type="hidden" name="is_rain" id="is-rain-input" value="0">
        <div class="input-group"><input type="text" name="area" id="area-in" placeholder="📍 エリア・駅名 (例: 姫路)"></div>
        <div class="input-group"><input type="text" name="keyword" id="kw-in" placeholder="🔍 キーワード (例: 個室 焼鳥)"></div>
        <button type="submit" class="btn-block btn-primary">Googleマップ基準で検索する</button>
    </form>
</div>
</div>
<script>
    function showLoad(){ document.getElementById('loading-overlay').style.display='flex'; }
    function quick(k){ document.getElementById('kw-in').value=k; showLoad(); document.getElementById('s-form').submit(); }
    function searchLoc(){ if(!navigator.geolocation) return showAppAlert("エラー","GPS非対応です"); showLoad(); navigator.geolocation.getCurrentPosition(p=>{ window.location.href=`/search?lat=${p.coords.latitude.toFixed(6)}&lng=${p.coords.longitude.toFixed(6)}&area=現在地周辺`; }, ()=>showAppAlert("エラー","GPSを許可してください"), {timeout:8000}); }

    // 天気連動ロジック
    window.addEventListener('DOMContentLoaded', async ()=>{
        if(navigator.geolocation) {
            navigator.geolocation.getCurrentPosition(async pos => {
                try {
                    const res = await fetch(`https://api.open-meteo.com/v1/forecast?latitude=${pos.coords.latitude}&longitude=${pos.coords.longitude}&current_weather=true`);
                    const data = await res.json();
                    const wCode = data.current_weather.weathercode;
                    if(wCode >= 50) { document.getElementById('weather-banner').style.display = 'block'; document.getElementById('is-rain-input').value = '1'; }
                }catch(e){}
            });
        }
    });
</script>
"""

# --- 検索結果・地図画面 ---
RESULT_CONTENT = """
<div id="view-list" class="max-w">
    <div class="top-bar">
        <a href="/" class="btn-sm">← 戻る</a>
        <div style="font-size:13px; font-weight:800;"><span id="shop-count">{{ shops|length }}</span>件表示中</div>
    </div>

    <!-- 高視認性カプセルマップ ＆ ルート描画 -->
    <div style="position:relative; margin-bottom:12px;">
        <div id="map-preview" style="height:280px; width:100%; border-radius:14px; border:1.5px solid var(--border); box-shadow:var(--shadow);"></div>
        <div style="position:absolute; bottom:10px; right:10px; z-index:1000; display:flex; gap:6px;">
            <button onclick="zoomToAll()" style="background:var(--card); border:1.5px solid var(--border); border-radius:8px; padding:6px 9px; font-size:11px; font-weight:900;">🗺️ 全体</button>
            <button onclick="recenterToUser()" style="background:var(--card); border:1.5px solid var(--border); border-radius:8px; padding:6px 9px; font-size:11px; font-weight:900;">🎯 現在地</button>
        </div>
    </div>

    <div style="display:flex; gap:6px; margin-bottom:10px;">
        <input type="text" id="live-filter" placeholder="⚡ 表示中のお店から絞り込み..." style="flex:1; padding:8px 12px; border:1.5px solid var(--border); border-radius:10px; font-size:12px; outline:none; font-weight:700;" oninput="filterShops(this.value)">
        <button class="btn-sm btn-sub" onclick="toggleSortRating()" id="sort-btn">⭐ 評価順</button>
    </div>

    {% if recipes %}
    <div class="card" style="background:linear-gradient(135deg, #fff7ed, #ffedd5); border-color:#fed7aa; margin-bottom:12px;">
        <div style="font-size:12px; font-weight:900; color:#c2410c; margin-bottom:6px;">🍳 自炊するなら？ 人気レシピと比較</div>
        <div style="display:flex; gap:8px; overflow-x:auto; padding-bottom:4px;">
            {% for r in recipes %}
            <div style="flex:0 0 140px; background:#fff; border-radius:10px; padding:6px; border:1px solid #fed7aa; font-size:11px;">
                <img src="{{ r.photo }}" style="width:100%; height:75px; object-fit:cover; border-radius:6px; margin-bottom:4px;" loading="lazy">
                <div style="font-weight:800; height:30px; overflow:hidden; line-height:1.2;">{{ r.title }}</div>
                <div style="color:var(--muted); font-size:9.5px; margin-top:2px;">💰 {{ r.cost }} / ⏱️ {{ r.time }}</div>
            </div>
            {% endfor %}
        </div>
    </div>
    {% endif %}

    <div id="shops-list">
        {% for s in shops %}
        <div class="card shop-card" id="shop-card-{{ loop.index0 }}" data-name="{{ s.name }}">
            {% if s.photo %}
            <img src="{{ s.photo }}" style="width:100%; height:160px; object-fit:cover; border-radius:12px; margin-bottom:10px; background:#222; cursor:pointer;" loading="lazy" onclick='openShopDetailByIndex({{ loop.index0 }})'>
            {% endif %}

            <h3 style="font-size:16px; font-weight:900; margin:0 0 4px 0; line-height:1.3; cursor:pointer;" onclick='openShopDetailByIndex({{ loop.index0 }})'>
                {{ loop.index }}. {{ s.name }}
            </h3>

            <div style="font-size:11.5px; font-weight:800; color:#b45309; margin-bottom:6px;">
                <span id="g-badge-{{ loop.index0 }}">⭐ 評価取得中...</span> ・ 💰 {{ s.budget }} ・ {{ s.genre }}
            </div>

            <div class="op-badge" data-open="{{ s.open }}" data-close="{{ s.close }}" style="display:inline-block; font-size:10.5px; font-weight:800; padding:2px 6px; border-radius:4px; background:#e2e8f0; color:#475569; margin-bottom:8px;">時間確認中...</div>
            <div style="font-size:11.5px; color:var(--muted); margin-bottom:10px; line-height:1.4;">📍 {{ s.address }}</div>

            <div style="display:flex; gap:6px;">
                <button class="btn-sm btn-sub" style="flex:1;" onclick='openShopDetailByIndex({{ loop.index0 }})'>詳細</button>
                <button class="btn-sm btn-sub" style="flex:1;" onclick='drawRouteTo({{ loop.index0 }})'>🧭 経路</button>
                <a href="tel:{{ s.tel }}" class="btn-sm btn-green" style="flex:1; text-decoration:none;">📞 電話</a>
            </div>
        </div>
        {% endfor %}
    </div>
</div>

<!-- 店舗詳細シート（No-Exit） -->
<div id="detail-modal" style="display:none; position:fixed; top:0; left:0; width:100vw; height:100vh; background:rgba(0,0,0,0.75); z-index:99999; justify-content:flex-end; align-items:center; padding:14px; flex-direction:column;">
    <div class="card" style="width:100%; max-width:440px; max-height:85vh; display:flex; flex-direction:column; margin:0; padding:16px;">
        <div style="display:flex; justify-content:space-between; align-items:flex-start; margin-bottom:12px;">
            <div style="font-size:17px; font-weight:900; line-height:1.3; flex:1;" id="dt-name">店舗詳細</div>
            <button onclick="closeShopDetail()" style="background:none; border:none; font-size:20px; cursor:pointer; font-weight:900;">✕</button>
        </div>
        <div style="overflow-y:auto; flex:1;">
            <div style="font-size:12px; line-height:1.8; background:var(--bg); padding:14px; border-radius:12px; margin-bottom:12px;">
                <div style="margin-bottom:6px;"><b>⭐ 評価:</b> <span id="dt-google" style="color:#d97706; font-weight:900;">--</span></div>
                <div style="margin-bottom:6px;"><b>💰 予算:</b> <span id="dt-budget">--</span></div>
                <div style="margin-bottom:6px;"><b>🕒 営業:</b> <span id="dt-open">--</span></div>
                <div style="margin-bottom:6px;"><b>📍 住所:</b> <span id="dt-address">--</span></div>
            </div>
            <div style="display:grid; grid-template-columns:1fr 1fr; gap:8px; margin-bottom:12px;">
                <a href="#" id="dt-tel-btn" class="btn-block btn-green" style="margin:0; font-size:13px; text-decoration:none;">📞 お店に電話</a>
                <button class="btn-block btn-primary" style="margin:0; font-size:13px;" onclick="goToInviteFromDetail()">📨 案内文を作る</button>
            </div>
            <div style="display:grid; grid-template-columns:1fr 1fr; gap:8px;">
                <button id="dt-fav-btn" class="btn-block btn-sub" style="margin:0; font-size:13px;" onclick="toggleCurrentFav()">🤍 保存</button>
                <button id="dt-cal-btn" class="btn-block btn-sub" style="margin:0; font-size:13px;" onclick="addToCalendarFromDetail()">📅 予定登録</button>
                <button id="dt-line-btn" class="btn-block btn-line" style="margin:0; grid-column: span 2; font-size:13px;">💬 LINEでお店を共有</button>
            </div>
        </div>
    </div>
</div>

<script>
    let shops = {{ shops | tojson | safe }};
    let map = null;
    let markers = [];
    let uLat = null, uLng = null;
    let isSorted = false;
    let currentDetailIdx = null;
    let currentRouteLine = null;

    window.addEventListener('DOMContentLoaded', () => {
        const defaultLat = (shops.length>0 && shops[0].lat) ? shops[0].lat : 34.8290;
        const defaultLng = (shops.length>0 && shops[0].lng) ? shops[0].lng : 134.6900;

        map = L.map('map-preview', {zoomControl:true}).setView([defaultLat, defaultLng], 14);
        L.tileLayer('https://tile.openstreetmap.jp/{z}/{x}/{y}.png', { maxZoom: 19 }).addTo(map);

        renderMarkers();
        updateOpenStatus();

        if(navigator.geolocation){
            navigator.geolocation.getCurrentPosition(pos => {
                uLat = pos.coords.latitude; uLng = pos.coords.longitude;
                const curIcon = L.divIcon({
                    className:'', html:`<div class="gps-pulse-marker"><div class="gps-dot"></div><div class="gps-ring"></div></div>`,
                    iconSize:[22,22], iconAnchor:[11,11]
                });
                L.marker([uLat, uLng], {icon: curIcon, zIndexOffset:1000}).addTo(map);
                map.flyTo([uLat, uLng], 15, {duration: 1.0});
            }, ()=>{}, {timeout:5000});
        }

        // 評価取得（バックグラウンド）
        const topShops = shops.slice(0, 30).map((s, idx) => ({index: idx, name: s.name, address: s.address}));
        fetch('/api/places_enrich', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({shops: topShops}) })
        .then(res => res.json()).then(data => {
            data.forEach(item => {
                if(item.rating) {
                    shops[item.index].google_rating = item.rating;
                    shops[item.index].google_reviews_count = item.count;
                    const b = document.getElementById(`g-badge-${item.index}`);
                    if(b) b.innerText = `⭐ ${item.rating} (${item.count})`;
                    renderMarkers();
                }
            });
        });
    });

    // カプセルピン描画
    function renderMarkers(filteredIndices = null) {
        markers.forEach(m => map.removeLayer(m));
        markers = [];
        shops.forEach((s, i) => {
            if(filteredIndices && !filteredIndices.has(i)) return;
            if(s.lat && s.lng){
                const rText = s.google_rating ? s.google_rating.toFixed(1) : '-.-';
                const pinHtml = `<div class="pill-pin"><span style="font-size:12px;">🍽️</span> ${rText}</div>`;
                const icon = L.divIcon({ className:'', html: pinHtml, iconSize:[60,26], iconAnchor:[30,26] });
                const m = L.marker([s.lat, s.lng], {icon}).addTo(map);
                m.on('click', () => openShopDetailByIndex(i));
                markers.push(m);
            }
        });
    }

    // 営業ステータス
    function updateOpenStatus() {
        const nowH = new Date().getHours();
        document.querySelectorAll('.op-badge').forEach(el => {
            const openT = el.getAttribute('data-open');
            if(openT.includes('24時間')) { el.innerText = "🟢 営業中"; el.style.background = "#dcfce7"; el.style.color = "#166534"; }
            else if(openT.includes('要確認')) { el.innerText = "⚪ 時間要確認"; }
            else {
                if(nowH >= 17 && nowH <= 23) { el.innerText = "🟢 営業中"; el.style.background = "#dcfce7"; el.style.color = "#166534"; }
                else { el.innerText = "🔴 営業時間外"; el.style.background = "#fee2e2"; el.style.color = "#991b1b"; }
            }
        });
    }

    // アプリ内ルート描画 (OSRM)
    async function drawRouteTo(idx) {
        if(!uLat || !uLng) return showAppAlert("エラー","現在地が取得できていません。");
        const s = shops[idx];
        if(!s.lat || !s.lng) return;
        document.getElementById('loading-overlay').style.display = 'flex';
        document.getElementById('loading-msg').innerText = "ルート検索中...";
        try {
            const url = `https://router.project-osrm.org/route/v1/foot/${uLng},${uLat};${s.lng},${s.lat}?geometries=geojson`;
            const res = await fetch(url);
            const data = await res.json();
            if(data.routes && data.routes[0]) {
                if(currentRouteLine) map.removeLayer(currentRouteLine);
                const coords = data.routes[0].geometry.coordinates.map(c => [c[1], c[0]]);
                currentRouteLine = L.polyline(coords, {color: '#3b82f6', weight: 5, opacity:0.8}).addTo(map);
                map.fitBounds(currentRouteLine.getBounds(), {padding: [30,30]});
                const durMin = Math.ceil(data.routes[0].duration / 60);
                showAppAlert("ルート確認", `現在地から徒歩 約 ${durMin} 分です。`);
            } else { showAppAlert("エラー","ルートが見つかりませんでした。"); }
        } catch(e){ showAppAlert("エラー","ルート検索に失敗しました。"); }
        document.getElementById('loading-overlay').style.display = 'none';
        window.scrollTo(0, 0);
    }

    function zoomToAll() {
        const bounds = shops.filter(s=>s.lat&&s.lng).map(s=>[s.lat, s.lng]);
        if(bounds.length > 0) map.fitBounds(bounds, {padding:[20,20]});
    }
    function recenterToUser() { if(uLat && uLng) map.flyTo([uLat, uLng], 16, {duration: 0.8}); }

    function filterShops(val) {
        const q = val.toLowerCase().trim();
        const validIndices = new Set();
        let vc = 0;
        shops.forEach((s, idx) => {
            const el = document.getElementById(`shop-card-${idx}`);
            if(!q || `${s.name} ${s.genre}`.toLowerCase().includes(q)) { el.style.display = 'block'; validIndices.add(idx); vc++; }
            else { el.style.display = 'none'; }
        });
        document.getElementById('shop-count').innerText = vc;
        renderMarkers(validIndices);
    }
    function toggleSortRating() {
        const container = document.getElementById('shops-list');
        const cards = Array.from(container.children);
        isSorted = !isSorted;
        document.getElementById('sort-btn').innerText = isSorted ? "🔄 標準順" : "⭐ 評価順";
        cards.sort((a, b) => {
            if(!isSorted) return parseInt(a.id.replace('shop-card-','')) - parseInt(b.id.replace('shop-card-',''));
            const rA = shops[parseInt(a.id.replace('shop-card-',''))].google_rating || 0;
            const rB = shops[parseInt(b.id.replace('shop-card-',''))].google_rating || 0;
            return rB - rA;
        });
        cards.forEach(c => container.appendChild(c));
    }

    function openShopDetailByIndex(idx) {
        currentDetailIdx = idx;
        const s = shops[idx];
        document.getElementById('dt-name').innerText = s.name;
        document.getElementById('dt-budget').innerText = s.budget || "要確認";
        document.getElementById('dt-open').innerText = s.open || "要確認";
        document.getElementById('dt-address').innerText = s.address || "情報なし";
        document.getElementById('dt-google').innerText = s.google_rating ? `★ ${s.google_rating} (${s.google_reviews_count})` : "--";

        document.getElementById('dt-top-tel').href = `tel:${s.tel}`;
        document.getElementById('dt-line-btn').onclick = () => { shareToLine(`【EAT MAP】おすすめ店！\\n店名: ${s.name}\\nジャンル: ${s.genre}\\n住所: ${s.address}\\n電話: ${s.tel}`); };

        const favs = JSON.parse(localStorage.getItem('eatmap_favs')||'[]');
        const isFav = favs.some(f => f.name === s.name);
        const fb = document.getElementById('dt-fav-btn');
        fb.innerText = isFav ? "❤️ 保存済み(解除)" : "🤍 お気に入りに保存";
        fb.className = isFav ? "btn-block btn-primary" : "btn-block btn-sub";

        document.getElementById('detail-modal').style.display = 'flex';
        if(s.lat && s.lng) map.panTo([s.lat, s.lng]);
    }
    function closeShopDetail() { document.getElementById('detail-modal').style.display = 'none'; }

    function toggleCurrentFav() {
        if(currentDetailIdx === null) return;
        const s = shops[currentDetailIdx];
        let favs = JSON.parse(localStorage.getItem('eatmap_favs')||'[]');
        const existingIdx = favs.findIndex(f => f.name === s.name);
        if(existingIdx >= 0) { favs.splice(existingIdx, 1); showAppAlert("解除", "解除しました。"); }
        else { favs.unshift({name: s.name, genre: s.genre, address: s.address, visited: false, rating: s.google_rating||0, memo: ""}); showAppAlert("保存","保存しました！"); }
        localStorage.setItem('eatmap_favs', JSON.stringify(favs));
        openShopDetailByIndex(currentDetailIdx);
    }

    function goToInviteFromDetail() {
        const s = shops[currentDetailIdx];
        sessionStorage.setItem('eatmap_invite_preset', JSON.stringify({shop: s.name, address: s.address, budget: s.budget, sm: s.smoking_info, url: s.url}));
        window.location.href = '/tools';
    }
    function addToCalendarFromDetail() {
        const s = shops[currentDetailIdx];
        let cals = JSON.parse(localStorage.getItem('eatmap_cals')||'[]');
        const dateStr = prompt("予定の日付を入力してください (例: 11/20 19:00)");
        if(dateStr) {
            cals.push({date: dateStr, shop: s.name, address: s.address});
            localStorage.setItem('eatmap_cals', JSON.stringify(cals));
            showAppAlert("完了", "飲み会カレンダーに追加しました！");
        }
    }
</script>
"""

# ==============================================================================
# 【EAT MAP】幹事フルツール・カレンダー・記録・AI・ガイド画面・ルーティング (後半)
# ==============================================================================

# --- 幹事ツール画面 (LINE案内状・日程調整・カレンダー・タイマー・割り勘) ---
TOOLS_CONTENT = """
<div class="max-w">
<div class="top-bar">
    <div class="brand">🧮 幹事ツール</div>
    <a href="/game" class="btn-sm" style="background:var(--yellow); color:#493800;">🎯 ルーレット</a>
</div>

<!-- 📅 飲み会カレンダー -->
<div class="card" style="border-color:var(--green);">
    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
        <span style="font-size:13px; font-weight:900; color:var(--green);">📅 飲み会カレンダー</span>
        <button class="btn-sm btn-sub" onclick="addManualCalendar()">＋ 予定追加</button>
    </div>
    <div id="cal-list" style="display:flex; flex-direction:column; gap:6px;"></div>
</div>

<!-- 📨 LINEご案内状メーカー (画像再現レイアウト) -->
<div class="card" id="invite-section" style="border-color:var(--purple); background:linear-gradient(135deg, var(--card), var(--tag));">
    <div style="font-size:13px; font-weight:900; color:var(--purple); margin-bottom:4px;">📨 LINEご案内状メーカー</div>
    <div style="font-size:11px; color:var(--muted); margin-bottom:10px;">LINEグループにそのまま貼れる綺麗なご案内文を作成します。</div>

    <div class="input-group"><input type="text" id="inv-title" value="飲み会・お食事会のご案内" placeholder="イベント名"></div>
    <div class="input-group"><input type="text" id="inv-date" placeholder="📅 日時 (例: 今週金曜日 19:30〜)"></div>
    <div class="input-group"><input type="text" id="inv-shop" placeholder="🍽️ 店名 (例: 姫路和食 個室 旬彩庵)"></div>
    <div class="input-group"><input type="text" id="inv-budget" placeholder="💰 予算 (例: 3,500円〜5,000円)"></div>
    <div class="input-group"><input type="text" id="inv-address" placeholder="📍 住所 (例: 兵庫県姫路市駅前町 100)"></div>
    <div class="input-group"><input type="text" id="inv-sm" placeholder="🚬 喫煙情報 (例: 🚬 喫煙可 / 🚭 全面禁煙)"></div>
    <div class="input-group"><input type="text" id="inv-url" placeholder="🔗 詳細URL (ホットペッパー等のURL)"></div>

    <div style="display:flex; align-items:center; gap:6px; margin-bottom:12px;">
        <input type="checkbox" id="inv-auto-cal" checked style="width:18px; height:18px; accent-color:var(--green);">
        <label for="inv-auto-cal" style="font-size:12px; font-weight:800; cursor:pointer;">同時に「飲み会カレンダー」にも登録する</label>
    </div>

    <div style="display:grid; grid-template-columns:1fr 1fr; gap:6px;">
        <button class="btn-block btn-line" style="margin:0; justify-content:center; font-size:13px;" onclick="sendLineInvite()">💬 LINE送信</button>
        <button class="btn-block btn-sub" style="margin:0; justify-content:center; font-size:13px;" onclick="copyInviteText()">📋 文面コピー</button>
    </div>
</div>

<!-- 🗓 日程調整アンケートメーカー -->
<div class="card">
    <div style="font-size:13px; font-weight:900; margin-bottom:4px;">🗓 日程調整アンケート作成</div>
    <div style="font-size:11px; color:var(--muted); margin-bottom:8px;">候補日を入力するだけで出欠確認のLINE文面を生成します。</div>
    <div class="input-group">
        <textarea id="adj-dates" rows="3" placeholder="候補日を入力してください&#10;例:&#10;11/5(金) 19:00〜&#10;11/6(土) 18:30〜&#10;11/12(金) 19:30〜"></textarea>
    </div>
    <button class="btn-block btn-line" onclick="sendLineAdjust()">💬 日程調整アンケートをLINEで送る</button>
</div>

<!-- ⏳ 大型デジタル退席タイマー -->
<div class="card" style="border-color:var(--yellow); text-align:center; padding:18px 14px;">
    <div style="font-size:13px; font-weight:900; color:var(--yellow); margin-bottom:4px;">⏳ コース退席タイマー</div>
    <div style="font-size:11px; color:var(--muted); margin-bottom:10px;">終了15分前にラストオーダーを通知します</div>

    <div id="big-timer-display" style="font-size:44px; font-weight:900; font-family:monospace; color:var(--primary); margin:6px 0 10px; letter-spacing:2px;">00:00</div>
    <div id="timer-status-badge" style="font-size:12px; font-weight:800; color:var(--muted); margin-bottom:12px;">タイマー停止中</div>

    <div style="display:grid; grid-template-columns:repeat(4, 1fr); gap:6px; margin-bottom:10px;">
        <button class="btn-sm btn-sub" style="padding:8px 0; justify-content:center;" onclick="presetTimer(60)">60分</button>
        <button class="btn-sm btn-sub" style="padding:8px 0; justify-content:center;" onclick="presetTimer(90)">90分</button>
        <button class="btn-sm btn-sub" style="padding:8px 0; justify-content:center;" onclick="presetTimer(120)">120分</button>
        <button class="btn-sm btn-sub" style="padding:8px 0; justify-content:center;" onclick="presetTimer(150)">150分</button>
    </div>
    <div style="display:grid; grid-template-columns:1fr 1fr; gap:6px; margin-bottom:12px;">
        <button class="btn-sm btn-sub" style="padding:6px 0; justify-content:center;" onclick="adjustTimer(10)">＋10分 延長</button>
        <button class="btn-sm btn-sub" style="padding:6px 0; justify-content:center;" onclick="adjustTimer(-10)">ー10分 短縮</button>
    </div>
    <div style="display:grid; grid-template-columns:1fr 1fr; gap:6px;">
        <button id="timer-toggle-btn" class="btn-block btn-primary" style="margin:0; min-height:46px; justify-content:center;" onclick="toggleTimer()">▶ スタート</button>
        <button class="btn-block btn-sub" style="margin:0; min-height:46px; justify-content:center;" onclick="resetTimer()">⏹ リセット</button>
    </div>
</div>

<!-- 💸 傾斜割り勘計算 ＆ レシートOCR -->
<div class="card">
    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:10px;">
        <span style="font-size:13px; font-weight:900;">💸 傾斜割り勘計算</span>
        <label class="btn-sm btn-primary" style="padding:6px 10px; font-size:11px; cursor:pointer;">
            📸 レシート自動読取
            <input type="file" accept="image/*" capture="environment" style="display:none;" onchange="ocrReceipt(this)">
        </label>
    </div>
    <div class="input-group"><input type="number" id="split-total" placeholder="合計お会計 (円)"></div>
    <div style="display:grid; grid-template-columns: 1fr 1fr; gap:8px;">
        <div class="input-group"><input type="number" id="split-drinkers" value="2"><small style="font-size:11px; color:var(--muted); font-weight:700;">飲む人数</small></div>
        <div class="input-group"><input type="number" id="split-nondrinkers" value="1"><small style="font-size:11px; color:var(--muted); font-weight:700;">飲まない人数</small></div>
    </div>
    <div class="input-group"><input type="number" id="split-discount" value="1000"><small style="font-size:11px; color:var(--muted); font-weight:700;">飲まない人の割引額 (円引)</small></div>
    <button class="btn-block btn-primary" onclick="calcSplit()">割り勘を計算する</button>
    <div id="split-res" style="display:none; background:var(--tag); padding:12px; border-radius:12px; margin-top:10px; font-size:13px; font-weight:700;">
        <div style="display:flex; justify-content:space-between; margin-bottom:6px;"><span>🍺 飲む人:</span><b style="color:var(--primary); font-size:16px;" id="res-drinker">0円</b></div>
        <div style="display:flex; justify-content:space-between; margin-bottom:10px;"><span>🍵 飲まない人:</span><b style="color:var(--green); font-size:16px;" id="res-nondrinker">0円</b></div>
        <button class="btn-block btn-line" style="margin:0;" onclick="shareSplitLine()">💬 割り勘結果をLINEで送る</button>
    </div>
</div>

<!-- ⏰ 終電見張りアラーム -->
<div class="card" style="border-color:var(--purple);">
    <div style="font-size:12px; font-weight:800; color:var(--purple); margin-bottom:8px;">⏰ 終電見張りアラーム</div>
    <div style="display:flex; gap:6px; align-items:center;">
        <input type="time" id="train-time" style="padding:8px 10px; border:1.5px solid var(--border); border-radius:10px; font-size:14px; font-weight:800; background:var(--card); color:var(--text); outline:none;">
        <button class="btn-sm btn-purple" style="flex:1; justify-content:center; background:var(--purple); color:#fff;" onclick="setTrainAlarm()">セット</button>
    </div>
    <div id="train-status" style="font-size:11px; font-weight:800; color:var(--muted); margin-top:6px;">未設定</div>
</div>
</div>

<script>
    window.addEventListener('DOMContentLoaded', () => {
        const rawPreset = sessionStorage.getItem('eatmap_invite_preset');
        if(rawPreset) {
            try {
                const p = JSON.parse(rawPreset);
                if(p.shop) document.getElementById('inv-shop').value = p.shop;
                if(p.address) document.getElementById('inv-address').value = p.address;
                if(p.budget) document.getElementById('inv-budget').value = p.budget;
                if(p.sm) document.getElementById('inv-sm').value = p.sm;
                if(p.url) document.getElementById('inv-url').value = p.url;
            } catch(e){}
            sessionStorage.removeItem('eatmap_invite_preset');
        }
        renderCalendar();
        updateTimerDisplay();
    });

    // カレンダー
    function renderCalendar() {
        const list = document.getElementById('cal-list');
        const cals = JSON.parse(localStorage.getItem('eatmap_cals')||'[]');
        if(cals.length === 0) {
            list.innerHTML = '<div style="font-size:11px; color:var(--muted); text-align:center; padding:10px;">予定はありません。</div>';
            return;
        }
        list.innerHTML = cals.map((c, i) => `
            <div style="background:var(--tag); padding:8px 12px; border-radius:10px; display:flex; justify-content:space-between; align-items:center;">
                <div>
                    <div style="font-size:13px; font-weight:900; color:var(--green);">${c.date}</div>
                    <div style="font-size:12px; font-weight:800;">${c.shop}</div>
                    ${c.address ? `<div style="font-size:10px; color:var(--muted);">📍 ${c.address}</div>` : ''}
                </div>
                <button class="btn-icon" style="width:24px; height:24px; font-size:11px; border:none; background:none; color:var(--muted);" onclick="delCal(${i})">✕</button>
            </div>
        `).join('');
    }

    function addManualCalendar() {
        const dateStr = prompt("日時を入力してください (例: 今週金曜 19:30〜)");
        if(!dateStr) return;
        const shopStr = prompt("店名を入力してください (例: 旬彩庵)");
        if(!shopStr) return;
        let cals = JSON.parse(localStorage.getItem('eatmap_cals')||'[]');
        cals.push({ date: dateStr, shop: shopStr, address: "" });
        localStorage.setItem('eatmap_cals', JSON.stringify(cals));
        renderCalendar();
        showAppAlert("完了", "カレンダーに予定を追加しました！");
    }

    function delCal(i) {
        let cals = JSON.parse(localStorage.getItem('eatmap_cals')||'[]');
        cals.splice(i, 1);
        localStorage.setItem('eatmap_cals', JSON.stringify(cals));
        renderCalendar();
    }

    // LINE案内状フォーマット (ご提示画像完全再現)
    function makeInviteBody() {
        const t = document.getElementById('inv-title').value.trim() || '飲み会・お食事会のご案内';
        const d = document.getElementById('inv-date').value.trim() || '未定';
        const s = document.getElementById('inv-shop').value.trim() || '未定';
        const b = document.getElementById('inv-budget').value.trim() || '未定';
        const a = document.getElementById('inv-address').value.trim() || '未定';
        const sm = document.getElementById('inv-sm').value.trim() || '要確認';
        const url = document.getElementById('inv-url').value.trim();

        // 自動カレンダー登録
        if(document.getElementById('inv-auto-cal').checked && d !== '未定' && s !== '未定') {
            let cals = JSON.parse(localStorage.getItem('eatmap_cals')||'[]');
            if(!cals.some(c => c.shop === s && c.date === d)) {
                cals.push({ date: d, shop: s, address: a });
                localStorage.setItem('eatmap_cals', JSON.stringify(cals));
                renderCalendar();
            }
        }

        return `🍻【${t}】\\n\\n📅 日時: ${d}\\n🍽️ 店名: ${s}\\n💰 予算: ${b}\\n📍 住所: ${a}\\n🚬 喫煙: ${sm}${url ? '\\n🔗 詳細: ' + url : ''}\\n\\nよろしくお願いします！✨`;
    }

    function sendLineInvite() { shareToLine(makeInviteBody()); }
    function copyInviteText() {
        navigator.clipboard.writeText(makeInviteBody()).then(()=>{
            showAppAlert("コピー完了！", "ご案内文をクリップボードにコピーしました。LINEに貼り付けて送ってください！");
        }).catch(()=>{ showAppAlert("完了", makeInviteBody()); });
    }

    // 日程調整
    function sendLineAdjust() {
        const d = document.getElementById('adj-dates').value.trim();
        if(!d) return showAppAlert("エラー", "候補日を入力してください。");
        let txt = "飲み会の日程調整です！🍻\\n以下の候補日で都合の良い日を教えてください✨\\n\\n";
        const lines = d.split('\\n');
        lines.forEach((l, i) => {
            if(l.trim()) {
                const numIcon = String.fromCharCode(9312 + i);
                txt += `${numIcon} ${l.trim()}\\n`;
            }
        });
        txt += "\\n出欠の回答よろしくお願いします！";
        shareToLine(txt);
    }

    // タイマー
    let timerTotalSec = 5400, timerRemainSec = 5400, timerInterval = null, isTimerRunning = false;
    function formatTime(s) { const m = Math.floor(s / 60), sec = s % 60; return `${String(m).padStart(2,'0')}:${String(sec).padStart(2,'0')}`; }
    function updateTimerDisplay() { document.getElementById('big-timer-display').innerText = formatTime(timerRemainSec); }
    function presetTimer(min) { resetTimer(); timerTotalSec = min * 60; timerRemainSec = timerTotalSec; updateTimerDisplay(); document.getElementById('timer-status-badge').innerText = `【${min}分コース】にセットしました`; }
    function adjustTimer(min) { if(!isTimerRunning){ timerRemainSec = Math.max(60, timerRemainSec + min * 60); timerTotalSec = timerRemainSec; updateTimerDisplay(); } }
    function toggleTimer() {
        doVibrate(30); const btn = document.getElementById('timer-toggle-btn');
        if(isTimerRunning) {
            clearInterval(timerInterval); isTimerRunning = false;
            btn.innerText = "▶ 再開"; btn.className = "btn-block btn-primary";
            document.getElementById('timer-status-badge').innerText = "一時停止中";
        } else {
            isTimerRunning = true; btn.innerText = "⏸ 一時停止"; btn.className = "btn-block btn-yellow";
            document.getElementById('timer-status-badge').innerText = "カウントダウン中 (15分前にラストオーダー通知)";
            timerInterval = setInterval(() => {
                if(timerRemainSec > 0) {
                    timerRemainSec--; updateTimerDisplay();
                    if(timerRemainSec === 900) showAppAlert("⚠️ ラストオーダー", "退席15分前です！ラストオーダーの確認をおすすめします。");
                } else {
                    clearInterval(timerInterval); isTimerRunning = false;
                    showAppAlert("🔔 お時間です", "コース・お席の終了時刻になりました！"); resetTimer();
                }
            }, 1000);
        }
    }
    function resetTimer() {
        if(timerInterval) clearInterval(timerInterval);
        isTimerRunning = false; timerRemainSec = timerTotalSec; updateTimerDisplay();
        const btn = document.getElementById('timer-toggle-btn');
        btn.innerText = "▶ スタート"; btn.className = "btn-block btn-primary";
        document.getElementById('timer-status-badge').innerText = "タイマー停止中";
    }

    // 割り勘 & レシートOCR
    let lastSplitData = null;
    function calcSplit() {
        const tot = parseInt(document.getElementById('split-total').value)||0, dr = parseInt(document.getElementById('split-drinkers').value)||0, ndr = parseInt(document.getElementById('split-nondrinkers').value)||0, disc = parseInt(document.getElementById('split-discount').value)||0;
        const num = dr + ndr; if(!tot || num <= 0) return showAppAlert("エラー", "金額と人数を入力してください");
        const adj = tot + (disc * ndr), base = Math.ceil((adj / num) / 100) * 100, nonBase = Math.max(0, base - disc);
        document.getElementById('res-drinker').innerText = `${base.toLocaleString()} 円`;
        document.getElementById('res-nondrinker').innerText = `${nonBase.toLocaleString()} 円`;
        document.getElementById('split-res').style.display = 'block';
        lastSplitData = { total: tot, drinker: base, nonDrinker: nonBase, drCount: dr, ndrCount: ndr };
    }
    function shareSplitLine() {
        if(!lastSplitData) return;
        shareToLine(`【お会計・割り勘計算】\\n合計: ¥${lastSplitData.total.toLocaleString()}\\n🍺 飲む人 (${lastSplitData.drCount}名): 各 ¥${lastSplitData.drinker.toLocaleString()}\\n🍵 飲まない人 (${lastSplitData.ndrCount}名): 各 ¥${lastSplitData.nonDrinker.toLocaleString()}\\nよろしくお願いします！✨`);
    }

    async function ocrReceipt(input) {
        if (!input.files || !input.files[0]) return;
        document.getElementById('loading-overlay').style.display = 'flex';
        document.getElementById('loading-msg').innerText = "レシートの合計金額を解析中...";
        const r = new FileReader();
        r.onload = async function() {
            try {
                const res = await fetch('/api/ocr', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({image: r.result.split(',')[1]}) });
                const data = await res.json();
                document.getElementById('loading-overlay').style.display = 'none';
                if(data.amount) {
                    document.getElementById('split-total').value = data.amount;
                    calcSplit();
                    showAppAlert("読取成功！", `合計金額【¥${data.amount.toLocaleString()}】を読み取りました！`);
                } else {
                    showAppAlert("ご案内", "合計金額が見つかりませんでした。直接入力してください。");
                }
            } catch(e) {
                document.getElementById('loading-overlay').style.display = 'none';
                showAppAlert("エラー", "画像の解析に失敗しました。");
            }
        };
        r.readAsDataURL(input.files[0]);
    }

    function setTrainAlarm(){
        const val = document.getElementById('train-time').value;
        if(!val) return showAppAlert("エラー", "時刻を選択してください");
        document.getElementById('train-status').innerText = `【${val}】にセットしました`;
        document.getElementById('train-status').style.color = "var(--purple)";
        showAppAlert("完了", `終電を【${val}】にセットしました！`);
    }
</script>
"""

# --- グルメ記録画面 (毎回シャッフルガチャ) ---
FAVORITES_CONTENT = """
<div class="max-w">
<div class="top-bar">
    <div class="brand">📋 グルメ記録</div>
    <button class="btn-sm" style="background:var(--yellow); color:#493800; border:none;" onclick="pickRandomFav()">🎲 ガチャ (毎回更新)</button>
</div>
<div class="card" style="background:linear-gradient(135deg, #6366f1, #8b5cf6); color:#fff; border:none; margin-bottom:12px;">
    <div style="display:flex; justify-content:space-between; align-items:center;">
        <div><div style="font-size:11px; font-weight:800; opacity:.9;">🏆 現在のグルメ称号</div><div style="font-size:18px; font-weight:900;" id="user-title">Lv.1 ひよっこ探検家 🐣</div></div>
        <div style="font-size:24px;" id="badge-icon">🌟</div>
    </div>
    <div style="font-size:11px; margin-top:8px; display:flex; justify-content:space-between; font-weight:800;"><span id="visited-count">訪問数: 0軒</span><span id="exp-text">EXP: 0/100</span></div>
    <div style="background:rgba(255,255,255,0.25); height:6px; border-radius:3px; overflow:hidden; margin-top:4px;"><div id="exp-bar" style="background:var(--yellow); height:100%; width:0%; transition:width .4s;"></div></div>
</div>
<div id="fav-list" style="display:flex; flex-direction:column; gap:10px;"></div>
</div>

<!-- ガチャ当選ポップアップ -->
<div id="gacha-modal" style="display:none; position:fixed; top:0; left:0; width:100vw; height:100vh; background:rgba(0,0,0,0.75); z-index:99999; justify-content:center; align-items:center; padding:16px;">
    <div class="card" style="width:100%; max-width:380px; text-align:center; padding:20px; border-color:var(--yellow);">
        <div style="font-size:32px; margin-bottom:6px;">🎉</div>
        <div style="font-size:12px; font-weight:800; color:var(--yellow);">今日行くべきお店が決まりました！</div>
        <div style="font-size:18px; font-weight:900; margin:8px 0;" id="gacha-name">--</div>
        <div style="font-size:12px; color:var(--muted); margin-bottom:12px;" id="gacha-addr">--</div>

        <div style="display:grid; grid-template-columns:1fr 1fr; gap:6px; margin-bottom:8px;">
            <a href="#" id="gacha-search-btn" class="btn-block btn-green" style="margin:0; justify-content:center; font-size:12px;">🔍 お店を探す</a>
            <button id="gacha-line-btn" class="btn-block btn-line" style="margin:0; justify-content:center; font-size:12px;">💬 LINE提案</button>
        </div>
        <div style="display:grid; grid-template-columns:1fr 1fr; gap:6px;">
            <button onclick="pickRandomFav()" class="btn-block btn-yellow" style="margin:0; min-height:38px; font-size:12px; background:var(--yellow); color:#493800;">🔄 もう一度引く</button>
            <button onclick="document.getElementById('gacha-modal').style.display='none'" class="btn-block btn-sub" style="margin:0; min-height:38px; font-size:12px;">閉じる</button>
        </div>
    </div>
</div>

<script>
    const titles = [{ lv:1, count:0, title:"Lv.1 ひよっこ探検家 🐣", icon:"🐣" },{ lv:2, count:2, title:"Lv.2 街角の食べ歩き隊 🚶", icon:"🍙" },{ lv:3, count:5, title:"Lv.3 こだわりグルメ通 🍴", icon:"🍝" },{ lv:4, count:10, title:"Lv.4 地域の名店ハンター 🏅", icon:"🥩" },{ lv:5, count:20, title:"Lv.5 伝説の美食王 👑", icon:"👑" }];
    let lastGachaShopName = "";

    function renderFavs(){
        const list = document.getElementById('fav-list');
        const f = JSON.parse(localStorage.getItem('eatmap_favs')||'[]');
        const vCount = f.filter(s => s.visited).length;
        let cur = titles[0], nxtC = titles[1].count;
        for(let i=0; i<titles.length; i++){ if(vCount >= titles[i].count){ cur = titles[i]; nxtC = titles[i+1] ? titles[i+1].count : vCount + 10; } }
        document.getElementById('user-title').innerText = cur.title; document.getElementById('badge-icon').innerText = cur.icon; document.getElementById('visited-count').innerText = `訪問達成: ${vCount}軒`;
        const eR = Math.min(100, Math.max(5, ((vCount - cur.count) / Math.max(1, (nxtC - cur.count))) * 100));
        document.getElementById('exp-text').innerText = `次まで あと${Math.max(0, nxtC - vCount)}軒`; document.getElementById('exp-bar').style.width = eR + '%';

        if(f.length === 0){ list.innerHTML = `<div class="card" style="text-align:center; color:var(--muted); font-weight:700; padding:30px 10px;">保存したお店がまだありません。検索結果の「🤍 保存」ボタンで追加できます！</div>`; return; }
        const tags = ["😋絶品", "🔥コスパ", "🍺酒進む", "✨雰囲気"];

        list.innerHTML = f.map((s,i)=>{
            const rating = s.rating || 0;
            const starsHtml = [1,2,3,4,5].map(star => `<span style="cursor:pointer; font-size:16px; color:${star <= rating ? '#f59e0b':'#cbd5e1'};" onclick="setRating(${i}, ${star})">★</span>`).join('');
            return `
            <div class="card" style="display:flex; flex-direction:column; padding:12px; margin-bottom:0;">
                <div style="display:flex; gap:10px; align-items:center;">
                    <div style="width:65px; height:65px; border-radius:10px; overflow:hidden; flex-shrink:0; background:var(--tag); display:flex; align-items:center; justify-content:center; font-size:24px;">🍽️</div>
                    <div style="flex:1; overflow:hidden;">
                        <div style="display:flex; justify-content:space-between; align-items:flex-start;">
                            <h3 style="margin:0 0 2px 0; font-size:13.5px; font-weight:900; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;">${s.name}</h3>
                            <button class="btn-icon" style="width:22px; height:22px; font-size:11px; border:none; background:var(--tag); color:var(--muted);" onclick="delFav(${i})">✕</button>
                        </div>
                        <div style="font-size:10px; color:var(--muted); margin-bottom:4px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;">📍 ${s.address}</div>
                        <div style="display:flex; align-items:center; gap:2px; margin-bottom:4px;">
                            ${starsHtml}
                            <span style="font-size:10px; color:var(--muted); margin-left:4px; font-weight:800;">${rating > 0 ? rating + '.0' : '未評価'}</span>
                        </div>
                    </div>
                </div>
                <div style="margin-top:6px;">
                    <input type="text" value="${(s.memo||'').replace(/"/g, '&quot;')}" placeholder="📝 一言メモ (例: レモンサワー最高、奥の席が静か)" maxlength="40" style="width:100%; padding:6px 10px; border:1.5px solid var(--border); border-radius:8px; font-size:11px; outline:none; font-weight:700;" onchange="saveMemo(${i}, this.value)">
                </div>
                <div style="display:flex; gap:6px; margin-top:8px;">
                    <button class="btn-sm ${s.visited?'btn-green':'btn-sub'}" style="flex:1; padding:6px 0; font-size:10.5px; border:none;" onclick="toggleV(${i})">${s.visited?'🏁 行った！':'🚩 行ってみたい'}</button>
                    <a href="/search?keyword=${encodeURIComponent(s.name)}" class="btn-sm btn-sub" style="padding:6px 10px; font-size:10.5px;">🔍 検索</a>
                    <button class="btn-sm btn-line" style="padding:6px 10px; font-size:10.5px; border:none;" onclick="shareFavLine(${i})">LINE共有</button>
                </div>
            </div>`;
        }).join('');
    }

    function pickRandomFav(){
        const f = JSON.parse(localStorage.getItem('eatmap_favs')||'[]');
        let picked = null;
        if(f.length > 0) {
            let pool = f.filter(x => x.name !== lastGachaShopName);
            if(pool.length === 0) pool = f;
            picked = pool[Math.floor(Math.random() * pool.length)];
        } else {
            const fallbackShops = [
                { name: "炭火焼鳥と旬菜 個室居酒屋", address: "駅前商店街・徒歩2分", genre: "居酒屋" },
                { name: "黒毛和牛 特選焼肉ダイニング", address: "本通り沿い・駅北口すぐ", genre: "焼肉" },
                { name: "自家製生パスタ＆薪窯ピッツァ", address: "隠れ家ビル2F", genre: "イタリアン" },
                { name: "鮮魚と地酒の個室和食処", address: "駅前南口ロータリー前", genre: "海鮮和食" }
            ];
            let pool = fallbackShops.filter(x => x.name !== lastGachaShopName);
            if(pool.length === 0) pool = fallbackShops;
            picked = pool[Math.floor(Math.random() * pool.length)];
        }

        lastGachaShopName = picked.name;
        doVibrate([50, 50, 100]);
        document.getElementById('gacha-name').innerText = picked.name;
        document.getElementById('gacha-addr').innerText = `📍 ${picked.address || picked.genre}`;
        document.getElementById('gacha-search-btn').href = `/search?keyword=${encodeURIComponent(picked.name)}`;
        document.getElementById('gacha-line-btn').onclick = () => {
            shareToLine(`【今日の提案店舗！】ガチャで選ばれたよ！\\n店名: ${picked.name}\\nジャンル: ${picked.genre}\\n場所: ${picked.address}\\n一緒に行こう！`);
        };
        document.getElementById('gacha-modal').style.display = 'flex';
    }

    function setRating(i, r){ doVibrate(30); let f = JSON.parse(localStorage.getItem('eatmap_favs')); f[i].rating = (f[i].rating === r) ? 0 : r; localStorage.setItem('eatmap_favs', JSON.stringify(f)); renderFavs(); }
    function saveMemo(i, val){ let f = JSON.parse(localStorage.getItem('eatmap_favs')); f[i].memo = val.trim(); localStorage.setItem('eatmap_favs', JSON.stringify(f)); }
    function toggleV(i){ doVibrate(30); let f = JSON.parse(localStorage.getItem('eatmap_favs')); f[i].visited = !f[i].visited; localStorage.setItem('eatmap_favs', JSON.stringify(f)); renderFavs(); }
    function delFav(i){ if(confirm("削除しますか？")){ doVibrate(30); let f = JSON.parse(localStorage.getItem('eatmap_favs')); f.splice(i,1); localStorage.setItem('eatmap_favs', JSON.stringify(f)); renderFavs(); } }
    function shareFavLine(i){
        const f = JSON.parse(localStorage.getItem('eatmap_favs')||'[]');
        const s = f[i];
        shareToLine(`【おすすめ店舗記録】\\n店名: ${s.name}\\n評価: ${s.rating ? '★'+s.rating : '記録中'}\\nメモ: ${s.memo || 'なし'}`);
    }
    window.addEventListener('DOMContentLoaded', renderFavs);
</script>
"""

# --- 抽選・可変ルーレット画面 ---
GAME_CONTENT = """
<div class="max-w">
<div class="top-bar"><div class="brand">🎯 抽選ルーレット</div></div>
<div class="card" style="text-align:center; padding:18px 12px; margin-bottom:12px;">
    <div style="font-size:13px; font-weight:800; color:var(--muted); margin-bottom:12px;">🍽️ 何を食べるか迷ったらルーレット！</div>
    <div style="position:relative; width:280px; height:280px; margin:0 auto 18px;">
        <div style="position:absolute; top:-12px; left:50%; transform:translateX(-50%); width:0; height:0; border-left:12px solid transparent; border-right:12px solid transparent; border-top:22px solid var(--primary); z-index:20;"></div>
        <div style="position:absolute; top:50%; left:50%; transform:translate(-50%, -50%); width:44px; height:44px; background:var(--card); border:3px solid var(--primary); border-radius:50%; z-index:15; display:flex; align-items:center; justify-content:center; font-size:18px;">🍽️</div>
        <canvas id="wheel-canvas" width="280" height="280" style="border-radius:50%; box-shadow:var(--shadow); transition:transform 4.5s cubic-bezier(0.15, 0.9, 0.2, 1);"></canvas>
    </div>
    <button class="btn-block btn-primary" id="spin-btn" style="font-size:16px; min-height:50px;" onclick="spinWheel()">🎯 ルーレットを回す！</button>
</div>

<!-- 当選結果＆店舗直接ジャンプ -->
<div class="card" id="result-box" style="display:none; text-align:center; background:var(--primary-light); border-color:var(--primary); margin-bottom:12px;">
    <div style="font-size:12px; font-weight:800; color:var(--muted);">当選結果</div>
    <div style="font-size:26px; font-weight:900; color:var(--primary); margin:8px 0;" id="res-val">--</div>
    <div style="display:grid; grid-template-columns:1fr 1fr; gap:6px; margin-top:8px;">
        <a href="#" id="res-search-btn" class="btn-block btn-green" style="margin:0; justify-content:center;">🔍 このジャンルを探す</a>
        <button class="btn-block btn-line" id="res-line-btn" style="margin:0; justify-content:center;" onclick="shareResultLine()">💬 LINE共有</button>
    </div>
</div>

<!-- 自由な追加・削除UI -->
<div class="card">
    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:6px;">
        <div style="font-size:13px; font-weight:900;">🎨 ルーレット項目のカスタマイズ</div>
        <button class="btn-sm btn-sub" onclick="addWheelSlot()">＋ 項目を追加</button>
    </div>
    <div style="font-size:11px; color:var(--muted); margin-bottom:10px;">自由に項目を増やしたり削ったりできます (2〜16個)。</div>
    <div id="wheel-items-list" style="display:flex; flex-direction:column; gap:6px; margin-bottom:10px;"></div>
    <button class="btn-block btn-sub" onclick="saveCustomWheel()">盤面を保存して更新</button>
</div>
</div>
<script>
    const colorPalette = [
        { code: "#ffc9c9", border: "#ff8787" }, { code: "#ffe3a8", border: "#ffa94d" },
        { code: "#fff3bf", border: "#ffe066" }, { code: "#bbf7d0", border: "#69db7c" },
        { code: "#c5f6fa", border: "#3bc9db" }, { code: "#d0ebff", border: "#74c0fc" },
        { code: "#dbe4ff", border: "#91a7ff" }, { code: "#f3d9fa", border: "#da77f2" }
    ];

    let defaultItems = ["焼肉 🥩","居酒屋 🍺","カフェ ☕","ラーメン 🍜","海鮮 🐟","カレー 🍛","イタリアン 🍕","中華 🥟"];
    let wheelItems = JSON.parse(localStorage.getItem('eatmap_wheel_items') || JSON.stringify(defaultItems));
    let curDeg = 0, isSpinning = false, lastWinner = "";

    function renderWheelInputs() {
        const c = document.getElementById('wheel-items-list');
        c.innerHTML = wheelItems.map((val, i) => {
            const col = colorPalette[i % colorPalette.length];
            return `
            <div style="display:flex; align-items:center; gap:6px; background:var(--tag); padding:6px 10px; border-radius:10px; border-left:6px solid ${col.border};">
                <input type="text" id="slot-input-${i}" value="${val}" style="flex:1; border:none; background:transparent; font-size:13px; font-weight:800; color:var(--text); outline:none;">
                <button class="btn-icon" style="width:24px; height:24px; font-size:11px; border:none; background:none; color:var(--muted);" onclick="removeWheelSlot(${i})">✕</button>
            </div>`;
        }).join('');
    }

    function addWheelSlot() {
        if(wheelItems.length >= 16) return showAppAlert("ご案内", "項目は最大16個までです。");
        syncCurrentInputs();
        wheelItems.push("新規項目 " + (wheelItems.length + 1));
        renderWheelInputs(); drawCanvas();
    }
    function removeWheelSlot(idx) {
        if(wheelItems.length <= 2) return showAppAlert("ご案内", "最低2項目は必要です。");
        syncCurrentInputs();
        wheelItems.splice(idx, 1);
        renderWheelInputs(); drawCanvas();
    }
    function syncCurrentInputs() {
        for(let i=0; i<wheelItems.length; i++){
            const inp = document.getElementById(`slot-input-${i}`);
            if(inp) wheelItems[i] = inp.value.trim() || `項目 ${i+1}`;
        }
    }
    function drawCanvas() {
        const canvas = document.getElementById('wheel-canvas'); if(!canvas) return;
        const ctx = canvas.getContext('2d'); ctx.clearRect(0, 0, 280, 280);
        const num = wheelItems.length, arc = (2 * Math.PI) / num;
        for(let i=0; i<num; i++){
            const a = i * arc, col = colorPalette[i % colorPalette.length];
            ctx.fillStyle = col.code; ctx.beginPath();
            ctx.arc(140, 140, 136, a, a + arc, false); ctx.arc(140, 140, 0, a + arc, a, true); ctx.fill();
            ctx.save(); ctx.strokeStyle = "rgba(255,255,255,0.85)"; ctx.lineWidth = 2; ctx.stroke();
            ctx.fillStyle = "#2d3142"; ctx.font = "bold 12px -apple-system, sans-serif";
            ctx.translate(140 + Math.cos(a + arc/2) * 88, 140 + Math.sin(a + arc/2) * 88);
            ctx.rotate(a + arc/2 + Math.PI/2); ctx.fillText(wheelItems[i], -ctx.measureText(wheelItems[i]).width / 2, 0);
            ctx.restore();
        }
    }
    function spinWheel(){
        if(isSpinning) return; isSpinning = true; document.getElementById('spin-btn').disabled = true;
        document.getElementById('result-box').style.display = 'none';
        curDeg += 360 * 5 + Math.floor(Math.random() * 360);
        document.getElementById('wheel-canvas').style.transform = `rotate(${curDeg}deg)`;
        setTimeout(() => {
            isSpinning = false; document.getElementById('spin-btn').disabled = false; doVibrate([100, 50, 100]);
            const deg = curDeg % 360, step = 360 / wheelItems.length;
            const idx = Math.floor((360 - deg + 270) % 360 / step);
            lastWinner = wheelItems[idx];
            document.getElementById('res-val').innerText = lastWinner;
            const clean = lastWinner.replace(/[^\\u4E00-\\u9FFF\\u3040-\\u309F\\u30A0-\\u30FAa-zA-Z]/g, '').trim();
            const sBtn = document.getElementById('res-search-btn');
            if(clean){ sBtn.style.display = 'inline-flex'; sBtn.href = `/search?keyword=${encodeURIComponent(clean)}`; }
            document.getElementById('result-box').style.display = 'block';
        }, 4500);
    }
    function saveCustomWheel() {
        syncCurrentInputs();
        localStorage.setItem('eatmap_wheel_items', JSON.stringify(wheelItems));
        drawCanvas();
        showAppAlert("設定完了", "ルーレットの項目を保存・更新しました！");
    }
    function shareResultLine() {
        if(!lastWinner) return;
        shareToLine(`【EAT MAP】今日のランチ・ディナー抽選結果！\\n🎉 当選ジャンル: ${lastWinner}\\nこれに決定！一緒に行こう！🍽️`);
    }
    window.addEventListener('DOMContentLoaded', () => { renderWheelInputs(); drawCanvas(); });
</script>
"""

# --- AIコンシェルジュ相談画面 (過去メモAI逆引き機能付き) ---
CHAT_CONTENT = """
<style>
    .chat-container { display:flex; flex-direction:column; height:calc(100vh - 145px); max-height:800px; }
    .msg { max-width:85%; padding:10px 14px; border-radius:16px; font-size:13.5px; font-weight:700; line-height:1.6; word-wrap:break-word; }
    .msg-ai { background:var(--tag); border-top-left-radius:4px; color:var(--text); margin-right:auto; }
    .msg-user { background:var(--primary); border-top-right-radius:4px; color:#fff; margin-left:auto; }
    .chat-box { flex:1; overflow-y:auto; padding:14px; background:var(--card); border:1.5px solid var(--border); border-radius:18px; margin-bottom:10px; display:flex; flex-direction:column; gap:12px; }
    .s-btn { display:inline-flex; align-items:center; gap:4px; background:var(--primary); color:#fff; padding:6px 12px; border-radius:10px; font-size:11.5px; font-weight:800; text-decoration:none; margin-top:8px; border:none; }
</style>
<div class="max-w chat-container">
    <div class="top-bar"><div class="brand">💬 AIコンシェルジュ</div></div>
    <div class="chat-box" id="box">
        <div style="display:flex; gap:8px; align-items:flex-start;">
            <div style="font-size:24px;">🤖</div>
            <div class="msg msg-ai">お店探しのお手伝いをします✨<br>「胃に優しい料理」「落ち着いた個室居酒屋」のほか、「<b>保存したあのお店どこだっけ？</b>」と聞いてもメモから探し出します！</div>
        </div>
    </div>
    <div style="display:flex; gap:8px;">
        <input type="text" id="inp" maxlength="80" placeholder="相談を入力..." style="flex:1; padding:13px 14px; border:1.5px solid var(--border); border-radius:12px; font-size:14px; outline:none; font-weight:700;" onkeydown="if(event.key==='Enter' && !event.isComposing) { event.preventDefault(); send(); }">
        <button class="btn-primary" style="width:64px; border-radius:12px; border:none; font-weight:800; cursor:pointer;" onclick="send()" id="s-btn">送信</button>
    </div>
</div>
<script>
    const box = document.getElementById('box'), inp = document.getElementById('inp'), btn = document.getElementById('s-btn');
    async function send(){
        const txt = inp.value.trim(); if(!txt) return;
        doVibrate(30);
        box.innerHTML += `<div style="display:flex; justify-content:flex-end;"><div class="msg msg-user">${txt}</div></div>`;
        inp.value = ""; btn.disabled = true; box.scrollTop = box.scrollHeight;
        const wId = "w-" + Date.now();
        box.innerHTML += `<div id="${wId}" style="display:flex; gap:8px; align-items:flex-start; margin-top:4px;"><div style="font-size:24px;">🤖</div><div class="msg msg-ai" style="color:var(--muted);"><span class="spinner" style="width:12px;height:12px;border-width:2px;display:inline-block;border-top-color:var(--primary);margin:0;"></span> 考え中...</div></div>`;
        box.scrollTop = box.scrollHeight;

        // 過去メモをプロンプト補強として渡す
        const favs = JSON.parse(localStorage.getItem('eatmap_favs')||'[]');
        const memoSummary = favs.slice(0, 10).map(f => `${f.name}(${f.genre}):${f.memo}`).join(' / ');

        try {
            const res = await fetch('/api/chat', {
                method:'POST',
                headers:{'Content-Type':'application/json'},
                body:JSON.stringify({ message: txt, user_memos: memoSummary })
            });
            const d = await res.json();
            document.getElementById(wId).remove();
            const clean = d.reply.replace(/\\*\\*/g,'').replace(/\\*/g,'・').replace(/\\n/g,'<br>');
            const sKw = encodeURIComponent(d.keyword || txt);
            box.innerHTML += `<div style="display:flex; gap:8px; align-items:flex-start;"><div style="font-size:24px;">🤖</div><div class="msg msg-ai">${clean}<br><a href="/search?keyword=${sKw}" class="s-btn">🔍 この条件で探す ↗</a></div></div>`;
        } catch(e) {
            document.getElementById(wId).remove();
            box.innerHTML += `<div style="text-align:center; color:var(--primary); font-size:12px; font-weight:800;">⚠️ 通信エラーが発生しました</div>`;
        }
        btn.disabled = false; box.scrollTop = box.scrollHeight;
    }
</script>
"""

# --- 使い方・機能説明画面 (ABOUT_CONTENT) ---
ABOUT_CONTENT = """
<div class="max-w">
<div class="top-bar"><div class="brand">📖 アプリの使い方</div></div>

<div class="card" style="text-align:center; padding:20px 10px;">
    <div style="font-size:40px; margin-bottom:8px;">🗺️✨</div>
    <div style="font-size:16px; font-weight:900; color:var(--primary); margin-bottom:8px;">「EAT MAP」へようこそ！</div>
    <div style="font-size:12px; color:var(--muted); line-height:1.6; text-align:left; display:inline-block; max-width:320px;">
        Googleマップの網羅性と、幹事サポートツールを完全合体させた<b>「No-Exit（外部離脱ゼロ）マップアプリ」</b>です。<br>探す・案内・当日の時間管理・割り勘まで全てここで完結します。
    </div>
</div>

<div class="card" style="border-left:4px solid var(--primary);">
    <div style="font-size:14px; font-weight:900; margin-bottom:4px;">📍 アプリ内徒歩ルート案内</div>
    <div style="font-size:12px; color:var(--muted); line-height:1.5;">店舗カードの「🧭 経路」を押すと、外部アプリを開かずに現在地からの青い徒歩ルート線と所要分数を直接マップに描画します。</div>
</div>

<div class="card" style="border-left:4px solid var(--purple);">
    <div style="font-size:14px; font-weight:900; margin-bottom:4px;">📨 LINEご案内状メーカー</div>
    <div style="font-size:12px; color:var(--muted); line-height:1.5;">店舗詳細から「📨 案内文を作る」を押すだけで、店名・住所・予算・喫煙情報が揃った綺麗な案内文が生成され、ワンタップでLINEへ送信できます。</div>
</div>

<div class="card" style="border-left:4px solid var(--green);">
    <div style="font-size:14px; font-weight:900; margin-bottom:4px;">📅 飲み会カレンダー</div>
    <div style="font-size:12px; color:var(--muted); line-height:1.5;">案内状を作った日時や予約したお店を自動的にアプリ内カレンダーへ登録し、幹事の予定管理をサポートします。</div>
</div>

<div class="card" style="border-left:4px solid var(--yellow);">
    <div style="font-size:14px; font-weight:900; margin-bottom:4px;">⏳ 大型退席タイマー ＆ レシートOCR割り勘</div>
    <div style="font-size:12px; color:var(--muted); line-height:1.5;">終了15分前にラストオーダーを通知する大型タイマーや、レシートを撮影するだけで合計額を読み取る傾斜割り勘電卓を完備しています。</div>
</div>

<div class="card" style="border-left:4px solid var(--blue);">
    <div style="font-size:14px; font-weight:900; margin-bottom:4px;">🎲 毎回更新ガチャ ＆ 可変ルーレット</div>
    <div style="font-size:12px; color:var(--muted); line-height:1.5;">迷った時はルーレットやガチャにお任せ。当選したジャンルや店舗の詳細画面へ1タップでジャンプできます。</div>
</div>

<div style="text-align:center; margin-top:20px;">
    <a href="/" class="btn-block btn-primary" style="width:200px; text-decoration:none; margin:0 auto;">さっそく探す 🚀</a>
</div>
</div>
"""

# ================= 5. バックエンドAPI・ルーティング =================

@app.route('/')
def home(): return render_page(HOME_CONTENT)

@app.route('/search')
def search():
    k = html.escape(request.args.get('keyword', '')[:40])
    a = html.escape(request.args.get('area', '')[:40])
    is_rain = request.args.get('is_rain') == '1'
    try: lat_val, lng_val = float(request.args.get('lat')), float(request.args.get('lng'))
    except: lat_val, lng_val = None, None

    shops = fetch_all_shops_massive(k, a, lat_val, lng_val, is_rain)
    recipes = fetch_rakuten_recipes(k or a or "肉")
    return render_page(render_template_string(RESULT_CONTENT, shops=shops, recipes=recipes))

@app.route('/tools')
def tools(): return render_page(TOOLS_CONTENT)

@app.route('/favorites')
def favorites(): return render_page(FAVORITES_CONTENT)

@app.route('/game')
def game(): return render_page(GAME_CONTENT)

@app.route('/chat')
def chat(): return render_page(CHAT_CONTENT)

@app.route('/about')
def about(): return render_page(ABOUT_CONTENT)

@app.route('/api/places_enrich', methods=['POST'])
def api_places_enrich():
    req_json = request.get_json(silent=True) or {}
    items = req_json.get('shops', [])
    if not items or not GOOGLE_PLACES_API_KEY: return jsonify([])
    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as executor:
        f_map = {executor.submit(fetch_single_google_rating, s.get('name',''), s.get('address','')): s for s in items}
        for f in concurrent.futures.as_completed(f_map):
            try:
                r, c = f.result()
                if r: results.append({"index": f_map[f].get('index'), "rating": r, "count": c})
            except: pass
    return jsonify(results)

@app.route('/api/ocr', methods=['POST'])
def api_ocr():
    req_json = request.get_json(silent=True) or {}
    img_b64 = req_json.get('image', '')
    if not img_b64 or not GOOGLE_PLACES_API_KEY: return jsonify({"amount": None})
    try:
        url = f"https://vision.googleapis.com/v1/images:annotate?key={GOOGLE_PLACES_API_KEY}"
        payload = {"requests": [{"image": {"content": img_b64}, "features": [{"type": "TEXT_DETECTION"}]}]}
        req = urllib.request.Request(url, data=json.dumps(payload).encode('utf-8'), headers={'Content-Type': 'application/json'})
        with urllib.request.urlopen(req, timeout=5.0) as res:
            text = json.loads(res.read().decode('utf-8'))['responses'][0].get('fullTextAnnotation', {}).get('text', '')
            matches = re.findall(r'(?:合計|小計|お会計|支払|領収|計)?[\s:：]*[¥￥]?\s*([0-9]{1,3}(?:,[0-9]{3})+|[0-9]{3,6})\s*(?:円)?', text)
            if matches:
                nums = [int(m.replace(',', '')) for m in matches if int(m.replace(',', '')) >= 500]
                if nums: return jsonify({"amount": max(nums)})
    except: pass
    return jsonify({"amount": None})

@app.route('/api/chat', methods=['POST'])
def api_chat():
    req_json = request.get_json(silent=True) or {}
    msg = html.escape(str(req_json.get('message', ''))[:80].strip())
    user_memos = str(req_json.get('user_memos', ''))[:300]

    clean_reply, search_keyword = None, None
    prompt = f"あなたは飲食店探しアプリ「EAT MAP」の親切な専属コンシェルジュです。ユーザーの言葉「{msg}」に日本語敬語で答え、具体的な料理やお店の選び方を80文字以内で提案してください。もしユーザーが過去の保存メモについて尋ねており、参考情報({user_memos})に合致するものがあればその店名を親切に教えてください。最後に検索に最適なキーワードを「【SEARCH:キーワード】」という形式で必ず1つ付けてください。"

    if GROQ_API_KEY:
        try:
            p = {"model": "llama-3.3-70b-versatile", "messages": [{"role": "system", "content": prompt}, {"role": "user", "content": msg}], "max_tokens": 140, "temperature": 0.5}
            req = urllib.request.Request("https://api.groq.com/openai/v1/chat/completions", data=json.dumps(p).encode('utf-8'), headers={'Content-Type': 'application/json', 'Authorization': f'Bearer {GROQ_API_KEY}'})
            with urllib.request.urlopen(req, timeout=4) as res:
                raw = json.loads(res.read().decode('utf-8'))['choices'][0]['message']['content']
                m = re.search(r'【SEARCH:(.*?)】', raw)
                if m: search_keyword = m.group(1).strip(); raw = re.sub(r'【SEARCH:.*?】', '', raw)
                clean_reply = raw.replace("**", "").replace("*", "").strip()
        except: pass

    if not clean_reply and GEMINI_API_KEY:
        try:
            req = urllib.request.Request(f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={urllib.parse.quote(GEMINI_API_KEY)}", data=json.dumps({"contents": [{"parts": [{"text": prompt}]}], "generationConfig": {"maxOutputTokens": 140, "temperature": 0.5}}).encode('utf-8'), headers={'Content-Type': 'application/json'})
            with urllib.request.urlopen(req, timeout=4) as res:
                raw = json.loads(res.read().decode('utf-8'))['candidates'][0]['content']['parts'][0]['text']
                m = re.search(r'【SEARCH:(.*?)】', raw)
                if m: search_keyword = m.group(1).strip(); raw = re.sub(r'【SEARCH:.*?】', '', raw)
                clean_reply = raw.replace("**", "").replace("*", "").strip()
        except: pass

    if not clean_reply:
        clean_reply = f"「{msg}」ですね！今すぐ行きたくなるおすすめのお店をご案内します🍽️"
        search_keyword = msg

    return jsonify({"reply": clean_reply, "keyword": search_keyword})

@app.route('/manifest.json')
def manifest():
    return jsonify({
        "name": "EAT MAP", "short_name": "EAT MAP", "start_url": "/", "display": "standalone",
        "background_color": "#0f172a", "theme_color": "#ff5252",
        "icons": [{"src": "data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 100 100%22><text y=%22.9em%22 font-size=%2290%22>🍽️</text></svg>", "sizes": "192x192", "type": "image/svg+xml"}]
    })

@app.route('/ping')
def ping(): return "OK", 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
