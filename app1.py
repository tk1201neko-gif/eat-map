# ==============================================================================
# 【EAT MAP】OpenStreetMap切り替え＆視認性強化完全版 app1.py
# ==============================================================================
import os, urllib.request, urllib.parse, json, re, time, gzip, html, base64, socket, math
from collections import defaultdict
from flask import Flask, request, render_template_string, jsonify, Response

# クラウド(Render)のIPv6遅延・名前解決タイムアウトを完全防止
_orig_gai = socket.getaddrinfo
socket.getaddrinfo = lambda *args, **kwargs: [r for r in _orig_gai(*args, **kwargs) if r[0] == socket.AF_INET] or _orig_gai(*args, **kwargs)

app = Flask(__name__)

# --- APIキーの設定 ---
HOTPEPPER_API_KEY   = os.environ.get("HOTPEPPER_API_KEY", "").strip()
MAPBOX_ACCESS_TOKEN = os.environ.get("MAPBOX_ACCESS_TOKEN", "").strip()

# Gemini APIキー（環境変数優先・フォールバック自動復号）
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
    ip = request.headers.get('X-Forwarded-For', request.remote_addr).split(',')[0].strip()
    now = time.time()
    IP_LOG[ip] = [t for t in IP_LOG[ip] if now - t < 60]
    if len(IP_LOG) > 2000:
        for k in list(IP_LOG.keys()):
            if not IP_LOG[k]: del IP_LOG[k]
    if len(IP_LOG[ip]) >= 100: 
        return "アクセス過多です。少し時間をおいて再試行してください。", 429
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
        "connect-src 'self' https://api.open-meteo.com https://generativelanguage.googleapis.com https://*.openstreetmap.org;"
    )
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

# ================= 2. デフォルト店舗データ =================
DEFAULT_SHOPS = [
    {
        "name": "姫路和食 個室 旬彩庵 (サンプル)", "genre": "居酒屋・個室和食",
        "address": "兵庫県姫路市駅前町100", "budget": "3,500円〜5,000円", "min_budget": 3500,
        "lat": 34.8290, "lng": 134.6900, "tel": "079-000-0002",
        "has_private": True, "smoking_info": "🚬 喫煙可", "has_free_drink": True,
        "photo": "https://images.unsplash.com/photo-1517248135467-4c7edcad34c4?w=600", "url": "https://www.hotpepper.jp/"
    },
    {
        "name": "CAFÉ DE ÉTOILE (サンプル)", "genre": "カフェ・スイーツ",
        "address": "兵庫県姫路市本町68", "budget": "1,000円〜2,000円", "min_budget": 1000,
        "lat": 34.8340, "lng": 134.6930, "tel": "079-000-0001",
        "has_private": False, "smoking_info": "🚭 全席禁煙", "has_free_drink": False,
        "photo": "https://images.unsplash.com/photo-1554118811-1e0d58224f24?w=600", "url": "https://www.hotpepper.jp/"
    },
    {
        "name": "深夜営業 麺処 夜桜 (サンプル)", "genre": "ラーメン・シメ飯",
        "address": "兵庫県姫路市魚町1-1", "budget": "1,000円〜2,000円", "min_budget": 1000,
        "lat": 34.8315, "lng": 134.6880, "tel": "079-000-0003",
        "has_private": False, "smoking_info": "🚬 喫煙可", "has_free_drink": False,
        "photo": "https://images.unsplash.com/photo-1569718212165-3a8278d5f624?w=600", "url": "https://www.hotpepper.jp/"
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
            if ("Notification" in window && Notification.permission === "granted") {
                try { new Notification(title, { body: message }); } catch(e){}
            }
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
        body { 
            background: var(--bg); color: var(--text); 
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Hiragino Sans", sans-serif;
            margin: 0; padding: 14px 14px 92px; min-height: 100vh;
            -webkit-overflow-scrolling: touch;
        }
        .max-w { max-width: 480px; margin: 0 auto; }
        .card { 
            background: var(--card); border: 1.5px solid var(--border); 
            border-radius: 16px; padding: 14px; margin-bottom: 12px; 
            box-shadow: var(--shadow); position: relative; 
        }
        .top-bar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
        .brand { font-size: 21px; font-weight: 900; color: var(--primary); display: flex; align-items: center; gap: 6px; text-decoration: none; }
        .btn-icon, .btn-sm, .btn-block { 
            cursor: pointer; border-radius: 10px; display: inline-flex; align-items: center; justify-content: center; 
            font-weight: 800; border: 1.5px solid var(--border); text-decoration: none; 
            transition: opacity .15s; 
        }
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
        .input-group input, .input-group select { 
            width: 100%; padding: 12px 14px; border: 1.5px solid var(--border); 
            border-radius: 10px; font-size: 14px; background: var(--input); 
            color: var(--text); outline: none; font-weight: 700; transition: border-color .2s; 
        }
        .input-group input:focus, .input-group select:focus { border-color: var(--primary); }

        .badge { display: inline-flex; align-items: center; gap: 3px; font-size: 10.5px; font-weight: 800; padding: 3px 6px; border-radius: 6px; background: var(--tag); color: var(--text); }
        .badge-primary { background: var(--primary-light); color: var(--primary); }
        .badge-dist { background: #e0f2fe; color: #0284c7; }
        .badge-smoke { background: #fef3c7; color: #92400e; }
        .badge-private { background: #fce7f3; color: #9d174d; }
        .badge-drink { background: #ecfdf5; color: #065f46; }

        .filter-chip {
            background: var(--tag); border: 1.5px solid var(--border); border-radius: 8px;
            padding: 8px 10px; font-size: 11.5px; font-weight: 800; color: var(--text);
            cursor: pointer; display: flex; align-items: center; justify-content: center; gap: 4px;
            user-select: none; transition: background .15s;
        }
        .filter-chip.active { background: var(--primary-light); border-color: var(--primary); color: var(--primary); }

        .bottom-nav { 
            position: fixed; bottom: 0; left: 0; width: 100%; 
            background: var(--card); border-top: 1.5px solid var(--border); 
            display: flex; justify-content: space-around; padding: 6px 0 calc(6px + env(safe-area-inset-bottom)); 
            z-index: 1000; box-shadow: 0 -2px 10px rgba(0,0,0,0.03); 
        }
        .bottom-nav a { 
            color: var(--muted); text-decoration: none; font-size: 10px; 
            display: flex; flex-direction: column; align-items: center; 
            gap: 2px; font-weight: 800; width: 20%; 
        }
        .bottom-nav a.active { color: var(--primary); }
        .bottom-nav span.icon { font-size: 20px; }

        #loading-overlay { 
            position: fixed; top: 0; left: 0; width: 100vw; height: 100vh; 
            background: rgba(0,0,0,0.7); 
            display: none; justify-content: center; align-items: center; 
            flex-direction: column; z-index: 9999; 
        }
        .spinner { width: 36px; height: 36px; border: 4px solid rgba(255,255,255,0.2); border-top-color: #fff; border-radius: 50%; animation: spin .8s linear infinite; margin-bottom: 12px; }
        @keyframes spin { 100% { transform: rotate(360deg); } }
        .credit { text-align: center; font-size: 11px; font-weight: 700; color: var(--muted); margin: 20px 0 10px; }
        .credit a { color: var(--primary); text-decoration: none; }
    </style>
</head>
<body>
    <div id="loading-overlay"><div class="spinner"></div><div style="color:#fff; font-size:13px; font-weight:800;">処理中...</div></div>
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

# ================= 4. 各画面コンテンツ =================

# --- 🔰 アプリの機能説明（ガイド）画面 ---
GUIDE_CONTENT = """
<div class="top-bar">
    <a href="/" class="btn-sm">← ホームへ戻る</a>
    <div style="font-size:13px; font-weight:800; color:var(--muted);">アプリの使い方</div>
</div>

<div class="card" style="background:linear-gradient(135deg, var(--primary), #e11d48); color:#fff; border:none; margin-bottom:12px;">
    <div style="font-size:20px; font-weight:900; margin-bottom:4px;">🍽️ EAT MAP ガイド</div>
    <div style="font-size:12px; opacity:.95; line-height:1.5;">お店探し・飲み会の幹事・毎日のご飯選びを爆速＆快適にするオールインワンアプリです！</div>
</div>

<div class="card">
    <h3 style="font-size:14px; font-weight:900; margin:0 0 8px 0; color:var(--primary); display:flex; align-items:center; gap:6px;">
        🔍 1. お店を探す＆深夜シメ飯
    </h3>
    <ul style="margin:0; padding-left:18px; font-size:12px; font-weight:700; line-height:1.7; color:var(--text);">
        <li><b>現在地・二次会一発検索</b>：GPS連動で近くの店舗を瞬時に地図表示。</li>
        <li><b>こだわり条件</b>：🚬喫煙可、🚪個室、🍺飲み放題などをワンタップ指定。</li>
        <li><b>🌙 深夜の背徳シメ飯</b>：夜21時以降は限定ボタンが点灯！シメ飯を即抽出。</li>
        <li><b>📌 今夜の予約メモ</b>：予約情報をホーム最上部に固定。地下で電波が無くても安心！</li>
    </ul>
</div>

<div class="card">
    <h3 style="font-size:14px; font-weight:900; margin:0 0 8px 0; color:var(--blue); display:flex; align-items:center; gap:6px;">
        💬 2. 爆速AIコンシェルジュ
    </h3>
    <ul style="margin:0; padding-left:18px; font-size:12px; font-weight:700; line-height:1.7; color:var(--text);">
        <li><b>待ち時間なしの即答</b>：自然な会話でおすすめのお店や気分に寄り添った案内。</li>
        <li><b>検索直結</b>：AIの返答から「探す」を押せばそのまま地図・一覧へ直行！</li>
    </ul>
</div>

<div class="card">
    <h3 style="font-size:14px; font-weight:900; margin:0 0 8px 0; color:var(--green); display:flex; align-items:center; gap:6px;">
        📋 3. グルメ記録 ＆ 称号育成
    </h3>
    <ul style="margin:0; padding-left:18px; font-size:12px; font-weight:700; line-height:1.7; color:var(--text);">
        <li><b>見やすい画像リスト</b>：保存したお店がサムネイル付きで綺麗に並びます。</li>
        <li><b>訪問EXP・称号</b>：「行った！」を押すとレベルアップ（美食王を目指そう！）。</li>
        <li><b>🎲 保存店ガチャ</b>：「どこ行く？」をランダムに即決。</li>
    </ul>
</div>

<div class="card">
    <h3 style="font-size:14px; font-weight:900; margin:0 0 8px 0; color:var(--purple); display:flex; align-items:center; gap:6px;">
        🧮 4. おでかけ・幹事便利ツール
    </h3>
    <ul style="margin:0; padding-left:18px; font-size:12px; font-weight:700; line-height:1.7; color:var(--text);">
        <li><b>⏰ 終電見張りアラーム</b>：終電時刻の30分前・15分前に通知＆振動。解除もワンタップ！</li>
        <li><b>⏱️ ダブル退席タイマー</b>：ラストオーダーと退席時間を同時にカウントダウン。</li>
        <li><b>💸 傾斜割り勘計算</b>：飲む人/飲まない人の傾斜、端数丸め、LINE共有に対応。</li>
    </ul>
</div>

<div class="card">
    <h3 style="font-size:14px; font-weight:900; margin:0 0 8px 0; color:var(--yellow); display:flex; align-items:center; gap:6px;">
        🎯 5. 万能ルーレット (個別入力エディタ)
    </h3>
    <ul style="margin:0; padding-left:18px; font-size:12px; font-weight:700; line-height:1.7; color:var(--text);">
        <li><b>直感的な項目編集</b>：1行ずつテキスト入力や追加・削除が思い通りに操作可能。</li>
        <li><b>迷ったら回すだけ</b>：おごり役決めや罰ゲームなど、その場で何でも書き換え可能。</li>
    </ul>
</div>

<a href="/" class="btn-block btn-primary" style="margin-top:14px;">さっそく使ってみる！</a>
"""

# --- ホーム画面 ---
HOME_CONTENT = """
<div class="top-bar">
    <a href="/" class="brand">🍽️ EAT MAP</a>
    <div style="display:flex; gap:6px;">
        <a href="/guide" class="btn-icon" title="機能ガイド">❓</a>
        <button class="btn-icon theme-btn" onclick="toggleTheme()" title="テーマ切替">🌙</button>
        <button class="btn-icon" onclick="forceUpdateApp()" title="最新版へ更新">🔄</button>
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

<div id="weather-banner" style="display:none; background:var(--tag); border:1.5px solid var(--blue); padding:10px 14px; border-radius:12px; margin-bottom:12px; font-size:12px; font-weight:800; align-items:center; justify-content:space-between;">
    <div style="display:flex; align-items:center; gap:8px;">
        <span id="w-icon" style="font-size:20px;">☀️</span>
        <div><span id="w-txt">天気取得中...</span><div style="font-size:10px; color:var(--muted);" id="w-temp"></div></div>
    </div>
    <button class="btn-sm" style="background:var(--blue); color:#fff; border:none; display:none;" id="btn-rain" onclick="applyRain()">🌧️ 雨宿り店優先</button>
</div>

<div style="display:grid; grid-template-columns:1fr 1fr; gap:8px; margin-bottom:8px;">
    <button class="btn-block btn-green" onclick="searchLoc()">📍 現在地周辺</button>
    <button class="btn-block btn-yellow" onclick="searchNiji()">🍻 二次会・深夜</button>
</div>

<button class="btn-block" id="btn-midnight-shime" style="background:linear-gradient(135deg, #4f46e5, #9333ea); color:#fff; margin-bottom:12px; font-size:13px;" onclick="searchShime()">
    🍜 深夜の背徳シメ飯を探す (ラーメン・夜パフェ・うどん)
</button>

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
                <select name="budget_filter">
                    <option value="">💰 予算指定なし</option>
                    <option value="2000">〜2,000円 (サク飲み)</option>
                    <option value="4000">〜4,000円 (定番)</option>
                    <option value="6000">〜6,000円 (ご褒美)</option>
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
    
    function toggleChip(el, targetId){
        doVibrate(25);
        const cb = document.getElementById(targetId);
        cb.checked = !cb.checked;
        if(cb.checked) el.classList.add('active');
        else el.classList.remove('active');
    }

    function searchLoc(){
        if(!navigator.geolocation) return alert("GPS非対応です");
        doVibrate(40); showLoad();
        navigator.geolocation.getCurrentPosition(p=>{ 
            window.location.href=`/search?lat=${p.coords.latitude.toFixed(6)}&lng=${p.coords.longitude.toFixed(6)}&area=現在地周辺`; 
        }, ()=>alert("GPSを許可してください"), {timeout:8000});
    }

    function searchNiji(){
        doVibrate(40); showLoad();
        if(navigator.geolocation){
            navigator.geolocation.getCurrentPosition(p=>{ 
                window.location.href=`/search?lat=${p.coords.latitude.toFixed(6)}&lng=${p.coords.longitude.toFixed(6)}&keyword=${encodeURIComponent("二次会 バー 深夜")}&area=現在地&midnight=1`; 
            }, ()=>{ window.location.href=`/search?keyword=${encodeURIComponent("二次会 バー 深夜")}&midnight=1`; }, {timeout:6000});
        } else { window.location.href=`/search?keyword=${encodeURIComponent("二次会 バー 深夜")}&midnight=1`; }
    }

    function searchShime(){
        doVibrate(40); showLoad();
        const kw = "ラーメン うどん 夜パフェ 雑炊 シメ";
        if(navigator.geolocation){
            navigator.geolocation.getCurrentPosition(p=>{ 
                window.location.href=`/search?lat=${p.coords.latitude.toFixed(6)}&lng=${p.coords.longitude.toFixed(6)}&keyword=${encodeURIComponent(kw)}&area=現在地&midnight=1`; 
            }, ()=>{ window.location.href=`/search?keyword=${encodeURIComponent(kw)}&midnight=1`; }, {timeout:6000});
        } else { window.location.href=`/search?keyword=${encodeURIComponent(kw)}&midnight=1`; }
    }

    const curHour = new Date().getHours();
    if(curHour >= 21 || curHour < 5){
        const shimeBtn = document.getElementById('btn-midnight-shime');
        if(shimeBtn){
            shimeBtn.style.boxShadow = "0 0 15px rgba(168, 85, 247, 0.5)";
            shimeBtn.innerHTML = "🌙⚡【深夜限定】背徳のシメ飯を探す (ラーメン・夜パフェ)";
        }
    }

    function checkPinReservation(){
        const res = JSON.parse(localStorage.getItem('eatmap_pinned_res')||'null');
        const box = document.getElementById('pinned-reservation');
        if(res){
            document.getElementById('pin-name').innerText = res.name;
            document.getElementById('pin-detail').innerText = `${res.time || '予約あり'} / ${res.course || '席のみ予約'}`;
            document.getElementById('pin-tel').href = `tel:${res.tel}`;
            document.getElementById('pin-map').href = `https://www.google.com/maps/dir/?api=1&destination=${encodeURIComponent(res.address)}`;
            box.style.display = 'block';
        } else {
            box.style.display = 'none';
        }
    }
    function clearPinReservation(){
        if(confirm("予約メモのピン留めを解除しますか？")){
            localStorage.removeItem('eatmap_pinned_res');
            checkPinReservation();
        }
    }
    window.addEventListener('DOMContentLoaded', checkPinReservation);

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

# --- 検索結果 & 見やすいOpenStreetMap地図（自動ズーム＆現在地青ピン付き） ---
RESULT_CONTENT = """
<div class="top-bar">
    <a href="/" class="btn-sm">← 戻る</a>
    <div style="font-size:13px; font-weight:800; color:var(--muted);">{{ search_title }} ({{ shops|length }}件)</div>
</div>

<div style="display:flex; gap:6px; margin-bottom:10px;">
    <button class="btn-sm sort-tab" id="sort-rec" style="flex:1; justify-content:center; background:var(--primary); color:#fff; border-color:var(--primary);" onclick="sortShops('default')">⭐ おすすめ順</button>
    <button class="btn-sm sort-tab" id="sort-price" style="flex:1; justify-content:center;" onclick="sortShops('price')">💰 予算が安い順</button>
</div>

<div id="map" style="height:230px; width:100%; border-radius:14px; border:1.5px solid var(--border); margin-bottom:12px; box-shadow:var(--shadow);"></div>

<div id="shops-list">
    {% for s in shops %}
    <div class="card shop-card" data-budget="{{ s.min_budget }}" data-lat="{{ s.lat }}" data-lng="{{ s.lng }}">
        <button class="fav-btn" style="position:absolute; top:12px; right:12px; font-size:18px; cursor:pointer; background:var(--card); border:1.5px solid var(--border); border-radius:10px; width:34px; height:34px; display:flex; align-items:center; justify-content:center;" onclick='toggleFav(this, {{ s | tojson }})'>♡</button>
        {% if s.photo %}<img src="{{ s.photo }}" style="width:100%; height:150px; object-fit:cover; border-radius:12px; margin-bottom:10px; background:#222;" loading="lazy">{% endif %}
        
        <h3 class="shop-name" style="font-size:15px; font-weight:900; margin:0 0 6px 0; padding-right:40px; line-height:1.3;"><span style="background:var(--primary); color:#fff; font-size:11px; padding:2px 6px; border-radius:6px; margin-right:4px;">{{ loop.index }}</span>{{ s.name }}</h3>
        
        <div style="display:flex; flex-wrap:wrap; gap:4px; margin-bottom:6px;">
            <span class="badge badge-primary">🏷️ {{ s.genre }}</span>
            <span class="badge">💰 {{ s.budget }}</span>
            <span class="badge badge-dist" id="dist-{{ loop.index0 }}" style="display:none;">📍 計算中...</span>
        </div>

        <div style="display:flex; flex-wrap:wrap; gap:4px; margin-bottom:8px;">
            {% if s.has_private %}<span class="badge badge-private">🚪 個室</span>{% endif %}
            <span class="badge badge-smoke">{{ s.smoking_info }}</span>
            {% if s.has_free_drink %}<span class="badge badge-drink">🍺 飲み放題</span>{% endif %}
        </div>

        <div style="font-size:11.5px; color:var(--muted); margin-bottom:10px; line-height:1.4;">📍 {{ s.address }}</div>
        
        <div style="display:grid; grid-template-columns:1fr 1fr; gap:6px; margin-bottom:6px;">
            <a href="tel:{{ s.tel }}" class="btn-sm" style="justify-content:center; background:#ecfdf5; color:#065f46; padding:10px 0;">📞 電話する</a>
            <a href="{{ s.url }}" target="_blank" class="btn-sm btn-primary" style="justify-content:center; padding:10px 0;">予約・詳細 ↗</a>
        </div>
        
        <div style="display:grid; grid-template-columns:1fr 1fr; gap:6px;">
            <button class="btn-sm btn-sub" style="justify-content:center;" onclick='openInviteModal({{ s | tojson }})'>📅 案内状作成</button>
            <button class="btn-sm btn-sub" style="justify-content:center;" onclick='pinReservation({{ s | tojson }})'>📌 予約メモ登録</button>
        </div>
    </div>
    {% endfor %}
</div>

<!-- 案内状モーダル -->
<div id="invite-modal" style="display:none; position:fixed; top:0; left:0; width:100vw; height:100vh; background:rgba(0,0,0,0.75); z-index:99999; justify-content:center; align-items:center; padding:14px;">
    <div class="card" style="width:100%; max-width:440px; margin:0; background:var(--card);">
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:10px;">
            <span style="font-size:14px; font-weight:900;">📅 LINE幹事案内状を作成</span>
            <button onclick="closeInviteModal()" style="background:none; border:none; font-size:18px; cursor:pointer; color:var(--text);">✕</button>
        </div>
        <div class="input-group"><input type="text" id="inv-time" placeholder="日時 (例: 10月28日(水) 19:30〜)"></div>
        <div class="input-group"><input type="text" id="inv-fee" placeholder="会費 (例: 4,000円 / 割り勘)"></div>
        <div style="font-size:11px; color:var(--muted); margin-bottom:6px;">生成プレビュー:</div>
        <textarea id="inv-preview" rows="6" style="width:100%; border:1.5px solid var(--border); border-radius:10px; font-size:12px; padding:10px; font-family:sans-serif; background:var(--tag); color:var(--text); margin-bottom:10px;"></textarea>
        <div style="display:grid; grid-template-columns:1fr 1fr; gap:8px;">
            <button class="btn-block btn-sub" style="min-height:42px; font-size:13px; margin:0;" onclick="copyInviteText()">📋 コピー</button>
            <button class="btn-block btn-green" style="min-height:42px; font-size:13px; margin:0;" onclick="sendInviteLine()">💬 LINE送信</button>
        </div>
    </div>
</div>

<script>
    let shops = {{ shops | tojson | safe }};
    const lat = (shops.length>0 && shops[0].lat) ? shops[0].lat : 34.8290;
    const lng = (shops.length>0 && shops[0].lng) ? shops[0].lng : 134.6900;
    
    setTimeout(() => {
        const map = L.map('map', {zoomControl:false}).setView([lat, lng], 14);
        L.control.zoom({position:'bottomright'}).addTo(map);

        // 完全無料・APIキー不要のOpenStreetMap公式タイル
        L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
            maxZoom: 19,
            attribution: '&copy; OpenStreetMap'
        }).addTo(map);

        const bounds = [];
        shops.forEach((s, i) => {
            if(s.lat && s.lng){
                bounds.push([s.lat, s.lng]);
                const icon = L.divIcon({
                    className:'',
                    html:`<div style="background:var(--primary); color:#fff; border-radius:50%; border:2px solid #fff; box-shadow:0 2px 6px rgba(0,0,0,0.3); font-size:11px; font-weight:900; display:flex; align-items:center; justify-content:center; width:26px; height:26px;">${i+1}</div>`,
                    iconSize:[26,26], iconAnchor:[13,13]
                });
                L.marker([s.lat, s.lng], {icon}).addTo(map).bindPopup(`<b style="font-size:12px;">${s.name}</b><br><a href="https://www.google.com/maps/dir/?api=1&destination=${encodeURIComponent(s.address)}" target="_blank" style="color:var(--primary); font-size:11px; font-weight:bold;">ルート案内 ↗</a>`);
            }
        });

        // 全店舗がぴったり収まるよう自動ズーム調整
        if(bounds.length > 0){
            map.fitBounds(bounds, {padding: [30, 30], maxZoom: 15});
        }

        // 現在地の青い光る点を描画
        if(navigator.geolocation){
            navigator.geolocation.getCurrentPosition(pos => {
                const uLat = pos.coords.latitude, uLng = pos.coords.longitude;
                const curIcon = L.divIcon({
                    className:'',
                    html:`<div style="background:#0284c7; width:14px; height:14px; border-radius:50%; border:3px solid #fff; box-shadow:0 0 10px rgba(2,132,199,0.9);"></div>`,
                    iconSize:[14,14], iconAnchor:[7,7]
                });
                L.marker([uLat, uLng], {icon: curIcon}).addTo(map).bindPopup("<b>📍 あなたの現在地</b>");
            }, ()=>{}, {timeout:4000});
        }
    }, 100);

    if(navigator.geolocation){
        navigator.geolocation.getCurrentPosition(pos => {
            const uLat = pos.coords.latitude, uLng = pos.coords.longitude;
            shops.forEach((s, idx) => {
                if(s.lat && s.lng){
                    const d = getDistance(uLat, uLng, s.lat, s.lng);
                    const tag = document.getElementById('dist-' + idx);
                    if(tag){
                        const walkMin = Math.ceil(d / 80);
                        tag.innerText = `📍 約${d > 1000 ? (d/1000).toFixed(1)+'km' : Math.round(d)+'m'} (徒歩${walkMin}分)`;
                        tag.style.display = 'inline-flex';
                    }
                }
            });
        }, ()=>{}, {timeout:4000});
    }

    function getDistance(lat1, lon1, lat2, lon2) {
        const R = 6371e3;
        const φ1 = lat1 * Math.PI/180, φ2 = lat2 * Math.PI/180;
        const Δφ = (lat2-lat1) * Math.PI/180, Δλ = (lon2-lon1) * Math.PI/180;
        const a = Math.sin(Δφ/2) * Math.sin(Δφ/2) + Math.cos(φ1) * Math.cos(φ2) * Math.sin(Δλ/2) * Math.sin(Δλ/2);
        return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1-a));
    }

    function sortShops(type){
        doVibrate(30);
        document.querySelectorAll('.sort-tab').forEach(t => {
            t.style.background = 'var(--tag)'; t.style.borderColor = 'var(--border)'; t.style.color = 'var(--text)';
        });
        const container = document.getElementById('shops-list');
        const cards = Array.from(container.children);
        if(type==='price'){
            document.getElementById('sort-price').style.background='var(--primary)';
            document.getElementById('sort-price').style.color='#fff';
            cards.sort((a,b)=> parseInt(a.dataset.budget||0) - parseInt(b.dataset.budget||0));
        } else {
            document.getElementById('sort-rec').style.background='var(--primary)';
            document.getElementById('sort-rec').style.color='#fff';
            cards.sort((a,b)=> parseInt(a.querySelector('.shop-name span').innerText) - parseInt(b.querySelector('.shop-name span').innerText));
        }
        cards.forEach(c => container.appendChild(c));
    }

    let targetShop = null;
    function openInviteModal(s){
        doVibrate(30);
        targetShop = s;
        document.getElementById('inv-time').value = "今週金曜日 19:30〜";
        document.getElementById('inv-fee').value = s.budget || "割り勘";
        updateInvitePreview();
        document.getElementById('invite-modal').style.display = 'flex';
    }
    function closeInviteModal(){
        document.getElementById('invite-modal').style.display = 'none';
    }
    function updateInvitePreview(){
        if(!targetShop) return;
        const t = document.getElementById('inv-time').value.trim();
        const f = document.getElementById('inv-fee').value.trim();
        const txt = `📢【飲み会・お食事会のご案内】\\n\\n📅 日時: ${t}\\n🍽️ 店名: ${targetShop.name}\\n💰 予算: ${f}\\n📍 住所: ${targetShop.address}\\n🚬 喫煙: ${targetShop.smoking_info}\\n🔗 詳細: ${targetShop.url}\\n\\nよろしくお願いします！✨`;
        document.getElementById('inv-preview').value = txt;
    }
    document.getElementById('inv-time').addEventListener('input', updateInvitePreview);
    document.getElementById('inv-fee').addEventListener('input', updateInvitePreview);

    function copyInviteText(){
        doVibrate(30);
        const txt = document.getElementById('inv-preview').value;
        if(navigator.clipboard) navigator.clipboard.writeText(txt).then(()=>showAppAlert("完了","案内文をコピーしました！"));
        else prompt("コピーしてください:", txt);
    }
    function sendInviteLine(){
        doVibrate(30);
        const txt = document.getElementById('inv-preview').value;
        const u = `https://line.me/R/msg/text/?${encodeURIComponent(txt)}`;
        window.open(u, '_blank');
    }

    function pinReservation(s){
        doVibrate(40);
        const t = prompt("予約時間を入力してください (例: 19:30):", "19:30");
        if(t === null) return;
        const c = prompt("コース名や席のメモ (例: 飲み放題付き4000円コース):", "席のみ予約");
        const res = { name: s.name, time: t, course: c, tel: s.tel, address: s.address };
        localStorage.setItem('eatmap_pinned_res', JSON.stringify(res));
        showAppAlert("ピン留め完了", "ホーム最上部に今夜の予約メモをピン留めしました！\\n（地下でも電波なしで確認できます）");
    }

    function toggleFav(btn, s){
        doVibrate(40);
        let f = JSON.parse(localStorage.getItem('eatmap_favs')||'[]');
        const idx = f.findIndex(x=>x.name===s.name);
        if(idx>-1){ f.splice(idx,1); btn.innerHTML='♡'; btn.style.color=''; }
        else { s.visited=false; s.tag=""; f.push(s); btn.innerHTML='♥'; btn.style.color='var(--primary)'; }
        localStorage.setItem('eatmap_favs', JSON.stringify(f));
    }
    window.addEventListener('DOMContentLoaded', ()=>{
        const f = JSON.parse(localStorage.getItem('eatmap_favs')||'[]');
        document.querySelectorAll('#shops-list .card').forEach(c=>{
            const n = c.querySelector('h3').innerText.replace(/^\\d+/,'').trim();
            if(f.some(x=>x.name.trim()===n)){ const b = c.querySelector('.fav-btn'); b.innerHTML='♥'; b.style.color='var(--primary)'; }
        });
    });
</script>
"""

# --- 記録画面 (UI刷新・横長リスト型) ---
FAVORITES_CONTENT = """
<div class="top-bar">
    <div class="brand">📋 グルメ記録</div>
    <div style="display:flex; gap:6px;">
        <a href="/guide" class="btn-icon" title="機能ガイド">❓</a>
        <button class="btn-sm btn-yellow" onclick="pickRandomFav()">🎲 ガチャ</button>
    </div>
</div>

<div class="card" style="background:linear-gradient(135deg, #6366f1, #8b5cf6); color:#fff; border:none; margin-bottom:12px;">
    <div style="display:flex; justify-content:space-between; align-items:center;">
        <div>
            <div style="font-size:11px; font-weight:800; opacity:.9;">🏆 現在のグルメ称号</div>
            <div style="font-size:18px; font-weight:900;" id="user-title">Lv.1 ひよっこ探検家 🐣</div>
        </div>
        <div style="font-size:24px;" id="badge-icon">🌟</div>
    </div>
    <div style="font-size:11px; margin-top:8px; display:flex; justify-content:space-between; font-weight:800;">
        <span id="visited-count">訪問数: 0軒</span>
        <span id="exp-text">EXP: 0/100</span>
    </div>
    <div style="background:rgba(255,255,255,0.25); height:6px; border-radius:3px; overflow:hidden; margin-top:4px;">
        <div id="exp-bar" style="background:var(--yellow); height:100%; width:0%; transition:width .4s;"></div>
    </div>
</div>

<div id="fav-list" style="display:flex; flex-direction:column; gap:10px;"></div>

<script>
    const titles = [
        { lv:1, count:0, title:"Lv.1 ひよっこ探検家 🐣", icon:"🐣" },
        { lv:2, count:2, title:"Lv.2 街角の食べ歩き隊 🚶", icon:"🍙" },
        { lv:3, count:5, title:"Lv.3 こだわりグルメ通 🍴", icon:"🍝" },
        { lv:4, count:10, title:"Lv.4 地域の名店ハンター 🏅", icon:"🥩" },
        { lv:5, count:20, title:"Lv.5 伝説の美食王 👑", icon:"👑" }
    ];

    function renderFavs(){
        const list = document.getElementById('fav-list');
        const f = JSON.parse(localStorage.getItem('eatmap_favs')||'[]');
        const visitedShops = f.filter(s => s.visited);
        const vCount = visitedShops.length;

        let current = titles[0];
        let nextCount = titles[1].count;
        for(let i=0; i<titles.length; i++){
            if(vCount >= titles[i].count){
                current = titles[i];
                nextCount = titles[i+1] ? titles[i+1].count : vCount + 10;
            }
        }
        document.getElementById('user-title').innerText = current.title;
        document.getElementById('badge-icon').innerText = current.icon;
        document.getElementById('visited-count').innerText = `訪問達成: ${vCount}軒`;
        
        const prevCount = current.count;
        const expRate = Math.min(100, Math.max(5, ((vCount - prevCount) / Math.max(1, (nextCount - prevCount))) * 100));
        document.getElementById('exp-text').innerText = `次レベルまで あと${Math.max(0, nextCount - vCount)}軒`;
        document.getElementById('exp-bar').style.width = expRate + '%';

        if(f.length===0){ 
            list.innerHTML = `<div class="card" style="text-align:center; color:var(--muted); font-weight:700; padding:30px 10px;">保存したお店がまだありません。<br>検索画面から「♡」を押して追加してみてね！</div>`; 
            return; 
        }

        const tags = ["😋絶品", "🔥コスパ", "🍺酒進む", "✨雰囲気"];

        list.innerHTML = f.map((s,i)=>`
            <div class="card" style="display:flex; gap:10px; padding:12px; align-items:center; margin-bottom:0;">
                <div style="width:65px; height:65px; border-radius:10px; overflow:hidden; flex-shrink:0; background:var(--tag); display:flex; align-items:center; justify-content:center; font-size:24px;">
                    ${s.photo ? `<img src="${s.photo}" style="width:100%; height:100%; object-fit:cover;" loading="lazy">` : '🍽️'}
                </div>
                <div style="flex:1; overflow:hidden;">
                    <div style="display:flex; justify-content:space-between; align-items:flex-start;">
                        <h3 style="margin:0 0 4px 0; font-size:13.5px; font-weight:900; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; line-height:1.2;">${s.name}</h3>
                        <button class="btn-icon" style="width:22px; height:22px; min-height:22px; font-size:11px; border-radius:6px; box-shadow:none; border:none; background:var(--tag); color:var(--muted); margin-left:6px;" onclick="delFav(${i})">✕</button>
                    </div>
                    <div style="font-size:10px; color:var(--muted); margin-bottom:6px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;">📍 ${s.address}</div>
                    
                    ${s.visited ? `
                    <div style="display:flex; gap:3px; margin-bottom:6px; overflow-x:auto;">
                        ${tags.map(t => `
                            <span style="padding:2px 6px; font-size:9px; border-radius:6px; font-weight:800; cursor:pointer; background:${s.tag===t?'var(--yellow)':'var(--tag)'}; color:${s.tag===t?'#493800':'var(--muted)'};" onclick="setTag(${i}, '${t}')">${t}</span>
                        `).join('')}
                    </div>` : ''}

                    <div style="display:flex; gap:6px;">
                        <button class="btn-sm ${s.visited?'btn-green':'btn-sub'}" style="flex:1; padding:6px 0; font-size:10.5px; margin:0; border:none;" onclick="toggleV(${i})">
                            ${s.visited?'🏁 行った！':'🚩 行ってみたい'}
                        </button>
                        <a href="https://www.google.com/maps/dir/?api=1&destination=${encodeURIComponent(s.address)}" target="_blank" class="btn-sm btn-primary" style="padding:6px 10px; font-size:11px; margin:0;">
                            🗺️
                        </a>
                    </div>
                </div>
            </div>
        `).join('');
    }

    function toggleV(i){ 
        doVibrate(30); 
        let f = JSON.parse(localStorage.getItem('eatmap_favs')); 
        f[i].visited = !f[i].visited; 
        localStorage.setItem('eatmap_favs', JSON.stringify(f)); 
        renderFavs(); 
    }

    function setTag(i, t){
        doVibrate(20);
        let f = JSON.parse(localStorage.getItem('eatmap_favs'));
        f[i].tag = (f[i].tag === t) ? '' : t;
        localStorage.setItem('eatmap_favs', JSON.stringify(f)); 
        renderFavs(); 
    }

    function delFav(i){ 
        if(confirm("リストから削除しますか？")){ 
            doVibrate(30); 
            let f = JSON.parse(localStorage.getItem('eatmap_favs')); 
            f.splice(i,1); 
            localStorage.setItem('eatmap_favs', JSON.stringify(f)); 
            renderFavs(); 
        } 
    }

    function pickRandomFav(){
        const f = JSON.parse(localStorage.getItem('eatmap_favs')||'[]');
        if(f.length === 0) return showAppAlert("ご案内", "保存したお店がありません！先にお店をお気に入り登録してね。");
        doVibrate([50, 50, 100]);
        const picked = f[Math.floor(Math.random() * f.length)];
        showAppAlert("🎲 今日のオススメ！", `【${picked.name}】\\nジャンル: ${picked.genre}\\n住所: ${picked.address}`);
    }

    window.addEventListener('DOMContentLoaded', renderFavs);
</script>
"""

# --- 抽選画面 (単一万能ルーレット ＆ GPU最適化) ---
GAME_CONTENT = """
<div class="top-bar">
    <div class="brand">🎯 ルーレット</div>
    <div style="display:flex; gap:6px;">
        <a href="/guide" class="btn-icon" title="機能ガイド">❓</a>
        <button class="btn-sm btn-sub" onclick="openWheelEditor()">✏️ 項目を編集</button>
    </div>
</div>

<div class="card" style="text-align:center; padding:18px 12px; margin-bottom:12px;">
    <div style="font-size:12px; font-weight:800; color:var(--muted); margin-bottom:12px;">迷ったら回すだけ！好きな項目に自由に書き換えられます</div>
    
    <div style="position:relative; width:280px; height:280px; margin:0 auto 18px;">
        <div style="position:absolute; top:-12px; left:50%; transform:translateX(-50%); width:0; height:0; border-left:12px solid transparent; border-right:12px solid transparent; border-top:22px solid var(--primary); z-index:20; filter:drop-shadow(0 2px 4px rgba(0,0,0,0.25));"></div>
        <div style="position:absolute; top:50%; left:50%; transform:translate(-50%, -50%); width:44px; height:44px; background:var(--card); border:3px solid var(--primary); border-radius:50%; z-index:15; display:flex; align-items:center; justify-content:center; font-size:18px; box-shadow:0 2px 8px rgba(0,0,0,0.15);">🍽️</div>
        <canvas id="wheel-canvas" width="280" height="280" style="border-radius:50%; box-shadow:var(--shadow); transition:transform 4.5s cubic-bezier(0.15, 0.9, 0.2, 1); will-change:transform;"></canvas>
    </div>

    <button class="btn-block btn-primary" id="spin-btn" style="font-size:16px; min-height:50px;" onclick="spinWheel()">🎯 ルーレットを回す！</button>
</div>

<div class="card" id="result-box" style="display:none; text-align:center; background:var(--primary-light); border-color:var(--primary);">
    <div style="font-size:12px; font-weight:800; color:var(--muted);">当選結果</div>
    <div style="font-size:26px; font-weight:900; color:var(--primary); margin:8px 0;" id="res-val">--</div>
    <a href="#" id="res-search-btn" class="btn-block btn-green" style="display:none; margin:8px auto 0;">🔍 このジャンルでお店を探す ↗</a>
</div>

<div id="wheel-edit-modal" style="display:none; position:fixed; top:0; left:0; width:100vw; height:100vh; background:rgba(0,0,0,0.75); z-index:99999; justify-content:center; align-items:center; padding:14px;">
    <div class="card" style="width:100%; max-width:440px; max-height:85vh; display:flex; flex-direction:column; margin:0; background:var(--card); padding:16px;">
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:12px;">
            <span style="font-size:15px; font-weight:900;">✏️ ルーレット項目の編集</span>
            <button onclick="closeWheelEditor()" style="background:none; border:none; font-size:18px; cursor:pointer; color:var(--text);">✕</button>
        </div>
        
        <div style="font-size:11px; color:var(--muted); margin-bottom:10px;">各行に項目を入力してください（絵文字もOK）</div>
        
        <div id="wheel-items-container" style="overflow-y:auto; flex:1; margin-bottom:12px; padding-right:4px;"></div>

        <button class="btn-block btn-sub" style="min-height:40px; font-size:13px; margin-bottom:10px;" onclick="addWheelRow()">＋ 項目を1つ追加</button>
        
        <div style="display:grid; grid-template-columns:1fr 1fr; gap:8px;">
            <button class="btn-block btn-sub" style="min-height:42px; font-size:13px; margin:0;" onclick="resetWheelPreset()">初期値に戻す</button>
            <button class="btn-block btn-primary" style="min-height:42px; font-size:13px; margin:0;" onclick="saveWheelEditor()">保存する</button>
        </div>
    </div>
</div>

<script>
    let wheelItems = JSON.parse(localStorage.getItem('eat_custom_wheel') || '["焼肉 🥩","居酒屋 🍺","カフェ ☕","ラーメン 🍜","海鮮 🐟","カレー 🍛","イタリアン 🍕","中華 🥟"]');
    const wheelColors = ["#ffc9c9","#ffe3a8","#fff3bf","#bbf7d0","#c5f6fa","#d0ebff","#dbe4ff","#f3d9fa"];
    let curDeg = 0, isSpinning = false;

    function drawCanvas() {
        const canvas = document.getElementById('wheel-canvas');
        if(!canvas) return;
        const ctx = canvas.getContext('2d');
        ctx.clearRect(0, 0, 280, 280);
        const num = wheelItems.length, arc = (2 * Math.PI) / num;
        for(let i=0; i<num; i++){
            const a = i * arc;
            ctx.fillStyle = wheelColors[i % wheelColors.length];
            ctx.beginPath();
            ctx.arc(140, 140, 136, a, a + arc, false);
            ctx.arc(140, 140, 0, a + arc, a, true);
            ctx.fill();
            ctx.save();
            ctx.strokeStyle = "rgba(255,255,255,0.85)"; ctx.lineWidth = 2; ctx.stroke();
            ctx.fillStyle = "#2d3142";
            ctx.font = "bold 12.5px -apple-system, sans-serif";
            ctx.translate(140 + Math.cos(a + arc/2) * 88, 140 + Math.sin(a + arc/2) * 88);
            ctx.rotate(a + arc/2 + Math.PI/2);
            ctx.fillText(wheelItems[i], -ctx.measureText(wheelItems[i]).width / 2, 0);
            ctx.restore();
        }
    }

    function spinWheel(){
        if(isSpinning) return;
        isSpinning = true;
        const btn = document.getElementById('spin-btn');
        btn.disabled = true; btn.innerText = "抽選中...";
        document.getElementById('result-box').style.display = 'none';
        
        let vibs = 0;
        const vTimer = setInterval(() => {
            doVibrate(20); vibs++;
            if(vibs > 14) clearInterval(vTimer);
        }, 250);

        const extra = Math.floor(Math.random() * 360);
        curDeg += 360 * 5 + extra;
        const canvas = document.getElementById('wheel-canvas');
        canvas.style.transform = `rotate(${curDeg}deg)`;

        setTimeout(() => {
            isSpinning = false;
            btn.disabled = false; btn.innerText = "🎯 もう一度回す！";
            doVibrate([100, 50, 100]);

            const deg = curDeg % 360;
            const step = 360 / wheelItems.length;
            const idx = Math.floor((360 - deg + 270) % 360 / step);
            const picked = wheelItems[idx];

            document.getElementById('res-val').innerText = picked;
            const clean = picked.replace(/[^\\u4E00-\\u9FFF\\u3040-\\u309F\\u30A0-\\u30FAa-zA-Z]/g, '').trim();
            const sBtn = document.getElementById('res-search-btn');
            if(clean){
                sBtn.style.display = 'inline-flex';
                sBtn.href = `/search?keyword=${encodeURIComponent(clean)}`;
            } else {
                sBtn.style.display = 'none';
            }
            document.getElementById('result-box').style.display = 'block';
        }, 4500);
    }

    function openWheelEditor(){
        doVibrate(30);
        renderWheelEditorRows();
        document.getElementById('wheel-edit-modal').style.display = 'flex';
    }

    function closeWheelEditor(){
        document.getElementById('wheel-edit-modal').style.display = 'none';
    }

    function renderWheelEditorRows(){
        const container = document.getElementById('wheel-items-container');
        container.innerHTML = wheelItems.map((item, idx) => `
            <div style="display:flex; gap:6px; margin-bottom:8px; align-items:center;">
                <span style="font-size:12px; font-weight:800; color:var(--muted); width:20px; text-align:center;">${idx+1}</span>
                <input type="text" class="wheel-row-input" value="${item}" maxlength="20" style="flex:1; padding:10px 12px; border:1.5px solid var(--border); border-radius:10px; font-size:13px; font-weight:700; background:var(--input); color:var(--text); outline:none;">
                <button type="button" class="btn-icon" style="width:36px; height:36px; border-radius:10px; color:var(--primary);" onclick="removeWheelRow(${idx})">✕</button>
            </div>
        `).join('');
    }

    function addWheelRow(){
        doVibrate(20);
        collectCurrentInputs();
        wheelItems.push("新しい項目 ✨");
        renderWheelEditorRows();
        const container = document.getElementById('wheel-items-container');
        container.scrollTop = container.scrollHeight;
    }

    function removeWheelRow(idx){
        doVibrate(30);
        collectCurrentInputs();
        if(wheelItems.length <= 2) return showAppAlert("エラー", "項目は最低2つ必要です");
        wheelItems.splice(idx, 1);
        renderWheelEditorRows();
    }

    function collectCurrentInputs(){
        const inputs = document.querySelectorAll('.wheel-row-input');
        const list = [];
        inputs.forEach(inp => {
            const v = inp.value.trim();
            if(v) list.push(v);
        });
        if(list.length > 0) wheelItems = list;
    }

    function saveWheelEditor(){
        doVibrate(40);
        collectCurrentInputs();
        if(wheelItems.length < 2) return showAppAlert("エラー", "2つ以上の項目を入力してください");
        localStorage.setItem('eat_custom_wheel', JSON.stringify(wheelItems));
        drawCanvas();
        closeWheelEditor();
        showAppAlert("完了", "ルーレットの項目を保存しました！");
    }

    function resetWheelPreset(){
        if(confirm("最初の項目リストに戻しますか？")){
            wheelItems = ["焼肉 🥩","居酒屋 🍺","カフェ ☕","ラーメン 🍜","海鮮 🐟","カレー 🍛","イタリアン 🍕","中華 🥟"];
            renderWheelEditorRows();
        }
    }

    window.addEventListener('DOMContentLoaded', drawCanvas);
</script>
"""

# --- ツール画面 (終電キャンセルボタン付き ＆ ダブルタイマー ＆ 傾斜割り勘) ---
TOOLS_CONTENT = """
<div class="top-bar">
    <div class="brand">🧮 おでかけツール</div>
    <div style="display:flex; gap:6px;">
        <a href="/guide" class="btn-icon" title="機能ガイド">❓</a>
        <button class="btn-sm" id="btn-notify-perm" onclick="requestNotification()">🔔 通知をON</button>
    </div>
</div>

<div class="card" style="border-color:var(--purple); background:var(--card);">
    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
        <span style="font-size:12px; font-weight:800; color:var(--purple);">⏰ 終電見張りアラーム</span>
        <span id="train-status" style="font-size:11px; font-weight:800; color:var(--muted);">未設定</span>
    </div>
    <div style="display:flex; gap:6px; align-items:center; margin-bottom:8px;">
        <input type="time" id="train-time" style="padding:8px 10px; border:1.5px solid var(--border); border-radius:10px; font-size:14px; font-weight:800; background:var(--input); color:var(--text); outline:none;">
        <button class="btn-sm btn-purple" style="flex:1; justify-content:center;" onclick="setTrainAlarm()">セット</button>
        <button class="btn-sm btn-sub" style="justify-content:center; padding:8px 10px;" onclick="cancelTrainAlarm()">解除</button>
    </div>
    <div style="font-size:11px; color:var(--muted);">※終電の30分前・15分前・定刻に通知とバイブでお知らせします</div>
</div>

<div class="card">
    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:10px;">
        <span style="font-size:12px; font-weight:800; color:var(--muted);">⏱️ 席・コース時間管理</span>
        <span id="current-clock" style="font-size:12px; font-weight:800; color:var(--primary);">--:--</span>
    </div>
    <div style="display:grid; grid-template-columns: 1fr 1fr; gap:8px; margin-bottom:10px;">
        <div style="background:var(--tag); padding:12px; border-radius:12px; text-align:center;">
            <div style="font-size:11px; font-weight:800; color:var(--muted);">🍺 ラストオーダー</div>
            <div style="font-size:26px; font-weight:900; font-family:monospace; color:var(--yellow);" id="timer-lo">--:--</div>
        </div>
        <div style="background:var(--tag); padding:12px; border-radius:12px; text-align:center;">
            <div style="font-size:11px; font-weight:800; color:var(--muted);">🚪 完全退席</div>
            <div style="font-size:26px; font-weight:900; font-family:monospace; color:var(--primary);" id="timer-exit">--:--</div>
        </div>
    </div>
    <div style="display:flex; gap:6px; margin-bottom:6px;">
        <button class="btn-sm" style="flex:1; justify-content:center;" onclick="setTimer(90, 60)">90分(LO60)</button>
        <button class="btn-sm" style="flex:1; justify-content:center;" onclick="setTimer(120, 90)">120分(LO90)</button>
        <button class="btn-sm" style="flex:1; justify-content:center;" onclick="setTimer(180, 150)">180分(LO150)</button>
    </div>
    <div style="display:flex; gap:6px;">
        <button class="btn-sm btn-primary" style="flex:1; justify-content:center;" onclick="toggleTimer()" id="btn-timer-run">タイマー開始</button>
        <button class="btn-sm" onclick="resetTimer()">リセット</button>
    </div>
</div>

<div class="card">
    <div style="font-size:12px; font-weight:800; color:var(--muted); margin-bottom:10px;">💸 傾斜割り勘計算</div>
    <div class="input-group">
        <input type="number" id="split-total" placeholder="合計お会計 (円)">
    </div>
    <div style="display:grid; grid-template-columns: 1fr 1fr; gap:8px;">
        <div class="input-group"><input type="number" id="split-drinkers" value="2" placeholder="飲む人"><small style="font-size:11px; font-weight:700; color:var(--muted);">飲む人数</small></div>
        <div class="input-group"><input type="number" id="split-nondrinkers" value="1" placeholder="飲まない人"><small style="font-size:11px; font-weight:700; color:var(--muted);">飲まない人数</small></div>
    </div>
    <div style="display:grid; grid-template-columns: 1fr 1fr; gap:8px;">
        <div class="input-group"><input type="number" id="split-discount" value="1000" placeholder="割引額"><small style="font-size:11px; font-weight:700; color:var(--muted);">飲まない人の割引額 (円引)</small></div>
        <div class="input-group"><input type="number" id="split-kanji" value="0" placeholder="幹事負担"><small style="font-size:11px; font-weight:700; color:var(--muted);">幹事の追加負担 (円)</small></div>
    </div>
    <div style="display:flex; gap:6px; margin-bottom:10px; align-items:center;">
        <span style="font-size:11px; font-weight:800; color:var(--muted);">端数丸め:</span>
        <button class="btn-sm round-btn" id="rnd-100" onclick="setRound(100)" style="flex:1; justify-content:center; background:var(--primary); color:#fff; border-color:var(--primary);">100円</button>
        <button class="btn-sm round-btn" id="rnd-500" onclick="setRound(500)" style="flex:1; justify-content:center;">500円</button>
        <button class="btn-sm round-btn" id="rnd-1000" onclick="setRound(1000)" style="flex:1; justify-content:center;">1000円</button>
    </div>
    <button class="btn-block btn-primary" onclick="calcSplit()">割り勘を計算する</button>

    <div id="split-res" style="display:none; background:var(--tag); padding:12px; border-radius:12px; margin-top:10px; font-size:13px; font-weight:700;">
        <div style="display:flex; justify-content:space-between; margin-bottom:6px;"><span>🍺 飲む人:</span><b style="color:var(--primary); font-size:16px;" id="res-drinker">0円</b></div>
        <div style="display:flex; justify-content:space-between; margin-bottom:6px;" id="box-nondrinker"><span>🍵 飲まない人:</span><b style="color:var(--green); font-size:16px;" id="res-nondrinker">0円</b></div>
        <div style="font-size:11px; color:var(--muted); text-align:right;" id="res-diff">余剰: 0円</div>
        <div class="input-group" style="margin-top:8px;">
            <input type="text" id="paypay-link" placeholder="送金先PayPay ID・リンク (任意)">
        </div>
        <div style="display:flex; gap:6px; margin-top:8px;">
            <button class="btn-sm" style="flex:1; justify-content:center;" onclick="copySplitText()">📋 結果コピー</button>
            <button class="btn-sm btn-green" style="flex:1; justify-content:center;" onclick="shareSplit()">💬 LINE共有</button>
        </div>
    </div>
</div>

<div class="card">
    <div style="font-size:12px; font-weight:800; color:var(--muted); margin-bottom:10px;">📝 幹事ToDoチェックリスト</div>
    <div id="todo-box"></div>
    <div style="display:flex; gap:6px; margin-top:10px;">
        <input type="text" id="todo-input" placeholder="やること追加..." style="flex:1; padding:10px; border:1.5px solid var(--border); border-radius:10px; font-size:12px; background:var(--input); color:var(--text); font-weight:700; outline:none;">
        <button class="btn-sm btn-primary" onclick="addTodo()">追加</button>
    </div>
</div>

<script>
    setInterval(() => {
        const d = new Date();
        document.getElementById('current-clock').innerText = d.toTimeString().split(' ')[0].substring(0, 5);
        checkTrainCountdown();
    }, 1000);

    let targetTrainDate = null;
    let warned30 = false, warned15 = false;
    
    function setTrainAlarm(){
        doVibrate(30);
        const val = document.getElementById('train-time').value;
        if(!val) return showAppAlert("エラー", "終電の時刻を選択してください");
        const parts = val.split(':');
        const now = new Date();
        const d = new Date(now.getFullYear(), now.getMonth(), now.getDate(), parseInt(parts[0]), parseInt(parts[1]), 0);
        if(d < now) d.setDate(d.getDate() + 1);
        targetTrainDate = d;
        warned30 = false; warned15 = false;
        showAppAlert("終電セット完了", `終電を【${val}】にセットしました！`);
        checkTrainCountdown();
    }

    function cancelTrainAlarm(){
        doVibrate(30);
        if(!targetTrainDate && !document.getElementById('train-time').value){
            return showAppAlert("ご案内", "終電アラームはセットされていません");
        }
        targetTrainDate = null;
        warned30 = false; warned15 = false;
        document.getElementById('train-time').value = '';
        const st = document.getElementById('train-status');
        st.innerText = '未設定';
        st.style.color = 'var(--muted)';
        showAppAlert("解除完了", "終電アラームを解除しました。");
    }

    function checkTrainCountdown(){
        if(!targetTrainDate) return;
        const now = new Date();
        const diffMs = targetTrainDate - now;
        const st = document.getElementById('train-status');
        if(diffMs <= 0){
            st.innerText = "終電の時刻を過ぎました！";
            st.style.color = "var(--primary)";
            showAppAlert("⚠️ 警告", "終電の時刻を過ぎました！");
            targetTrainDate = null;
            return;
        }
        const diffMin = Math.floor(diffMs / 60000);
        const diffSec = Math.floor((diffMs % 60000) / 1000);
        st.innerText = `残り ${diffMin}分${diffSec}秒`;
        st.style.color = "var(--purple)";

        if(diffMin === 30 && !warned30){
            warned30 = true;
            showAppAlert("終電アラーム", "終電まで残り30分です！");
        }
        if(diffMin === 15 && !warned15){
            warned15 = true;
            showAppAlert("終電アラーム", "終電まで残り15分！お会計や移動の準備を！");
        }
    }

    let exitSec = 7200, loSec = 5400, timerId = null, running = false, roundUnit = 100;
    function setTimer(ex, lo) { exitSec = ex * 60; loSec = lo * 60; updateTimerUI(); }
    
    function setRound(u){
        roundUnit = u;
        document.querySelectorAll('.round-btn').forEach(b=>{
            b.style.background='var(--tag)'; b.style.color='var(--text)'; b.style.borderColor='var(--border)';
        });
        const active = document.getElementById('rnd-'+u);
        active.style.background='var(--primary)'; active.style.color='#fff'; active.style.borderColor='var(--primary)';
        if(document.getElementById('split-res').style.display==='block') calcSplit();
    }

    function requestNotification() {
        if (!("Notification" in window)) {
            document.getElementById('btn-notify-perm').style.display = 'none';
            return showAppAlert("ご案内", "お使いのブラウザはWeb通知に非対応ですが、アプリを開いている間はポップアップとバイブレーションでお知らせします。");
        }
        Notification.requestPermission().then(perm => {
            if(perm === 'granted') {
                document.getElementById('btn-notify-perm').innerText = "🔔 通知ON済み";
                showAppAlert("完了", "バックグラウンド通知をONにしました！");
            }
        });
    }

    window.addEventListener('DOMContentLoaded', ()=>{
        if (!("Notification" in window)) document.getElementById('btn-notify-perm').style.display = 'none';
    });

    function toggleTimer() {
        doVibrate(30); running = !running;
        const b = document.getElementById('btn-timer-run');
        if(running) {
            b.innerText = "停止";
            timerId = setInterval(() => {
                if(exitSec > 0) exitSec--;
                if(loSec > 0) loSec--;
                if (loSec === 0) showAppAlert("タイマー", "🍺 ラストオーダーの時間です！");
                if (exitSec === 0) {
                    showAppAlert("タイマー", "🚪 お席の終了時間です！");
                    clearInterval(timerId);
                }
                updateTimerUI();
            }, 1000);
        } else { b.innerText = "再開"; clearInterval(timerId); }
    }
    function resetTimer() {
        doVibrate(30); running = false; clearInterval(timerId);
        document.getElementById('btn-timer-run').innerText = "タイマー開始";
        setTimer(120, 90);
    }
    function updateTimerUI() {
        const lm = String(Math.floor(loSec/60)).padStart(2,'0'), ls = String(loSec%60).padStart(2,'0');
        const em = String(Math.floor(exitSec/60)).padStart(2,'0'), es = String(exitSec%60).padStart(2,'0');
        document.getElementById('timer-lo').innerText = `${lm}:${ls}`;
        document.getElementById('timer-exit').innerText = `${em}:${es}`;
    }
    updateTimerUI();

    let splitData = null;
    function calcSplit() {
        doVibrate(30);
        const tot = parseInt(document.getElementById('split-total').value) || 0;
        const dr = parseInt(document.getElementById('split-drinkers').value) || 0;
        const ndr = parseInt(document.getElementById('split-nondrinkers').value) || 0;
        const disc = parseInt(document.getElementById('split-discount').value) || 0;
        const kj = parseInt(document.getElementById('split-kanji').value) || 0;
        const num = dr + ndr;
        if(!tot || num <= 0) return showAppAlert("エラー", "金額と人数を入力してください");

        const adj = tot - kj + (disc * ndr);
        const base = Math.ceil((adj / num) / roundUnit) * roundUnit;
        const nonBase = Math.max(0, base - disc);
        const collected = (base * dr) + (nonBase * ndr) + kj;

        document.getElementById('res-drinker').innerText = `${base.toLocaleString()} 円`;
        document.getElementById('res-nondrinker').innerText = `${nonBase.toLocaleString()} 円`;
        document.getElementById('res-diff').innerText = `集金合計: ${collected.toLocaleString()}円 (お釣り: ${collected - tot}円)`;
        document.getElementById('split-res').style.display = 'block';

        splitData = { tot, dr, ndr, base, nonBase, kj };
    }

    function getSplitMsg() {
        if(!splitData) return "";
        const pay = document.getElementById('paypay-link').value.trim();
        let msg = `🍻 お会計の割り勘まとめ\\n合計: ${splitData.tot.toLocaleString()}円\\n---\\n・飲む人: 各 ${splitData.base.toLocaleString()}円 (${splitData.dr}名)\\n`;
        if(splitData.ndr > 0) msg += `・飲まない人: 各 ${splitData.nonBase.toLocaleString()}円 (${splitData.ndr}名)\\n`;
        if(pay) msg += `\\n💰 送金先: ${pay}\\n`;
        msg += `よろしくお願いします！`;
        return msg;
    }

    function copySplitText() {
        doVibrate(30);
        const msg = getSplitMsg();
        if(navigator.clipboard) navigator.clipboard.writeText(msg).then(() => showAppAlert("完了", "割り勘結果をコピーしました！"));
        else prompt("コピーしてください:", msg);
    }

    function shareSplit() {
        doVibrate(30);
        const msg = getSplitMsg();
        const u = `https://line.me/R/msg/text/?${encodeURIComponent(msg)}`;
        if(navigator.share) navigator.share({title: 'お会計割り勘', text: msg});
        else window.open(u, '_blank');
    }

    let todos = JSON.parse(localStorage.getItem('eatmap_todos') || '["お店の予約確認", "アレルギーの有無確認", "集金・PayPay回収"]');
    function renderTodos() {
        const box = document.getElementById('todo-box');
        box.innerHTML = todos.map((t, idx) => `
            <div style="display:flex; align-items:center; gap:10px; font-size:13px; font-weight:700; padding:8px 0; border-bottom:1.5px dashed var(--border);">
                <input type="checkbox" onchange="removeTodo(${idx})" style="width:16px; height:16px; accent-color:var(--primary);">
                <span>${t}</span>
            </div>
        `).join('');
    }
    function addTodo() {
        const input = document.getElementById('todo-input');
        const v = input.value.trim();
        if(!v) return;
        doVibrate(20);
        todos.push(v);
        localStorage.setItem('eatmap_todos', JSON.stringify(todos));
        input.value = "";
        renderTodos();
    }
    function removeTodo(i) {
        doVibrate(40);
        setTimeout(() => {
            todos.splice(i, 1);
            localStorage.setItem('eatmap_todos', JSON.stringify(todos));
            renderTodos();
        }, 300);
    }
    renderTodos();
</script>
"""

# --- AI相談画面 ---
CHAT_CONTENT = """
<style>
    .msg { max-width:85%; padding:10px 14px; border-radius:16px; font-size:13.5px; font-weight:700; line-height:1.6; word-wrap:break-word; }
    .msg-ai { background:var(--tag); border-top-left-radius:4px; color:var(--text); margin-right:auto; }
    .msg-user { background:var(--primary); border-top-right-radius:4px; color:#fff; margin-left:auto; }
    .chat-box { display:flex; flex-direction:column; gap:12px; padding:14px; overflow-y:auto; height:52vh; background:var(--card); border:1.5px solid var(--border); border-radius:18px; margin-bottom:10px; }
    .s-btn { display:inline-flex; align-items:center; gap:4px; background:var(--primary); color:#fff; padding:6px 12px; border-radius:10px; font-size:11.5px; font-weight:800; text-decoration:none; margin-top:8px; box-shadow:var(--shadow); border:none; }
    .chip-bar { display:flex; gap:6px; overflow-x:auto; padding-bottom:8px; margin-bottom:8px; -webkit-overflow-scrolling:touch; }
    .q-chip { background:var(--tag); border:1.5px solid var(--border); border-radius:16px; padding:6px 12px; font-size:11.5px; font-weight:800; color:var(--text); white-space:nowrap; cursor:pointer; }
    .q-chip:active { opacity:.7; }
</style>

<div class="top-bar">
    <div class="brand">💬 AIコンシェルジュ</div>
    <a href="/guide" class="btn-icon" title="機能ガイド">❓</a>
</div>

<div class="chat-box" id="box">
    <div style="display:flex; gap:8px; align-items:flex-start;">
        <div style="font-size:24px;">🤖</div>
        <div class="msg msg-ai">こんにちは！お店探しのお手伝いをします✨<br>「姫路の喫煙できる居酒屋」「個室のあるカフェ」など、何でも聞いてください！</div>
    </div>
</div>

<div class="chip-bar">
    <button class="q-chip" onclick="askChip('姫路駅近くで喫煙できる個室居酒屋')">🚬 喫煙可の個室居酒屋</button>
    <button class="q-chip" onclick="askChip('深夜営業しているおすすめラーメンやシメ')">🍜 深夜の背徳シメ飯</button>
    <button class="q-chip" onclick="askChip('姫路の静かで落ち着くカフェ')">☕ 姫路の静かなカフェ</button>
    <button class="q-chip" onclick="askChip('姫路の美味しい焼肉店')">🍖 姫路の美味しい焼肉</button>
</div>

<div style="display:flex; gap:8px;">
    <input type="text" id="inp" maxlength="80" placeholder="相談を入力..." style="flex:1; padding:13px 14px; border:1.5px solid var(--border); border-radius:12px; font-size:14px; background:var(--input); color:var(--text); font-weight:700; outline:none;" onkeypress="if(event.key==='Enter') send()">
    <button class="btn-primary" style="width:60px; border-radius:12px; border:none; font-weight:800; cursor:pointer;" onclick="send()" id="s-btn">送信</button>
</div>

<script>
    const box = document.getElementById('box'), inp = document.getElementById('inp'), btn = document.getElementById('s-btn');
    
    function askChip(txt) {
        inp.value = txt;
        send();
    }

    async function send(){
        const txt = inp.value.trim();
        if(!txt) return;
        doVibrate(30);
        box.innerHTML += `<div style="display:flex; justify-content:flex-end;"><div class="msg msg-user">${htmlEscape(txt)}</div></div>`;
        inp.value = ""; btn.disabled = true;
        box.scrollTop = box.scrollHeight;

        const wId = "w-" + Date.now();
        box.innerHTML += `<div id="${wId}" style="display:flex; gap:8px; align-items:flex-start; margin-top:4px;"><div style="font-size:24px;">🤖</div><div class="msg msg-ai" style="color:var(--muted);"><span class="spinner" style="width:12px;height:12px;border-width:2px;display:inline-block;border-top-color:var(--primary);margin:0;"></span> 考え中...</div></div>`;
        box.scrollTop = box.scrollHeight;

        try {
            const res = await fetch('/api/chat', { 
                method:'POST', 
                headers:{'Content-Type':'application/json'}, 
                body:JSON.stringify({message:txt}) 
            });
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

    function htmlEscape(str) {
        return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
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
    else:
        params["keyword"] = " ".join(parts) if parts else "居酒屋 グルメ"

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
                    "name": s.get("name", "店舗名不明"),
                    "genre": (s.get("genre") or {}).get("name", "グルメ"),
                    "address": s.get("address", ""),
                    "budget": b_name,
                    "min_budget": min_b,
                    "lat": s.get("lat"), "lng": s.get("lng"),
                    "tel": s.get("tel", "0000000000"),
                    "has_private": has_pr,
                    "smoking_info": sm_info,
                    "has_free_drink": has_fd,
                    "url": (s.get("urls") or {}).get("pc", "#"),
                    "photo": ((s.get("photo") or {}).get("pc") or {}).get("l", "")
                })
            return results or DEFAULT_SHOPS
    except Exception:
        return DEFAULT_SHOPS

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
    smoking = (request.args.get('smoking') == '1')
    private_room = (request.args.get('private_room') == '1')
    free_drink = (request.args.get('free_drink') == '1')
    midnight = (request.args.get('midnight') == '1')
    pref_fish = (request.args.get('pref_fish') == '1')
    pref_meat = (request.args.get('pref_meat') == '1')
    pref_spicy = (request.args.get('pref_spicy') == '1')

    lat_val, lng_val = None, None
    try:
        if request.args.get('lat') and request.args.get('lng'):
            lat_val = float(request.args.get('lat'))
            lng_val = float(request.args.get('lng'))
    except (ValueError, TypeError):
        lat_val, lng_val = None, None

    tags = []
    if smoking: tags.append("喫煙可")
    if private_room: tags.append("個室")
    if free_drink: tags.append("飲み放題")
    if midnight: tags.append("深夜")
    tag_str = f"({'/'.join(tags)})" if tags else ""

    title = f"{a} {k} {tag_str}".strip() or "おすすめ店舗"
    shops = fetch_shops(
        keyword=k, area=a, lat=lat_val, lng=lng_val,
        smoking=smoking, private_room=private_room, 
        free_drink=free_drink, midnight=midnight,
        pref_fish=pref_fish, pref_meat=pref_meat, pref_spicy=pref_spicy
    )
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

# --- 爆速・確実に対話する Gemini API ---
@app.route('/api/chat', methods=['POST'])
def api_chat():
    req_json = request.get_json(silent=True) or {}
    raw_msg = str(req_json.get('message', ''))[:80].strip()
    msg = html.escape(raw_msg)
    
    if msg in AI_CACHE:
        return jsonify({"reply": AI_CACHE[msg]})
        
    key = GEMINI_API_KEY
    if not key:
        return jsonify({"reply": "APIキーが設定されていません。"})
        
    models = ["gemini-1.5-flash", "gemini-flash-latest"]
    prompt = f"飲食店案内役としてユーザーの言葉「{msg}」に日本語敬語で共感や案内を60文字以内で親切に即答してください。"
    
    payload = json.dumps({
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "maxOutputTokens": 80,
            "temperature": 0.4
        }
    }).encode('utf-8')
    
    headers = {
        'Content-Type': 'application/json',
        'X-goog-api-key': key,
        'User-Agent': 'Mozilla/5.0'
    }
    
    for model_name in models:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent"
        try:
            req = urllib.request.Request(url, data=payload, headers=headers)
            with urllib.request.urlopen(req, timeout=12) as res:
                res_data = json.loads(res.read().decode('utf-8'))
                reply = res_data['candidates'][0]['content']['parts'][0]['text']
                clean_reply = reply.replace("**", "").replace("*", "").strip()
                if len(AI_CACHE) > 100: AI_CACHE.clear()
                AI_CACHE[msg] = clean_reply
                return jsonify({"reply": clean_reply})
        except Exception:
            continue

    if any(w in msg for w in ["眠", "つかれ", "帰る", "しんど"]):
        return jsonify({"reply": f"お疲れさまです！無理せずゆっくり休んでくださいね。温かいシメ飯や落ち着くカフェも探せますよ✨"})
    return jsonify({"reply": f"「{msg}」ですね！おすすめの美味しいお店を下のボタンからすぐ探せますよ✨"})

@app.route('/manifest.json')
def manifest():
    return jsonify({
        "name": "EAT MAP", "short_name": "EAT MAP", "start_url": "/", "display": "standalone",
        "background_color": "#0f172a", "theme_color": "#ff5252",
        "icons": [{"src": "data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 100 100%22><text y=%22.9em%22 font-size=%2290%22>🍽️</text></svg>", "sizes": "192x192", "type": "image/svg+xml"}]
    })

@app.route('/sw.js')
def sw():
    return Response("self.addEventListener('fetch', e => {});", mimetype="application/javascript")

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
