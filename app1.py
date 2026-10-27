# ==============================================================================
# 【EAT MAP】HotPepper × Google × Yahoo! × 楽天レシピ 完全統合版 app1.py
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
    if len(IP_LOG[ip]) >= 120: 
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
        "connect-src 'self' https://api.open-meteo.com https://generativelanguage.googleapis.com https://api.groq.com https://*.openstreetmap.org https://tile.openstreetmap.jp https://cyberjapandata.gsi.go.jp https://router.project-osrm.org https://places.googleapis.com https://maps.googleapis.com https://map.yahooapis.jp https://app.rakuten.co.jp;"
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

# ================= 2. API連携エンジン =================

# 1. Google Places API (評価と口コミ件数の並行取得)
def fetch_google_place_rating(name, address):
    if not GOOGLE_PLACES_API_KEY: return None, 0
    clean_name = re.sub(r'\(.*?\)|（.*?）', '', name).strip()
    cache_key = f"{clean_name}_{address[:12]}"
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
        with urllib.request.urlopen(req, timeout=3.5) as res:
            places = json.loads(res.read().decode("utf-8")).get("places", [])
            if places:
                r, c = places[0].get("rating"), places[0].get("userRatingCount", 0)
                PLACES_CACHE[cache_key] = (r, c)
                return r, c
    except Exception: pass
    PLACES_CACHE[cache_key] = (None, 0)
    return None, 0

def enrich_shops_with_google_places(shop_list):
    if not GOOGLE_PLACES_API_KEY or not shop_list: return
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        future_map = {executor.submit(fetch_google_place_rating, s["name"], s.get("address", "")): s for s in shop_list[:15]}
        for future in concurrent.futures.as_completed(future_map):
            s = future_map[future]
            try:
                r, c = future.result()
                s["google_rating"], s["google_reviews_count"] = r, c
            except Exception:
                s["google_rating"], s["google_reviews_count"] = None, 0

# 2. Yahoo!ローカルサーチ (個人店・隠れ家店舗の補完取得)
def fetch_yahoo_local(keyword, lat, lng):
    if not YAHOO_CLIENT_ID: return []
    params = {"appid": YAHOO_CLIENT_ID, "output": "json", "results": 8, "gc": "01"}
    if keyword: params["query"] = keyword
    if lat and lng:
        params["lat"], params["lon"], params["dist"] = lat, lng, 3
        if not keyword: params["query"] = "飲食店"
    
    try:
        url = f"https://map.yahooapis.jp/search/local/V1/localSearch?{urllib.parse.urlencode(params)}"
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=3.5) as res:
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

# 3. 楽天レシピAPI (自炊との比較提案)
def fetch_rakuten_recipes(keyword):
    if not RAKUTEN_APP_ID or not keyword: return []
    clean_kw = re.sub(r'[^a-zA-Z0-9\u3040-\u309F\u30A0-\u30FA\u4E00-\u9FFF]', ' ', keyword).strip()
    first_word = clean_kw.split()[0] if clean_kw else "簡単"
    if first_word in RECIPE_CACHE: return RECIPE_CACHE[first_word]

    url = f"https://app.rakuten.co.jp/services/api/Recipe/CategoryRanking/20170426?applicationId={RAKUTEN_APP_ID}"
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=3.0) as res:
            d = json.loads(res.read().decode('utf-8'))
            recipes = []
            for r in d.get("result", [])[:3]:
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

# 4. ホットペッパー API
def fetch_shops(keyword="", area="", lat=None, lng=None, smoking=False, private_room=False, free_drink=False, midnight=False, pref_fish=False, pref_meat=False, pref_spicy=False):
    cache_key = f"{keyword}_{area}_{lat}_{lng}_{smoking}_{private_room}_{free_drink}_{midnight}_{pref_fish}_{pref_meat}_{pref_spicy}"
    if cache_key in SEARCH_CACHE: return SEARCH_CACHE[cache_key]

    params = {"key": HOTPEPPER_API_KEY, "count": 20, "format": "json"}
    if private_room: params["private_room"] = 1
    if free_drink: params["free_drink"] = 1
    if midnight: params["midnight"] = 1
    parts = [p for p in [area, keyword] if p]
    if smoking and "喫煙" not in " ".join(parts): parts.append("喫煙")
    if pref_fish: parts.append("肉 居酒屋")
    if pref_meat: parts.append("焼肉 ステーキ 肉")
    if pref_spicy: parts.append("和食 カフェ うどん")
    if lat and lng:
        params.update({"lat": lat, "lng": lng, "range": 4})
        if parts: params["keyword"] = " ".join(parts)
    else: params["keyword"] = " ".join(parts) if parts else "居酒屋 グルメ"

    results = []
    try:
        url = f"https://webservice.recruit.co.jp/hotpepper/gourmet/v1/?{urllib.parse.urlencode(params)}"
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=4.5) as res:
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

    # Yahoo!ローカルサーチとの合体
    yahoo_list = fetch_yahoo_local(" ".join(parts), lat, lng)
    existing_names = {s["name"] for s in results}
    for ys in yahoo_list:
        if ys["name"] not in existing_names:
            results.append(ys)

    # Google Placesによる評価の並行付与
    enrich_shops_with_google_places(results)

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
    <link rel="preconnect" href="https://cyberjapandata.gsi.go.jp" crossorigin>
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
    </script>
    <style>
        :root {
            --bg: #f8fafc; --card: #ffffff; --border: #e2e8f0;
            --text: #1e293b; --muted: #64748b;
            --primary: #ff5252; --primary-light: #fff1f2;
            --yellow: #f59e0b; --green: #10b981; --blue: #3b82f6; --purple: #8b5cf6;
            --input: #ffffff; --tag: #f1f5f9; --shadow: 0 2px 10px rgba(15, 23, 42, 0.04);
        }
        [data-theme="dark"] {
            --bg: #0f172a; --card: #1e293b; --border: #334155;
            --text: #f8fafc; --muted: #94a3b8;
            --primary: #ff6b6b; --primary-light: #2c2125;
            --yellow: #fbbf24; --green: #34d399; --blue: #60a5fa; --purple: #a78bfa;
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
        #loading-overlay { position: fixed; top: 0; left: 0; width: 100vw; height: 100vh; background: rgba(0,0,0,0.7); display: none; justify-content: center; align-items: center; flex-direction: column; z-index: 99999; }
        .spinner { width: 36px; height: 36px; border: 4px solid rgba(255,255,255,0.2); border-top-color: #fff; border-radius: 50%; animation: spin .8s linear infinite; margin-bottom: 12px; }
        @keyframes spin { 100% { transform: rotate(360deg); } }
        [data-theme="light"] .leaflet-tile-pane { filter: contrast(1.06) saturate(1.12); }
        [data-theme="dark"] .leaflet-tile-pane { filter: brightness(0.6) invert(1) contrast(3) hue-rotate(200deg) saturate(0.3) brightness(0.7); }
    </style>
</head>
<body>
    <div id="loading-overlay"><div class="spinner"></div><div style="color:#fff; font-size:13px; font-weight:800;">店舗と評価データを取得中...</div></div>
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
        <div class="input-group"><input type="text" name="keyword" id="kw-in" maxlength="40" placeholder="🔍 キーワード (例: 個室, 焼鳥)"></div>
        
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

        <button type="submit" class="btn-block btn-primary" onclick="doVibrate(40)">条件でお店を探す</button>
    </form>
</div>
<div class="credit" style="font-size:11px; text-align:center; color:var(--muted); margin-top:8px;">
    Powered by ホットペッパー Webサービス, Google Places & Yahoo!ローカルサーチ
</div>
</div>
<script>
    function showLoad(){ document.getElementById('loading-overlay').style.display='flex'; }
    function quick(k){ document.getElementById('kw-in').value=k; doVibrate(40); showLoad(); document.getElementById('s-form').submit(); }
    function toggleChip(el, targetId){ doVibrate(25); const cb = document.getElementById(targetId); cb.checked = !cb.checked; if(cb.checked) el.classList.add('active'); else el.classList.remove('active'); }
</script>
"""

# --- 検索結果・店舗シート画面 ---
RESULT_CONTENT = """
<div id="view-list" class="max-w">
    <div class="top-bar">
        <a href="/" class="btn-sm">← 戻る</a>
        <div style="font-size:13px; font-weight:800; color:var(--muted);">{{ search_title }} ({{ shops|length }}件)</div>
    </div>

    <!-- 楽天レシピ：自炊との比較カード -->
    {% if recipes %}
    <div class="card" style="background:linear-gradient(135deg, #fff7ed, #ffedd5); border-color:#fed7aa; margin-bottom:12px;">
        <div style="font-size:12px; font-weight:900; color:#c2410c; margin-bottom:6px;">🍳 自炊するなら？ 人気レシピと比較 (楽天レシピ)</div>
        <div style="display:flex; gap:8px; overflow-x:auto; padding-bottom:4px;">
            {% for r in recipes %}
            <div style="flex:0 0 140px; background:#fff; border-radius:10px; padding:6px; border:1px solid #fed7aa; font-size:11px;">
                <img src="{{ r.photo }}" style="width:100%; height:75px; object-fit:cover; border-radius:6px; margin-bottom:4px;">
                <div style="font-weight:800; height:30px; overflow:hidden; line-height:1.2;">{{ r.title }}</div>
                <div style="color:var(--muted); font-size:9.5px; margin-top:2px;">💰 {{ r.cost }} / ⏱️ {{ r.time }}</div>
            </div>
            {% endfor %}
        </div>
    </div>
    {% endif %}

    <!-- 日本語高精細マップ (OSM-JP) -->
    <div style="position:relative; margin-bottom:12px;">
        <div id="map-preview" style="height:220px; width:100%; border-radius:14px; border:1.5px solid var(--border); box-shadow:var(--shadow);"></div>
    </div>

    <div id="shops-list">
        {% for s in shops %}
        <div class="card shop-card">
            {% if s.photo %}
            <img src="{{ s.photo }}" style="width:100%; height:150px; object-fit:cover; border-radius:12px; margin-bottom:10px; background:#222; cursor:pointer;" loading="lazy" onclick='openShopDetail({{ s | tojson }})'>
            {% endif %}
            
            <h3 class="shop-name" style="font-size:15px; font-weight:900; margin:0 0 4px 0; line-height:1.3; cursor:pointer;" onclick='openShopDetail({{ s | tojson }})'>
                <span style="background:var(--primary); color:#fff; font-size:11px; padding:2px 6px; border-radius:6px; margin-right:4px;">{{ loop.index }}</span>{{ s.name }}
            </h3>

            {% if s.catch %}
            <div style="font-size:11px; font-weight:700; color:var(--muted); margin-bottom:6px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;">✨ {{ s.catch }}</div>
            {% endif %}
            
            <div style="display:flex; flex-wrap:wrap; gap:4px; margin-bottom:6px;">
                {% if s.google_rating %}
                <span class="badge" style="background:#fef3c7; color:#92400e; font-weight:900; border:1px solid #fde68a;">⭐ Google {{ s.google_rating }} ({{ s.google_reviews_count }}件)</span>
                {% endif %}
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
                <button class="btn-sm btn-primary" style="justify-content:center; padding:10px 0; font-weight:900;" onclick='openShopDetail({{ s | tojson }})'>🔍 店舗詳細シート</button>
                <a href="tel:{{ s.tel }}" class="btn-sm btn-sub" style="justify-content:center; padding:10px 0; font-weight:900; color:var(--green); border-color:var(--green);">📞 電話予約</a>
            </div>
        </div>
        {% endfor %}
    </div>
</div>

<!-- アプリ内完結：店舗詳細モーダルシート -->
<div id="detail-modal" style="display:none; position:fixed; top:0; left:0; width:100vw; height:100vh; background:rgba(0,0,0,0.75); z-index:99999; justify-content:flex-end; align-items:center; padding:14px; flex-direction:column;">
    <div class="card" style="width:100%; max-width:440px; max-height:88vh; display:flex; flex-direction:column; margin:0; background:var(--card); padding:16px;">
        <div style="display:flex; justify-content:space-between; align-items:flex-start; margin-bottom:8px;">
            <div style="font-size:16px; font-weight:900; line-height:1.3; flex:1;" id="dt-name">店舗詳細</div>
            <button onclick="closeShopDetail()" style="background:none; border:none; font-size:20px; cursor:pointer; color:var(--text); padding-left:10px;">✕</button>
        </div>
        
        <div style="overflow-y:auto; flex:1;">
            <img id="dt-photo" src="" style="width:100%; height:190px; object-fit:cover; border-radius:12px; margin-bottom:10px; background:#222; display:none;">
            <div id="dt-catch" style="font-size:12px; font-weight:800; color:var(--primary); margin-bottom:10px; line-height:1.5;"></div>
            
            <div style="font-size:12px; line-height:1.8; background:var(--tag); padding:14px; border-radius:14px; margin-bottom:12px;">
                <div style="margin-bottom:6px;"><b>⭐ Google星評価:</b> <span id="dt-google" style="color:#d97706; font-weight:900;">--</span></div>
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
            <a href="#" id="dt-tel-btn" class="btn-block btn-primary" style="margin:0; min-height:44px; font-size:13px; justify-content:center; background:var(--green);">📞 電話予約</a>
            <button onclick="closeShopDetail()" class="btn-block btn-sub" style="margin:0; min-height:44px; font-size:13px;">閉じる</button>
        </div>
    </div>
</div>

<script>
    let shops = {{ shops | tojson | safe }};
    const lat = (shops.length>0 && shops[0].lat) ? shops[0].lat : 34.8290;
    const lng = (shops.length>0 && shops[0].lng) ? shops[0].lng : 134.6900;
    
    // OSM-JP 高精細マップ初期化
    window.addEventListener('DOMContentLoaded', () => {
        const map = L.map('map-preview', {zoomControl:false}).setView([lat, lng], 15);
        L.tileLayer('https://tile.openstreetmap.jp/{z}/{x}/{y}.png', {
            maxZoom: 19,
            attribution: '&copy; OpenStreetMap contributors'
        }).addTo(map);

        const bounds = [];
        shops.forEach((s, i) => {
            if(s.lat && s.lng){
                bounds.push([s.lat, s.lng]);
                const icon = L.divIcon({
                    className:'',
                    html:`<div style="background:var(--primary); color:#fff; border-radius:50%; border:2px solid #fff; box-shadow:0 2px 4px rgba(0,0,0,0.3); font-size:11px; font-weight:900; display:flex; align-items:center; justify-content:center; width:24px; height:24px;">${i+1}</div>`,
                    iconSize:[24,24], iconAnchor:[12,12]
                });
                const m = L.marker([s.lat, s.lng], {icon}).addTo(map);
                m.on('click', () => openShopDetail(s));
            }
        });
        if(bounds.length > 0) map.fitBounds(bounds, {padding:[15,15]});
    });

    function openShopDetail(s) {
        doVibrate(30);
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
        document.getElementById('dt-tel-btn').href = `tel:${s.tel}`;
        document.getElementById('detail-modal').style.display = 'flex';
    }

    function closeShopDetail() {
        document.getElementById('detail-modal').style.display = 'none';
    }
</script>
"""

# ================= 5. ルーティング =================
@app.route('/')
def home(): return render_page(HOME_CONTENT)

@app.route('/search')
def search():
    k = html.escape(request.args.get('keyword', '')[:40])
    a = html.escape(request.args.get('area', '')[:40])
    smoking = request.args.get('smoking') == '1'
    private_room = request.args.get('private_room') == '1'
    free_drink = request.args.get('free_drink') == '1'
    midnight = request.args.get('midnight') == '1'

    shops = fetch_shops(keyword=k, area=a, smoking=smoking, private_room=private_room, free_drink=free_drink, midnight=midnight)
    recipes = fetch_rakuten_recipes(k or a or "肉")
    
    title = f"{a} {k}".strip() or "おすすめ店舗"
    content = render_template_string(RESULT_CONTENT, shops=shops, search_title=title, recipes=recipes)
    return render_page(content)

@app.route('/ping')
def ping(): return "OK", 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
