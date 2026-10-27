# ==============================================================================
# 【EAT MAP】大量店舗スキャン × LINE共有 × カラー別ルーレット × 完全電話予約特化
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
AI_CACHE = {}
PLACES_CACHE = {}
SEARCH_CACHE = {}
RECIPE_CACHE = {}

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

def fetch_single_google_rating(name, address):
    if not GOOGLE_PLACES_API_KEY: return None, 0
    clean_name = re.sub(r'\(.*?\)|（.*?）', '', name).strip()
    cache_key = f"{clean_name}_{address[:10]}"
    if cache_key in PLACES_CACHE: return PLACES_CACHE[cache_key]

    try:
        url = "https://places.googleapis.com/v1/places:searchText"
        headers = {
            "Content-Type": "application/json",
            "X-Goog-Api-Key": GOOGLE_PLACES_API_KEY,
            "X-Goog-FieldMask": "places.displayName,places.rating,places.userRatingCount"
        }
        body = json.dumps({"textQuery": f"{clean_name} {address}".strip(), "maxResultCount": 1}).encode("utf-8")
        req = urllib.request.Request(url, data=body, headers=headers)
        with urllib.request.urlopen(req, timeout=2.0) as res:
            places = json.loads(res.read().decode("utf-8")).get("places", [])
            if places:
                r, c = places[0].get("rating"), places[0].get("userRatingCount", 0)
                PLACES_CACHE[cache_key] = (r, c)
                return r, c
    except Exception: pass
    PLACES_CACHE[cache_key] = (None, 0)
    return None, 0

def fetch_yahoo_local_task(keyword, lat, lng, dist=5):
    if not YAHOO_CLIENT_ID: return []
    params = {"appid": YAHOO_CLIENT_ID, "output": "json", "results": 50, "gc": "01"}
    if keyword: params["query"] = keyword
    if lat and lng:
        params["lat"], params["lon"], params["dist"] = lat, lng, dist
        if not keyword: params["query"] = "飲食店"
    
    try:
        url = f"https://map.yahooapis.jp/search/local/V1/localSearch?{urllib.parse.urlencode(params)}"
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=2.5) as res:
            features = json.loads(res.read().decode('utf-8')).get("Feature", [])
            y_shops = []
            for f in features:
                prop = f.get("Property", {})
                name = f.get("Name", "店舗名不明")
                geom = f.get("Geometry", {}).get("Coordinates", "")
                lat_str, lng_str = None, None
                if geom and "," in geom: lng_str, lat_str = geom.split(",")
                cat = prop.get("Genre", [])
                genre = cat[0].get("Name", "グルメ") if cat else "グルメ"
                y_shops.append({
                    "name": name, "catch": prop.get("CatchCopy", ""), "genre": genre,
                    "address": prop.get("Address", ""), "budget": "要確認", "min_budget": 0,
                    "lat": float(lat_str) if lat_str else None, "lng": float(lng_str) if lng_str else None,
                    "tel": prop.get("Tel1", "0000000000"), "open": "要確認", "close": "要確認",
                    "capacity": "要確認", "card": "要確認", "access": "周辺地域",
                    "has_private": False, "smoking_info": "🚬/🚭 要確認", "has_free_drink": False,
                    "photo": prop.get("Detail", {}).get("Image1", ""),
                    "google_rating": None, "google_reviews_count": 0, "source": "yahoo"
                })
            return y_shops
    except Exception: return []

def fetch_hotpepper_task(keyword, area, lat, lng, smoking, private_room, free_drink, midnight, start_idx=1):
    if not HOTPEPPER_API_KEY: return []
    params = {"key": HOTPEPPER_API_KEY, "count": 100, "start": start_idx, "format": "json"}
    if private_room: params["private_room"] = 1
    if free_drink: params["free_drink"] = 1
    if midnight: params["midnight"] = 1
    parts = [p for p in [area, keyword] if p]
    if smoking and "喫煙" not in " ".join(parts): parts.append("喫煙")
    
    if lat and lng:
        params.update({"lat": lat, "lng": lng, "range": 5})
        if parts: params["keyword"] = " ".join(parts)
    else: params["keyword"] = " ".join(parts) if parts else "居酒屋 グルメ"

    results = []
    try:
        url = f"https://webservice.recruit.co.jp/hotpepper/gourmet/v1/?{urllib.parse.urlencode(params)}"
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=3.0) as res:
            data = json.loads(res.read().decode('utf-8'))
            for s in data.get("results", {}).get("shop", []):
                b_name = (s.get("budget") or {}).get("name", "要確認")
                min_b = 3000
                m = re.search(r'(\d[\d,]*)(円)?', b_name)
                if m: min_b = int(m.group(1).replace(',', ''))
                has_pr = bool(s.get("private_room") and "あり" in s.get("private_room"))
                has_fd = bool(s.get("free_drink") and "あり" in s.get("free_drink"))
                non_sm = s.get("non_smoking", "")
                if "全面禁煙" in non_sm: sm_info = "🚭 全面禁煙"
                elif "一部禁煙" in non_sm or "分煙" in non_sm: sm_info = "🚬 分煙"
                elif "喫煙可" in non_sm or "禁煙席なし" in non_sm: sm_info = "🚬 喫煙可"
                else: sm_info = "🚬 喫煙可" if smoking else "🚭 禁煙"
                
                results.append({
                    "name": s.get("name", "店舗名不明"), "catch": s.get("catch", ""),
                    "genre": (s.get("genre") or {}).get("name", "グルメ"),
                    "address": s.get("address", ""), "budget": b_name, "min_budget": min_b,
                    "lat": s.get("lat"), "lng": s.get("lng"), "tel": s.get("tel", "0000000000"),
                    "open": s.get("open", "要確認"), "close": s.get("close", "不定休"),
                    "capacity": f"{s.get('capacity', '要確認')}席" if s.get('capacity') else "要確認",
                    "card": s.get("card", "要確認"), "access": s.get("access", "駅近"),
                    "has_private": has_pr, "smoking_info": sm_info, "has_free_drink": has_fd,
                    "photo": ((s.get("photo") or {}).get("pc") or {}).get("l", ""),
                    "google_rating": None, "google_reviews_count": 0, "source": "hotpepper"
                })
    except Exception: pass
    return results

def fetch_rakuten_recipes(keyword):
    if not RAKUTEN_APP_ID or not keyword: return []
    clean_kw = re.sub(r'[^a-zA-Z0-9\u3040-\u309F\u30A0-\u30FA\u4E00-\u9FFF]', ' ', keyword).strip()
    first_word = clean_kw.split()[0] if clean_kw else "肉"
    if first_word in RECIPE_CACHE: return RECIPE_CACHE[first_word]

    url = f"https://app.rakuten.co.jp/services/api/Recipe/CategoryRanking/20170426?applicationId={RAKUTEN_APP_ID}"
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=2.5) as res:
            d = json.loads(res.read().decode('utf-8'))
            recipes = []
            for r in d.get("result", [])[:4]:
                recipes.append({
                    "title": r.get("recipeTitle"),
                    "url": r.get("recipeUrl"),
                    "photo": r.get("foodImageUrl"),
                    "cost": r.get("recipeCost"),
                    "time": r.get("recipeIndication")
                })
            RECIPE_CACHE[first_word] = recipes
            return recipes
    except Exception: return []

# 食べログ規模の大量データ取得（ページネーション＆マルチグリッド走査）
def fetch_all_shops_massive(keyword="", area="", lat=None, lng=None, smoking=False, private_room=False, free_drink=False, midnight=False):
    cache_key = f"{keyword}_{area}_{lat}_{lng}_{smoking}_{private_room}_{free_drink}_{midnight}"
    if cache_key in SEARCH_CACHE: return SEARCH_CACHE[cache_key]

    parts = [p for p in [area, keyword] if p]
    query_str = " ".join(parts) if parts else "居酒屋 グルメ"

    # ホットペッパー（1〜100件、101〜200件）とYahoo!（50件）を並行取得して最大250件規模を確保
    tasks = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        f_hp1 = executor.submit(fetch_hotpepper_task, keyword, area, lat, lng, smoking, private_room, free_drink, midnight, 1)
        f_hp2 = executor.submit(fetch_hotpepper_task, keyword, area, lat, lng, smoking, private_room, free_drink, midnight, 101)
        f_yh  = executor.submit(fetch_yahoo_local_task, query_str, lat, lng, 5)
        
        hp1 = f_hp1.result()
        hp2 = f_hp2.result()
        yh  = f_yh.result()

    all_raw = hp1 + hp2 + yh
    results = []
    existing_names = set()
    for s in all_raw:
        if s["name"] not in existing_names:
            results.append(s)
            existing_names.add(s["name"])

    if len(SEARCH_CACHE) > 50: SEARCH_CACHE.clear()
    SEARCH_CACHE[cache_key] = results
    return results

# ================= 3. 共通ベーステンプレート =================
LAYOUT_HTML = """<!DOCTYPE html>
<html lang="ja">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no, viewport-fit=cover">
    <link rel="icon" href="data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 100 100%22><text y=%22.9em%22 font-size=%2290%22>🍽️</text></svg>">
    <link rel="manifest" href="/manifest.json">
    <meta name="theme-color" content="#ff5252">
    <link rel="preconnect" href="https://tile.openstreetmap.jp" crossorigin>
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

        // LINE共有ヘルパー
        function shareToLine(text) {
            const lineUrl = `https://line.me/R/msg/text/?${encodeURIComponent(text)}`;
            window.open(lineUrl, '_blank');
        }
    </script>
    <style>
        :root {
            --bg: #f8fafc; --card: #ffffff; --border: #e2e8f0;
            --text: #1e293b; --muted: #64748b;
            --primary: #ff5252; --primary-light: #fff1f2;
            --yellow: #f59e0b; --green: #10b981; --blue: #3b82f6; --purple: #8b5cf6;
            --line: #06c755;
            --input: #ffffff; --tag: #f1f5f9; --shadow: 0 2px 10px rgba(15, 23, 42, 0.04);
        }
        [data-theme="dark"] {
            --bg: #0f172a; --card: #1e293b; --border: #334155;
            --text: #f8fafc; --muted: #94a3b8;
            --primary: #ff6b6b; --primary-light: #2c2125;
            --yellow: #fbbf24; --green: #34d399; --blue: #60a5fa; --purple: #a78bfa;
            --line: #06c755;
            --input: #0f172a; --tag: #283347; --shadow: 0 2px 12px rgba(0,0,0,0.25);
        }
        * { box-sizing: border-box; -webkit-tap-highlight-color: transparent; }
        body { background: var(--bg); color: var(--text); font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; margin: 0; padding: 0 0 70px 0; min-height: 100vh; }
        .max-w { max-width: 480px; margin: 0 auto; padding: 14px; }
        .card { background: var(--card); border: 1.5px solid var(--border); border-radius: 16px; padding: 14px; margin-bottom: 12px; box-shadow: var(--shadow); position: relative; }
        .top-bar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
        .brand { font-size: 21px; font-weight: 900; color: var(--primary); display: flex; align-items: center; gap: 6px; text-decoration: none; }
        .btn-icon, .btn-sm, .btn-block { cursor: pointer; border-radius: 10px; display: inline-flex; align-items: center; justify-content: center; font-weight: 800; border: 1.5px solid var(--border); text-decoration: none; }
        .btn-icon { background: var(--card); color: var(--text); width: 36px; height: 36px; font-size: 15px; box-shadow: var(--shadow); }
        .btn-sm { background: var(--tag); color: var(--text); padding: 8px 12px; font-size: 12px; gap: 4px; }
        .btn-block { width: 100%; min-height: 46px; font-size: 14px; gap: 6px; margin-bottom: 8px; box-shadow: var(--shadow); border: none; }
        .btn-primary { background: var(--primary); color: #fff; border:none; }
        .btn-yellow { background: var(--yellow); color: #493800; border:none; }
        .btn-green { background: var(--green); color: #fff; border:none; }
        .btn-purple { background: var(--purple); color: #fff; border:none; }
        .btn-line { background: var(--line); color: #fff; border:none; }
        .btn-sub { background: var(--tag); color: var(--text); border: 1.5px solid var(--border); }
        .input-group { margin-bottom: 10px; }
        .input-group input, .input-group select { width: 100%; padding: 12px 14px; border: 1.5px solid var(--border); border-radius: 10px; font-size: 14px; background: var(--input); color: var(--text); outline: none; font-weight: 700; }
        .badge { display: inline-flex; align-items: center; gap: 3px; font-size: 10.5px; font-weight: 800; padding: 3px 6px; border-radius: 6px; background: var(--tag); color: var(--text); }
        .badge-primary { background: var(--primary-light); color: var(--primary); }
        .filter-chip { background: var(--tag); border: 1.5px solid var(--border); border-radius: 8px; padding: 8px 10px; font-size: 11.5px; font-weight: 800; color: var(--text); cursor: pointer; display: flex; align-items: center; justify-content: center; gap: 4px; user-select: none; }
        .filter-chip.active { background: var(--primary-light); border-color: var(--primary); color: var(--primary); }
        
        .bottom-nav { position: fixed; bottom: 0; left: 0; width: 100%; background: var(--card); border-top: 1.5px solid var(--border); display: flex; justify-content: space-around; padding: 6px 0 calc(6px + env(safe-area-inset-bottom)); z-index: 9000; }
        .bottom-nav a { color: var(--muted); text-decoration: none; font-size: 10px; display: flex; flex-direction: column; align-items: center; gap: 2px; font-weight: 800; width: 20%; }
        .bottom-nav a.active { color: var(--primary); }
        .bottom-nav span.icon { font-size: 20px; }
        
        #loading-overlay { position: fixed; top: 0; left: 0; width: 100vw; height: 100vh; background: rgba(0,0,0,0.65); display: none; justify-content: center; align-items: center; flex-direction: column; z-index: 99999; backdrop-filter: blur(4px); }
        .spinner { width: 36px; height: 36px; border: 4px solid rgba(255,255,255,0.25); border-top-color: #fff; border-radius: 50%; animation: spin .7s linear infinite; margin-bottom: 12px; }
        @keyframes spin { 100% { transform: rotate(360deg); } }

        [data-theme="light"] .leaflet-tile-pane { filter: contrast(1.06) saturate(1.12); }
        [data-theme="dark"] .leaflet-tile-pane { filter: brightness(0.6) invert(1) contrast(3) hue-rotate(200deg) saturate(0.3) brightness(0.7); }
    </style>
</head>
<body>
    <div id="loading-overlay"><div class="spinner"></div><div id="loading-msg" style="color:#fff; font-size:13.5px; font-weight:800;">食べログ規模の店舗データを取得中...</div></div>
    {{ content | safe }}
    <div class="bottom-nav">
        <a href="/" id="nav-home"><span class="icon">🔍</span><span>探す</span></a>
        <a href="/chat" id="nav-chat"><span class="icon">💬</span><span>相談</span></a>
        <a href="/favorites" id="nav-fav"><span class="icon">📋</span><span>記録</span></a>
        <a href="/game" id="nav-game"><span class="icon">🎯</span><span>抽選</span></a>
        <a href="/tools" id="nav-tools"><span class="icon">🧮</span><span>ツール</span></a>
    </div>
    <script>
        const p = window.location.pathname;
        const navMap = {'/':'nav-home','/chat':'nav-chat','/favorites':'nav-fav','/game':'nav-game','/tools':'nav-tools'};
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
        <button class="btn-icon theme-btn" onclick="toggleTheme()">🌙</button>
        <button class="btn-icon" onclick="window.location.reload(true)">🔄</button>
    </div>
</div>

<div style="display:grid; grid-template-columns:1fr 1fr; gap:8px; margin-bottom:8px;">
    <button class="btn-block btn-green" onclick="searchLoc()">📍 現在地周辺で探す</button>
    <button class="btn-block btn-yellow" onclick="searchNiji()">🍻 二次会・深夜営業</button>
</div>

<div class="card">
    <div style="font-size:12px; font-weight:800; color:var(--muted); margin-bottom:10px;">⭐ 人気ジャンル一発検索</div>
    <div style="display:grid; grid-template-columns:repeat(4,1fr); gap:6px; margin-bottom:14px;">
        <button type="button" class="btn-sm" style="background:#fee2e2; border-color:#fca5a5; color:#991b1b; justify-content:center; padding:6px;" onclick="quick('居酒屋 個室')">🍺 居酒屋</button>
        <button type="button" class="btn-sm" style="background:#fef3c7; border-color:#fde047; color:#854d0e; justify-content:center; padding:6px;" onclick="quick('焼肉')">🍖 焼肉</button>
        <button type="button" class="btn-sm" style="background:#dcfce7; border-color:#86efac; color:#166534; justify-content:center; padding:6px;" onclick="quick('カフェ')">☕ カフェ</button>
        <button type="button" class="btn-sm" style="background:#e0f2fe; border-color:#7dd3fc; color:#075985; justify-content:center; padding:6px;" onclick="quick('ラーメン')">🍜 麺類</button>
    </div>

    <form action="/search" method="GET" id="s-form" onsubmit="showLoad()">
        <div class="input-group"><input type="text" name="area" id="area-in" maxlength="40" placeholder="📍 エリア・駅名 (例: 姫路, 梅田)"></div>
        <div class="input-group"><input type="text" name="keyword" id="kw-in" maxlength="40" placeholder="🔍 キーワード (例: 個室, 焼鳥, 海鮮)"></div>
        
        <div style="font-size:12px; font-weight:800; color:var(--muted); margin:10px 0 6px;">✨ こだわり設備</div>
        <div style="display:grid; grid-template-columns:1fr 1fr; gap:6px; margin-bottom:12px;">
            <div class="filter-chip" onclick="toggleChip(this, 'c-smoking')">🚬 喫煙可能店</div>
            <div class="filter-chip" onclick="toggleChip(this, 'c-private')">🚪 個室あり</div>
            <div class="filter-chip" onclick="toggleChip(this, 'c-drink')">🍺 飲み放題あり</div>
            <div class="filter-chip" onclick="toggleChip(this, 'c-midnight')">🌙 深夜営業</div>
        </div>

        <input type="checkbox" name="smoking" id="c-smoking" value="1" style="display:none;">
        <input type="checkbox" name="private_room" id="c-private" value="1" style="display:none;">
        <input type="checkbox" name="free_drink" id="c-drink" value="1" style="display:none;">
        <input type="checkbox" name="midnight" id="c-midnight" value="1" style="display:none;">

        <button type="submit" class="btn-block btn-primary">最大250件規模で一括検索する</button>
    </form>
</div>
<div style="font-size:11px; text-align:center; color:var(--muted); margin-top:8px;">
    HotPepper (最大200件) ＋ Yahoo!ローカル (最大50件) のハイブリッド網羅
</div>
</div>
<script>
    function showLoad(){ document.getElementById('loading-overlay').style.display='flex'; }
    function quick(k){ document.getElementById('kw-in').value=k; showLoad(); document.getElementById('s-form').submit(); }
    function toggleChip(el, targetId){ doVibrate(25); const cb = document.getElementById(targetId); cb.checked = !cb.checked; if(cb.checked) el.classList.add('active'); else el.classList.remove('active'); }
    function searchLoc(){ if(!navigator.geolocation) return showAppAlert("エラー", "GPS非対応です"); showLoad(); navigator.geolocation.getCurrentPosition(p=>{ window.location.href=`/search?lat=${p.coords.latitude.toFixed(6)}&lng=${p.coords.longitude.toFixed(6)}&area=現在地周辺`; }, ()=>showAppAlert("エラー", "GPSを許可してください"), {timeout:8000}); }
    function searchNiji(){ showLoad(); if(navigator.geolocation){ navigator.geolocation.getCurrentPosition(p=>{ window.location.href=`/search?lat=${p.coords.latitude.toFixed(6)}&lng=${p.coords.longitude.toFixed(6)}&keyword=${encodeURIComponent("二次会 バー 深夜")}&area=現在地&midnight=1`; }, ()=>{ window.location.href=`/search?keyword=${encodeURIComponent("二次会 バー 深夜")}&midnight=1`; }, {timeout:6000}); } else { window.location.href=`/search?keyword=${encodeURIComponent("二次会 バー 深夜")}&midnight=1`; } }
</script>
"""

# --- 検索結果・地図画面（動画再生なし・電話直通・LINE共有復元） ---
RESULT_CONTENT = """
<div id="view-list" class="max-w">
    <div class="top-bar">
        <a href="/" class="btn-sm">← 戻る</a>
        <div style="font-size:13px; font-weight:800; color:var(--muted);"><span id="shop-count">{{ shops|length }}</span>件表示中</div>
    </div>

    <div style="display:flex; gap:6px; margin-bottom:10px;">
        <input type="text" id="live-filter" placeholder="⚡ 表示中のお店から絞り込み..." style="flex:1; padding:8px 12px; border:1.5px solid var(--border); border-radius:10px; font-size:12px; background:var(--input); color:var(--text); outline:none; font-weight:700;" oninput="filterShops(this.value)">
        <button class="btn-sm btn-sub" onclick="toggleSortRating()" id="sort-btn">⭐ 評価順</button>
    </div>

    {% if recipes %}
    <div class="card" style="background:linear-gradient(135deg, #fff7ed, #ffedd5); border-color:#fed7aa; margin-bottom:12px;">
        <div style="font-size:12px; font-weight:900; color:#c2410c; margin-bottom:6px;">🍳 自炊するなら？ 人気レシピと比較 (楽天レシピ)</div>
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

    <div style="position:relative; margin-bottom:12px;">
        <div id="map-preview" style="height:230px; width:100%; border-radius:14px; border:1.5px solid var(--border); box-shadow:var(--shadow);"></div>
        <button onclick="recenterToUser()" style="position:absolute; bottom:10px; right:10px; z-index:1000; background:var(--card); border:1.5px solid var(--border); border-radius:10px; padding:6px 10px; font-size:11px; font-weight:900; cursor:pointer;">🎯 現在地へ</button>
    </div>

    <div id="shops-list">
        {% for s in shops %}
        <div class="card shop-card" id="shop-card-{{ loop.index0 }}" data-name="{{ s.name }}" data-genre="{{ s.genre }}" data-address="{{ s.address }}">
            {% if s.photo %}
            <img src="{{ s.photo }}" style="width:100%; height:150px; object-fit:cover; border-radius:12px; margin-bottom:10px; background:#222; cursor:pointer;" loading="lazy" onclick='openShopDetailByIndex({{ loop.index0 }})'>
            {% endif %}
            
            <div style="display:flex; justify-content:space-between; align-items:flex-start; margin-bottom:4px;">
                <h3 style="font-size:15px; font-weight:900; margin:0; line-height:1.3; flex:1; cursor:pointer;" onclick='openShopDetailByIndex({{ loop.index0 }})'>
                    <span style="background:var(--primary); color:#fff; font-size:11px; padding:2px 6px; border-radius:6px; margin-right:4px;">{{ loop.index }}</span>{{ s.name }}
                </h3>
                <div style="display:flex; gap:4px;">
                    <button class="btn-icon" style="width:30px; height:30px; font-size:14px; border:none; background:none;" onclick='shareShopLine({{ loop.index0 }})' title="LINEで共有">💬</button>
                    <button class="btn-icon" style="width:30px; height:30px; font-size:14px; border:none; background:none;" onclick='saveToFavDirectByIndex({{ loop.index0 }})' title="お気に入り保存">❤️</button>
                </div>
            </div>

            {% if s.catch %}
            <div style="font-size:11px; font-weight:700; color:var(--muted); margin-bottom:6px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;">✨ {{ s.catch }}</div>
            {% endif %}
            
            <div style="display:flex; flex-wrap:wrap; gap:4px; margin-bottom:6px;">
                <span class="badge google-badge" id="g-badge-{{ loop.index0 }}" style="display:none; background:#fef3c7; color:#92400e; font-weight:900; border:1px solid #fde68a;">⭐ 取得中...</span>
                {% if s.source == 'yahoo' %}
                <span class="badge" style="background:#e0f2fe; color:#0284c7; border:1px solid #bae6fd;">🔎 Yahoo!個人店</span>
                {% else %}
                <span class="badge" style="background:#fce7f3; color:#be185d;">🔥 ホットペッパー</span>
                {% endif %}
                <span class="badge badge-primary">🏷️ {{ s.genre }}</span>
                <span class="badge">💰 {{ s.budget }}</span>
            </div>

            <div style="font-size:11.5px; color:var(--muted); margin-bottom:10px; line-height:1.4;">📍 {{ s.address }}</div>
            
            <div style="display:grid; grid-template-columns:1fr 1fr; gap:6px;">
                <button class="btn-sm btn-sub" style="justify-content:center; padding:10px 0; font-weight:900;" onclick='openShopDetailByIndex({{ loop.index0 }})'>🔍 店舗詳細</button>
                <a href="tel:{{ s.tel }}" class="btn-sm btn-green" style="justify-content:center; padding:10px 0; font-weight:900;">📞 今すぐ電話</a>
            </div>
        </div>
        {% endfor %}
    </div>
</div>

<!-- アプリ内完結：店舗詳細シート（動画なし・電話直通特化・LINE共有ボタン付き） -->
<div id="detail-modal" style="display:none; position:fixed; top:0; left:0; width:100vw; height:100vh; background:rgba(0,0,0,0.75); z-index:99999; justify-content:flex-end; align-items:center; padding:14px; flex-direction:column;">
    <div class="card" style="width:100%; max-width:440px; max-height:88vh; display:flex; flex-direction:column; margin:0; background:var(--card); padding:16px;">
        <div style="display:flex; justify-content:space-between; align-items:flex-start; margin-bottom:8px;">
            <div style="font-size:16px; font-weight:900; line-height:1.3; flex:1;" id="dt-name">店舗詳細</div>
            <button onclick="closeShopDetail()" style="background:none; border:none; font-size:20px; cursor:pointer; color:var(--text); padding-left:10px;">✕</button>
        </div>
        
        <div style="overflow-y:auto; flex:1;">
            <img id="dt-photo" src="" style="width:100%; height:190px; object-fit:cover; border-radius:12px; margin-bottom:10px; background:#222; display:none;">
            <div id="dt-catch" style="font-size:12px; font-weight:800; color:var(--primary); margin-bottom:10px; line-height:1.5;"></div>
            
            <!-- 上部直通電話ボタン -->
            <a href="#" id="dt-top-tel" class="btn-block btn-green" style="justify-content:center; font-size:15px; margin-bottom:10px;">📞 店舗に電話予約する</a>

            <div style="font-size:12px; line-height:1.8; background:var(--tag); padding:14px; border-radius:14px; margin-bottom:12px;">
                <div style="margin-bottom:6px;"><b>⭐ Google星評価:</b> <span id="dt-google" style="color:#d97706; font-weight:900;">取得中...</span></div>
                <div style="margin-bottom:6px;"><b>💰 予算目安:</b> <span id="dt-budget">--</span></div>
                <div style="margin-bottom:6px;"><b>🕒 営業時間:</b> <span id="dt-open">--</span></div>
                <div style="margin-bottom:6px;"><b>🎌 定休日:</b> <span id="dt-close">--</span></div>
                <div style="margin-bottom:6px;"><b>🪑 総席数:</b> <span id="dt-capacity">--</span></div>
                <div style="margin-bottom:6px;"><b>💳 支払方法:</b> <span id="dt-card">--</span></div>
                <div style="margin-bottom:6px;"><b>🚃 アクセス:</b> <span id="dt-access">--</span></div>
                <div><b>📍 所在地:</b> <span id="dt-address">--</span></div>
            </div>
        </div>

        <div style="display:grid; grid-template-columns:1fr 1fr; gap:8px; margin-top:8px;">
            <button id="dt-line-btn" class="btn-block btn-line" style="margin:0; min-height:44px; font-size:13px; justify-content:center;">💬 LINEで共有</button>
            <button onclick="closeShopDetail()" class="btn-block btn-sub" style="margin:0; min-height:44px; font-size:13px;">閉じる</button>
        </div>
    </div>
</div>

<script>
    let shops = {{ shops | tojson | safe }};
    let map = null;
    let markers = [];
    let uLat = null, uLng = null;
    let isSorted = false;
    let currentDetailShop = null;

    window.addEventListener('DOMContentLoaded', () => {
        const defaultLat = (shops.length>0 && shops[0].lat) ? shops[0].lat : 34.8290;
        const defaultLng = (shops.length>0 && shops[0].lng) ? shops[0].lng : 134.6900;

        map = L.map('map-preview', {zoomControl:false}).setView([defaultLat, defaultLng], 14);
        L.tileLayer('https://tile.openstreetmap.jp/{z}/{x}/{y}.png', {
            maxZoom: 19,
            attribution: '&copy; OpenStreetMap contributors'
        }).addTo(map);

        renderMarkers();

        if(navigator.geolocation){
            navigator.geolocation.getCurrentPosition(pos => {
                uLat = pos.coords.latitude;
                uLng = pos.coords.longitude;

                const curIcon = L.divIcon({
                    className:'',
                    html:`<div style="background:#3b82f6; width:18px; height:18px; border-radius:50%; border:3px solid #fff; box-shadow:0 0 0 6px rgba(59,130,246,0.35);"></div>`,
                    iconSize:[18,18], iconAnchor:[9,9]
                });
                L.marker([uLat, uLng], {icon: curIcon, zIndexOffset:1000}).addTo(map);
                map.setView([uLat, uLng], 15);
            }, () => {
                const bounds = shops.filter(s=>s.lat&&s.lng).map(s=>[s.lat, s.lng]);
                if(bounds.length > 0) map.fitBounds(bounds, {padding:[15,15]});
            }, {timeout:5000});
        }

        loadRatingsInBackground();
    });

    function renderMarkers(filteredIndices = null) {
        markers.forEach(m => map.removeLayer(m));
        markers = [];
        shops.forEach((s, i) => {
            if(filteredIndices && !filteredIndices.has(i)) return;
            if(s.lat && s.lng){
                const icon = L.divIcon({
                    className:'',
                    html:`<div style="background:var(--primary); color:#fff; border-radius:50%; border:2px solid #fff; box-shadow:0 2px 4px rgba(0,0,0,0.3); font-size:11px; font-weight:900; display:flex; align-items:center; justify-content:center; width:24px; height:24px;">${i+1}</div>`,
                    iconSize:[24,24], iconAnchor:[12,12]
                });
                const m = L.marker([s.lat, s.lng], {icon}).addTo(map);
                m.on('click', () => openShopDetailByIndex(i));
                markers.push(m);
            }
        });
    }

    async function loadRatingsInBackground() {
        const topShops = shops.slice(0, 30).map((s, idx) => ({index: idx, name: s.name, address: s.address}));
        try {
            const res = await fetch('/api/places_enrich', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({shops: topShops})
            });
            const data = await res.json();
            data.forEach(item => {
                if(item.rating) {
                    shops[item.index].google_rating = item.rating;
                    shops[item.index].google_reviews_count = item.count;
                    const b = document.getElementById(`g-badge-${item.index}`);
                    if(b) {
                        b.innerText = `⭐ Google ${item.rating} (${item.count}件)`;
                        b.style.display = 'inline-flex';
                    }
                }
            });
        } catch(e) {}
    }

    function filterShops(val) {
        const q = val.toLowerCase().trim();
        const validIndices = new Set();
        let visibleCount = 0;
        shops.forEach((s, idx) => {
            const el = document.getElementById(`shop-card-${idx}`);
            const text = `${s.name} ${s.genre} ${s.address}`.toLowerCase();
            if(!q || text.includes(q)) {
                el.style.display = 'block';
                validIndices.add(idx);
                visibleCount++;
            } else {
                el.style.display = 'none';
            }
        });
        document.getElementById('shop-count').innerText = visibleCount;
        renderMarkers(validIndices);
    }

    function toggleSortRating() {
        const container = document.getElementById('shops-list');
        const cards = Array.from(container.children);
        isSorted = !isSorted;
        document.getElementById('sort-btn').innerText = isSorted ? "🔄 標準順" : "⭐ 評価順";

        cards.sort((a, b) => {
            if(!isSorted) return parseInt(a.id.replace('shop-card-','')) - parseInt(b.id.replace('shop-card-',''));
            const idxA = parseInt(a.id.replace('shop-card-','')), idxB = parseInt(b.id.replace('shop-card-',''));
            const rA = shops[idxA].google_rating || 0, rB = shops[idxB].google_rating || 0;
            return rB - rA;
        });
        cards.forEach(c => container.appendChild(c));
    }

    function recenterToUser() {
        if(uLat && uLng) {
            map.setView([uLat, uLng], 16);
        } else if(navigator.geolocation) {
            navigator.geolocation.getCurrentPosition(pos => {
                uLat = pos.coords.latitude; uLng = pos.coords.longitude;
                map.setView([uLat, uLng], 16);
            });
        }
    }

    function openShopDetailByIndex(idx) {
        const s = shops[idx];
        currentDetailShop = s;
        document.getElementById('dt-name').innerText = s.name;
        document.getElementById('dt-catch').innerText = s.catch ? `「${s.catch}」` : '';
        document.getElementById('dt-budget').innerText = s.budget || "要確認";
        document.getElementById('dt-open').innerText = s.open || "要確認";
        document.getElementById('dt-close').innerText = s.close || "無休 / 要確認";
        document.getElementById('dt-capacity').innerText = s.capacity || "要確認";
        document.getElementById('dt-card').innerText = s.card || "要確認";
        document.getElementById('dt-access').innerText = s.access || "駅近";
        document.getElementById('dt-address').innerText = s.address || "情報なし";
        
        const gEl = document.getElementById('dt-google');
        if(s.google_rating) {
            gEl.innerText = `★ ${s.google_rating} (${s.google_reviews_count || 0} 件のクチコミ)`;
        } else {
            gEl.innerText = "データ取得中またはクチコミなし";
        }

        const photoEl = document.getElementById('dt-photo');
        if(s.photo) { photoEl.src = s.photo; photoEl.style.display = 'block'; } else { photoEl.style.display = 'none'; }
        
        document.getElementById('dt-top-tel').href = `tel:${s.tel}`;
        document.getElementById('dt-line-btn').onclick = () => {
            const shareText = `【EAT MAP】おすすめのお店を見つけたよ！\\n店名: ${s.name}\\nジャンル: ${s.genre}\\n住所: ${s.address}\\n電話: ${s.tel}`;
            shareToLine(shareText);
        };

        document.getElementById('detail-modal').style.display = 'flex';
        if(s.lat && s.lng) map.panTo([s.lat, s.lng]);
    }

    function closeShopDetail() {
        document.getElementById('detail-modal').style.display = 'none';
    }

    function shareShopLine(idx) {
        const s = shops[idx];
        const shareText = `【EAT MAP】ここはどう？\\n店名: ${s.name}\\nジャンル: ${s.genre}\\n住所: ${s.address}\\n電話: ${s.tel}`;
        shareToLine(shareText);
    }

    function saveToFavDirectByIndex(idx) {
        const s = shops[idx];
        let f = JSON.parse(localStorage.getItem('eatmap_favs')||'[]');
        if(f.some(x => x.name === s.name)){
            showAppAlert("ご案内", "すでにお気に入りに保存されています！");
            return;
        }
        f.unshift({
            name: s.name, genre: s.genre, address: s.address, photo: s.photo,
            visited: false, rating: 0, memo: "", tag: ""
        });
        localStorage.setItem('eatmap_favs', JSON.stringify(f));
        showAppAlert("保存完了！", `【${s.name}】をお気に入りに追加しました📋`);
    }
</script>
"""

# --- グルメ記録画面 ---
FAVORITES_CONTENT = """
<div class="max-w">
<div class="top-bar"><div class="brand">📋 グルメ記録</div><button class="btn-sm btn-yellow" onclick="pickRandomFav()">🎲 ガチャ</button></div>
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
<script>
    const titles = [{ lv:1, count:0, title:"Lv.1 ひよっこ探検家 🐣", icon:"🐣" },{ lv:2, count:2, title:"Lv.2 街角の食べ歩き隊 🚶", icon:"🍙" },{ lv:3, count:5, title:"Lv.3 こだわりグルメ通 🍴", icon:"🍝" },{ lv:4, count:10, title:"Lv.4 地域の名店ハンター 🏅", icon:"🥩" },{ lv:5, count:20, title:"Lv.5 伝説の美食王 👑", icon:"👑" }];
    
    function renderFavs(){
        const list = document.getElementById('fav-list');
        const f = JSON.parse(localStorage.getItem('eatmap_favs')||'[]');
        const vCount = f.filter(s => s.visited).length;
        let cur = titles[0], nxtC = titles[1].count;
        for(let i=0; i<titles.length; i++){ if(vCount >= titles[i].count){ cur = titles[i]; nxtC = titles[i+1] ? titles[i+1].count : vCount + 10; } }
        document.getElementById('user-title').innerText = cur.title; document.getElementById('badge-icon').innerText = cur.icon; document.getElementById('visited-count').innerText = `訪問達成: ${vCount}軒`;
        const eR = Math.min(100, Math.max(5, ((vCount - cur.count) / Math.max(1, (nxtC - cur.count))) * 100));
        document.getElementById('exp-text').innerText = `次まで あと${Math.max(0, nxtC - vCount)}軒`; document.getElementById('exp-bar').style.width = eR + '%';
        
        if(f.length===0){ list.innerHTML = `<div class="card" style="text-align:center; color:var(--muted); font-weight:700; padding:30px 10px;">保存したお店がまだありません。検索結果の「❤️」ボタンで追加できます！</div>`; return; }
        const tags = ["😋絶品", "🔥コスパ", "🍺酒進む", "✨雰囲気"];
        
        list.innerHTML = f.map((s,i)=>{
            const rating = s.rating || 0;
            const starsHtml = [1,2,3,4,5].map(star => `<span style="cursor:pointer; font-size:16px; color:${star <= rating ? '#f59e0b':'#cbd5e1'};" onclick="setRating(${i}, ${star})">★</span>`).join('');
            return `
            <div class="card" style="display:flex; flex-direction:column; padding:12px; margin-bottom:0;">
                <div style="display:flex; gap:10px; align-items:center;">
                    <div style="width:65px; height:65px; border-radius:10px; overflow:hidden; flex-shrink:0; background:var(--tag); display:flex; align-items:center; justify-content:center; font-size:24px;">${s.photo ? `<img src="${s.photo}" style="width:100%; height:100%; object-fit:cover;" loading="lazy">` : '🍽️'}</div>
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
                ${s.visited ? `<div style="display:flex; gap:3px; margin:6px 0; overflow-x:auto;">${tags.map(t => `<span style="padding:2px 6px; font-size:9px; border-radius:6px; font-weight:800; cursor:pointer; background:${s.tag===t?'var(--yellow)':'var(--tag)'}; color:${s.tag===t?'#493800':'var(--muted)'};" onclick="setTag(${i}, '${t}')">${t}</span>`).join('')}</div>` : ''}
                <div style="margin-top:6px;">
                    <input type="text" value="${(s.memo||'').replace(/"/g, '&quot;')}" placeholder="📝 一言メモ (例: レモンサワー最高、奥の席が静か)" maxlength="40" style="width:100%; padding:6px 10px; border:1px solid var(--border); border-radius:8px; font-size:11px; background:var(--tag); color:var(--text); outline:none; font-weight:700;" onchange="saveMemo(${i}, this.value)">
                </div>
                <div style="display:flex; gap:6px; margin-top:8px;">
                    <button class="btn-sm ${s.visited?'btn-green':'btn-sub'}" style="flex:1; padding:6px 0; font-size:10.5px; border:none;" onclick="toggleV(${i})">${s.visited?'🏁 行った！':'🚩 行ってみたい'}</button>
                    <button class="btn-sm btn-line" style="padding:6px 10px; font-size:10.5px; border:none;" onclick="shareFavLine(${i})">LINE共有</button>
                </div>
            </div>`;
        }).join('');
    }
    function setRating(i, r){ doVibrate(30); let f = JSON.parse(localStorage.getItem('eatmap_favs')); f[i].rating = (f[i].rating === r) ? 0 : r; localStorage.setItem('eatmap_favs', JSON.stringify(f)); renderFavs(); }
    function saveMemo(i, val){ let f = JSON.parse(localStorage.getItem('eatmap_favs')); f[i].memo = val.trim(); localStorage.setItem('eatmap_favs', JSON.stringify(f)); }
    function toggleV(i){ doVibrate(30); let f = JSON.parse(localStorage.getItem('eatmap_favs')); f[i].visited = !f[i].visited; localStorage.setItem('eatmap_favs', JSON.stringify(f)); renderFavs(); }
    function setTag(i, t){ doVibrate(20); let f = JSON.parse(localStorage.getItem('eatmap_favs')); f[i].tag = (f[i].tag === t) ? '' : t; localStorage.setItem('eatmap_favs', JSON.stringify(f)); renderFavs(); }
    function delFav(i){ if(confirm("リストから削除しますか？")){ doVibrate(30); let f = JSON.parse(localStorage.getItem('eatmap_favs')); f.splice(i,1); localStorage.setItem('eatmap_favs', JSON.stringify(f)); renderFavs(); } }
    function pickRandomFav(){ const f = JSON.parse(localStorage.getItem('eatmap_favs')||'[]'); if(f.length===0) return showAppAlert("ご案内", "保存したお店がありません！"); doVibrate([50, 50, 100]); const p = f[Math.floor(Math.random() * f.length)]; showAppAlert("🎲 今日のオススメ！", `【${p.name}】\\nジャンル: ${p.genre}\\n住所: ${p.address}`); }
    function shareFavLine(i){
        const f = JSON.parse(localStorage.getItem('eatmap_favs')||'[]');
        const s = f[i];
        shareToLine(`【おすすめ店舗記録】\\n店名: ${s.name}\\n評価: ${s.rating ? '★'+s.rating : '記録中'}\\nメモ: ${s.memo || 'なし'}`);
    }
    window.addEventListener('DOMContentLoaded', renderFavs);
</script>
"""

# --- 抽選画面（カラー別ルーレットカスタム＆LINE共有復元） ---
GAME_CONTENT = """
<div class="max-w">
<div class="top-bar"><div class="brand">🎯 抽選・診断</div></div>
<div class="card" style="text-align:center; padding:18px 12px; margin-bottom:12px;">
    <div style="font-size:13px; font-weight:800; color:var(--muted); margin-bottom:12px;">🍽️ 何を食べるか迷ったらルーレット！</div>
    <div style="position:relative; width:280px; height:280px; margin:0 auto 18px;">
        <div style="position:absolute; top:-12px; left:50%; transform:translateX(-50%); width:0; height:0; border-left:12px solid transparent; border-right:12px solid transparent; border-top:22px solid var(--primary); z-index:20;"></div>
        <div style="position:absolute; top:50%; left:50%; transform:translate(-50%, -50%); width:44px; height:44px; background:var(--card); border:3px solid var(--primary); border-radius:50%; z-index:15; display:flex; align-items:center; justify-content:center; font-size:18px;">🍽️</div>
        <canvas id="wheel-canvas" width="280" height="280" style="border-radius:50%; box-shadow:var(--shadow); transition:transform 4.5s cubic-bezier(0.15, 0.9, 0.2, 1);"></canvas>
    </div>
    <button class="btn-block btn-primary" id="spin-btn" style="font-size:16px; min-height:50px;" onclick="spinWheel()">🎯 ルーレットを回す！</button>
</div>

<div class="card" id="result-box" style="display:none; text-align:center; background:var(--primary-light); border-color:var(--primary); margin-bottom:12px;">
    <div style="font-size:12px; font-weight:800; color:var(--muted);">当選結果</div>
    <div style="font-size:26px; font-weight:900; color:var(--primary); margin:8px 0;" id="res-val">--</div>
    
    <div style="display:grid; grid-template-columns:1fr 1fr; gap:6px; margin-top:8px;">
        <a href="#" id="res-search-btn" class="btn-block btn-green" style="margin:0; justify-content:center;">🔍 お店を探す</a>
        <button class="btn-block btn-line" id="res-line-btn" style="margin:0; justify-content:center;" onclick="shareResultLine()">💬 結果をLINE共有</button>
    </div>
</div>

<!-- カラー別直感カスタムUI -->
<div class="card">
    <div style="font-size:13px; font-weight:900; color:var(--text); margin-bottom:4px;">🎨 ルーレット項目のカラー別編集</div>
    <div style="font-size:11px; color:var(--muted); margin-bottom:12px;">それぞれの色に対応するジャンルや店名を自由に変更できます。</div>
    
    <div id="color-slots" style="display:grid; grid-template-columns:1fr 1fr; gap:8px;"></div>
    <button class="btn-block btn-sub" style="margin-top:10px;" onclick="saveCustomWheel()">盤面を保存して更新</button>
</div>

<div class="card">
    <div style="font-size:13px; font-weight:900; color:var(--blue); margin-bottom:6px;">🍶 今夜飲むべきお酒診断 (さけのわ連携)</div>
    <div style="display:grid; grid-template-columns:1fr 1fr; gap:6px;">
        <button class="btn-sm btn-sub" onclick="showDrinkPick('華やかフルーティー（獺祭・鳳凰美田系）')">🌸 フルーティー系</button>
        <button class="btn-sm btn-sub" onclick="showDrinkPick('すっきり超辛口（久保田・八海山系）')">❄️ すっきり辛口</button>
        <button class="btn-sm btn-sub" onclick="showDrinkPick('ジントニック・モスコミュール')">🍸 定番カクテル</button>
        <button class="btn-sm btn-sub" onclick="showDrinkPick('芳醇ハイボール・山崎白州系')">🥃 芳醇ウイスキー</button>
    </div>
</div>
</div>
<script>
    const wheelColors = [
        { name: "レッド", code: "#ffc9c9", border: "#ff8787" },
        { name: "オレンジ", code: "#ffe3a8", border: "#ffa94d" },
        { name: "イエロー", code: "#fff3bf", border: "#ffe066" },
        { name: "グリーン", code: "#bbf7d0", border: "#69db7c" },
        { name: "スカイ", code: "#c5f6fa", border: "#3bc9db" },
        { name: "ブルー", code: "#d0ebff", border: "#74c0fc" },
        { name: "パープル", code: "#dbe4ff", border: "#91a7ff" },
        { name: "ピンク", code: "#f3d9fa", border: "#da77f2" }
    ];

    let defaultItems = ["焼肉 🥩","居酒屋 🍺","カフェ ☕","ラーメン 🍜","海鮮 🐟","カレー 🍛","イタリアン 🍕","中華 🥟"];
    let wheelItems = JSON.parse(localStorage.getItem('eatmap_wheel_items') || JSON.stringify(defaultItems));
    let curDeg = 0, isSpinning = false;
    let lastWinner = "";

    function renderColorSlots() {
        const c = document.getElementById('color-slots');
        c.innerHTML = wheelColors.map((col, i) => `
            <div style="display:flex; align-items:center; gap:6px; background:var(--tag); padding:6px 8px; border-radius:10px; border-left:6px solid ${col.border};">
                <input type="text" id="slot-${i}" value="${wheelItems[i] || ''}" style="width:100%; border:none; background:transparent; font-size:12px; font-weight:800; color:var(--text); outline:none;">
            </div>
        `).join('');
    }

    function drawCanvas() { 
        const canvas = document.getElementById('wheel-canvas'); if(!canvas) return; 
        const ctx = canvas.getContext('2d'); ctx.clearRect(0, 0, 280, 280); 
        const num = wheelItems.length, arc = (2 * Math.PI) / num; 
        for(let i=0; i<num; i++){ 
            const a = i * arc; ctx.fillStyle = wheelColors[i % wheelColors.length].code; ctx.beginPath(); 
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
            const deg = curDeg % 360; const step = 360 / wheelItems.length; 
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
        const newItems = [];
        for(let i=0; i<wheelColors.length; i++){
            const val = document.getElementById(`slot-${i}`).value.trim();
            newItems.push(val || `項目 ${i+1}`);
        }
        wheelItems = newItems;
        localStorage.setItem('eatmap_wheel_items', JSON.stringify(wheelItems));
        drawCanvas();
        showAppAlert("設定完了", "ルーレットの各カラー項目を更新しました！");
    }

    function shareResultLine() {
        if(!lastWinner) return;
        shareToLine(`【EAT MAP】今日のランチ・ディナー抽選結果！\\n🎉 当選ジャンル: ${lastWinner}\\nこれで決定！行こう！🍽️`);
    }

    function showDrinkPick(msg){
        showAppAlert("🍶 おすすめのお酒", `【${msg}】\\nお店で注文してみてください！✨`);
    }

    window.addEventListener('DOMContentLoaded', () => {
        renderColorSlots();
        drawCanvas();
    });
</script>
"""

# --- おでかけツール画面 ---
TOOLS_CONTENT = """
<div class="max-w">
<div class="top-bar"><div class="brand">🧮 おでかけツール</div></div>

<div class="card" style="border-color:var(--yellow);">
    <div style="font-size:12px; font-weight:800; color:var(--yellow); margin-bottom:8px;">⏳ 飲み放題・コース退席タイマー</div>
    <div style="display:flex; gap:6px;">
        <button class="btn-sm btn-sub" onclick="startTimer(90)">90分</button>
        <button class="btn-sm btn-sub" onclick="startTimer(120)">120分</button>
        <button class="btn-sm btn-sub" onclick="startTimer(150)">150分</button>
        <button class="btn-sm btn-primary" onclick="cancelTimer()">停止</button>
    </div>
    <div id="timer-status" style="font-size:11px; font-weight:800; color:var(--muted); margin-top:6px;">未稼働</div>
</div>

<div class="card" style="border-color:var(--purple);">
    <div style="font-size:12px; font-weight:800; color:var(--purple); margin-bottom:8px;">⏰ 終電見張りアラーム</div>
    <div style="display:flex; gap:6px; align-items:center;">
        <input type="time" id="train-time" style="padding:8px 10px; border:1.5px solid var(--border); border-radius:10px; font-size:14px; font-weight:800; background:var(--input); color:var(--text); outline:none;">
        <button class="btn-sm btn-purple" style="flex:1; justify-content:center;" onclick="setTrainAlarm()">セット</button>
    </div>
    <div id="train-status" style="font-size:11px; font-weight:800; color:var(--muted); margin-top:6px;">未設定</div>
</div>

<div class="card">
    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:10px;">
        <span style="font-size:12px; font-weight:800; color:var(--muted);">💸 傾斜割り勘計算</span>
        <label class="btn-sm btn-primary" style="padding:6px 10px; font-size:11px; cursor:pointer;">
            📸 レシート自動読取
            <input type="file" accept="image/*" capture="environment" style="display:none;" onchange="ocrReceipt(this)">
        </label>
    </div>

    <div class="input-group"><input type="number" id="split-total" placeholder="合計お会計 (円)"></div>
    <div style="display:grid; grid-template-columns: 1fr 1fr; gap:8px;">
        <div class="input-group"><input type="number" id="split-drinkers" value="2"><small style="font-size:11px; font-weight:700; color:var(--muted);">飲む人数</small></div>
        <div class="input-group"><input type="number" id="split-nondrinkers" value="1"><small style="font-size:11px; font-weight:700; color:var(--muted);">飲まない人数</small></div>
    </div>
    <div class="input-group"><input type="number" id="split-discount" value="1000"><small style="font-size:11px; font-weight:700; color:var(--muted);">飲まない人の割引額 (円引)</small></div>
    <button class="btn-block btn-primary" onclick="calcSplit()">割り勘を計算する</button>
    <div id="split-res" style="display:none; background:var(--tag); padding:12px; border-radius:12px; margin-top:10px; font-size:13px; font-weight:700;">
        <div style="display:flex; justify-content:space-between; margin-bottom:6px;"><span>🍺 飲む人:</span><b style="color:var(--primary); font-size:16px;" id="res-drinker">0円</b></div>
        <div style="display:flex; justify-content:space-between; margin-bottom:10px;"><span>🍵 飲まない人:</span><b style="color:var(--green); font-size:16px;" id="res-nondrinker">0円</b></div>
        <button class="btn-block btn-line" style="margin:0;" onclick="shareSplitLine()">💬 割り勘結果をLINEで送る</button>
    </div>
</div>
</div>
<script>
    let timerInterval = null;
    function startTimer(min) {
        if(timerInterval) clearInterval(timerInterval);
        let rem = min * 60;
        document.getElementById('timer-status').innerText = `残り時間: ${min}分 (退席15分前に通知)`;
        document.getElementById('timer-status').style.color = "var(--yellow)";
        timerInterval = setInterval(() => {
            rem--;
            if(rem === 900) { showAppAlert("⚠️ ラストオーダー", "退席15分前です！ラストオーダーの確認をおすすめします。"); }
            if(rem <= 0) { clearInterval(timerInterval); showAppAlert("🔔 お時間です", "コースの利用時間・お席の終了時刻になりました！"); }
            const m = Math.floor(rem / 60), s = rem % 60;
            document.getElementById('timer-status').innerText = `残り時間: ${m}分 ${s}秒`;
        }, 1000);
        showAppAlert("セット完了", `${min}分タイマーを開始しました。`);
    }
    function cancelTimer() {
        if(timerInterval) clearInterval(timerInterval);
        document.getElementById('timer-status').innerText = "未稼働";
        document.getElementById('timer-status').style.color = "var(--muted)";
    }

    function setTrainAlarm(){ 
        const val = document.getElementById('train-time').value; if(!val) return showAppAlert("エラー", "時刻を選択してください"); 
        document.getElementById('train-status').innerText = `【${val}】にセットしました`; 
        document.getElementById('train-status').style.color = "var(--purple)";
        showAppAlert("完了", `終電を【${val}】にセットしました！`); 
    }

    let lastSplitData = null;
    function calcSplit() { 
        const tot = parseInt(document.getElementById('split-total').value)||0, dr = parseInt(document.getElementById('split-drinkers').value)||0, ndr = parseInt(document.getElementById('split-nondrinkers').value)||0, disc = parseInt(document.getElementById('split-discount').value)||0; 
        const num = dr + ndr; if(!tot || num <= 0) return showAppAlert("エラー", "金額と人数を入力してください"); 
        const adj = tot + (disc * ndr); const base = Math.ceil((adj / num) / 100) * 100; const nonBase = Math.max(0, base - disc); 
        document.getElementById('res-drinker').innerText = `${base.toLocaleString()} 円`; 
        document.getElementById('res-nondrinker').innerText = `${nonBase.toLocaleString()} 円`; 
        document.getElementById('split-res').style.display = 'block'; 
        lastSplitData = { total: tot, drinker: base, nonDrinker: nonBase, drCount: dr, ndrCount: ndr };
    }

    function shareSplitLine() {
        if(!lastSplitData) return;
        const text = `【お会計・割り勘計算】\\n合計: ¥${lastSplitData.total.toLocaleString()}\\n🍺 飲む人 (${lastSplitData.drCount}名): 各 ¥${lastSplitData.drinker.toLocaleString()}\\n🍵 飲まない人 (${lastSplitData.ndrCount}名): 各 ¥${lastSplitData.nonDrinker.toLocaleString()}\\nよろしくお願いします！✨`;
        shareToLine(text);
    }

    async function ocrReceipt(input) {
        if (!input.files || !input.files[0]) return;
        const file = input.files[0];
        document.getElementById('loading-overlay').style.display = 'flex';
        document.getElementById('loading-msg').innerText = "レシートの金額を読み取り中...";

        const reader = new FileReader();
        reader.onload = async function() {
            const b64 = reader.result.split(',')[1];
            try {
                const res = await fetch('/api/ocr', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({image: b64})
                });
                const data = await res.json();
                document.getElementById('loading-overlay').style.display = 'none';
                if(data.amount) {
                    document.getElementById('split-total').value = data.amount;
                    showAppAlert("読取成功！", `合計金額【¥${data.amount.toLocaleString()}】を読み取りました！`);
                    calcSplit();
                } else {
                    showAppAlert("ご案内", "合計金額が見つかりませんでした。直接入力してください。");
                }
            } catch(e) {
                document.getElementById('loading-overlay').style.display = 'none';
                showAppAlert("エラー", "画像の解析に失敗しました。");
            }
        };
        reader.readAsDataURL(file);
    }
</script>
"""

# --- AIコンシェルジュ相談画面 ---
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
            <div class="msg msg-ai">お店探しのお手伝いをします✨<br>「胃に優しい料理」「元気が出るお肉」「姫路駅周辺で個室居酒屋」など気軽に相談してください！</div>
        </div>
    </div>
    <div style="display:flex; gap:8px;">
        <input type="text" id="inp" maxlength="80" placeholder="相談を入力..." style="flex:1; padding:13px 14px; border:1.5px solid var(--border); border-radius:12px; font-size:14px; background:var(--input); color:var(--text); font-weight:700; outline:none;" onkeydown="if(event.key==='Enter' && !event.isComposing) { event.preventDefault(); send(); }">
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
        try {
            const res = await fetch('/api/chat', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({message:txt}) });
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

# ================= 5. バックエンドAPI・ルーティング =================

@app.route('/')
def home(): return render_page(HOME_CONTENT)

@app.route('/favorites')
def favorites(): return render_page(FAVORITES_CONTENT)

@app.route('/game')
def game(): return render_page(GAME_CONTENT)

@app.route('/tools')
def tools(): return render_page(TOOLS_CONTENT)

@app.route('/chat')
def chat(): return render_page(CHAT_CONTENT)

@app.route('/search')
def search():
    k = html.escape(request.args.get('keyword', '')[:40])
    a = html.escape(request.args.get('area', '')[:40])
    smoking = request.args.get('smoking') == '1'
    private_room = request.args.get('private_room') == '1'
    free_drink = request.args.get('free_drink') == '1'
    midnight = request.args.get('midnight') == '1'
    
    try:
        lat_val = float(request.args.get('lat')) if request.args.get('lat') else None
        lng_val = float(request.args.get('lng')) if request.args.get('lng') else None
    except (ValueError, TypeError): lat_val, lng_val = None, None

    # 並行処理で店舗大量取得 ＆ 楽天レシピ比較取得
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        f_shops = executor.submit(fetch_all_shops_massive, k, a, lat_val, lng_val, smoking, private_room, free_drink, midnight)
        f_recipes = executor.submit(fetch_rakuten_recipes, k or a or "肉")
        shops = f_shops.result()
        recipes = f_recipes.result()
    
    title = f"{a} {k}".strip() or "おすすめ店舗"
    content = render_template_string(RESULT_CONTENT, shops=shops, search_title=title, recipes=recipes)
    return render_page(content)

# Google Places 評価の遅延注入エンドポイント
@app.route('/api/places_enrich', methods=['POST'])
def api_places_enrich():
    req_json = request.get_json(silent=True) or {}
    items = req_json.get('shops', [])
    if not items or not GOOGLE_PLACES_API_KEY:
        return jsonify([])

    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as executor:
        future_map = {executor.submit(fetch_single_google_rating, s.get('name',''), s.get('address','')): s for s in items}
        for future in concurrent.futures.as_completed(future_map):
            target = future_map[future]
            try:
                r, c = future.result()
                if r:
                    results.append({"index": target.get('index'), "rating": r, "count": c})
            except Exception: pass

    return jsonify(results)

# レシートOCR解析API
@app.route('/api/ocr', methods=['POST'])
def api_ocr():
    req_json = request.get_json(silent=True) or {}
    img_b64 = req_json.get('image', '')
    if not img_b64 or not GOOGLE_PLACES_API_KEY:
        return jsonify({"amount": None})

    url = f"https://vision.googleapis.com/v1/images:annotate?key={GOOGLE_PLACES_API_KEY}"
    payload = {
        "requests": [{
            "image": {"content": img_b64},
            "features": [{"type": "TEXT_DETECTION"}]
        }]
    }
    try:
        req = urllib.request.Request(url, data=json.dumps(payload).encode('utf-8'), headers={'Content-Type': 'application/json'})
        with urllib.request.urlopen(req, timeout=5.0) as res:
            d = json.loads(res.read().decode('utf-8'))
            text = d['responses'][0].get('fullTextAnnotation', {}).get('text', '')
            matches = re.findall(r'(?:合計|小計|お会計|支払|領収|計)?[\s:：]*[¥￥]?\s*([0-9]{1,3}(?:,[0-9]{3})+|[0-9]{3,6})\s*(?:円)?', text)
            if matches:
                nums = [int(m.replace(',', '')) for m in matches if int(m.replace(',', '')) >= 500]
                if nums:
                    return jsonify({"amount": max(nums)})
    except Exception: pass
    return jsonify({"amount": None})

# AI相談API
@app.route('/api/chat', methods=['POST'])
def api_chat():
    req_json = request.get_json(silent=True) or {}
    raw_msg = str(req_json.get('message', ''))[:80].strip()
    msg = html.escape(raw_msg)
    
    if msg in AI_CACHE: return jsonify(AI_CACHE[msg])
    clean_reply, search_keyword = None, None
    prompt = f"あなたは飲食店探しアプリ「EAT MAP」の親身な専属コンシェルジュです。ユーザーの言葉「{msg}」に日本語敬語で寄り添い、具体的な料理やお店の選び方を80文字以内で親切に提案してください。返答の最後に店舗検索に最適なキーワードを「【SEARCH:キーワード】」という形式で必ず1つ付けてください。"

    if GROQ_API_KEY:
        groq_payload = {"model": "llama-3.3-70b-versatile", "messages": [{"role": "system", "content": prompt}, {"role": "user", "content": msg}], "max_tokens": 120, "temperature": 0.5}
        try:
            req = urllib.request.Request("https://api.groq.com/openai/v1/chat/completions", data=json.dumps(groq_payload).encode('utf-8'), headers={'Content-Type': 'application/json', 'Authorization': f'Bearer {GROQ_API_KEY}', 'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=4) as res:
                raw_text = json.loads(res.read().decode('utf-8'))['choices'][0]['message']['content']
                kw_match = re.search(r'【SEARCH:(.*?)】', raw_text)
                if kw_match:
                    search_keyword = kw_match.group(1).strip()
                    raw_text = re.sub(r'【SEARCH:.*?】', '', raw_text)
                clean_reply = raw_text.replace("**", "").replace("*", "").strip()
        except Exception: pass

    if not clean_reply and GEMINI_API_KEY:
        try:
            req = urllib.request.Request(f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={urllib.parse.quote(GEMINI_API_KEY)}", data=json.dumps({"contents": [{"parts": [{"text": prompt}]}], "generationConfig": {"maxOutputTokens": 120, "temperature": 0.5}}).encode('utf-8'), headers={'Content-Type': 'application/json'})
            with urllib.request.urlopen(req, timeout=4) as res:
                raw_text = json.loads(res.read().decode('utf-8'))['candidates'][0]['content']['parts'][0]['text']
                kw_match = re.search(r'【SEARCH:(.*?)】', raw_text)
                if kw_match:
                    search_keyword = kw_match.group(1).strip()
                    raw_text = re.sub(r'【SEARCH:.*?】', '', raw_text)
                clean_reply = raw_text.replace("**", "").replace("*", "").strip()
        except Exception: pass

    if not clean_reply:
        clean_reply = f"「{msg}」ですね！今すぐ行きたくなるおすすめのお店をピックアップしてご案内しますね🍽️"
        search_keyword = msg

    res_payload = {"reply": clean_reply, "keyword": search_keyword}
    if len(AI_CACHE) > 100: AI_CACHE.clear()
    AI_CACHE[msg] = res_payload
    return jsonify(res_payload)

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
