# ==============================================================================
# 【EAT MAP】完全日本語高精細マップ(OSM-JP) ＆ ダブルAI搭載 完全統合版 app1.py
# ==============================================================================
import os, urllib.request, urllib.parse, json, re, time, gzip, html, base64, socket, math
from collections import defaultdict
from flask import Flask, request, render_template_string, jsonify, Response

# IPv6遅延対策
_orig_gai = socket.getaddrinfo
socket.getaddrinfo = lambda *args, **kwargs: [r for r in _orig_gai(*args, **kwargs) if r[0] == socket.AF_INET] or _orig_gai(*args, **kwargs)

app = Flask(__name__)

# --- APIキーの設定 ---
HOTPEPPER_API_KEY = os.environ.get("HOTPEPPER_API_KEY", "").strip()
GROQ_API_KEY      = os.environ.get("GROQ_API_KEY", "").strip()

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()
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
    if len(IP_LOG[ip]) >= 100: 
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
        "connect-src 'self' https://api.open-meteo.com https://generativelanguage.googleapis.com https://api.groq.com https://*.openstreetmap.org https://tile.openstreetmap.jp https://cyberjapandata.gsi.go.jp https://router.project-osrm.org;"
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

# ================= 2. デフォルト店舗データ =================
DEFAULT_SHOPS = [
    {
        "name": "姫路和食 個室 旬彩庵 (サンプル)", "genre": "居酒屋・個室和食",
        "address": "兵庫県姫路市駅前町100", "budget": "3,500円〜5,000円", "min_budget": 3500,
        "lat": 34.8290, "lng": 134.6900, "tel": "079-000-0002", "open": "17:00～23:30", "access": "姫路駅北口徒歩3分",
        "has_private": True, "smoking_info": "🚬 喫煙可", "has_free_drink": True,
        "photo": "https://images.unsplash.com/photo-1517248135467-4c7edcad34c4?w=600", "url": "https://www.hotpepper.jp/"
    },
    {
        "name": "CAFÉ DE ÉTOILE (サンプル)", "genre": "カフェ・スイーツ",
        "address": "兵庫県姫路市本町68", "budget": "1,000円〜2,000円", "min_budget": 1000,
        "lat": 34.8340, "lng": 134.6930, "tel": "079-000-0001", "open": "10:00～19:00", "access": "地下街直結",
        "has_private": False, "smoking_info": "🚭 全席禁煙", "has_free_drink": False,
        "photo": "https://images.unsplash.com/photo-1554118811-1e0d58224f24?w=600", "url": "https://www.hotpepper.jp/"
    }
]

# ================= 3. 共通ベーステンプレート =================
LAYOUT_HTML = """<!DOCTYPE html>
<html lang="ja">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <link rel="icon" href="data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 100 100%22><text y=%22.9em%22 font-size=%2290%22>🍽️</text></svg>">
    <link rel="manifest" href="/manifest.json">
    <meta name="theme-color" content="#ff5252">
    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
    <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
    <script>
        const savedTheme = localStorage.getItem('eatmap_theme') || (window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
        document.documentElement.setAttribute('data-theme', savedTheme);
        function doVibrate(ms=30){ try{ if('vibrate' in navigator) navigator.vibrate(ms); }catch(e){} }
        
        function showAppAlert(title, message) {
            doVibrate([200, 100, 200]);
            if ("Notification" in window && Notification.permission === "granted") { try { new Notification(title, { body: message }); } catch(e){} }
            const box = document.createElement('div');
            box.style.position = 'fixed'; box.style.top = '20px'; box.style.left = '50%';
            box.style.transform = 'translateX(-50%)'; box.style.background = 'var(--primary)';
            box.style.color = '#fff'; box.style.padding = '16px'; box.style.borderRadius = '16px';
            box.style.boxShadow = '0 6px 20px rgba(0,0,0,0.2)'; box.style.zIndex = '99999';
            box.style.width = '90%'; box.style.maxWidth = '400px'; box.style.textAlign = 'center';
            box.innerHTML = `<div style="font-size:16px; font-weight:900; margin-bottom:8px;">${title}</div><div style="font-size:13px; font-weight:700;">${message}</div><button onclick="this.parentElement.remove()" style="margin-top:12px; width:100%; padding:10px; background:rgba(255,255,255,0.25); border:none; border-radius:10px; color:#fff; font-weight:900; cursor:pointer;">OK</button>`;
            document.body.appendChild(box);
        }

        // リップル（波紋）エフェクト
        document.addEventListener('click', function(e) {
            const btn = e.target.closest('button') || e.target.closest('.btn-block');
            if (!btn || btn.classList.contains('fav-btn')) return;
            btn.style.position = 'relative'; btn.style.overflow = 'hidden';
            const rect = btn.getBoundingClientRect(); const size = Math.max(rect.width, rect.height);
            const x = e.clientX - rect.left - size / 2, y = e.clientY - rect.top - size / 2;
            const ripple = document.createElement('span');
            ripple.className = 'ripple-anim';
            ripple.style.width = ripple.style.height = `${size}px`; ripple.style.left = `${x}px`; ripple.style.top = `${y}px`;
            btn.appendChild(ripple);
            setTimeout(() => ripple.remove(), 600);
        });
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
        body { background: var(--bg); color: var(--text); font-family: -apple-system, BlinkMacSystemFont, sans-serif; margin: 0; padding: 0 0 65px 0; min-height: 100vh; }
        .max-w { max-width: 480px; margin: 0 auto; padding: 14px; }
        .card { background: var(--card); border: 1.5px solid var(--border); border-radius: 16px; padding: 14px; margin-bottom: 12px; box-shadow: var(--shadow); position: relative; }
        .top-bar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
        .brand { font-size: 21px; font-weight: 900; color: var(--primary); display: flex; align-items: center; gap: 6px; text-decoration: none; }
        .btn-icon, .btn-sm, .btn-block { cursor: pointer; border-radius: 10px; display: inline-flex; align-items: center; justify-content: center; font-weight: 800; border: 1.5px solid var(--border); text-decoration: none; transition: opacity .15s; }
        .btn-icon { background: var(--card); color: var(--text); width: 36px; height: 36px; font-size: 15px; box-shadow: var(--shadow); }
        .btn-sm { background: var(--tag); color: var(--text); padding: 8px 12px; font-size: 12px; gap: 4px; }
        .btn-block { width: 100%; min-height: 46px; font-size: 14px; gap: 6px; margin-bottom: 8px; box-shadow: var(--shadow); border: none; }
        .btn-icon:active, .btn-sm:active { opacity: .7; }
        .btn-block:active { opacity: .8; }
        .btn-primary { background: var(--primary); color: #fff; border:none; }
        .btn-yellow { background: var(--yellow); color: #493800; border:none; }
        .btn-green { background: var(--green); color: #fff; border:none; }
        .btn-purple { background: var(--purple); color: #fff; border:none; }
        .btn-sub { background: var(--tag); color: var(--text); border: 1.5px solid var(--border); }
        .input-group { margin-bottom: 10px; }
        .input-group input, .input-group select { width: 100%; padding: 12px 14px; border: 1.5px solid var(--border); border-radius: 10px; font-size: 14px; background: var(--input); color: var(--text); outline: none; font-weight: 700; transition: border-color .2s; }
        .badge { display: inline-flex; align-items: center; gap: 3px; font-size: 10.5px; font-weight: 800; padding: 3px 6px; border-radius: 6px; background: var(--tag); color: var(--text); }
        .badge-primary { background: var(--primary-light); color: var(--primary); }
        .badge-dist { background: #e0f2fe; color: #0284c7; }
        .badge-smoke { background: #fef3c7; color: #92400e; }
        .badge-private { background: #fce7f3; color: #9d174d; }
        .badge-drink { background: #ecfdf5; color: #065f46; }
        .filter-chip { background: var(--tag); border: 1.5px solid var(--border); border-radius: 8px; padding: 8px 10px; font-size: 11.5px; font-weight: 800; color: var(--text); cursor: pointer; display: flex; align-items: center; justify-content: center; gap: 4px; user-select: none; }
        .filter-chip.active { background: var(--primary-light); border-color: var(--primary); color: var(--primary); }
        
        .ripple-anim { position: absolute; border-radius: 50%; background: rgba(255,255,255,0.4); transform: scale(0); animation: ripple-run 0.6s linear; pointer-events: none; }
        [data-theme="light"] .btn-sub .ripple-anim, [data-theme="light"] .btn-icon .ripple-anim { background: rgba(0,0,0,0.1); }
        @keyframes ripple-run { to { transform: scale(3); opacity: 0; } }

        /* ナイトマップ用CSSフィルター */
        [data-theme="dark"] .leaflet-tile-pane {
            filter: brightness(0.6) invert(1) contrast(3) hue-rotate(200deg) saturate(0.3) brightness(0.7);
        }

        .bottom-nav { position: fixed; bottom: 0; left: 0; width: 100%; background: var(--card); border-top: 1.5px solid var(--border); display: flex; justify-content: space-around; padding: 6px 0 calc(6px + env(safe-area-inset-bottom)); z-index: 9000; box-shadow: 0 -2px 10px rgba(0,0,0,0.03); }
        .bottom-nav a { color: var(--muted); text-decoration: none; font-size: 10px; display: flex; flex-direction: column; align-items: center; gap: 2px; font-weight: 800; width: 20%; }
        .bottom-nav a.active { color: var(--primary); }
        .bottom-nav span.icon { font-size: 20px; }
        #loading-overlay { position: fixed; top: 0; left: 0; width: 100vw; height: 100vh; background: rgba(0,0,0,0.7); display: none; justify-content: center; align-items: center; flex-direction: column; z-index: 99999; }
        .spinner { width: 36px; height: 36px; border: 4px solid rgba(255,255,255,0.2); border-top-color: #fff; border-radius: 50%; animation: spin .8s linear infinite; margin-bottom: 12px; }
        @keyframes spin { 100% { transform: rotate(360deg); } }
        
        .swipe-modal-content { transition: transform 0.2s; will-change: transform; }
        .swipe-handle { width: 40px; height: 5px; background: var(--muted); border-radius: 3px; margin: 0 auto 12px; opacity: 0.5; }
    </style>
</head>
<body>
    <div id="loading-overlay"><div class="spinner"></div><div style="color:#fff; font-size:13px; font-weight:800;">処理中...</div></div>
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
        
        async function forceUpdateApp(){
            if('caches' in window){ const n = await caches.keys(); await Promise.all(n.map(k=>caches.delete(k))); }
            window.location.reload(true);
        }

        function enableSwipeToClose(modalId, closeFn) {
            const el = document.getElementById(modalId);
            if(!el) return;
            const content = el.querySelector('.swipe-modal-content');
            let startY = 0, curY = 0;
            el.addEventListener('touchstart', e => {
                if(e.target.tagName.toLowerCase() === 'textarea' || e.target.tagName.toLowerCase() === 'input' || e.target.closest('#wheel-items-container')) return;
                startY = e.touches[0].clientY; 
                content.style.transition = 'none';
            }, {passive: true});
            el.addEventListener('touchmove', e => { 
                if(!startY) return;
                curY = e.touches[0].clientY;
                const diff = curY - startY;
                if(diff > 0) content.style.transform = `translateY(${diff}px)`;
            }, {passive: true});
            el.addEventListener('touchend', e => {
                if(!startY) return;
                const diff = curY - startY;
                content.style.transition = 'transform 0.2s';
                content.style.transform = '';
                if(diff > 120) closeFn();
                startY = 0; curY = 0;
            });
        }
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
        <a href="/guide" class="btn-icon" title="機能ガイド">❓</a>
        <button class="btn-icon theme-btn" onclick="toggleTheme()" title="テーマ切替">🌙</button>
        <button class="btn-icon" onclick="forceUpdateApp()">🔄</button>
    </div>
</div>

<div id="pinned-reservation" class="card" style="display:none; background:linear-gradient(135deg, #1e293b, #0f172a); color:#fff; border:none; padding:14px; margin-bottom:12px;">
    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:6px;">
        <span style="font-size:11px; font-weight:800; color:var(--yellow);">📌 今夜の予約メモ (オフラインOK)</span>
        <button onclick="clearPinReservation()" style="background:none; border:none; color:#94a3b8; font-size:14px; cursor:pointer;">✕ 解除</button>
    </div>
    <div style="font-size:16px; font-weight:900;" id="pin-name">店舗名</div>
    <div style="font-size:12px; margin-top:4px; opacity:.9;" id="pin-detail">19:30〜 / コース予約</div>
    <div style="display:flex; gap:8px; margin-top:8px;">
        <a href="#" id="pin-tel" class="btn-sm" style="flex:1; justify-content:center; background:#10b981; color:#fff; border:none; padding:6px 0;">📞 電話する</a>
        <a href="#" id="pin-map" target="_blank" class="btn-sm" style="flex:1; justify-content:center; background:rgba(255,255,255,0.2); color:#fff; border:none; padding:6px 0;">🗺️ ルート案内</a>
    </div>
</div>

<div style="display:grid; grid-template-columns:1fr 1fr; gap:8px; margin-bottom:8px;">
    <button class="btn-block btn-green" onclick="searchLoc()">📍 現在地周辺</button>
    <button class="btn-block btn-yellow" onclick="searchNiji()">🍻 二次会・深夜</button>
</div>
<button class="btn-block" id="btn-midnight-shime" style="background:linear-gradient(135deg, #4f46e5, #9333ea); color:#fff; margin-bottom:12px; font-size:13px;" onclick="searchShime()">🍜 深夜の背徳シメ飯を探す (ラーメン・夜パフェ)</button>

<div class="card">
    <div style="font-size:12px; font-weight:800; color:var(--muted); margin-bottom:10px;">⭐ 人気ジャンル一発検索</div>
    <div style="display:grid; grid-template-columns:repeat(4,1fr); gap:6px; margin-bottom:16px;">
        <button type="button" class="btn-sm" style="background:#fee2e2; border-color:#fca5a5; color:#991b1b; justify-content:center; padding:6px;" onclick="quick('居酒屋 個室')">🍺 居酒屋</button>
        <button type="button" class="btn-sm" style="background:#fef3c7; border-color:#fde047; color:#854d0e; justify-content:center; padding:6px;" onclick="quick('焼肉')">🍖 焼肉</button>
        <button type="button" class="btn-sm" style="background:#dcfce7; border-color:#86efac; color:#166534; justify-content:center; padding:6px;" onclick="quick('カフェ')">☕ カフェ</button>
        <button type="button" class="btn-sm" style="background:#e0f2fe; border-color:#7dd3fc; color:#075985; justify-content:center; padding:6px;" onclick="quick('ラーメン')">🍜 麺類</button>
    </div>

    <form action="/search" method="GET" id="s-form" onsubmit="showLoad()">
        <div class="input-group"><input type="text" name="area" id="area-in" maxlength="40" placeholder="📍 エリア・駅名 (例: 姫路, 梅田)"></div>
        <div class="input-group"><input type="text" name="keyword" id="kw-in" maxlength="40" placeholder="🔍 キーワード (例: 個室, 焼鳥)"></div>
        
        <div style="font-size:12px; font-weight:800; color:var(--muted); margin:10px 0 6px;">✨ こだわり設備 (タップでON/OFF)</div>
        <div style="display:grid; grid-template-columns:1fr 1fr; gap:6px; margin-bottom:10px;">
            <div class="filter-chip" onclick="toggleChip(this, 'c-smoking')">🚬 喫煙可能店</div>
            <div class="filter-chip" onclick="toggleChip(this, 'c-private')">🚪 個室あり</div>
            <div class="filter-chip" onclick="toggleChip(this, 'c-drink')">🍺 飲み放題あり</div>
            <div class="filter-chip" onclick="toggleChip(this, 'c-midnight')">🌙 深夜営業 (23時以降)</div>
        </div>

        <div style="font-size:12px; font-weight:800; color:var(--muted); margin:10px 0 6px;">🚫 苦手・アレルギー配慮</div>
        <div style="display:grid; grid-template-columns:repeat(3, 1fr); gap:6px; margin-bottom:12px;">
            <div class="filter-chip" onclick="toggleChip(this, 'c-fish')">🐟 魚介NG</div>
            <div class="filter-chip" onclick="toggleChip(this, 'c-meat')">🥩 肉メイン</div>
            <div class="filter-chip" onclick="toggleChip(this, 'c-spicy')">🌶️ 辛いのNG</div>
        </div>
        
        <input type="checkbox" name="smoking" id="c-smoking" value="1" style="display:none;">
        <input type="checkbox" name="private_room" id="c-private" value="1" style="display:none;">
        <input type="checkbox" name="free_drink" id="c-drink" value="1" style="display:none;">
        <input type="checkbox" name="midnight" id="c-midnight" value="1" style="display:none;">
        <input type="checkbox" name="pref_fish" id="c-fish" value="1" style="display:none;">
        <input type="checkbox" name="pref_meat" id="c-meat" value="1" style="display:none;">
        <input type="checkbox" name="pref_spicy" id="c-spicy" value="1" style="display:none;">

        <div style="display:flex; gap:8px;">
            <div class="input-group" style="flex:1;">
                <select name="budget_filter"><option value="">💰 予算指定なし</option><option value="2000">〜2,000円 (サク飲み)</option><option value="4000">〜4,000円 (定番)</option><option value="6000">〜6,000円 (ご褒美)</option></select>
            </div>
            <div class="input-group" style="flex:1;">
                <select name="people"><option value="1名">👤 1名</option><option value="2名" selected>👥 2名</option><option value="3〜4名">🍻 3〜4名</option><option value="5名以上">🎉 5名以上</option></select>
            </div>
        </div>
        <button type="submit" class="btn-block btn-primary" onclick="doVibrate(40)">条件でお店を探す</button>
    </form>
</div>
<div class="credit">Powered by <a href="http://webservice.recruit.co.jp/" target="_blank">ホットペッパー Webサービス</a></div>
</div>
<script>
    function showLoad(){ document.getElementById('loading-overlay').style.display='flex'; }
    function quick(k){ document.getElementById('kw-in').value=k; doVibrate(40); showLoad(); document.getElementById('s-form').submit(); }
    function toggleChip(el, targetId){ doVibrate(25); const cb = document.getElementById(targetId); cb.checked = !cb.checked; if(cb.checked) el.classList.add('active'); else el.classList.remove('active'); }
    function searchLoc(){ if(!navigator.geolocation) return showAppAlert("エラー", "GPS非対応です"); doVibrate(40); showLoad(); navigator.geolocation.getCurrentPosition(p=>{ window.location.href=`/search?lat=${p.coords.latitude.toFixed(6)}&lng=${p.coords.longitude.toFixed(6)}&area=現在地周辺`; }, ()=>showAppAlert("エラー", "GPSを許可してください"), {timeout:8000}); }
    function searchNiji(){ doVibrate(40); showLoad(); if(navigator.geolocation){ navigator.geolocation.getCurrentPosition(p=>{ window.location.href=`/search?lat=${p.coords.latitude.toFixed(6)}&lng=${p.coords.longitude.toFixed(6)}&keyword=${encodeURIComponent("二次会 バー 深夜")}&area=現在地&midnight=1`; }, ()=>{ window.location.href=`/search?keyword=${encodeURIComponent("二次会 バー 深夜")}&midnight=1`; }, {timeout:6000}); } else { window.location.href=`/search?keyword=${encodeURIComponent("二次会 バー 深夜")}&midnight=1`; } }
    function searchShime(){ doVibrate(40); showLoad(); const kw = "ラーメン うどん 夜パフェ 雑炊 シメ"; if(navigator.geolocation){ navigator.geolocation.getCurrentPosition(p=>{ window.location.href=`/search?lat=${p.coords.latitude.toFixed(6)}&lng=${p.coords.longitude.toFixed(6)}&keyword=${encodeURIComponent(kw)}&area=現在地&midnight=1`; }, ()=>{ window.location.href=`/search?keyword=${encodeURIComponent(kw)}&midnight=1`; }, {timeout:6000}); } else { window.location.href=`/search?keyword=${encodeURIComponent(kw)}&midnight=1`; } }

    const curHour = new Date().getHours();
    if(curHour >= 21 || curHour < 5){
        const shimeBtn = document.getElementById('btn-midnight-shime');
        if(shimeBtn){ shimeBtn.style.boxShadow = "0 0 15px rgba(168, 85, 247, 0.5)"; shimeBtn.innerHTML = "🌙⚡【深夜限定】背徳のシメ飯を探す (ラーメン・夜パフェ)"; }
    }

    function checkPinReservation(){
        const res = JSON.parse(localStorage.getItem('eatmap_pinned_res')||'null');
        const box = document.getElementById('pinned-reservation');
        if(res){ document.getElementById('pin-name').innerText = res.name; document.getElementById('pin-detail').innerText = `${res.time || '予約あり'} / ${res.course || '席のみ予約'}`; document.getElementById('pin-tel').href = `tel:${res.tel}`; document.getElementById('pin-map').href = `https://www.google.com/maps/dir/?api=1&destination=${encodeURIComponent(res.address)}`; box.style.display = 'block'; } else { box.style.display = 'none'; }
    }
    function clearPinReservation(){ if(confirm("予約メモのピン留めを解除しますか？")){ localStorage.removeItem('eatmap_pinned_res'); checkPinReservation(); } }
    
    function showWelcomeMessage(isRain) {
        if(sessionStorage.getItem('eatmap_welcomed')) return;
        sessionStorage.setItem('eatmap_welcomed', '1');
        const h = new Date().getHours();
        let msg = "美味しいお店を探しましょう！";
        if (isRain) msg = "雨が降っていますね☔ 駅直結や地下のお店を探しましょうか？";
        else if (h >= 22 || h < 4) msg = "夜遅くまでお疲れ様です！そろそろシメのラーメンはいかがですか？🍜";
        else if (h >= 11 && h <= 14) msg = "こんにちは！今日のランチはどこにしましょうか？🍔";
        else if (h >= 17 && h <= 20) msg = "お疲れ様です！サクッと飲める居酒屋を探しますか？🍺";
        
        const box = document.createElement('div');
        box.style.position = 'fixed'; box.style.top = '-100px'; box.style.left = '12px'; box.style.right = '12px';
        box.style.background = 'var(--primary)'; box.style.color = '#fff'; box.style.padding = '14px'; box.style.borderRadius = '16px';
        box.style.boxShadow = '0 6px 20px rgba(0,0,0,0.2)'; box.style.zIndex = '99999';
        box.style.transition = 'top 0.5s cubic-bezier(0.175, 0.885, 0.32, 1.275)';
        box.innerHTML = `<div style="display:flex; gap:10px; align-items:center;"><div style="font-size:24px;">🤖</div><div style="font-size:12px; font-weight:800; line-height:1.4;">${msg}</div></div>`;
        document.body.appendChild(box);
        setTimeout(() => box.style.top = '12px', 500);
        setTimeout(() => { box.style.top = '-100px'; setTimeout(()=>box.remove(), 500); }, 5500);
    }

    window.addEventListener('DOMContentLoaded', ()=>{
        checkPinReservation();
        if(navigator.geolocation){
            navigator.geolocation.getCurrentPosition(p=>{
                fetch(`https://api.open-meteo.com/v1/forecast?latitude=${p.coords.latitude}&longitude=${p.coords.longitude}&current=weather_code&timezone=Asia%2FTokyo`)
                .then(r=>r.json()).then(d=>{
                    if(!d.current) return;
                    const isRain=(d.current.weather_code>=51&&d.current.weather_code<=67)||(d.current.weather_code>=80&&d.current.weather_code<=82)||(d.current.weather_code>=95);
                    showWelcomeMessage(isRain);
                }).catch(()=>{ showWelcomeMessage(false); });
            }, ()=>{ showWelcomeMessage(false); }, {timeout:5000});
        } else { showWelcomeMessage(false); }
    });
</script>
"""

# --- 検索画面 (通常リスト ＋ OSM日本語/国土地理院ハイブリッド全画面マップ切替) ---
RESULT_CONTENT = """
<!-- ① 通常リストビュー -->
<div id="view-list" class="max-w">
    <div class="top-bar">
        <a href="/" class="btn-sm">← 戻る</a>
        <div style="font-size:13px; font-weight:800; color:var(--muted);">{{ search_title }} ({{ shops|length }}件)</div>
    </div>

    <div style="display:flex; gap:6px; margin-bottom:10px;">
        <button class="btn-sm sort-tab" id="sort-rec" style="flex:1; justify-content:center; background:var(--primary); color:#fff; border-color:var(--primary);" onclick="sortShops('default')">⭐ おすすめ順</button>
        <button class="btn-sm sort-tab" id="sort-price" style="flex:1; justify-content:center;" onclick="sortShops('price')">💰 予算が安い順</button>
    </div>

    <!-- 通常マッププレビュー（右上に⛶拡大ボタン） -->
    <div style="position:relative; margin-bottom:12px;">
        <div id="map-preview" style="height:220px; width:100%; border-radius:14px; border:1.5px solid var(--border); box-shadow:var(--shadow);"></div>
        <button onclick="switchToFullMap()" style="position:absolute; top:10px; right:10px; z-index:1000; background:var(--card); border:1.5px solid var(--border); border-radius:10px; padding:6px 12px; font-size:12px; font-weight:900; box-shadow:0 2px 8px rgba(0,0,0,0.2); cursor:pointer; color:var(--text); display:flex; align-items:center; gap:4px;">⛶ 地図を拡大</button>
    </div>

    <div id="shops-list">
        {% for s in shops %}
        <div class="card shop-card" data-budget="{{ s.min_budget }}">
            <button class="fav-btn" style="position:absolute; top:12px; right:12px; font-size:18px; cursor:pointer; background:var(--card); border:1.5px solid var(--border); border-radius:10px; width:34px; height:34px; display:flex; align-items:center; justify-content:center;" onclick='toggleFav(this, {{ s | tojson }})'>♡</button>
            {% if s.photo %}<img src="{{ s.photo }}" style="width:100%; height:150px; object-fit:cover; border-radius:12px; margin-bottom:10px; background:#222;" loading="lazy">{% endif %}
            
            <h3 class="shop-name" style="font-size:15px; font-weight:900; margin:0 0 6px 0; padding-right:40px; line-height:1.3;">
                <span style="background:var(--primary); color:#fff; font-size:11px; padding:2px 6px; border-radius:6px; margin-right:4px;">{{ loop.index }}</span>{{ s.name }}
            </h3>
            
            <div style="display:flex; flex-wrap:wrap; gap:4px; margin-bottom:6px;">
                <span class="badge badge-primary">🏷️ {{ s.genre }}</span>
                <span class="badge">💰 {{ s.budget }}</span>
            </div>

            <div style="display:flex; flex-wrap:wrap; gap:4px; margin-bottom:8px;">
                {% if s.has_private %}<span class="badge badge-private">🚪 個室</span>{% endif %}
                <span class="badge badge-smoke">{{ s.smoking_info }}</span>
                {% if s.has_free_drink %}<span class="badge badge-drink">🍺 飲み放題</span>{% endif %}
            </div>

            <div style="font-size:11.5px; color:var(--muted); margin-bottom:10px; line-height:1.4;">📍 {{ s.address }}</div>
            
            <div style="display:grid; grid-template-columns:1fr 1fr; gap:6px; margin-bottom:6px;">
                <button class="btn-sm btn-sub" style="justify-content:center; padding:10px 0; border:1px solid var(--blue); color:var(--blue);" onclick='switchToFullMap({{ loop.index0 }})'>🗺️ 地図・ルート</button>
                <a href="{{ s.url }}" target="_blank" class="btn-sm btn-primary" style="justify-content:center; padding:10px 0;">予約・詳細 ↗</a>
            </div>
            
            <div style="display:grid; grid-template-columns:1fr 1fr; gap:6px;">
                <button class="btn-sm btn-sub" style="justify-content:center;" onclick='openInviteModal({{ s | tojson }})'>📅 案内状作成</button>
                <button class="btn-sm btn-sub" style="justify-content:center;" onclick='pinReservation({{ s | tojson }})'>📌 予約メモ登録</button>
            </div>
        </div>
        {% endfor %}
    </div>
</div>

<!-- ② 全画面マップビュー（拡大時） -->
<style>
    #map-full { width: 100%; height: 100%; z-index: 1; }
    .card-slider-container { position: absolute; bottom: 12px; left: 0; width: 100vw; z-index: 1000; overflow-x: auto; scroll-snap-type: x mandatory; display: flex; gap: 12px; padding: 0 12px 12px 12px; -webkit-overflow-scrolling: touch; transition: transform 0.3s; }
    .card-slider-container::-webkit-scrollbar { display: none; }
    .snap-card { scroll-snap-align: center; flex: 0 0 90%; background: var(--card); border-radius: 16px; box-shadow: 0 6px 16px rgba(0,0,0,0.2); padding: 12px; border: 1.5px solid var(--border); }
    #route-panel { position: absolute; top: 0; left: 0; width: 100%; background: var(--card); z-index: 1001; padding: 14px 14px 20px; box-shadow: 0 4px 16px rgba(0,0,0,0.15); transform: translateY(-100%); transition: transform 0.3s; border-bottom-left-radius: 16px; border-bottom-right-radius: 16px; }
    #route-panel.active { transform: translateY(0); }
</style>

<div id="view-fullmap" style="display:none; position:fixed; top:0; left:0; width:100vw; height:calc(100vh - 60px); z-index:900; background:var(--bg);">
    <div id="map-full"></div>

    <!-- 上部バー -->
    <div style="position:absolute; top:12px; left:12px; right:12px; z-index:1000; display:flex; gap:8px;">
        <div style="flex:1; background:var(--card); border-radius:12px; padding:8px 12px; box-shadow:0 4px 12px rgba(0,0,0,0.15); display:flex; align-items:center; gap:8px; font-size:13px; font-weight:800;">
            <button onclick="switchToList()" style="background:none; border:none; font-size:16px; cursor:pointer; padding:0; display:flex; align-items:center; color:var(--muted);"><span style="background:var(--tag); padding:4px 8px; border-radius:8px;">⬅️ リスト</span></button>
            <div style="flex:1; text-align:right; display:flex; justify-content:flex-end; gap:6px;">
                <button class="btn-sm" style="background:var(--tag); border:none; padding:4px 8px; font-size:11px;" onclick="toggleMapTile()" id="btn-maptile">🗾 標準マップ</button>
                <button class="btn-sm" style="background:var(--tag); border:none; padding:4px 8px; font-size:11px;" onclick="toggleOpenNow()" id="btn-open">🟢 営業中</button>
            </div>
        </div>
    </div>
    
    <button id="btn-research" onclick="doReSearch()" style="position:absolute; top:70px; left:50%; transform:translateX(-50%); z-index:1000; background:var(--primary); color:#fff; padding:8px 16px; border-radius:20px; font-weight:900; font-size:13px; box-shadow:0 4px 12px rgba(255,82,82,0.4); border:none; cursor:pointer; display:none;">📍 このエリアで再検索</button>

    <!-- 右側コントロールボタン -->
    <div style="position:absolute; right:12px; bottom:200px; z-index:1000; display:flex; flex-direction:column; gap:8px;" id="map-controls">
        <button onclick="toggle5MinCircle()" style="width:42px; height:42px; border-radius:50%; background:var(--card); border:1.5px solid var(--border); box-shadow:0 4px 12px rgba(0,0,0,0.15); font-size:18px; cursor:pointer;" title="5分圏内円">🚶</button>
        <button onclick="trackLocation()" style="width:42px; height:42px; border-radius:50%; background:var(--card); border:1.5px solid var(--border); box-shadow:0 4px 12px rgba(0,0,0,0.15); font-size:18px; cursor:pointer;" title="現在地追従">🎯</button>
    </div>

    <!-- ルート案内上部パネル -->
    <div id="route-panel">
        <div style="display:flex; justify-content:space-between; align-items:center;">
            <div style="font-size:18px; font-weight:900; color:var(--blue);" id="route-summary">🚶 --分 (--m)</div>
            <button class="btn-sm" style="background:#fee2e2; color:#ef4444; border:none;" onclick="cancelRoute()">✕ 案内終了</button>
        </div>
        <div id="route-dest" style="font-size:12px; font-weight:800; color:var(--muted); margin-top:4px;">目的地: --</div>
        <div id="route-steps" style="max-height:25vh; overflow-y:auto; margin-top:10px; padding:10px; background:var(--tag); border-radius:10px; font-size:12px; font-weight:700; line-height:1.6;">経路を計算中...</div>
    </div>

    <!-- 下部スワイプカード -->
    <div class="card-slider-container" id="card-slider">
        {% for s in shops %}
        <div class="snap-card" data-index="{{ loop.index0 }}">
            <div style="display:flex; gap:10px;">
                {% if s.photo %}<img src="{{ s.photo }}" style="width:70px; height:70px; border-radius:10px; object-fit:cover; background:#222; flex-shrink:0;">{% endif %}
                <div style="flex:1; overflow:hidden;">
                    <div style="font-size:14px; font-weight:900; line-height:1.2; margin-bottom:4px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;">
                        <span style="background:var(--primary); color:#fff; font-size:10px; padding:1px 5px; border-radius:4px; margin-right:4px;">{{ loop.index }}</span>{{ s.name }}
                    </div>
                    <div style="font-size:10px; color:var(--muted); margin-bottom:4px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;">📍 {{ s.address }}</div>
                    <div style="display:flex; flex-wrap:wrap; gap:3px;">
                        <span class="badge badge-primary">💰 {{ s.budget }}</span>
                        {% if s.has_private %}<span class="badge badge-private">🚪個室</span>{% endif %}
                        <span class="badge badge-smoke">{{ s.smoking_info }}</span>
                    </div>
                </div>
            </div>
            <div style="display:grid; grid-template-columns:1fr 1fr; gap:6px; margin-top:8px;">
                <button class="btn-sm btn-sub" style="justify-content:center; padding:9px 0; border:1px solid var(--blue); color:var(--blue);" onclick='drawRoute({{ s.lat }}, {{ s.lng }}, "{{ s.name }}")'>🚶 ルート案内</button>
                <button class="btn-sm btn-sub" style="justify-content:center; padding:9px 0;" onclick='openInviteModal({{ s | tojson }})'>📅 案内状/メモ</button>
            </div>
        </div>
        {% endfor %}
    </div>
</div>

<!-- 案内状・予約メモモーダル -->
<div id="invite-modal" style="display:none; position:fixed; top:0; left:0; width:100vw; height:100vh; background:rgba(0,0,0,0.75); z-index:99999; justify-content:flex-end; align-items:center; padding:14px; flex-direction:column;">
    <div class="card swipe-modal-content" style="width:100%; max-width:440px; margin:0 0 env(safe-area-inset-bottom); background:var(--card);">
        <div class="swipe-handle"></div>
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:10px;">
            <span style="font-size:14px; font-weight:900;">📅 LINE案内状 ＆ メモ登録</span>
            <button onclick="closeInviteModal()" style="background:none; border:none; font-size:18px; cursor:pointer; color:var(--text);">✕</button>
        </div>
        <div class="input-group"><input type="text" id="inv-time" placeholder="日時 (例: 10月28日(水) 19:30〜)"></div>
        <div class="input-group"><input type="text" id="inv-fee" placeholder="会費 (例: 4,000円 / 割り勘)"></div>
        <div style="font-size:11px; color:var(--muted); margin-bottom:6px;">生成プレビュー:</div>
        <textarea id="inv-preview" rows="5" style="width:100%; border:1.5px solid var(--border); border-radius:10px; font-size:12px; padding:10px; font-family:sans-serif; background:var(--tag); color:var(--text); margin-bottom:10px;"></textarea>
        <div style="display:grid; grid-template-columns:1fr 1fr; gap:8px;">
            <button class="btn-block btn-sub" style="min-height:42px; font-size:13px; margin:0;" onclick="copyInviteText()">📋 案内文コピー</button>
            <button class="btn-block btn-green" style="min-height:42px; font-size:13px; margin:0;" onclick="sendInviteLine()">💬 LINE送信</button>
        </div>
        <button class="btn-block btn-primary" style="min-height:42px; font-size:13px; margin-top:8px;" onclick="pinReservationFromModal()">📌 トップに予約メモとして固定</button>
    </div>
</div>

<script>
    let shops = {{ shops | tojson | safe }};
    const lat = (shops.length>0 && shops[0].lat) ? shops[0].lat : 34.8290;
    const lng = (shops.length>0 && shops[0].lng) ? shops[0].lng : 134.6900;
    
    let mapPreview = null, mapFull = null;
    let previewLayer = null, fullLayer = null;
    let fullMarkers = [], routeLayer = null, circle5m = null, userMarker = null;
    let uLat = null, uLng = null, isTracking = false, watchId = null;
    
    // デフォルトをOSM日本公式の高精細日本語マップに設定
    let currentTileMode = 'osmjp';

    const tileConfigs = {
        osmjp: {
            url: 'https://tile.openstreetmap.jp/{z}/{x}/{y}.png',
            attr: '&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank">OpenStreetMap</a> contributors',
            maxZoom: 19
        },
        gsi: {
            url: 'https://cyberjapandata.gsi.go.jp/xyz/pale/{z}/{x}/{y}.png',
            attr: '&copy; <a href="https://maps.gsi.go.jp/development/ichiran.html" target="_blank">国土地理院</a>',
            maxZoom: 18
        }
    };

    function getGenreEmoji(genre) {
        if(!genre) return '🍽️';
        if(genre.includes('居酒屋') || genre.includes('バー')) return '🍺';
        if(genre.includes('焼肉') || genre.includes('肉') || genre.includes('ステーキ')) return '🍖';
        if(genre.includes('カフェ') || genre.includes('スイーツ')) return '☕';
        if(genre.includes('ラーメン') || genre.includes('麺') || genre.includes('そば') || genre.includes('うどん')) return '🍜';
        if(genre.includes('海鮮') || genre.includes('魚') || genre.includes('寿司')) return '🐟';
        if(genre.includes('イタリアン') || genre.includes('パスタ') || genre.includes('ピザ')) return '🍕';
        if(genre.includes('和食')) return '🍣';
        return '🍽️';
    }

    // ① 通常プレビュー地図の初期化
    window.addEventListener('DOMContentLoaded', () => {
        const cfg = tileConfigs[currentTileMode];
        mapPreview = L.map('map-preview', {zoomControl:false, dragging:false, touchZoom:false, scrollWheelZoom:false, doubleClickZoom:false}).setView([lat, lng], 15);
        previewLayer = L.tileLayer(cfg.url, { maxZoom: cfg.maxZoom, attribution: cfg.attr }).addTo(mapPreview);

        const bounds = [];
        shops.forEach((s, i) => {
            if(s.lat && s.lng){
                bounds.push([s.lat, s.lng]);
                const icon = L.divIcon({
                    className:'',
                    html:`<div style="background:var(--primary); color:#fff; border-radius:50%; border:2px solid #fff; box-shadow:0 2px 4px rgba(0,0,0,0.3); font-size:11px; font-weight:900; display:flex; align-items:center; justify-content:center; width:24px; height:24px;">${i+1}</div>`,
                    iconSize:[24,24], iconAnchor:[12,12]
                });
                L.marker([s.lat, s.lng], {icon}).addTo(mapPreview);
            }
        });
        if(bounds.length > 0) mapPreview.fitBounds(bounds, {padding:[10,10]});

        if(navigator.geolocation){
            navigator.geolocation.getCurrentPosition(pos => {
                uLat = pos.coords.latitude; uLng = pos.coords.longitude;
            }, ()=>{}, {timeout:5000});
        }
        
        enableSwipeToClose('invite-modal', closeInviteModal);
        updateTileButtonLabel();
    });

    // ② 全画面マップへの切り替え
    function switchToFullMap(targetIdx=0) {
        doVibrate(30);
        document.getElementById('view-list').style.display = 'none';
        document.getElementById('view-fullmap').style.display = 'block';
        if(!mapFull) { initFullMap(); } else { mapFull.invalidateSize(); }
        setTimeout(() => { focusCard(targetIdx); }, 150);
    }

    function switchToList() {
        doVibrate(20);
        document.getElementById('view-fullmap').style.display = 'none';
        document.getElementById('view-list').style.display = 'block';
    }

    function initFullMap() {
        const cfg = tileConfigs[currentTileMode];
        mapFull = L.map('map-full', {zoomControl:false}).setView([lat, lng], 15);
        fullLayer = L.tileLayer(cfg.url, { maxZoom: cfg.maxZoom, attribution: cfg.attr }).addTo(mapFull);

        const bounds = [];
        shops.forEach((s, i) => {
            if(s.lat && s.lng){
                bounds.push([s.lat, s.lng]);
                const icon = createEmojiPin(i+1, false, s.genre);
                const marker = L.marker([s.lat, s.lng], {icon}).addTo(mapFull);
                marker.on('click', () => focusCard(i));
                fullMarkers.push(marker);
            } else { fullMarkers.push(null); }
        });
        if(bounds.length > 0) mapFull.fitBounds(bounds, {padding:[50, 200]});

        mapFull.on('dragend', () => { document.getElementById('btn-research').style.display = 'block'; });

        const slider = document.getElementById('card-slider');
        const observer = new IntersectionObserver((entries) => {
            entries.forEach(entry => {
                if(entry.isIntersecting && entry.intersectionRatio > 0.5){
                    const idx = parseInt(entry.target.dataset.index);
                    highlightFullMarker(idx);
                }
            });
        }, { root: slider, threshold: 0.6 });
        document.querySelectorAll('.snap-card').forEach(c => observer.observe(c));

        if(uLat && uLng) updateFullUserMarker();
        updateTileButtonLabel();
    }

    function toggleMapTile() {
        doVibrate(25);
        currentTileMode = (currentTileMode === 'osmjp') ? 'gsi' : 'osmjp';
        const cfg = tileConfigs[currentTileMode];
        updateTileButtonLabel();
        if(fullLayer && mapFull) {
            mapFull.removeLayer(fullLayer);
            fullLayer = L.tileLayer(cfg.url, { maxZoom: cfg.maxZoom, attribution: cfg.attr }).addTo(mapFull);
        }
    }

    function updateTileButtonLabel() {
        const btn = document.getElementById('btn-maptile');
        if(!btn) return;
        const labelMap = { 'osmjp': '🗺️ 標準マップ', 'gsi': '🗾 地理院(淡色)' };
        btn.innerText = labelMap[currentTileMode] || '🗺️ 切替';
    }

    function createEmojiPin(num, isHighlight, genre) {
        const emoji = getGenreEmoji(genre);
        const bg = isHighlight ? 'var(--yellow)' : 'var(--primary)';
        const col = isHighlight ? '#493800' : '#fff';
        const scale = isHighlight ? 'transform: scale(1.15) translateY(-5px); z-index:1000;' : '';
        return L.divIcon({
            className:'',
            html:`<div style="background:${bg}; color:${col}; border-radius:50%; border:2px solid #fff; box-shadow:0 4px 10px rgba(0,0,0,0.3); display:flex; flex-direction:column; align-items:center; justify-content:center; width:34px; height:34px; transition:all 0.3s; ${scale}"><span style="font-size:10px; font-weight:900; line-height:1;">${num}</span><span style="font-size:13px; line-height:1;">${emoji}</span></div>`,
            iconSize:[34,34], iconAnchor:[17,17]
        });
    }

    let activeFullIdx = -1;
    function highlightFullMarker(idx) {
        if(activeFullIdx === idx || !fullMarkers[idx]) return;
        if(activeFullIdx > -1 && fullMarkers[activeFullIdx]) fullMarkers[activeFullIdx].setIcon(createEmojiPin(activeFullIdx+1, false, shops[activeFullIdx].genre));
        fullMarkers[idx].setIcon(createEmojiPin(idx+1, true, shops[idx].genre));
        mapFull.panTo(fullMarkers[idx].getLatLng(), {animate:true, duration:0.3});
        activeFullIdx = idx;
    }

    function focusCard(idx) {
        const cards = document.querySelectorAll('.snap-card');
        if(cards[idx]) cards[idx].scrollIntoView({behavior: 'smooth', block: 'nearest', inline: 'center'});
    }

    function drawRoute(tLat, tLng, name) {
        doVibrate(40);
        if(!uLat || !uLng) return showAppAlert("エラー", "現在地を取得中です。GPSをONにしてください。");
        document.getElementById('card-slider').style.transform = 'translateY(150%)'; 
        document.getElementById('map-controls').style.bottom = '20px';
        document.getElementById('route-panel').classList.add('active');
        document.getElementById('route-dest').innerText = `目的地: ${name}`;
        document.getElementById('route-steps').innerHTML = "経路を計算中...";

        const url = `https://router.project-osrm.org/route/v1/foot/${uLng},${uLat};${tLng},${tLat}?overview=full&geometries=geojson&steps=true`;
        fetch(url).then(r=>r.json()).then(data => {
            if(data.code !== 'Ok') return document.getElementById('route-steps').innerHTML = "ルートが見つかりませんでした。";
            const route = data.routes[0];
            document.getElementById('route-summary').innerText = `🚶 徒歩 約${Math.ceil(route.duration/60)}分 (${Math.round(route.distance)}m)`;
            if(routeLayer) mapFull.removeLayer(routeLayer);
            routeLayer = L.geoJSON(route.geometry, { style: { color: '#3b82f6', weight: 6, opacity: 0.85, lineJoin: 'round' } }).addTo(mapFull);
            mapFull.fitBounds(routeLayer.getBounds(), {padding:[50, 80]});

            const steps = route.legs[0].steps; let stepHtml = '';
            steps.forEach((s, i) => {
                if(s.distance > 0 && s.maneuver.type !== 'arrive') {
                    let dir = "進む";
                    if(s.maneuver.modifier) { if(s.maneuver.modifier.includes('right')) dir = "右折 ⤴"; if(s.maneuver.modifier.includes('left')) dir = "左折 ⤵"; }
                    stepHtml += `<div style="padding:4px 0; border-bottom:1px dashed var(--border);"><span style="color:var(--primary);">${i+1}.</span> ${Math.round(s.distance)}m 先 ${s.name ? '「'+s.name+'」を ' : ''}${dir}</div>`;
                }
            });
            document.getElementById('route-steps').innerHTML = stepHtml + `<div style="padding:4px 0; color:var(--green); font-weight:900;">🏁 目的地に到着</div>`;
        }).catch(() => { document.getElementById('route-steps').innerHTML = "ルート計算に失敗しました。"; });
    }

    function cancelRoute() {
        doVibrate(20);
        if(routeLayer) { mapFull.removeLayer(routeLayer); routeLayer = null; }
        document.getElementById('route-panel').classList.remove('active');
        document.getElementById('card-slider').style.transform = 'translateY(0)';
        document.getElementById('map-controls').style.bottom = '200px';
        if(activeFullIdx > -1 && fullMarkers[activeFullIdx]) mapFull.panTo(fullMarkers[activeFullIdx].getLatLng());
    }

    function doReSearch() {
        doVibrate(40);
        const center = mapFull.getCenter();
        document.getElementById('loading-overlay').style.display = 'flex';
        const urlParams = new URLSearchParams(window.location.search);
        urlParams.set('lat', center.lat.toFixed(6)); urlParams.set('lng', center.lng.toFixed(6)); urlParams.set('area', 'マップ中心周辺');
        window.location.href = '/search?' + urlParams.toString();
    }

    function updateFullUserMarker() {
        if(!userMarker && mapFull && uLat) {
            const curIcon = L.divIcon({
                className:'',
                html:`<div style="position:relative; width:16px; height:16px;">
                        <div id="user-vision" style="position:absolute; top:-24px; left:-12px; width:0; height:0; border-left:20px solid transparent; border-right:20px solid transparent; border-bottom:40px solid rgba(59,130,246,0.25); transform-origin: center bottom; border-radius:40px 40px 0 0; transition: transform 0.2s;"></div>
                        <div style="background:#3b82f6; width:16px; height:16px; border-radius:50%; border:3px solid #fff; box-shadow:0 0 0 4px rgba(59,130,246,0.3); position:absolute; z-index:2; animation: pulse 2s infinite;"></div>
                      </div><style>@keyframes pulse { 0% { box-shadow: 0 0 0 0 rgba(59,130,246,0.5); } 70% { box-shadow: 0 0 0 15px rgba(59,130,246,0); } 100% { box-shadow: 0 0 0 0 rgba(59,130,246,0.5); } }</style>`,
                iconSize:[16,16], iconAnchor:[8,8]
            });
            userMarker = L.marker([uLat, uLng], {icon: curIcon, zIndexOffset:1000}).addTo(mapFull);
        } else if(userMarker && uLat) {
            userMarker.setLatLng([uLat, uLng]);
        }
    }

    function trackLocation() {
        doVibrate(30); isTracking = !isTracking;
        const btn = document.querySelector('button[title="現在地追従"]');
        if(isTracking) {
            btn.style.background = 'var(--primary)'; btn.style.color = '#fff';
            if(!navigator.geolocation) return;
            
            if(typeof DeviceOrientationEvent !== 'undefined' && typeof DeviceOrientationEvent.requestPermission === 'function') {
                DeviceOrientationEvent.requestPermission().then(p => { if(p === 'granted') window.addEventListener('deviceorientation', handleOrientation, true); }).catch(()=>{});
            } else { window.addEventListener('deviceorientationabsolute', handleOrientation, true); }

            watchId = navigator.geolocation.watchPosition(pos => {
                uLat = pos.coords.latitude; uLng = pos.coords.longitude;
                updateFullUserMarker(); mapFull.panTo([uLat, uLng]);
            }, e=>{}, {enableHighAccuracy:true});
        } else {
            btn.style.background = 'var(--card)'; btn.style.color = 'var(--text)';
            if(watchId) navigator.geolocation.clearWatch(watchId);
        }
    }

    function handleOrientation(e) {
        let alpha = e.webkitCompassHeading || e.alpha;
        if (alpha !== null && userMarker) {
            const vision = document.getElementById('user-vision');
            if(vision) vision.style.transform = `rotate(${alpha}deg)`;
        }
    }

    function toggle5MinCircle() {
        doVibrate(20);
        if(!uLat) return showAppAlert("エラー", "現在地を取得中です。");
        if(circle5m) {
            mapFull.removeLayer(circle5m); circle5m = null;
        } else {
            circle5m = L.circle([uLat, uLng], { radius: 400, color: '#10b981', fillColor: '#10b981', fillOpacity: 0.1, weight:2 }).addTo(mapFull);
            mapFull.fitBounds(circle5m.getBounds(), {padding:[20,20]});
        }
    }

    let hideClosed = false;
    function toggleOpenNow() {
        doVibrate(20); hideClosed = !hideClosed;
        const btn = document.getElementById('btn-open');
        btn.style.background = hideClosed ? 'var(--green)' : 'var(--tag)'; btn.style.color = hideClosed ? '#fff' : 'var(--text)';
        const curH = new Date().getHours(); const isLate = curH >= 23 || curH < 5;
        shops.forEach((s, i) => {
            if(!fullMarkers[i]) return;
            let isOpen = true;
            if(hideClosed && isLate && !s.open.includes('翌') && !s.open.includes('24')) isOpen = false;
            if(isOpen) mapFull.addLayer(fullMarkers[i]); else mapFull.removeLayer(fullMarkers[i]);
        });
    }

    function sortShops(type){
        doVibrate(30);
        document.querySelectorAll('.sort-tab').forEach(t => { t.style.background = 'var(--tag)'; t.style.color = 'var(--text)'; });
        const container = document.getElementById('shops-list');
        const cards = Array.from(container.children);
        if(type==='price'){
            document.getElementById('sort-price').style.background='var(--primary)'; document.getElementById('sort-price').style.color='#fff';
            cards.sort((a,b)=> parseInt(a.dataset.budget||0) - parseInt(b.dataset.budget||0));
        } else {
            document.getElementById('sort-rec').style.background='var(--primary)'; document.getElementById('sort-rec').style.color='#fff';
            cards.sort((a,b)=> parseInt(a.querySelector('.shop-name span').innerText) - parseInt(b.querySelector('.shop-name span').innerText));
        }
        cards.forEach(c => container.appendChild(c));
    }

    let targetShop = null;
    function openInviteModal(s){ doVibrate(30); targetShop = s; document.getElementById('inv-time').value = "今週 19:30〜"; document.getElementById('inv-fee').value = s.budget || "割り勘"; updateInvitePreview(); document.getElementById('invite-modal').style.display = 'flex'; }
    function closeInviteModal(){ document.getElementById('invite-modal').style.display = 'none'; }
    function updateInvitePreview(){ if(!targetShop) return; const t = document.getElementById('inv-time').value.trim(); const f = document.getElementById('inv-fee').value.trim(); document.getElementById('inv-preview').value = `📢【お食事会のご案内】\\n\\n📅 日時: ${t}\\n🍽️ 店名: ${targetShop.name}\\n💰 予算: ${f}\\n📍 住所: ${targetShop.address}\\n🔗 詳細: ${targetShop.url}\\n\\nよろしくお願いします！✨`; }
    document.getElementById('inv-time').addEventListener('input', updateInvitePreview); document.getElementById('inv-fee').addEventListener('input', updateInvitePreview);
    function copyInviteText(){ doVibrate(30); const txt = document.getElementById('inv-preview').value; if(navigator.clipboard) navigator.clipboard.writeText(txt).then(()=>showAppAlert("完了","案内文をコピーしました！")); else prompt("コピー:", txt); }
    function sendInviteLine(){ doVibrate(30); const txt = document.getElementById('inv-preview').value; window.open(`https://line.me/R/msg/text/?${encodeURIComponent(txt)}`, '_blank'); }
    function pinReservation(s){ doVibrate(40); const t = prompt("予約時間を入力 (例: 19:30):", "19:30"); if(t === null) return; const res = { name: s.name, time: t, course: "席のみ予約", tel: s.tel, address: s.address }; localStorage.setItem('eatmap_pinned_res', JSON.stringify(res)); showAppAlert("完了", "予約メモを固定しました！"); }
    function pinReservationFromModal(){ doVibrate(40); if(!targetShop) return; const res = { name: targetShop.name, time: document.getElementById('inv-time').value, course: "席のみ予約", tel: targetShop.tel, address: targetShop.address }; localStorage.setItem('eatmap_pinned_res', JSON.stringify(res)); closeInviteModal(); showAppAlert("完了", "予約メモを固定しました！"); }
    function toggleFav(btn, s){ doVibrate(40); let f = JSON.parse(localStorage.getItem('eatmap_favs')||'[]'); const idx = f.findIndex(x=>x.name===s.name); if(idx>-1){ f.splice(idx,1); btn.innerHTML='♡'; btn.style.color=''; } else { s.visited=false; s.tag=""; f.push(s); btn.innerHTML='♥'; btn.style.color='var(--primary)'; } localStorage.setItem('eatmap_favs', JSON.stringify(f)); }
</script>
"""

# --- ガイド画面 ---
GUIDE_CONTENT = """
<div class="max-w">
<div class="top-bar"><a href="/" class="btn-sm">← ホームへ</a><div style="font-size:13px; font-weight:800; color:var(--muted);">アプリの使い方</div></div>
<div class="card" style="background:linear-gradient(135deg, var(--primary), #e11d48); color:#fff; border:none; margin-bottom:12px;">
    <div style="font-size:20px; font-weight:900; margin-bottom:4px;">🍽️ EAT MAP ガイド</div>
    <div style="font-size:12px; opacity:.95; line-height:1.5;">お店探し・飲み会の幹事・毎日のご飯選びを爆速＆快適にするオールインワンアプリです！</div>
</div>
<div class="card"><h3 style="font-size:14px; font-weight:900; margin:0 0 8px 0; color:var(--primary);">🔍 1. お店探索 ＆ 全画面マップ</h3><ul style="margin:0; padding-left:18px; font-size:12px; font-weight:700; line-height:1.7;"><li><b>通常リスト</b>：見やすい縦スクロールでお店を比較。</li><li><b>⛶ 地図拡大</b>：ボタンを押すと全画面マップになり、スワイプでお店を直感的に探せます。</li><li><b>🗾 地図切替</b>：OSM日本語公式（高精細）と国土地理院（淡色）をワンタップ切替。</li><li><b>アプリ内ルート案内</b>：地図上に直接青い道順が引かれ、徒歩分数を案内します。</li></ul></div>
<div class="card"><h3 style="font-size:14px; font-weight:900; margin:0 0 8px 0; color:var(--blue);">💬 2. ダブルAIコンシェルジュ</h3><ul style="margin:0; padding-left:18px; font-size:12px; font-weight:700; line-height:1.7;"><li><b>Gemini ＋ Groq</b>：2つの無料AIを併用し、途切れることなく自然な会話を実現。</li><li><b>検索直結</b>：会話から最適な店舗検索キーワードをAIが自動抽出します。</li></ul></div>
<div class="card"><h3 style="font-size:14px; font-weight:900; margin:0 0 8px 0; color:var(--purple);">🧮 3. おでかけ・幹事便利ツール</h3><ul style="margin:0; padding-left:18px; font-size:12px; font-weight:700; line-height:1.7;"><li><b>⏰ 終電見張りアラーム</b>：終電時刻の30分前・15分前に通知＆振動。解除も可能。</li><li><b>⏱️ 退席タイマー ＆ 傾斜割り勘</b>：ラストオーダー管理や送金先付きの割り勘計算。</li></ul></div>
<a href="/" class="btn-block btn-primary" style="margin-top:14px;">さっそく使ってみる！</a>
</div>
"""

# --- グルメ記録画面 ---
FAVORITES_CONTENT = """
<div class="max-w">
<div class="top-bar"><div class="brand">📋 グルメ記録</div><div style="display:flex; gap:6px;"><button class="btn-sm btn-yellow" onclick="pickRandomFav()">🎲 ガチャ</button></div></div>
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
        if(f.length===0){ list.innerHTML = `<div class="card" style="text-align:center; color:var(--muted); font-weight:700; padding:30px 10px;">保存したお店がまだありません。</div>`; return; }
        const tags = ["😋絶品", "🔥コスパ", "🍺酒進む", "✨雰囲気"];
        list.innerHTML = f.map((s,i)=>`
            <div class="card" style="display:flex; gap:10px; padding:12px; align-items:center; margin-bottom:0;">
                <div style="width:65px; height:65px; border-radius:10px; overflow:hidden; flex-shrink:0; background:var(--tag); display:flex; align-items:center; justify-content:center; font-size:24px;">${s.photo ? `<img src="${s.photo}" style="width:100%; height:100%; object-fit:cover;" loading="lazy">` : '🍽️'}</div>
                <div style="flex:1; overflow:hidden;">
                    <div style="display:flex; justify-content:space-between; align-items:flex-start;"><h3 style="margin:0 0 4px 0; font-size:13.5px; font-weight:900; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;">${s.name}</h3><button class="btn-icon" style="width:22px; height:22px; min-height:22px; font-size:11px; border-radius:6px; box-shadow:none; border:none; background:var(--tag); color:var(--muted);" onclick="delFav(${i})">✕</button></div>
                    <div style="font-size:10px; color:var(--muted); margin-bottom:6px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;">📍 ${s.address}</div>
                    ${s.visited ? `<div style="display:flex; gap:3px; margin-bottom:6px; overflow-x:auto;">${tags.map(t => `<span style="padding:2px 6px; font-size:9px; border-radius:6px; font-weight:800; cursor:pointer; background:${s.tag===t?'var(--yellow)':'var(--tag)'}; color:${s.tag===t?'#493800':'var(--muted)'};" onclick="setTag(${i}, '${t}')">${t}</span>`).join('')}</div>` : ''}
                    <div style="display:flex; gap:6px;"><button class="btn-sm ${s.visited?'btn-green':'btn-sub'}" style="flex:1; padding:6px 0; font-size:10.5px; margin:0; border:none;" onclick="toggleV(${i})">${s.visited?'🏁 行った！':'🚩 行ってみたい'}</button></div>
                </div>
            </div>`).join('');
    }
    function toggleV(i){ doVibrate(30); let f = JSON.parse(localStorage.getItem('eatmap_favs')); f[i].visited = !f[i].visited; localStorage.setItem('eatmap_favs', JSON.stringify(f)); renderFavs(); }
    function setTag(i, t){ doVibrate(20); let f = JSON.parse(localStorage.getItem('eatmap_favs')); f[i].tag = (f[i].tag === t) ? '' : t; localStorage.setItem('eatmap_favs', JSON.stringify(f)); renderFavs(); }
    function delFav(i){ if(confirm("リストから削除しますか？")){ doVibrate(30); let f = JSON.parse(localStorage.getItem('eatmap_favs')); f.splice(i,1); localStorage.setItem('eatmap_favs', JSON.stringify(f)); renderFavs(); } }
    function pickRandomFav(){ const f = JSON.parse(localStorage.getItem('eatmap_favs')||'[]'); if(f.length===0) return showAppAlert("ご案内", "保存したお店がありません！"); doVibrate([50, 50, 100]); const p = f[Math.floor(Math.random() * f.length)]; showAppAlert("🎲 今日のオススメ！", `【${p.name}】\\nジャンル: ${p.genre}\\n住所: ${p.address}`); }
    window.addEventListener('DOMContentLoaded', renderFavs);
</script>
"""

# --- 抽選画面 ---
GAME_CONTENT = """
<div class="max-w">
<div class="top-bar"><div class="brand">🎯 ルーレット</div><div style="display:flex; gap:6px;"><button class="btn-sm btn-sub" onclick="openWheelEditor()">✏️ 項目を編集</button></div></div>
<div class="card" style="text-align:center; padding:18px 12px; margin-bottom:12px;">
    <div style="position:relative; width:280px; height:280px; margin:0 auto 18px;">
        <div style="position:absolute; top:-12px; left:50%; transform:translateX(-50%); width:0; height:0; border-left:12px solid transparent; border-right:12px solid transparent; border-top:22px solid var(--primary); z-index:20; filter:drop-shadow(0 2px 4px rgba(0,0,0,0.25));"></div>
        <div style="position:absolute; top:50%; left:50%; transform:translate(-50%, -50%); width:44px; height:44px; background:var(--card); border:3px solid var(--primary); border-radius:50%; z-index:15; display:flex; align-items:center; justify-content:center; font-size:18px; box-shadow:0 2px 8px rgba(0,0,0,0.15);">🍽️</div>
        <canvas id="wheel-canvas" width="280" height="280" style="border-radius:50%; box-shadow:var(--shadow); transition:transform 4.5s cubic-bezier(0.15, 0.9, 0.2, 1); will-change:transform;"></canvas>
    </div>
    <button class="btn-block btn-primary" id="spin-btn" style="font-size:16px; min-height:50px;" onclick="spinWheel()">🎯 ルーレットを回す！</button>
</div>
<div class="card" id="result-box" style="display:none; text-align:center; background:var(--primary-light); border-color:var(--primary);"><div style="font-size:12px; font-weight:800; color:var(--muted);">当選結果</div><div style="font-size:26px; font-weight:900; color:var(--primary); margin:8px 0;" id="res-val">--</div><a href="#" id="res-search-btn" class="btn-block btn-green" style="display:none; margin:8px auto 0;">🔍 このジャンルでお店を探す ↗</a></div>
<div id="wheel-edit-modal" style="display:none; position:fixed; top:0; left:0; width:100vw; height:100vh; background:rgba(0,0,0,0.75); z-index:99999; justify-content:flex-end; align-items:center; padding:14px; flex-direction:column;">
    <div class="card swipe-modal-content" style="width:100%; max-width:440px; max-height:85vh; display:flex; flex-direction:column; margin:0 0 env(safe-area-inset-bottom); background:var(--card); padding:16px;">
        <div class="swipe-handle"></div>
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:12px;"><span style="font-size:15px; font-weight:900;">✏️ ルーレット項目の編集</span><button onclick="closeWheelEditor()" style="background:none; border:none; font-size:18px; cursor:pointer; color:var(--text);">✕</button></div>
        <div id="wheel-items-container" style="overflow-y:auto; flex:1; margin-bottom:12px; padding-right:4px;"></div>
        <button class="btn-block btn-sub" style="min-height:40px; font-size:13px; margin-bottom:10px;" onclick="addWheelRow()">＋ 項目を追加</button>
        <div style="display:grid; grid-template-columns:1fr 1fr; gap:8px;"><button class="btn-block btn-sub" style="min-height:42px; margin:0;" onclick="resetWheelPreset()">初期値</button><button class="btn-block btn-primary" style="min-height:42px; margin:0;" onclick="saveWheelEditor()">保存する</button></div>
    </div>
</div>
</div>
<script>
    let wheelItems = JSON.parse(localStorage.getItem('eat_custom_wheel') || '["焼肉 🥩","居酒屋 🍺","カフェ ☕","ラーメン 🍜","海鮮 🐟","カレー 🍛","イタリアン 🍕","中華 🥟"]');
    const wheelColors = ["#ffc9c9","#ffe3a8","#fff3bf","#bbf7d0","#c5f6fa","#d0ebff","#dbe4ff","#f3d9fa"]; let curDeg = 0, isSpinning = false;
    function drawCanvas() { const canvas = document.getElementById('wheel-canvas'); if(!canvas) return; const ctx = canvas.getContext('2d'); ctx.clearRect(0, 0, 280, 280); const num = wheelItems.length, arc = (2 * Math.PI) / num; for(let i=0; i<num; i++){ const a = i * arc; ctx.fillStyle = wheelColors[i % wheelColors.length]; ctx.beginPath(); ctx.arc(140, 140, 136, a, a + arc, false); ctx.arc(140, 140, 0, a + arc, a, true); ctx.fill(); ctx.save(); ctx.strokeStyle = "rgba(255,255,255,0.85)"; ctx.lineWidth = 2; ctx.stroke(); ctx.fillStyle = "#2d3142"; ctx.font = "bold 12.5px -apple-system, sans-serif"; ctx.translate(140 + Math.cos(a + arc/2) * 88, 140 + Math.sin(a + arc/2) * 88); ctx.rotate(a + arc/2 + Math.PI/2); ctx.fillText(wheelItems[i], -ctx.measureText(wheelItems[i]).width / 2, 0); ctx.restore(); } }
    function spinWheel(){ if(isSpinning) return; isSpinning = true; document.getElementById('spin-btn').disabled = true; document.getElementById('result-box').style.display = 'none'; let vibs = 0; const vTimer = setInterval(() => { doVibrate(20); if(++vibs > 14) clearInterval(vTimer); }, 250); curDeg += 360 * 5 + Math.floor(Math.random() * 360); document.getElementById('wheel-canvas').style.transform = `rotate(${curDeg}deg)`; setTimeout(() => { isSpinning = false; document.getElementById('spin-btn').disabled = false; doVibrate([100, 50, 100]); const deg = curDeg % 360; const step = 360 / wheelItems.length; const idx = Math.floor((360 - deg + 270) % 360 / step); const picked = wheelItems[idx]; document.getElementById('res-val').innerText = picked; const clean = picked.replace(/[^\\u4E00-\\u9FFF\\u3040-\\u309F\\u30A0-\\u30FAa-zA-Z]/g, '').trim(); const sBtn = document.getElementById('res-search-btn'); if(clean){ sBtn.style.display = 'inline-flex'; sBtn.href = `/search?keyword=${encodeURIComponent(clean)}`; } else { sBtn.style.display = 'none'; } document.getElementById('result-box').style.display = 'block'; }, 4500); }
    function openWheelEditor(){ doVibrate(30); renderWheelEditorRows(); document.getElementById('wheel-edit-modal').style.display = 'flex'; }
    function closeWheelEditor(){ document.getElementById('wheel-edit-modal').style.display = 'none'; }
    function renderWheelEditorRows(){ document.getElementById('wheel-items-container').innerHTML = wheelItems.map((item, idx) => `<div style="display:flex; gap:6px; margin-bottom:8px; align-items:center;"><input type="text" class="wheel-row-input" value="${item}" maxlength="20" style="flex:1; padding:10px 12px; border:1.5px solid var(--border); border-radius:10px; font-size:13px; font-weight:700; outline:none;"><button type="button" class="btn-icon" style="width:36px; height:36px; color:var(--primary);" onclick="removeWheelRow(${idx})">✕</button></div>`).join(''); }
    function addWheelRow(){ doVibrate(20); collectCurrentInputs(); wheelItems.push("新しい項目 ✨"); renderWheelEditorRows(); }
    function removeWheelRow(idx){ doVibrate(30); collectCurrentInputs(); if(wheelItems.length <= 2) return showAppAlert("エラー", "項目は最低2つ必要です"); wheelItems.splice(idx, 1); renderWheelEditorRows(); }
    function collectCurrentInputs(){ const list = []; document.querySelectorAll('.wheel-row-input').forEach(inp => { const v = inp.value.trim(); if(v) list.push(v); }); if(list.length > 0) wheelItems = list; }
    function saveWheelEditor(){ doVibrate(40); collectCurrentInputs(); if(wheelItems.length < 2) return showAppAlert("エラー", "2つ以上の項目を入力してください"); localStorage.setItem('eat_custom_wheel', JSON.stringify(wheelItems)); drawCanvas(); closeWheelEditor(); showAppAlert("完了", "保存しました！"); }
    function resetWheelPreset(){ if(confirm("初期化しますか？")){ wheelItems = ["焼肉 🥩","居酒屋 🍺","カフェ ☕","ラーメン 🍜","海鮮 🐟","カレー 🍛","イタリアン 🍕","中華 🥟"]; renderWheelEditorRows(); } }
    window.addEventListener('DOMContentLoaded', () => { drawCanvas(); enableSwipeToClose('wheel-edit-modal', closeWheelEditor); });
</script>
"""

# --- ツール画面 ---
TOOLS_CONTENT = """
<div class="max-w">
<div class="top-bar"><div class="brand">🧮 おでかけツール</div><button class="btn-sm" id="btn-notify-perm" onclick="requestNotification()">🔔 通知をON</button></div>
<div class="card" style="border-color:var(--purple); background:var(--card);">
    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;"><span style="font-size:12px; font-weight:800; color:var(--purple);">⏰ 終電見張りアラーム</span><span id="train-status" style="font-size:11px; font-weight:800; color:var(--muted);">未設定</span></div>
    <div style="display:flex; gap:6px; align-items:center;"><input type="time" id="train-time" style="padding:8px 10px; border:1.5px solid var(--border); border-radius:10px; font-size:14px; font-weight:800; background:var(--input); color:var(--text); outline:none;"><button class="btn-sm btn-purple" style="flex:1; justify-content:center;" onclick="setTrainAlarm()">セット</button><button class="btn-sm btn-sub" style="justify-content:center; padding:8px 10px;" onclick="cancelTrainAlarm()">解除</button></div>
</div>
<div class="card">
    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:10px;"><span style="font-size:12px; font-weight:800; color:var(--muted);">⏱️ 席・コース時間管理</span><span id="current-clock" style="font-size:12px; font-weight:800; color:var(--primary);">--:--</span></div>
    <div style="display:grid; grid-template-columns: 1fr 1fr; gap:8px; margin-bottom:10px;"><div style="background:var(--tag); padding:12px; border-radius:12px; text-align:center;"><div style="font-size:11px; font-weight:800; color:var(--muted);">🍺 ラストオーダー</div><div style="font-size:26px; font-weight:900; font-family:monospace; color:var(--yellow);" id="timer-lo">--:--</div></div><div style="background:var(--tag); padding:12px; border-radius:12px; text-align:center;"><div style="font-size:11px; font-weight:800; color:var(--muted);">🚪 完全退席</div><div style="font-size:26px; font-weight:900; font-family:monospace; color:var(--primary);" id="timer-exit">--:--</div></div></div>
    <div style="display:flex; gap:6px; margin-bottom:6px;"><button class="btn-sm" style="flex:1;" onclick="setTimer(90, 60)">90分(LO60)</button><button class="btn-sm" style="flex:1;" onclick="setTimer(120, 90)">120分(LO90)</button><button class="btn-sm" style="flex:1;" onclick="setTimer(180, 150)">180分</button></div>
    <div style="display:flex; gap:6px;"><button class="btn-sm btn-primary" style="flex:1;" onclick="toggleTimer()" id="btn-timer-run">タイマー開始</button><button class="btn-sm" onclick="resetTimer()">リセット</button></div>
</div>
<div class="card">
    <div style="font-size:12px; font-weight:800; color:var(--muted); margin-bottom:10px;">💸 傾斜割り勘計算</div>
    <div class="input-group"><input type="number" id="split-total" placeholder="合計お会計 (円)"></div>
    <div style="display:grid; grid-template-columns: 1fr 1fr; gap:8px;"><div class="input-group"><input type="number" id="split-drinkers" value="2" placeholder="飲む人"><small style="font-size:11px; font-weight:700; color:var(--muted);">飲む人数</small></div><div class="input-group"><input type="number" id="split-nondrinkers" value="1" placeholder="飲まない人"><small style="font-size:11px; font-weight:700; color:var(--muted);">飲まない人数</small></div></div>
    <div style="display:grid; grid-template-columns: 1fr 1fr; gap:8px;"><div class="input-group"><input type="number" id="split-discount" value="1000" placeholder="割引額"><small style="font-size:11px; font-weight:700; color:var(--muted);">飲まない人の割引額 (円引)</small></div><div class="input-group"><input type="number" id="split-kanji" value="0" placeholder="幹事負担"><small style="font-size:11px; font-weight:700; color:var(--muted);">幹事の追加負担 (円)</small></div></div>
    <div style="display:flex; gap:6px; margin-bottom:10px; align-items:center;"><span style="font-size:11px; font-weight:800; color:var(--muted);">端数丸め:</span><button class="btn-sm round-btn" id="rnd-100" onclick="setRound(100)" style="flex:1; background:var(--primary); color:#fff; border-color:var(--primary);">100円</button><button class="btn-sm round-btn" id="rnd-500" onclick="setRound(500)" style="flex:1;">500円</button><button class="btn-sm round-btn" id="rnd-1000" onclick="setRound(1000)" style="flex:1;">1000円</button></div>
    <button class="btn-block btn-primary" onclick="calcSplit()">割り勘を計算する</button>
    <div id="split-res" style="display:none; background:var(--tag); padding:12px; border-radius:12px; margin-top:10px; font-size:13px; font-weight:700;">
        <div style="display:flex; justify-content:space-between; margin-bottom:6px;"><span>🍺 飲む人:</span><b style="color:var(--primary); font-size:16px;" id="res-drinker">0円</b></div>
        <div style="display:flex; justify-content:space-between; margin-bottom:6px;" id="box-nondrinker"><span>🍵 飲まない人:</span><b style="color:var(--green); font-size:16px;" id="res-nondrinker">0円</b></div>
        <div style="font-size:11px; color:var(--muted); text-align:right;" id="res-diff">余剰: 0円</div>
        <div class="input-group" style="margin-top:8px;"><input type="text" id="paypay-link" placeholder="送金先PayPay ID・リンク (任意)"></div>
        <div style="display:flex; gap:6px; margin-top:8px;"><button class="btn-sm" style="flex:1;" onclick="copySplitText()">📋 コピー</button><button class="btn-sm btn-green" style="flex:1;" onclick="shareSplit()">💬 LINE共有</button></div>
    </div>
</div>
</div>
<script>
    setInterval(() => { document.getElementById('current-clock').innerText = new Date().toTimeString().split(' ')[0].substring(0, 5); checkTrainCountdown(); }, 1000);
    let targetTrainDate = null, warned30 = false, warned15 = false;
    function setTrainAlarm(){ doVibrate(30); const val = document.getElementById('train-time').value; if(!val) return showAppAlert("エラー", "時刻を選択してください"); const parts = val.split(':'); const now = new Date(); const d = new Date(now.getFullYear(), now.getMonth(), now.getDate(), parseInt(parts[0]), parseInt(parts[1]), 0); if(d < now) d.setDate(d.getDate() + 1); targetTrainDate = d; warned30 = false; warned15 = false; showAppAlert("完了", `終電を【${val}】にセットしました！`); checkTrainCountdown(); }
    function cancelTrainAlarm(){ doVibrate(30); targetTrainDate = null; document.getElementById('train-time').value = ''; const st = document.getElementById('train-status'); st.innerText = '未設定'; st.style.color = 'var(--muted)'; showAppAlert("解除完了", "アラームを解除しました。"); }
    function checkTrainCountdown(){ if(!targetTrainDate) return; const diffMs = targetTrainDate - new Date(); const st = document.getElementById('train-status'); if(diffMs <= 0){ st.innerText = "時刻を過ぎました！"; st.style.color = "var(--primary)"; showAppAlert("⚠️", "終電の時刻です！"); targetTrainDate = null; return; } const diffMin = Math.floor(diffMs / 60000); st.innerText = `残り ${diffMin}分${Math.floor((diffMs % 60000) / 1000)}秒`; st.style.color = "var(--purple)"; if(diffMin === 30 && !warned30){ warned30 = true; showAppAlert("アラーム", "終電まで残り30分です！"); } if(diffMin === 15 && !warned15){ warned15 = true; showAppAlert("アラーム", "終電まで残り15分！準備を！"); } }
    let exitSec = 7200, loSec = 5400, timerId = null, running = false, roundUnit = 100;
    function setTimer(ex, lo) { exitSec = ex * 60; loSec = lo * 60; updateTimerUI(); }
    function setRound(u){ roundUnit = u; document.querySelectorAll('.round-btn').forEach(b=>{ b.style.background='var(--tag)'; b.style.color='var(--text)'; b.style.borderColor='var(--border)'; }); const active = document.getElementById('rnd-'+u); active.style.background='var(--primary)'; active.style.color='#fff'; active.style.borderColor='var(--primary)'; if(document.getElementById('split-res').style.display==='block') calcSplit(); }
    function requestNotification() { if (!("Notification" in window)) { document.getElementById('btn-notify-perm').style.display = 'none'; return showAppAlert("ご案内", "ポップアップでお知らせします。"); } Notification.requestPermission().then(p => { if(p === 'granted') { document.getElementById('btn-notify-perm').innerText = "🔔 通知ON済み"; showAppAlert("完了", "通知をONにしました！"); } }); }
    window.addEventListener('DOMContentLoaded', ()=>{ if (!("Notification" in window)) document.getElementById('btn-notify-perm').style.display = 'none'; });
    function toggleTimer() { doVibrate(30); running = !running; const b = document.getElementById('btn-timer-run'); if(running) { b.innerText = "停止"; timerId = setInterval(() => { if(exitSec > 0) exitSec--; if(loSec > 0) loSec--; if (loSec === 0) showAppAlert("タイマー", "🍺 ラストオーダーの時間です！"); if (exitSec === 0) { showAppAlert("タイマー", "🚪 お席の終了時間です！"); clearInterval(timerId); } updateTimerUI(); }, 1000); } else { b.innerText = "再開"; clearInterval(timerId); } }
    function resetTimer() { doVibrate(30); running = false; clearInterval(timerId); document.getElementById('btn-timer-run').innerText = "タイマー開始"; setTimer(120, 90); }
    function updateTimerUI() { document.getElementById('timer-lo').innerText = `${String(Math.floor(loSec/60)).padStart(2,'0')}:${String(loSec%60).padStart(2,'0')}`; document.getElementById('timer-exit').innerText = `${String(Math.floor(exitSec/60)).padStart(2,'0')}:${String(exitSec%60).padStart(2,'0')}`; }
    updateTimerUI();
    let splitData = null;
    function calcSplit() { doVibrate(30); const tot = parseInt(document.getElementById('split-total').value)||0, dr = parseInt(document.getElementById('split-drinkers').value)||0, ndr = parseInt(document.getElementById('split-nondrinkers').value)||0, disc = parseInt(document.getElementById('split-discount').value)||0, kj = parseInt(document.getElementById('split-kanji').value)||0; const num = dr + ndr; if(!tot || num <= 0) return showAppAlert("エラー", "金額と人数を入力してください"); const adj = tot - kj + (disc * ndr); const base = Math.ceil((adj / num) / roundUnit) * roundUnit; const nonBase = Math.max(0, base - disc); const collected = (base * dr) + (nonBase * ndr) + kj; document.getElementById('res-drinker').innerText = `${base.toLocaleString()} 円`; document.getElementById('res-nondrinker').innerText = `${nonBase.toLocaleString()} 円`; document.getElementById('res-diff').innerText = `集金合計: ${collected.toLocaleString()}円 (お釣り: ${collected - tot}円)`; document.getElementById('split-res').style.display = 'block'; splitData = { tot, dr, ndr, base, nonBase, kj }; }
    function copySplitText() { doVibrate(30); const pay = document.getElementById('paypay-link').value.trim(); let msg = `🍻 お会計\\n合計: ${splitData.tot.toLocaleString()}円\\n---\\n・飲む人: 各 ${splitData.base.toLocaleString()}円 (${splitData.dr}名)\\n` + (splitData.ndr>0 ? `・飲まない人: 各 ${splitData.nonBase.toLocaleString()}円 (${splitData.ndr}名)\\n` : "") + (pay ? `\\n💰 送金先: ${pay}\\n` : ""); if(navigator.clipboard) navigator.clipboard.writeText(msg).then(() => showAppAlert("完了", "コピーしました！")); else prompt("コピー:", msg); }
</script>
"""

# --- AI相談画面 ---
CHAT_CONTENT = """
<style>.msg { max-width:85%; padding:10px 14px; border-radius:16px; font-size:13.5px; font-weight:700; line-height:1.6; word-wrap:break-word; } .msg-ai { background:var(--tag); border-top-left-radius:4px; color:var(--text); margin-right:auto; } .msg-user { background:var(--primary); border-top-right-radius:4px; color:#fff; margin-left:auto; } .chat-box { display:flex; flex-direction:column; gap:12px; padding:14px; overflow-y:auto; height:52vh; background:var(--card); border:1.5px solid var(--border); border-radius:18px; margin-bottom:10px; } .s-btn { display:inline-flex; align-items:center; gap:4px; background:var(--primary); color:#fff; padding:6px 12px; border-radius:10px; font-size:11.5px; font-weight:800; text-decoration:none; margin-top:8px; box-shadow:var(--shadow); border:none; } .chip-bar { display:flex; gap:6px; overflow-x:auto; padding-bottom:8px; margin-bottom:8px; -webkit-overflow-scrolling:touch; } .q-chip { background:var(--tag); border:1.5px solid var(--border); border-radius:16px; padding:6px 12px; font-size:11.5px; font-weight:800; color:var(--text); white-space:nowrap; cursor:pointer; }</style>
<div class="max-w">
<div class="top-bar"><div class="brand">💬 AIコンシェルジュ</div></div>
<div class="chat-box" id="box"><div style="display:flex; gap:8px; align-items:flex-start;"><div style="font-size:24px;">🤖</div><div class="msg msg-ai">お店探しのお手伝いをします✨<br>「胃に優しいものが食べたい」「元気が出そうなお肉」など何でも相談してください！</div></div></div>
<div class="chip-bar"><button class="q-chip" onclick="askChip('胃に優しいもの')">🍵 胃に優しいもの</button><button class="q-chip" onclick="askChip('元気になれるスタミナ料理')">🔥 元気が出るスタミナ</button><button class="q-chip" onclick="askChip('姫路駅近くで喫煙できる個室居酒屋')">🚬 喫煙可の個室居酒屋</button><button class="q-chip" onclick="askChip('深夜営業しているおすすめシメ飯')">🍜 深夜の背徳シメ飯</button></div>
<div style="display:flex; gap:8px;"><input type="text" id="inp" maxlength="80" placeholder="相談を入力..." style="flex:1; padding:13px 14px; border:1.5px solid var(--border); border-radius:12px; font-size:14px; background:var(--input); color:var(--text); font-weight:700; outline:none;" onkeypress="if(event.key==='Enter') send()"><button class="btn-primary" style="width:60px; border-radius:12px; border:none; font-weight:800; cursor:pointer;" onclick="send()" id="s-btn">送信</button></div>
</div>
<script>
    const box = document.getElementById('box'), inp = document.getElementById('inp'), btn = document.getElementById('s-btn');
    function askChip(txt) { inp.value = txt; send(); }
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
            const sKw = encodeURIComponent(d.keyword || txt.replace(/[教えて|おすすめ|探して|の|近く]/g, ' ').trim() || txt);
            box.innerHTML += `<div style="display:flex; gap:8px; align-items:flex-start;"><div style="font-size:24px;">🤖</div><div class="msg msg-ai">${clean}<br><a href="/search?keyword=${sKw}" class="s-btn">🔍 この条件で探す ↗</a></div></div>`;
        } catch(e) {
            document.getElementById(wId).remove();
            box.innerHTML += `<div style="text-align:center; color:var(--primary); font-size:12px; font-weight:800;">⚠️ 通信エラーが発生しました</div>`;
        }
        btn.disabled = false;
        box.scrollTop = box.scrollHeight;
    }
</script>
"""

# ================= 5. バックエンドAPI & ルーティング =================

def fetch_shops(keyword="", area="", lat=None, lng=None, smoking=False, private_room=False, free_drink=False, midnight=False, pref_fish=False, pref_meat=False, pref_spicy=False):
    if not HOTPEPPER_API_KEY or "ここに" in HOTPEPPER_API_KEY:
        return DEFAULT_SHOPS
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

    try:
        url = f"https://webservice.recruit.co.jp/hotpepper/gourmet/v1/?{urllib.parse.urlencode(params)}"
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=5) as res:
            data = json.loads(res.read().decode('utf-8'))
            results = []
            for s in data.get("results", {}).get("shop", []):
                b_name = (s.get("budget") or {}).get("name", "要確認")
                min_b = 3000
                m = re.search(r'(\\d[\\d,]*)(円)?', b_name)
                if m: min_b = int(m.group(1).replace(',', ''))
                has_pr = bool(s.get("private_room") and "あり" in s.get("private_room"))
                has_fd = bool(s.get("free_drink") and "あり" in s.get("free_drink"))
                non_sm = s.get("non_smoking", "")
                if "全面禁煙" in non_sm: sm_info = "🚭 全面禁煙"
                elif "一部禁煙" in non_sm or "分煙" in non_sm: sm_info = "🚬 分煙"
                elif "喫煙可" in non_sm or "禁煙席なし" in non_sm: sm_info = "🚬 喫煙可"
                else: sm_info = "🚬 喫煙可" if smoking else "🚭 禁煙"
                results.append({
                    "name": s.get("name", "店舗名不明"), "genre": (s.get("genre") or {}).get("name", "グルメ"),
                    "address": s.get("address", ""), "budget": b_name, "min_budget": min_b,
                    "lat": s.get("lat"), "lng": s.get("lng"), "tel": s.get("tel", "0000000000"),
                    "open": s.get("open", ""), "access": s.get("access", ""),
                    "has_private": has_pr, "smoking_info": sm_info, "has_free_drink": has_fd,
                    "url": (s.get("urls") or {}).get("pc", "#"), "photo": ((s.get("photo") or {}).get("pc") or {}).get("l", "")
                })
            return results or DEFAULT_SHOPS
    except Exception: return DEFAULT_SHOPS

@app.route('/ping')
def ping(): return "OK", 200

@app.route('/')
def home(): return render_page(HOME_CONTENT)

@app.route('/guide')
def guide(): return render_page(GUIDE_CONTENT)

@app.route('/search')
def search():
    k = html.escape(request.args.get('keyword', '')[:40])
    a = html.escape(request.args.get('area', '')[:40])
    smoking, private_room, free_drink, midnight, pref_fish, pref_meat, pref_spicy = [(request.args.get(x) == '1') for x in ['smoking','private_room','free_drink','midnight','pref_fish','pref_meat','pref_spicy']]
    try:
        lat_val = float(request.args.get('lat')) if request.args.get('lat') else None
        lng_val = float(request.args.get('lng')) if request.args.get('lng') else None
    except (ValueError, TypeError): lat_val, lng_val = None, None

    tags = []
    if smoking: tags.append("喫煙可")
    if private_room: tags.append("個室")
    if free_drink: tags.append("飲み放題")
    if midnight: tags.append("深夜")
    tag_str = f"({'/'.join(tags)})" if tags else ""
    title = f"{a} {k} {tag_str}".strip() or "おすすめ店舗"
    
    shops = fetch_shops(keyword=k, area=a, lat=lat_val, lng=lng_val, smoking=smoking, private_room=private_room, free_drink=free_drink, midnight=midnight, pref_fish=pref_fish, pref_meat=pref_meat, pref_spicy=pref_spicy)
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

@app.route('/api/chat', methods=['POST'])
def api_chat():
    req_json = request.get_json(silent=True) or {}
    raw_msg = str(req_json.get('message', ''))[:80].strip()
    msg = html.escape(raw_msg)
    
    if msg in AI_CACHE:
        return jsonify(AI_CACHE[msg])
        
    clean_reply = None
    search_keyword = None

    prompt = (
        f"あなたは飲食店探しアプリ「EAT MAP」の親身な専属コンシェルジュです。"
        f"ユーザーの言葉「{msg}」に日本語敬語で寄り添い、具体的な料理やお店の選び方を80文字以内で親切に提案してください。"
        f"返答の最後に店舗検索に最適なキーワードを「【SEARCH:キーワード】」という形式で必ず1つ付けてください。"
    )

    # --- 1. Gemini API呼び出し (第1候補) ---
    if GEMINI_API_KEY:
        gemini_payload = json.dumps({
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"maxOutputTokens": 120, "temperature": 0.5}
        }).encode('utf-8')
        
        headers = {'Content-Type': 'application/json', 'x-goog-api-key': GEMINI_API_KEY, 'User-Agent': 'Mozilla/5.0'}
        for model_name in ["gemini-1.5-flash", "gemini-flash-latest", "gemini-2.0-flash"]:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={urllib.parse.quote(GEMINI_API_KEY)}"
            try:
                req = urllib.request.Request(url, data=gemini_payload, headers=headers)
                with urllib.request.urlopen(req, timeout=5) as res:
                    r_data = json.loads(res.read().decode('utf-8'))
                    raw_text = r_data['candidates'][0]['content']['parts'][0]['text']
                    kw_match = re.search(r'【SEARCH:(.*?)】', raw_text)
                    if kw_match:
                        search_keyword = kw_match.group(1).strip()
                        raw_text = re.sub(r'【SEARCH:.*?】', '', raw_text)
                    clean_reply = raw_text.replace("**", "").replace("*", "").strip()
                    if clean_reply: break
            except Exception:
                continue

    # --- 2. Groq API呼び出し (第2候補・完全無料高速AI) ---
    if not clean_reply and GROQ_API_KEY:
        groq_payload_dict = {
            "model": "llama-3.3-70b-versatile",
            "messages": [
                {"role": "system", "content": "あなたは飲食店探しアプリ「EAT MAP」の親身な専属コンシェルジュです。ユーザーの言葉に寄り添い、具体的な料理やお店の選び方を80文字以内で親切に提案してください。返答の最後に店舗検索に最適なキーワードを「【SEARCH:キーワード】」という形式で必ず1つ付けてください。"},
                {"role": "user", "content": msg}
            ],
            "max_tokens": 120,
            "temperature": 0.5
        }
        
        groq_headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {GROQ_API_KEY}',
            'User-Agent': 'Mozilla/5.0'
        }
        
        for g_model in ["llama-3.3-70b-versatile", "llama-3.1-8b-instant"]:
            try:
                groq_payload_dict["model"] = g_model
                req = urllib.request.Request("https://api.groq.com/openai/v1/chat/completions", data=json.dumps(groq_payload_dict).encode('utf-8'), headers=groq_headers)
                with urllib.request.urlopen(req, timeout=5) as res:
                    g_res = json.loads(res.read().decode('utf-8'))
                    raw_text = g_res['choices'][0]['message']['content']
                    kw_match = re.search(r'【SEARCH:(.*?)】', raw_text)
                    if kw_match:
                        search_keyword = kw_match.group(1).strip()
                        raw_text = re.sub(r'【SEARCH:.*?】', '', raw_text)
                    clean_reply = raw_text.replace("**", "").replace("*", "").strip()
                    if clean_reply: break
            except Exception:
                continue

    # --- 3. 内蔵スマート対話エンジン (第3候補・安全ネット) ---
    if not clean_reply:
        m_lower = msg.lower()
        if any(w in m_lower for w in ["胃", "優し", "消化", "あっさり", "お腹", "調子悪"]):
            clean_reply = "お腹やお身体がお疲れ気味ですか？無理なさらないでくださいね。温かい出汁うどんや雑炊、身体に染みる和食定食はいかがでしょう🍵"
            search_keyword = "うどん 雑炊 和食"
        elif any(w in m_lower for w in ["元気", "スタミナ", "肉", "ガッツリ", "焼肉", "ステーキ"]):
            clean_reply = "元気をしっかりチャージですね！香ばしい炭火焼肉や肉汁たっぷりの餃子、スタミナ満点のご飯でパワーをつけましょう🔥"
            search_keyword = "焼肉 餃子 ステーキ"
        elif any(w in m_lower for w in ["疲", "つかれ", "しんど", "眠", "帰る", "癒"]):
            clean_reply = "今日もお疲れさまでした✨ 落ち着いた個室でゆっくりお酒を嗜むか、ほっと温まる定食やお鍋で一息つきませんか？🍶"
            search_keyword = "居酒屋 個室 和食"
        elif any(w in m_lower for w in ["デート", "おしゃれ", "バル", "ワイン", "記念", "イタリアン"]):
            clean_reply = "素敵な時間になりますように✨ 照明が落ち着いたワインバルや、旬の素材が美味しいおしゃれなイタリアンがおすすめです🍷"
            search_keyword = "イタリアン バル 個室"
        elif any(w in m_lower for w in ["吸える", "喫煙", "たばこ", "タバコ"]):
            clean_reply = "ゆったり一服できるお店をお探しですね🚬 席で喫煙可能、または喫煙ブース完備の快適な居酒屋をご案内します！"
            search_keyword = "居酒屋 喫煙"
        elif any(w in m_lower for w in ["二次会", "2次会", "深夜", "シメ", "終電", "もう一軒"]):
            clean_reply = "まだまだ夜はこれからですね！サクッと飲めるバーや、背徳感たっぷりの深夜ラーメン、夜パフェはいかがですか？🍜"
            search_keyword = "バー ラーメン 深夜"
        elif any(w in m_lower for w in ["カフェ", "スイーツ", "休憩", "甘い", "コーヒー"]):
            clean_reply = "ちょっと一息カフェタイムですね☕ こだわりのコーヒーや美味しいスイーツで、まったり過ごせるお店を探しましょう✨"
            search_keyword = "カフェ スイーツ"
        else:
            clean_reply = f"「{msg}」ですね！今すぐ行きたくなる素敵なお店をピックアップしてご案内しますね🍽️"
            search_keyword = re.sub(r'[教えて|おすすめ|探して|の|近く|食べたい]', ' ', msg).strip() or msg

    res_payload = {"reply": clean_reply, "keyword": search_keyword or msg}
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

@app.route('/sw.js')
def sw(): return Response("self.addEventListener('fetch', e => {});", mimetype="application/javascript")

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
