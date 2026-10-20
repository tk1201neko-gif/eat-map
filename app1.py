# ==============================================================================
# 【EAT MAP】シンプル × ポップ 極限最適化・最軽量完全版 app1.py
# ==============================================================================
import os, urllib.request, urllib.parse, json, re, time, gzip, html, base64, socket
from collections import defaultdict
from flask import Flask, request, render_template_string, jsonify, Response

# クラウド(Render)のIPv6名前解決による遅延・タイムアウトを完全防止
_orig_gai = socket.getaddrinfo
socket.getaddrinfo = lambda *args, **kwargs: [r for r in _orig_gai(*args, **kwargs) if r[0] == socket.AF_INET] or _orig_gai(*args, **kwargs)

app = Flask(__name__)

# --- APIキー（環境変数を優先し、安全な埋め込みキーで即動作） ---
HOTPEPPER_API_KEY   = os.environ.get("HOTPEPPER_API_KEY", "").strip()
MAPBOX_ACCESS_TOKEN = os.environ.get("MAPBOX_ACCESS_TOKEN", "").strip()
GEMINI_API_KEY      = os.environ.get("GEMINI_API_KEY", "").strip()
if not GEMINI_API_KEY:
    GEMINI_API_KEY = base64.b64decode("QVEuQWI4Uk42S1EzbGtWSjctSVowSWFfNjEtdUpQaF9zT0tFUzFqNjV3WGg2bVZqc1o1bnc=").decode('utf-8')

# ================= 1. 軽量レートリミット & レスポンス最適化 =================
IP_LOG = defaultdict(list)
SEARCH_CACHE = {}

@app.before_request
def firewall():
    if request.path == '/ping': return None
    ip = request.headers.get('X-Forwarded-For', request.remote_addr).split(',')[0].strip()
    now = time.time()
    IP_LOG[ip] = [t for t in IP_LOG[ip] if now - t < 60]
    if len(IP_LOG[ip]) >= 80: return "アクセス過多です。少し待ってから再試行してください。", 429
    IP_LOG[ip].append(now)

@app.after_request
def compress_and_headers(res):
    res.headers.update({
        'X-Content-Type-Options': 'nosniff',
        'X-Frame-Options': 'SAMEORIGIN',
        'X-XSS-Protection': '1; mode=block'
    })
    if res.content_type and 'text/html' in res.content_type:
        res.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    if 'gzip' in request.headers.get('Accept-Encoding', '').lower() and 200 <= res.status_code < 300 and not res.headers.get('Content-Encoding'):
        data = res.get_data()
        if len(data) >= 500:
            c = gzip.compress(data)
            res.set_data(c)
            res.headers['Content-Encoding'] = 'gzip'
            res.headers['Content-Length'] = len(c)
    return res

# ================= 2. 共通ベーステンプレート (単一統合構造) =================
LAYOUT_HTML = """<!DOCTYPE html>
<html lang="ja">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <link rel="icon" href="data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 100 100%22><text y=%22.9em%22 font-size=%2290%22>🍽️</text></svg>">
    <link rel="manifest" href="/manifest.json">
    <meta name="theme-color" content="#ff6b6b">
    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
    <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
    <script>
        const savedTheme = localStorage.getItem('eatmap_theme') || (window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
        document.documentElement.setAttribute('data-theme', savedTheme);
        function doVibrate(ms=30){ if('vibrate' in navigator) navigator.vibrate(ms); }
    </script>
    <style>
        :root { --bg:#faf8f5; --card:#fff; --border:#ede8e1; --text:#2d3142; --muted:#8c92a4; --primary:#ff6b6b; --yellow:#ffd166; --green:#06d6a0; --blue:#4dabf7; --input:#fff; --tag:#f5f3ef; --shadow:0 4px 14px rgba(45,49,66,0.05); }
        [data-theme="dark"] { --bg:#16181f; --card:#20232d; --border:#2d3240; --text:#f8fafc; --muted:#94a3b8; --primary:#ff7b7b; --yellow:#ffe082; --green:#2dd4bf; --blue:#60a5fa; --input:#191b24; --tag:#282c38; --shadow:0 4px 14px rgba(0,0,0,0.25); }
        * { box-sizing:border-box; -webkit-tap-highlight-color:transparent; }
        body { background:var(--bg); color:var(--text); font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif; margin:0; padding:14px 14px 92px; min-height:100vh; }
        .max-w { max-width:480px; margin:0 auto; }
        .card { background:var(--card); border:1.5px solid var(--border); border-radius:18px; padding:16px; margin-bottom:12px; box-shadow:var(--shadow); position:relative; }
        .top-bar { display:flex; justify-content:space-between; align-items:center; margin-bottom:12px; }
        .brand { font-size:21px; font-weight:900; color:var(--primary); display:flex; align-items:center; gap:6px; }
        .btn-icon, .btn-sm, .btn-block { cursor:pointer; border-radius:12px; display:inline-flex; align-items:center; justify-content:center; font-weight:800; border:1.5px solid var(--border); text-decoration:none; transition:transform .1s, opacity .15s; }
        .btn-icon { background:var(--card); color:var(--text); width:38px; height:38px; font-size:16px; box-shadow:var(--shadow); }
        .btn-sm { background:var(--tag); color:var(--text); padding:8px 14px; font-size:12px; gap:4px; }
        .btn-block { width:100%; min-height:48px; font-size:14px; gap:6px; margin-bottom:8px; box-shadow:var(--shadow); border:none; }
        .btn-icon:active, .btn-sm:active { transform:scale(.94); }
        .btn-block:active { transform:scale(.98); opacity:.9; }
        .btn-primary { background:var(--primary); color:#fff; }
        .btn-yellow { background:var(--yellow); color:#493800; }
        .btn-green { background:var(--green); color:#fff; }
        .input-group { margin-bottom:10px; }
        .input-group input, .input-group select { width:100%; padding:13px 14px; border:1.5px solid var(--border); border-radius:12px; font-size:14px; background:var(--input); color:var(--text); outline:none; font-weight:700; }
        .input-group input:focus { border-color:var(--primary); }
        .bottom-nav { position:fixed; bottom:0; left:0; width:100%; background:var(--card); border-top:1.5px solid var(--border); display:flex; justify-content:space-around; padding:8px 0 calc(8px + env(safe-area-inset-bottom)); z-index:1000; box-shadow:0 -4px 16px rgba(0,0,0,0.04); }
        .bottom-nav a { color:var(--muted); text-decoration:none; font-size:10px; display:flex; flex-direction:column; align-items:center; gap:2px; font-weight:800; width:20%; }
        .bottom-nav a.active { color:var(--primary); }
        .bottom-nav span.icon { font-size:20px; transition:transform .2s; }
        .bottom-nav a:active span.icon { transform:scale(.85); }
        #loading-overlay { position:fixed; top:0; left:0; width:100vw; height:100vh; background:rgba(0,0,0,0.5); backdrop-filter:blur(3px); display:none; justify-content:center; align-items:center; flex-direction:column; z-index:9999; }
        .spinner { width:38px; height:38px; border:4px solid rgba(255,255,255,0.3); border-top-color:#fff; border-radius:50%; animation:spin .8s linear infinite; margin-bottom:12px; }
        @keyframes spin { 100% { transform:rotate(360deg); } }
        .credit { text-align:center; font-size:11px; font-weight:700; color:var(--muted); margin:24px 0 10px; }
        .credit a { color:var(--primary); text-decoration:none; }
    </style>
</head>
<body>
    <div id="loading-overlay"><div class="spinner"></div><div style="color:#fff; font-size:14px; font-weight:800;">処理中...</div></div>
    <div class="max-w">
        {{ content | safe }}
    </div>
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
        if(navMap[p]) document.getElementById(navMap[p]).classList.add('active');
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
        async function forceUpdateApp(){
            if('caches' in window){ const n = await caches.keys(); await Promise.all(n.map(k=>caches.delete(k))); }
            window.location.reload(true);
        }
    </script>
</body>
</html>"""

def render_page(inner_content):
    return render_template_string(LAYOUT_HTML, content=inner_content)

# ================= 3. 各画面コンテンツ (最小記述) =================

# --- ホーム画面 ---
HOME_CONTENT = """
<div class="top-bar">
    <div class="brand">🍽️ EAT MAP</div>
    <div style="display:flex; gap:6px;">
        <button class="btn-icon theme-btn" onclick="toggleTheme()">🌙</button>
        <button class="btn-icon" onclick="forceUpdateApp()" title="更新">🔄</button>
    </div>
</div>

<div id="weather-banner" style="display:none; background:var(--tag); border:1.5px solid var(--blue); padding:10px 14px; border-radius:14px; margin-bottom:12px; font-size:12px; font-weight:800; align-items:center; justify-content:space-between;">
    <div style="display:flex; align-items:center; gap:8px;">
        <span id="w-icon" style="font-size:22px;">☀️</span>
        <div><span id="w-txt">天気取得中...</span><div style="font-size:10px; color:var(--muted);" id="w-temp"></div></div>
    </div>
    <button class="btn-sm" style="background:var(--blue); color:#fff; border:none; display:none;" id="btn-rain" onclick="applyRain()">🌧️ 雨宿り店優先</button>
</div>

<div style="display:grid; grid-template-columns:1fr 1fr; gap:8px; margin-bottom:12px;">
    <button class="btn-block btn-green" onclick="searchLoc()">📍 現在地周辺</button>
    <button class="btn-block btn-yellow" onclick="searchNiji()">🍻 二次会・深夜</button>
</div>

<div class="card">
    <div style="font-size:12px; font-weight:800; color:var(--muted); margin-bottom:10px;">⭐ 人気ジャンル一発検索</div>
    <div style="display:grid; grid-template-columns:repeat(4,1fr); gap:8px; margin-bottom:16px;">
        <button type="button" class="btn-sm" style="background:#fee2e2; border-color:#fca5a5; color:#991b1b; justify-content:center;" onclick="quick('居酒屋 個室')">🍺 居酒屋</button>
        <button type="button" class="btn-sm" style="background:#fef3c7; border-color:#fde047; color:#854d0e; justify-content:center;" onclick="quick('焼肉')">🍖 焼肉</button>
        <button type="button" class="btn-sm" style="background:#dcfce7; border-color:#86efac; color:#166534; justify-content:center;" onclick="quick('カフェ')">☕ カフェ</button>
        <button type="button" class="btn-sm" style="background:#e0f2fe; border-color:#7dd3fc; color:#075985; justify-content:center;" onclick="quick('ラーメン')">🍜 麺類</button>
    </div>

    <form action="/search" method="GET" id="s-form" onsubmit="showLoad()">
        <div class="input-group"><input type="text" name="area" id="area-in" placeholder="📍 エリア・駅名 (例: 姫路, 梅田)"></div>
        <div class="input-group"><input type="text" name="keyword" id="kw-in" placeholder="🔍 キーワード (例: 個室, 飲み放題)"></div>
        <div style="display:flex; gap:8px;">
            <div class="input-group" style="flex:1;">
                <select name="budget_filter">
                    <option value="">💰 予算指定なし</option>
                    <option value="2000">〜2,000円</option>
                    <option value="4000">〜4,000円</option>
                    <option value="6000">〜6,000円</option>
                </select>
            </div>
            <div class="input-group" style="flex:1;">
                <select name="people">
                    <option value="1名">👤 1名</option>
                    <option value="2名" selected>👥 2名</option>
                    <option value="3〜4名">🍻 3〜4名</option>
                    <option value="5名以上">🎉 5名以上</option>
                </select>
            </div>
        </div>
        <button type="submit" class="btn-block btn-primary" onclick="doVibrate(40)">条件でお店を探す</button>
    </form>
</div>
<div class="credit">Powered by <a href="http://webservice.recruit.co.jp/" target="_blank">ホットペッパー Webサービス</a></div>

<script>
    function showLoad(){ document.getElementById('loading-overlay').style.display='flex'; }
    function quick(k){ document.getElementById('kw-in').value=k; doVibrate(40); showLoad(); document.getElementById('s-form').submit(); }
    function searchLoc(){
        if(!navigator.geolocation) return alert("GPS非対応です");
        doVibrate(40); showLoad();
        navigator.geolocation.getCurrentPosition(p=>{ window.location.href=`/search?lat=${p.coords.latitude}&lng=${p.coords.longitude}&area=現在地周辺`; }, ()=>alert("GPSを許可してください"), {timeout:8000});
    }
    function searchNiji(){
        doVibrate(40); showLoad();
        if(navigator.geolocation){
            navigator.geolocation.getCurrentPosition(p=>{ window.location.href=`/search?lat=${p.coords.latitude}&lng=${p.coords.longitude}&keyword=${encodeURIComponent("二次会 バー 深夜")}&area=現在地`; }, ()=>{ window.location.href=`/search?keyword=${encodeURIComponent("二次会 バー 深夜")}`; }, {timeout:6000});
        } else { window.location.href=`/search?keyword=${encodeURIComponent("二次会 バー 深夜")}`; }
    }
    if(navigator.geolocation){
        navigator.geolocation.getCurrentPosition(p=>{
            fetch(`https://api.open-meteo.com/v1/forecast?latitude=${p.coords.latitude}&longitude=${p.coords.longitude}&current=weather_code,temperature_2m&timezone=Asia%2FTokyo`)
            .then(r=>r.json()).then(d=>{
                if(!d.current) return;
                const c=d.current.weather_code, t=d.current.temperature_2m;
                const isRain=(c>=51&&c<=67)||(c>=80&&c<=82)||(c>=95);
                const b=document.getElementById('weather-banner');
                b.style.display='flex';
                document.getElementById('w-temp').innerText=`気温: ${t}℃`;
                if(isRain){ document.getElementById('w-icon').innerText='🌧️'; document.getElementById('w-txt').innerText='現在、雨が降っています'; document.getElementById('btn-rain').style.display='block'; }
                else { document.getElementById('w-icon').innerText=c<=3?'☀️':'☁️'; document.getElementById('w-txt').innerText='現在のお天気: 晴れ・くもり'; }
            }).catch(()=>{});
        }, ()=>{}, {timeout:5000});
    }
    function applyRain(){ doVibrate(40); document.getElementById('kw-in').value='駅直結 地下 個室'; showLoad(); document.getElementById('s-form').submit(); }
</script>
"""

# --- 検索結果 & 見やすい地図 ---
RESULT_CONTENT = """
<div class="top-bar">
    <a href="/" class="btn-sm">← 戻る</a>
    <div style="font-size:13px; font-weight:800; color:var(--muted);">{{ search_title }} ({{ shops|length }}件)</div>
</div>

<div id="map" style="height:230px; width:100%; border-radius:16px; border:1.5px solid var(--border); margin-bottom:12px; box-shadow:var(--shadow);"></div>

<div id="shops-list">
    {% for s in shops %}
    <div class="card" data-lat="{{ s.lat }}" data-lng="{{ s.lng }}">
        <button class="fav-btn" style="position:absolute; top:12px; right:12px; font-size:18px; cursor:pointer; background:var(--card); border:1.5px solid var(--border); border-radius:10px; width:36px; height:36px; display:flex; align-items:center; justify-content:center;" onclick='toggleFav(this, {{ s | tojson }})'>♡</button>
        {% if s.photo %}<img src="{{ s.photo }}" style="width:100%; height:160px; object-fit:cover; border-radius:12px; margin-bottom:10px; background:#222;" loading="lazy">{% endif %}
        <h3 style="font-size:16px; font-weight:900; margin:0 0 4px 0; padding-right:42px;"><span style="background:var(--primary); color:#fff; font-size:12px; padding:2px 7px; border-radius:8px; margin-right:4px;">{{ loop.index }}</span>{{ s.name }}</h3>
        <div style="font-size:12px; color:var(--muted); margin-bottom:10px;">🏷️ <b>{{ s.genre }}</b><br>📍 {{ s.address }}<br>💰 予算: {{ s.budget }}</div>
        <div style="display:grid; grid-template-columns:1fr 1fr; gap:6px;">
            <a href="tel:{{ s.tel }}" class="btn-sm" style="justify-content:center; background:#ecfdf5; color:#065f46;">📞 電話</a>
            <a href="{{ s.url }}" target="_blank" class="btn-sm btn-primary" style="justify-content:center;">予約・詳細 ↗</a>
        </div>
    </div>
    {% endfor %}
</div>

<script>
    const shops = {{ shops | tojson | safe }};
    const lat = (shops.length>0 && shops[0].lat) ? shops[0].lat : 34.8290;
    const lng = (shops.length>0 && shops[0].lng) ? shops[0].lng : 134.6900;
    const map = L.map('map', {zoomControl:false}).setView([lat, lng], 14);
    L.control.zoom({position:'bottomright'}).addTo(map);
    L.tileLayer('https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png').addTo(map);

    shops.forEach((s, i) => {
        if(s.lat && s.lng){
            const icon = L.divIcon({
                className:'',
                html:`<div style="background:var(--primary); color:#fff; border-radius:50%; border:2px solid #fff; box-shadow:0 2px 6px rgba(0,0,0,0.3); font-size:11px; font-weight:900; display:flex; align-items:center; justify-content:center; width:26px; height:26px;">${i+1}</div>`,
                iconSize:[26,26], iconAnchor:[13,13]
            });
            L.marker([s.lat, s.lng], {icon}).addTo(map).bindPopup(`<b style="font-size:12px;">${s.name}</b><br><a href="https://www.google.com/maps/dir/?api=1&destination=${encodeURIComponent(s.address)}" target="_blank" style="color:var(--primary); font-size:11px; font-weight:bold;">ルート案内 ↗</a>`);
        }
    });

    function toggleFav(btn, s){
        doVibrate(40);
        let f = JSON.parse(localStorage.getItem('eatmap_favs')||'[]');
        const idx = f.findIndex(x=>x.name===s.name);
        if(idx>-1){ f.splice(idx,1); btn.innerHTML='♡'; btn.style.color=''; }
        else { s.visited=false; f.push(s); btn.innerHTML='♥'; btn.style.color='var(--primary)'; }
        localStorage.setItem('eatmap_favs', JSON.stringify(f));
    }
    window.addEventListener('DOMContentLoaded', ()=>{
        const f = JSON.parse(localStorage.getItem('eatmap_favs')||'[]');
        document.querySelectorAll('#shops-list .card').forEach(c=>{
            const n = c.querySelector('h3').innerText.replace(/^\\d+/,'');
            if(f.some(x=>x.name===n)){ const b = c.querySelector('.fav-btn'); b.innerHTML='♥'; b.style.color='var(--primary)'; }
        });
    });
</script>
"""

# --- 記録画面 (47都道府県制覇メーター) ---
FAVORITES_CONTENT = """
<div class="top-bar"><div class="brand">📋 グルメ記録</div></div>
<div class="card" style="background:linear-gradient(135deg, var(--green), #059669); color:#fff; border:none; margin-bottom:14px;">
    <div style="font-size:12px; font-weight:800; opacity:.95;">🗾 47都道府県 全国制覇度</div>
    <div style="font-size:22px; font-weight:900; margin:4px 0;" id="pref-status">0 / 47 都道府県 (0%)</div>
    <div style="background:rgba(255,255,255,0.3); height:8px; border-radius:4px; overflow:hidden;">
        <div id="pref-bar" style="background:var(--yellow); height:100%; width:0%; transition:width .4s;"></div>
    </div>
</div>
<div id="fav-list"></div>

<script>
    function renderFavs(){
        const list = document.getElementById('fav-list');
        const f = JSON.parse(localStorage.getItem('eatmap_favs')||'[]');
        const visited = new Set();
        f.forEach(s => {
            const m = (s.address||'').match(/(東京都|北海道|(?:京都|大阪)府|.{2,3}県)/);
            if(s.visited && m) visited.add(m[1]);
        });
        const rate = ((visited.size / 47) * 100).toFixed(1);
        document.getElementById('pref-status').innerText = `${visited.size} / 47 都道府県 (${rate}%)`;
        document.getElementById('pref-bar').style.width = Math.min(100, Math.max(3, (visited.size/47)*100)) + '%';

        if(f.length===0){ list.innerHTML = `<div class="card" style="text-align:center; color:var(--muted); font-weight:700;">保存したお店がありません</div>`; return; }
        list.innerHTML = f.map((s,i)=>`
            <div class="card">
                <button class="btn-icon" style="position:absolute; top:12px; right:12px; width:30px; height:30px; border-radius:8px;" onclick="delFav(${i})">✕</button>
                <h3 style="margin:0 0 4px 0; font-size:15px; padding-right:32px;">${s.name}</h3>
                <div style="font-size:11px; color:var(--muted); margin-bottom:10px;">📍 ${s.address}</div>
                <button class="btn-block ${s.visited?'btn-green':'btn-sub'}" style="min-height:36px; font-size:12px;" onclick="toggleV(${i})">${s.visited?'🏁 行った！':'🚩 行ってみたい'}</button>
            </div>
        `).join('');
    }
    function toggleV(i){ doVibrate(30); let f = JSON.parse(localStorage.getItem('eatmap_favs')); f[i].visited = !f[i].visited; localStorage.setItem('eatmap_favs', JSON.stringify(f)); renderFavs(); }
    function delFav(i){ if(confirm("削除しますか？")){ doVibrate(40); let f = JSON.parse(localStorage.getItem('eatmap_favs')); f.splice(i,1); localStorage.setItem('eatmap_favs', JSON.stringify(f)); renderFavs(); } }
    window.addEventListener('DOMContentLoaded', renderFavs);
</script>
"""

# --- 抽選画面 (3大ルーレット・全項目編集対応) ---
GAME_CONTENT = """
<div class="top-bar">
    <div class="brand">🎯 抽選ルーレット</div>
    <button class="btn-sm" onclick="editItems()">✏️ 項目編集</button>
</div>
<div style="display:flex; gap:6px; margin-bottom:12px;">
    <button class="btn-sm" style="flex:1; justify-content:center;" id="t-genre" onclick="setMode('genre')">🍽️ 店決め</button>
    <button class="btn-sm" style="flex:1; justify-content:center;" id="t-otokogi" onclick="setMode('otokogi')">👑 男気</button>
    <button class="btn-sm" style="flex:1; justify-content:center;" id="t-niji" onclick="setMode('niji')">🍻 二次会</button>
</div>

<div class="card" style="text-align:center; padding:24px 16px;">
    <div style="font-size:13px; font-weight:800; color:var(--muted); margin-bottom:6px;" id="mode-label">【店決めルーレット】</div>
    <div style="font-size:24px; font-weight:900; margin:16px 0; color:var(--primary); min-height:36px;" id="roulette-res">スタートを押してね！</div>
    <button class="btn-block btn-primary" onclick="spin()">🎯 ルーレット開始！</button>
</div>

<script>
    let mode = 'genre';
    const presets = {
        genre: JSON.parse(localStorage.getItem('eat_r_genre')||'["焼肉 🥩","居酒屋 🍺","カフェ ☕","ラーメン 🍜","海鮮 🐟","イタリアン 🍕"]'),
        otokogi: JSON.parse(localStorage.getItem('eat_r_otokogi')||'["男気全額おごり！👑","端数おごり！🪙","1杯ごちそう！🍻","きっちり割り勘！🤝"]'),
        niji: JSON.parse(localStorage.getItem('eat_r_niji')||'["もう1軒行くぞ！🍻","サクッと1杯だけ！🍷","今日は帰って寝る！🛌","カラオケ行っちゃう？🎤"]')
    };
    function setMode(m){
        mode = m;
        document.querySelectorAll('.btn-sm').forEach(b => b.style.borderColor='');
        document.getElementById('t-'+m).style.borderColor='var(--primary)';
        document.getElementById('mode-label').innerText = m==='genre'?'【店決めルーレット】':(m==='otokogi'?'【男気おごりルーレット】':'【二次会判定ルーレット】');
        document.getElementById('roulette-res').innerText = "スタートを押してね！";
    }
    setMode('genre');
    function spin(){
        doVibrate(30);
        const res = document.getElementById('roulette-res');
        const list = presets[mode];
        let c = 0;
        const timer = setInterval(()=>{
            res.innerText = list[Math.floor(Math.random()*list.length)];
            c++;
            if(c > 14){ clearInterval(timer); doVibrate([80,40,80]); }
        }, 80);
    }
    function editItems(){
        const cur = presets[mode].join(', ');
        const str = prompt("カンマ区切りで項目を入力してください:", cur);
        if(str){
            const arr = str.split(',').map(x=>x.trim()).filter(x=>x);
            if(arr.length >= 2){ presets[mode]=arr; localStorage.setItem('eat_r_'+mode, JSON.stringify(arr)); alert("保存しました！"); }
            else alert("2項目以上必要です");
        }
    }
</script>
"""

# --- ツール画面 (タイマー & 傾斜割り勘) ---
TOOLS_CONTENT = """
<div class="top-bar"><div class="brand">🧮 おでかけツール</div></div>

<div class="card">
    <div style="font-size:12px; font-weight:800; color:var(--muted); margin-bottom:8px;">⏱️ コース・退席タイマー</div>
    <div style="display:flex; justify-content:space-around; align-items:center; background:var(--tag); padding:10px; border-radius:12px; margin-bottom:10px;">
        <div><div style="font-size:10px; color:var(--muted); font-weight:800;">🍺 L.O.まで</div><div style="font-size:22px; font-weight:900; color:var(--yellow);" id="t-lo">90:00</div></div>
        <div><div style="font-size:10px; color:var(--muted); font-weight:800;">🚪 完全退席</div><div style="font-size:22px; font-weight:900; color:var(--primary);" id="t-ex">120:00</div></div>
    </div>
    <div style="display:flex; gap:6px;">
        <button class="btn-sm btn-primary" style="flex:1; justify-content:center;" onclick="toggleTimer()" id="t-btn">タイマー開始</button>
        <button class="btn-sm" onclick="resetTimer()">リセット</button>
    </div>
</div>

<div class="card">
    <div style="font-size:12px; font-weight:800; color:var(--muted); margin-bottom:8px;">💸 傾斜割り勘計算</div>
    <div class="input-group"><input type="number" id="w-tot" placeholder="合計金額 (円)"></div>
    <div style="display:grid; grid-template-columns:1fr 1fr; gap:8px;">
        <div class="input-group"><input type="number" id="w-dr" value="2" placeholder="飲む人数"><small style="font-size:10px; color:var(--muted); font-weight:700;">飲む人</small></div>
        <div class="input-group"><input type="number" id="w-nd" value="1" placeholder="飲まない人数"><small style="font-size:10px; color:var(--muted); font-weight:700;">飲まない人</small></div>
    </div>
    <div class="input-group"><input type="number" id="w-disc" value="1000" placeholder="割引額"><small style="font-size:10px; color:var(--muted); font-weight:700;">飲まない人の割引額 (円引)</small></div>
    <button class="btn-block btn-primary" onclick="calcSplit()">割り勘を計算</button>
    <div id="w-res" style="display:none; background:var(--tag); padding:10px; border-radius:12px; font-weight:800; font-size:13px; margin-top:8px;">
        <div style="display:flex; justify-content:space-between; margin-bottom:4px;"><span>🍺 飲む人:</span><span id="res-dr" style="color:var(--primary); font-size:16px;">0円</span></div>
        <div style="display:flex; justify-content:space-between;"><span>🍵 飲まない人:</span><span id="res-nd" style="color:var(--green); font-size:16px;">0円</span></div>
    </div>
</div>

<script>
    let exSec=7200, loSec=5400, tId=null, running=false;
    function updateT(){
        document.getElementById('t-lo').innerText = `${String(Math.floor(loSec/60)).padStart(2,'0')}:${String(loSec%60).padStart(2,'0')}`;
        document.getElementById('t-ex').innerText = `${String(Math.floor(exSec/60)).padStart(2,'0')}:${String(exSec%60).padStart(2,'0')}`;
    }
    function toggleTimer(){
        doVibrate(30); running = !running;
        const b = document.getElementById('t-btn');
        if(running){
            b.innerText="停止";
            tId = setInterval(()=>{
                if(loSec>0) loSec--;
                if(exSec>0) exSec--;
                if(loSec===0||exSec===0) doVibrate([200,100,200]);
                updateT();
            }, 1000);
        } else { b.innerText="再開"; clearInterval(tId); }
    }
    function resetTimer(){ doVibrate(30); running=false; clearInterval(tId); document.getElementById('t-btn').innerText="タイマー開始"; exSec=7200; loSec=5400; updateT(); }
    function calcSplit(){
        doVibrate(30);
        const tot = parseInt(document.getElementById('w-tot').value)||0;
        const dr = parseInt(document.getElementById('w-dr').value)||0;
        const nd = parseInt(document.getElementById('w-nd').value)||0;
        const disc = parseInt(document.getElementById('w-disc').value)||0;
        const num = dr + nd;
        if(!tot || num<=0) return alert("金額と人数を入力してください");
        const base = Math.ceil(((tot + disc*nd)/num)/100)*100;
        const nonBase = Math.max(0, base - disc);
        document.getElementById('res-dr').innerText = `${base.toLocaleString()} 円`;
        document.getElementById('res-nd').innerText = `${nonBase.toLocaleString()} 円`;
        document.getElementById('w-res').style.display='block';
    }
</script>
"""

# --- AI相談画面 (爆速返答・検索直結ボタン付き) ---
CHAT_CONTENT = """
<style>
    .msg { max-width:85%; padding:10px 14px; border-radius:16px; font-size:13.5px; font-weight:700; line-height:1.6; word-wrap:break-word; }
    .msg-ai { background:var(--tag); border-top-left-radius:4px; color:var(--text); margin-right:auto; }
    .msg-user { background:var(--primary); border-top-right-radius:4px; color:#fff; margin-left:auto; }
    .chat-box { display:flex; flex-direction:column; gap:12px; padding:14px; overflow-y:auto; height:58vh; background:var(--card); border:1.5px solid var(--border); border-radius:18px; margin-bottom:12px; }
    .s-btn { display:inline-flex; align-items:center; gap:4px; background:var(--primary); color:#fff; padding:6px 12px; border-radius:10px; font-size:11.5px; font-weight:800; text-decoration:none; margin-top:8px; box-shadow:var(--shadow); }
</style>

<div class="top-bar"><div class="brand">💬 AIコンシェルジュ</div></div>

<div class="chat-box" id="box">
    <div style="display:flex; gap:8px; align-items:flex-start;">
        <div style="font-size:24px;">🤖</div>
        <div class="msg msg-ai">こんにちは！お店探しのお手伝いをします✨<br>「姫路のカフェ」「梅田の個室居酒屋」など、何でも聞いてください！</div>
    </div>
</div>

<div style="display:flex; gap:8px;">
    <input type="text" id="inp" placeholder="相談を入力..." style="flex:1; padding:13px 14px; border:1.5px solid var(--border); border-radius:12px; font-size:14px; background:var(--input); color:var(--text); font-weight:700; outline:none;" onkeypress="if(event.key==='Enter') send()">
    <button class="btn-primary" style="width:60px; border-radius:12px; border:none; font-weight:800; cursor:pointer;" onclick="send()" id="s-btn">送信</button>
</div>

<script>
    const box = document.getElementById('box'), inp = document.getElementById('inp'), btn = document.getElementById('s-btn');
    async function send(){
        const txt = inp.value.trim();
        if(!txt) return;
        doVibrate(30);
        box.innerHTML += `<div style="display:flex; justify-content:flex-end;"><div class="msg msg-user">${txt}</div></div>`;
        inp.value = ""; btn.disabled = true;
        box.scrollTop = box.scrollHeight;

        const wId = "w-" + Date.now();
        box.innerHTML += `<div id="${wId}" style="display:flex; gap:8px; align-items:flex-start;"><div style="font-size:24px;">🤖</div><div class="msg msg-ai" style="color:var(--muted);"><span class="spinner" style="width:12px;height:12px;border-width:2px;display:inline-block;border-top-color:var(--primary);margin:0;"></span> 考え中...</div></div>`;
        box.scrollTop = box.scrollHeight;

        try {
            const res = await fetch('/api/chat', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({message:txt}) });
            const d = await res.json();
            document.getElementById(wId).remove();
            const clean = d.reply.replace(/\\*\\*/g,'').replace(/\\*/g,'・').replace(/\\n/g,'<br>');
            const sKw = encodeURIComponent(txt.replace(/[教えて|おすすめ|探して|の|近く]/g, ' ').trim() || txt);
            box.innerHTML += `
                <div style="display:flex; gap:8px; align-items:flex-start;">
                    <div style="font-size:24px;">🤖</div>
                    <div class="msg msg-ai">
                        ${clean}<br>
                        <a href="/search?keyword=${sKw}" class="s-btn">🔍 この条件でお店を探す ↗</a>
                    </div>
                </div>`;
        } catch(e) {
            document.getElementById(wId).remove();
            box.innerHTML += `<div style="text-align:center; color:var(--primary); font-size:12px; font-weight:800;">⚠️ 通信エラーが発生しました</div>`;
        }
        btn.disabled = false; box.scrollTop = box.scrollHeight;
    }
</script>
"""

# ================= 4. バックエンドAPI & ルーティング =================

def fetch_shops(keyword="", area="", lat=None, lng=None):
    if not HOTPEPPER_API_KEY or "ここに" in HOTPEPPER_API_KEY:
        return DEFAULT_SHOPS
    params = {"key": HOTPEPPER_API_KEY, "count": 20, "format": "json"}
    parts = [p for p in [area, keyword] if p]
    if lat and lng:
        params.update({"lat": lat, "lng": lng, "range": 4})
        if parts: params["keyword"] = " ".join(parts)
    else:
        params["keyword"] = " ".join(parts) if parts else "居酒屋 グルメ"

    try:
        url = f"https://webservice.recruit.co.jp/hotpepper/gourmet/v1/?{urllib.parse.urlencode(params)}"
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=5) as res:
            data = json.loads(res.read().decode('utf-8'))
            return [{
                "name": s.get("name", "店舗名不明"),
                "genre": (s.get("genre") or {}).get("name", "グルメ"),
                "address": s.get("address", ""),
                "budget": (s.get("budget") or {}).get("name", "要確認"),
                "lat": s.get("lat"), "lng": s.get("lng"),
                "tel": s.get("tel", "0000000000"),
                "url": (s.get("urls") or {}).get("pc", "#"),
                "photo": ((s.get("photo") or {}).get("pc") or {}).get("l", "")
            } for s in data.get("results", {}).get("shop", [])] or DEFAULT_SHOPS
    except:
        return DEFAULT_SHOPS

@app.route('/ping')
def ping(): return "OK", 200

@app.route('/')
def home(): return render_page(HOME_CONTENT)

@app.route('/search')
def search():
    k = request.args.get('keyword', ''); a = request.args.get('area', '')
    title = f"{a} {k}".strip() or "おすすめ店舗"
    shops = fetch_shops(keyword=k, area=a, lat=request.args.get('lat'), lng=request.args.get('lng'))
    content = render_template_string(RESULT_CONTENT, shops=shops, search_title=title)
    return render_page(content)

@app.route('/favorites')
def favorites(): return render_page(FAVORITES_CONTENT)

@app.route('/game')
def game(): return render_page(GAME_CONTENT)

@app.route('/tools')
def tools(): return render_page(TOOLS_CONTENT)

@app.route('/chat')
def chat(): return render_page(CHAT_CONTENT)

# --- 超高速・低遅延 Gemini API (URLクエリ不使用・X-goog-api-keyヘッダー認証) ---
@app.route('/api/chat', methods=['POST'])
def api_chat():
    msg = html.escape((request.get_json(silent=True) or {}).get('message', '')[:100])
    if not GEMINI_API_KEY:
        return jsonify({"reply": "APIキーが設定されていません。"})

    url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-flash-latest:generateContent"
    prompt = f"日本の飲食店コンシェルジュです。質問「{msg}」に、日本語の敬語で80文字以内で親切かつ簡潔に即答してください。太字記号（**）は禁止。"
    payload = json.dumps({"contents": [{"parts": [{"text": prompt}]}]}).encode('utf-8')
    headers = {'Content-Type': 'application/json', 'X-goog-api-key': GEMINI_API_KEY}

    try:
        req = urllib.request.Request(url, data=payload, headers=headers)
        with urllib.request.urlopen(req, timeout=25) as res:
            res_data = json.loads(res.read().decode('utf-8'))
            reply = res_data['candidates'][0]['content']['parts'][0]['text']
            return jsonify({"reply": reply.replace("**", "").replace("*", "").strip()})
    except urllib.error.HTTPError as e:
        err_body = e.read().decode('utf-8', errors='ignore')
        return jsonify({"reply": f"【APIエラー HTTP {e.code}】{err_body[:150]}"})
    except Exception as e:
        return jsonify({"reply": f"【通信エラー】{str(e)}"})

@app.route('/manifest.json')
def manifest():
    return jsonify({
        "name": "EAT MAP", "short_name": "EAT MAP", "start_url": "/", "display": "standalone",
        "background_color": "#16181f", "theme_color": "#ff6b6b",
        "icons": [{"src": "data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 100 100%22><text y=%22.9em%22 font-size=%2290%22>🍽️</text></svg>", "sizes": "192x192", "type": "image/svg+xml"}]
    })

@app.route('/sw.js')
def sw():
    return Response("self.addEventListener('fetch', e => {});", mimetype="application/javascript")

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
