# ==============================================================================
# 【EAT MAP】シンプル × ポップ 完全統合版 app1.py
# ------------------------------------------------------------------------------
# ■ APIキー設定:
#   Render管理画面の「Environment」への登録を推奨します。
#   - HOTPEPPER_API_KEY : ホットペッパーグルメAPIキー
#   - GEMINI_API_KEY    : Google Gemini APIキー
# ==============================================================================
import os
import urllib.request
import urllib.parse
import json
import random
import re
import time
import gzip
import html
from collections import defaultdict
from flask import Flask, request, render_template_string, jsonify, Response

app = Flask(__name__)

HOTPEPPER_API_KEY = os.environ.get("HOTPEPPER_API_KEY", "").strip()
GEMINI_API_KEY    = os.environ.get("GEMINI_API_KEY", "").strip()

# ================= 1. 安全対策・セキュリティ機構 =================
IP_REQUEST_LOG = defaultdict(list)
RATE_LIMIT_WINDOW = 60
RATE_LIMIT_MAX = 60

@app.before_request
def security_firewall():
    if request.path == '/ping':
        return None
    ip = request.headers.get('X-Forwarded-For', request.remote_addr).split(',')[0].strip()
    now = time.time()
    IP_REQUEST_LOG[ip] = [t for t in IP_REQUEST_LOG[ip] if now - t < RATE_LIMIT_WINDOW]
    if len(IP_REQUEST_LOG[ip]) >= RATE_LIMIT_MAX:
        return "リクエスト上限を超えました。しばらく待ってから再アクセスしてください。", 429
    IP_REQUEST_LOG[ip].append(now)

@app.after_request
def apply_security_headers_and_compress(response):
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'SAMEORIGIN'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    
    if response.content_type and 'text/html' in response.content_type:
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'

    accept_encoding = request.headers.get('Accept-Encoding', '')
    if 'gzip' not in accept_encoding.lower() or response.status_code < 200 or response.status_code >= 300:
        return response
    if response.headers.get('Content-Encoding'):
        return response
    data = response.get_data()
    if len(data) < 500:
        return response
    compressed = gzip.compress(data)
    response.set_data(compressed)
    response.headers['Content-Encoding'] = 'gzip'
    response.headers['Content-Length'] = len(compressed)
    return response

# ================= 2. キャッシュ & デフォルトデータ =================
SEARCH_CACHE = {}
CACHE_TTL = 600
MAX_CACHE_SIZE = 150

DEFAULT_SHOPS = [
    {
        "name": "CAFÉ DE ÉTOILE (サンプル)", "genre": "カフェ・スイーツ", "catch": "こだわりの自家焙煎コーヒーと落ち着いたテラス席。",
        "address": "東京都渋谷区神南1-2-3", "access": "渋谷駅ハチ公口から徒歩5分", "budget": "1,000円〜2,000円", "min_budget": 1000,
        "lat": 35.6618, "lng": 139.7011, "tel": "03-0000-0001", "is_indoor": False,
        "photo": "https://images.unsplash.com/photo-1554118811-1e0d58224f24?w=600", "url": "https://www.hotpepper.jp/", "is_special": True
    },
    {
        "name": "個室和食 旬彩庵 (サンプル)", "genre": "和食・居酒屋", "catch": "旬の厳選鮮魚と地酒を嗜むプライベート個室空間。",
        "address": "兵庫県姫路市駅前町100", "access": "姫路駅北口徒歩3分", "budget": "3,500円〜5,000円", "min_budget": 3500,
        "lat": 34.8290, "lng": 134.6900, "tel": "079-000-0002", "is_indoor": True,
        "photo": "https://images.unsplash.com/photo-1517248135467-4c7edcad34c4?w=600", "url": "https://www.hotpepper.jp/", "is_special": True
    },
    {
        "name": "深夜営業 BAR 夜行列車 (サンプル)", "genre": "バー・お酒", "catch": "深夜も営業。二次会に最適な大人の隠れ家バー。",
        "address": "大阪府大阪市北区梅田1-1-1", "access": "梅田駅地下直結", "budget": "2,000円〜3,500円", "min_budget": 2000,
        "lat": 34.7024, "lng": 135.4959, "tel": "06-0000-0003", "is_indoor": True,
        "photo": "https://images.unsplash.com/photo-1514933651103-005eec06c04b?w=600", "url": "https://www.hotpepper.jp/", "is_special": True
    }
]

# ================= 3. シンプル × ポップ デザイン基盤 =================
COMMON_HEAD = """
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <link rel="icon" href="data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 100 100%22><text y=%22.9em%22 font-size=%2290%22>🍽️</text></svg>">
    <link rel="apple-touch-icon" href="data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 100 100%22><rect width=%22100%22 height=%22100%22 fill=%22%23ff6b6b%22 rx=%2224%22/><text x=%2250%%22 y=%2255%%22 dominant-baseline=%22central%22 text-anchor=%22middle%22 font-size=%2260%22>🍽️</text></svg>">
    <link rel="manifest" href="/manifest.json">
    <meta name="theme-color" content="#ff6b6b">
    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
    <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
    <script>
        const savedTheme = localStorage.getItem('eatmap_theme') || (window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
        document.documentElement.setAttribute('data-theme', savedTheme);
    </script>
    <style>
        :root {
            --bg: #faf8f5;
            --card-bg: #ffffff;
            --card-border: #ede8e1;
            --text-main: #2d3142;
            --text-muted: #8c92a4;
            --primary: #ff6b6b;
            --primary-hover: #fa5252;
            --primary-light: #fff0f0;
            --accent-yellow: #ffd166;
            --accent-green: #06d6a0;
            --accent-blue: #4dabf7;
            --accent-purple: #b197fc;
            --input-bg: #ffffff;
            --tag-bg: #f5f3ef;
            --shadow: 0 4px 14px rgba(45, 49, 66, 0.05);
        }
        [data-theme="dark"] {
            --bg: #16181f;
            --card-bg: #20232d;
            --card-border: #2d3240;
            --text-main: #f8fafc;
            --text-muted: #94a3b8;
            --primary: #ff7b7b;
            --primary-hover: #ff9494;
            --primary-light: #2c2125;
            --accent-yellow: #ffe082;
            --accent-green: #2dd4bf;
            --accent-blue: #60a5fa;
            --accent-purple: #c084fc;
            --input-bg: #191b24;
            --tag-bg: #282c38;
            --shadow: 0 4px 14px rgba(0, 0, 0, 0.25);
        }
        * { box-sizing: border-box; -webkit-tap-highlight-color: transparent; }
        body { 
            background-color: var(--bg); color: var(--text-main); 
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Hiragino Sans", sans-serif;
            margin: 0; padding: 14px; padding-bottom: 92px; min-height: 100vh;
        }
        .max-w { max-width: 480px; margin: 0 auto; }
        
        .card {
            background: var(--card-bg); border: 1.5px solid var(--card-border);
            border-radius: 18px; padding: 16px; margin-bottom: 12px;
            box-shadow: var(--shadow);
        }
        .top-bar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
        .brand { font-size: 21px; font-weight: 900; letter-spacing: 0.5px; color: var(--primary); display: flex; align-items: center; gap: 6px; }
        
        .btn-icon {
            background: var(--card-bg); border: 1.5px solid var(--card-border);
            color: var(--text-main); border-radius: 12px; width: 38px; height: 38px;
            display: inline-flex; align-items: center; justify-content: center; font-size: 16px; cursor: pointer;
            box-shadow: var(--shadow); transition: transform 0.1s;
        }
        .btn-icon:active { transform: scale(0.92); }

        .btn-sm {
            background: var(--tag-bg); color: var(--text-main); border: 1.5px solid var(--card-border);
            padding: 8px 14px; border-radius: 12px; font-size: 12px; font-weight: 800; cursor: pointer; text-decoration: none;
            display: inline-flex; align-items: center; gap: 4px; transition: transform 0.1s;
        }
        .btn-sm:active { transform: scale(0.95); }

        .btn-block {
            width: 100%; min-height: 48px; border-radius: 14px; font-size: 14px; font-weight: 800;
            display: flex; align-items: center; justify-content: center; gap: 6px; border: none; cursor: pointer;
            text-decoration: none; transition: transform 0.1s, opacity 0.15s; margin-bottom: 8px;
            box-shadow: var(--shadow);
        }
        .btn-block:active { transform: scale(0.98); opacity: 0.9; }
        .btn-primary { background: var(--primary); color: white; }
        .btn-yellow { background: var(--accent-yellow); color: #493800; }
        .btn-green { background: var(--accent-green); color: white; }
        .btn-blue { background: var(--accent-blue); color: white; }
        .btn-sub { background: var(--tag-bg); color: var(--text-main); border: 1.5px solid var(--card-border); }

        .input-group { position: relative; margin-bottom: 10px; }
        .input-group input, .input-group select, .input-group textarea {
            width: 100%; padding: 13px 14px; border: 1.5px solid var(--card-border); border-radius: 12px;
            font-size: 14px; background: var(--input-bg); color: var(--text-main); outline: none; font-weight: 700;
            transition: border-color 0.2s;
        }
        .input-group input:focus, .input-group select:focus { border-color: var(--primary); }

        .bottom-nav { 
            position: fixed; bottom: 0; left: 0; width: 100%; 
            background: var(--card-bg); border-top: 1.5px solid var(--card-border);
            display: flex; justify-content: space-around; padding: 8px 0;
            padding-bottom: calc(8px + env(safe-area-inset-bottom)); z-index: 1000;
            box-shadow: 0 -4px 16px rgba(0, 0, 0, 0.04);
        }
        .bottom-nav a { 
            color: var(--text-muted); text-decoration: none; font-size: 10px; display: flex; flex-direction: column; 
            align-items: center; gap: 2px; font-weight: 800; width: 20%; 
        }
        .bottom-nav a.active { color: var(--primary); }
        .bottom-nav span.icon { font-size: 20px; }

        .shop-card {
            background: var(--card-bg); border: 1.5px solid var(--card-border);
            border-radius: 16px; padding: 14px; margin-bottom: 12px; position: relative;
            box-shadow: var(--shadow);
        }
        .shop-img { width: 100%; height: 165px; object-fit: cover; border-radius: 12px; margin-bottom: 10px; background: #222; }
        .shop-title { font-size: 16px; font-weight: 900; margin: 0 0 4px 0; padding-right: 42px; color: var(--text-main); }
        .shop-meta { font-size: 12px; color: var(--text-muted); margin-bottom: 10px; line-height: 1.5; }
        
        .fav-btn {
            position: absolute; top: 12px; right: 12px; font-size: 18px; cursor: pointer;
            background: var(--card-bg); border: 1.5px solid var(--card-border); border-radius: 10px;
            width: 36px; height: 36px; display: flex; align-items: center; justify-content: center;
            box-shadow: var(--shadow);
        }
        .fav-btn.active { color: var(--primary); }

        #loading-overlay { position: fixed; top: 0; left: 0; width: 100vw; height: 100vh; background: rgba(0,0,0,0.45); backdrop-filter: blur(4px); display: none; justify-content: center; align-items: center; flex-direction: column; z-index: 9999; }
        .spinner { width: 40px; height: 40px; border: 4px solid rgba(255,255,255,0.3); border-top-color: white; border-radius: 50%; animation: spin 0.8s linear infinite; margin-bottom: 12px; }
        @keyframes spin { 100% { transform: rotate(360deg); } }

        .credit-footer { text-align: center; font-size: 11px; font-weight: 700; color: var(--text-muted); margin: 24px 0 10px 0; }
        .credit-footer a { color: var(--primary); text-decoration: none; }
    </style>
"""

BOTTOM_NAV = """
    <div class="bottom-nav">
        <a href="/" id="nav-home"><span class="icon">🔍</span><span>探す</span></a>
        <a href="/chat" id="nav-chat"><span class="icon">💬</span><span>相談</span></a>
        <a href="/favorites" id="nav-fav"><span class="icon">📋</span><span>記録</span></a>
        <a href="/game" id="nav-game"><span class="icon">🎯</span><span>抽選</span></a>
        <a href="/tools" id="nav-tools"><span class="icon">🧮</span><span>ツール</span></a>
    </div>
    <script>
        const p = window.location.pathname;
        if(p==='/') document.getElementById('nav-home').classList.add('active');
        if(p==='/chat') document.getElementById('nav-chat').classList.add('active');
        if(p==='/favorites') document.getElementById('nav-fav').classList.add('active');
        if(p==='/game') document.getElementById('nav-game').classList.add('active');
        if(p==='/tools') document.getElementById('nav-tools').classList.add('active');

        function toggleTheme() {
            const cur = document.documentElement.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
            document.documentElement.setAttribute('data-theme', cur);
            localStorage.setItem('eatmap_theme', cur);
            updateThemeIcon();
        }
        function updateThemeIcon() {
            const isDark = document.documentElement.getAttribute('data-theme') === 'dark';
            document.querySelectorAll('.theme-btn').forEach(b => b.innerText = isDark ? '☀️' : '🌙');
        }
        window.addEventListener('DOMContentLoaded', updateThemeIcon);

        async function forceUpdateApp() {
            if ('caches' in window) {
                const names = await caches.keys();
                await Promise.all(names.map(name => caches.delete(name)));
            }
            if ('serviceWorker' in navigator) {
                const regs = await navigator.serviceWorker.getRegistrations();
                for (let r of regs) { await r.update(); }
            }
            window.location.reload(true);
        }

        if ('serviceWorker' in navigator) {
            navigator.serviceWorker.register('/sw.js').then(reg => {
                reg.onupdatefound = () => {
                    const inst = reg.installing;
                    inst.onstatechange = () => {
                        if (inst.state === 'installed' && navigator.serviceWorker.controller) {
                            window.location.reload();
                        }
                    };
                };
            });
        }
    </script>
"""

# ================= 4. 各画面テンプレート =================

# --- 画面1: ホーム ---
HOME_HTML = """
<!DOCTYPE html>
<html lang="ja">
<head>
    """ + COMMON_HEAD + """
    <title>EAT MAP - お店探し</title>
</head>
<body>
    <div id="loading-overlay"><div class="spinner"></div><div style="color:white; font-size:14px; font-weight:800;">おいしいお店を探し中...</div></div>
    
    <div class="max-w">
        <div class="top-bar">
            <div class="brand">🍽️ EAT MAP</div>
            <div style="display:flex; gap:6px;">
                <button class="btn-icon" onclick="forceUpdateApp()" title="最新版へ更新">🔄</button>
                <button class="btn-icon theme-btn" onclick="toggleTheme()">🌙</button>
                <button class="btn-sm" onclick="shareApp()">📤 共有</button>
            </div>
        </div>

        <div style="display:grid; grid-template-columns: 1fr 1fr; gap:8px; margin-bottom:12px;">
            <button class="btn-block btn-green" onclick="searchCurrentLoc()">📍 現在地周辺</button>
            <button class="btn-block btn-yellow" onclick="searchNijikai()">🍻 二次会・深夜</button>
        </div>

        <div class="card">
            <div style="font-size:12px; font-weight:800; color:var(--text-muted); margin-bottom:10px;">⭐ 人気ジャンルから一発検索</div>
            <div style="display:grid; grid-template-columns: repeat(4, 1fr); gap:8px; margin-bottom:16px;">
                <button type="button" class="btn-sm" style="background:#fee2e2; border-color:#fca5a5; color:#991b1b; justify-content:center;" onclick="quickSearch('居酒屋 個室')">🍺 居酒屋</button>
                <button type="button" class="btn-sm" style="background:#fef3c7; border-color:#fde047; color:#854d0e; justify-content:center;" onclick="quickSearch('焼肉')">🍖 焼肉</button>
                <button type="button" class="btn-sm" style="background:#dcfce7; border-color:#86efac; color:#166534; justify-content:center;" onclick="quickSearch('カフェ')">☕ カフェ</button>
                <button type="button" class="btn-sm" style="background:#e0f2fe; border-color:#7dd3fc; color:#075985; justify-content:center;" onclick="quickSearch('ラーメン')">🍜 麺類</button>
            </div>

            <form action="/search" method="GET" id="search-form" onsubmit="showLoading()">
                <div class="input-group">
                    <input type="text" name="area" id="area-input" placeholder="📍 エリア・駅名 (例: 姫路, 梅田, 渋谷)">
                </div>
                <div class="input-group">
                    <input type="text" name="keyword" id="keyword-input" placeholder="🔍 キーワード (例: 個室, 飲み放題, 焼き鳥)">
                </div>
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
                        <select name="count">
                            <option value="15" selected>15件取得</option>
                            <option value="30">30件取得</option>
                        </select>
                    </div>
                </div>
                <button type="submit" class="btn-block btn-primary" style="margin-top:4px;">条件でお店を探す</button>
            </form>
        </div>

        <div class="credit-footer">
            Powered by <a href="http://webservice.recruit.co.jp/" target="_blank">ホットペッパー Webサービス</a>
        </div>
    </div>
    """ + BOTTOM_NAV + """

    <script>
        function showLoading() { document.getElementById('loading-overlay').style.display = 'flex'; }
        function quickSearch(k) {
            document.getElementById('keyword-input').value = k;
            showLoading();
            document.getElementById('search-form').submit();
        }
        function searchCurrentLoc() {
            if (!navigator.geolocation) return alert("位置情報がサポートされていません");
            showLoading();
            navigator.geolocation.getCurrentPosition(
                pos => { window.location.href = `/search?lat=${pos.coords.latitude}&lng=${pos.coords.longitude}&area=現在地周辺`; },
                err => { document.getElementById('loading-overlay').style.display = 'none'; alert("位置情報の取得を許可してください。"); },
                { timeout: 8000 }
            );
        }
        function searchNijikai() {
            if (!navigator.geolocation) {
                window.location.href = `/search?keyword=${encodeURIComponent("二次会 バー 深夜")}`;
                return;
            }
            showLoading();
            navigator.geolocation.getCurrentPosition(
                pos => { window.location.href = `/search?lat=${pos.coords.latitude}&lng=${pos.coords.longitude}&keyword=${encodeURIComponent("二次会 バー 深夜")}&area=現在地`; },
                () => { window.location.href = `/search?keyword=${encodeURIComponent("二次会 バー 深夜")}`; },
                { timeout: 6000 }
            );
        }
        async function shareApp() {
            if (navigator.share) navigator.share({title: 'EAT MAP', url: window.location.origin});
            else prompt("URLをコピー:", window.location.origin);
        }
    </script>
</body>
</html>
"""

# --- 画面2: 検索結果 ---
RESULT_HTML = """
<!DOCTYPE html>
<html lang="ja">
<head>
    """ + COMMON_HEAD + """
    <title>検索結果 - EAT MAP</title>
    <style>
        .map-box { height: 210px; width: 100%; border-radius: 14px; margin-bottom: 12px; border: 1.5px solid var(--card-border); }
        .filter-chip-bar { display: flex; gap: 8px; overflow-x: auto; padding-bottom: 6px; margin-bottom: 12px; }
        .chip { background: var(--card-bg); border: 1.5px solid var(--card-border); color: var(--text-main); padding: 7px 12px; border-radius: 10px; font-size: 12px; font-weight: 800; white-space: nowrap; cursor: pointer; box-shadow: var(--shadow); }
        .chip.active { background: var(--primary); color: white; border-color: var(--primary); }
    </style>
</head>
<body>
    <div class="max-w">
        <div class="top-bar">
            <a href="/" class="btn-sm">← 戻る</a>
            <div style="font-size:13px; font-weight:800; color:var(--text-muted);">{{ search_title }} ({{ shops|length }}件)</div>
            <button class="btn-sm" style="background:var(--accent-yellow); border-color:#fde047; color:#78350f;" onclick="sendSelectedVote()">🗳️ LINE投票 (<span id="vote-count">0</span>)</button>
        </div>

        <div id="map" class="map-box"></div>

        <div class="filter-chip-bar">
            <button class="chip" onclick="sortByDist()">📍 近い順</button>
            <button class="chip" onclick="sortByPrice()">💰 予算順</button>
            <button class="chip" id="chip-filter-open" onclick="toggleOnlyOpen(this)">✨ 個室・居酒屋のみ</button>
        </div>

        <div id="shops-list">
            {% for s in shops %}
            <div class="shop-card" data-lat="{{ s.lat }}" data-lng="{{ s.lng }}" data-budget="{{ s.min_budget }}" data-genre="{{ s.genre }}">
                <button class="fav-btn" onclick='toggleFavorite(this, {{ s | tojson }})'>♡</button>
                {% if s.photo %}<img src="{{ s.photo }}" class="shop-img" loading="lazy">{% endif %}
                <h3 class="shop-title">{{ s.name }}</h3>
                <div class="shop-meta">
                    🏷️ <b>{{ s.genre }}</b><br>
                    📍 {{ s.address }} <span class="dist-label" style="color:var(--primary); font-weight:800;"></span><br>
                    💰 予算目安: {{ s.budget }}
                </div>
                <div style="display:grid; grid-template-columns: 1fr 1fr 1fr; gap:6px; margin-bottom:8px;">
                    <a href="tel:{{ s.tel }}" class="btn-sm" style="justify-content:center;">📞 電話</a>
                    <a href="https://www.google.com/maps/dir/?api=1&destination={{ s.address | urlencode }}" target="_blank" class="btn-sm" style="justify-content:center;">📍 地図</a>
                    <a href="{{ s.url }}" target="_blank" class="btn-sm btn-primary" style="justify-content:center;">予約 ↗</a>
                </div>
                <div style="display:flex; gap:6px;">
                    <button class="btn-sm" style="flex:1; justify-content:center;" onclick="copyShopInfo('{{ s.name }}', '{{ s.address }}', '{{ s.url }}')">📋 コピー</button>
                    <button class="btn-sm vote-add-btn" style="flex:1; justify-content:center;" onclick="toggleVote('{{ s.name }}', this)">🗳️ 候補追加</button>
                </div>
            </div>
            {% endfor %}
        </div>

        <div class="credit-footer">
            Powered by <a href="http://webservice.recruit.co.jp/" target="_blank">ホットペッパー Webサービス</a>
        </div>
    </div>
    """ + BOTTOM_NAV + """

    <script>
        const shops = {{ shops | tojson | safe }};
        let voteList = [];

        if (shops.length > 0 && shops[0].lat && shops[0].lng) {
            const map = L.map('map').setView([shops[0].lat, shops[0].lng], 14);
            L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png').addTo(map);
            shops.forEach(s => {
                if(s.lat && s.lng) L.marker([s.lat, s.lng]).addTo(map).bindPopup(`<b>${s.name}</b><br>${s.genre}`);
            });
        } else {
            const map = L.map('map').setView([35.6812, 139.7671], 12);
            L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png').addTo(map);
        }

        function copyShopInfo(name, addr, url) {
            const text = `${name}\\n📍住所: ${addr}\\n🔗詳細: ${url}`;
            if(navigator.clipboard) {
                navigator.clipboard.writeText(text).then(() => alert("店舗情報をコピーしました！LINE等に貼り付けできます。"));
            } else { prompt("コピー:", text); }
        }

        function toggleVote(name, btn) {
            const idx = voteList.indexOf(name);
            if(idx > -1) { voteList.splice(idx, 1); btn.innerText = "🗳️ 候補追加"; btn.classList.remove('btn-yellow'); }
            else { voteList.push(name); btn.innerText = "✅ 追加済み"; btn.classList.add('btn-yellow'); }
            document.getElementById('vote-count').innerText = voteList.length;
        }

        function sendSelectedVote() {
            if(voteList.length === 0) return alert("投票候補のお店を1つ以上追加してください");
            const url = window.location.origin + "/vote?shops=" + encodeURIComponent(voteList.join(','));
            if(navigator.share) navigator.share({title: 'お店決めLINE投票', url: url});
            else prompt("この投票URLをLINEで送ってください:", url);
        }

        function sortByDist() {
            if (!navigator.geolocation) return alert("位置情報非対応です");
            navigator.geolocation.getCurrentPosition(pos => {
                const myLat = pos.coords.latitude, myLng = pos.coords.longitude;
                const container = document.getElementById('shops-list');
                const cards = Array.from(container.getElementsByClassName('shop-card'));
                cards.forEach(c => {
                    const lat = parseFloat(c.dataset.lat), lng = parseFloat(c.dataset.lng);
                    if(lat && lng) {
                        const d = calcDistance(myLat, myLng, lat, lng);
                        c.dataset.dist = d;
                        c.querySelector('.dist-label').innerText = `(約${(d*1000).toFixed(0)}m)`;
                    } else { c.dataset.dist = 99999; }
                });
                cards.sort((a,b) => parseFloat(a.dataset.dist) - parseFloat(b.dataset.dist));
                cards.forEach(c => container.appendChild(c));
            });
        }
        function calcDistance(lat1, lon1, lat2, lon2) {
            const R = 6371, dLat = (lat2-lat1)*Math.PI/180, dLon = (lon2-lon1)*Math.PI/180;
            const a = Math.sin(dLat/2)*Math.sin(dLat/2) + Math.cos(lat1*Math.PI/180)*Math.cos(lat2*Math.PI/180)*Math.sin(dLon/2)*Math.sin(dLon/2);
            return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1-a));
        }

        function sortByPrice() {
            const container = document.getElementById('shops-list');
            const cards = Array.from(container.getElementsByClassName('shop-card'));
            cards.sort((a,b) => parseInt(a.dataset.budget) - parseInt(b.dataset.budget));
            cards.forEach(c => container.appendChild(c));
        }

        function toggleOnlyOpen(btn) {
            btn.classList.toggle('active');
            const active = btn.classList.contains('active');
            const cards = document.querySelectorAll('.shop-card');
            cards.forEach(c => {
                const genre = c.dataset.genre || "";
                if(active && !genre.includes('個室') && !genre.includes('居酒屋')) {
                    c.style.display = 'none';
                } else { c.style.display = 'block'; }
            });
        }

        function toggleFavorite(btn, shop) {
            let favs = JSON.parse(localStorage.getItem('eatmap_favs') || '[]');
            const idx = favs.findIndex(i => i.name === shop.name);
            if (idx > -1) { favs.splice(idx, 1); btn.innerHTML = '♡'; btn.classList.remove('active'); }
            else { shop.memo = ""; shop.visited = false; shop.my_photo = ""; favs.push(shop); btn.innerHTML = '♥'; btn.classList.add('active'); }
            localStorage.setItem('eatmap_favs', JSON.stringify(favs));
        }

        window.addEventListener('DOMContentLoaded', () => {
            const favs = JSON.parse(localStorage.getItem('eatmap_favs') || '[]');
            document.querySelectorAll('.shop-card').forEach(c => {
                const name = c.querySelector('.shop-title').innerText;
                if(favs.some(i => i.name === name)) {
                    c.querySelector('.fav-btn').innerHTML = '♥';
                    c.querySelector('.fav-btn').classList.add('active');
                }
            });
        });
    </script>
</body>
</html>
"""

# --- 画面3: 記録・マイデータ ---
FAVORITES_HTML = """
<!DOCTYPE html>
<html lang="ja">
<head>
    """ + COMMON_HEAD + """
    <title>記録 - EAT MAP</title>
</head>
<body>
    <div class="max-w">
        <div class="top-bar">
            <div class="brand">📋 グルメ記録</div>
            <div style="display:flex; gap:6px;">
                <button class="btn-sm" onclick="exportData()">バックアップ</button>
                <button class="btn-sm" onclick="importData()">復元</button>
            </div>
        </div>

        <div class="card" style="background:linear-gradient(135deg, var(--accent-green), #059669); color:white; border:none;">
            <div style="font-size:12px; font-weight:800; opacity:0.95;">🗾 47都道府県 全国制覇度</div>
            <div style="font-size:22px; font-weight:900; margin:4px 0;" id="pref-status">0 / 47 都道府県 (0%)</div>
            <div style="background:rgba(255,255,255,0.3); height:8px; border-radius:4px; overflow:hidden;">
                <div id="pref-bar" style="background:#ffd166; height:100%; width:0%; transition:width 0.4s;"></div>
            </div>
        </div>

        <div id="fav-container"></div>
    </div>
    """ + BOTTOM_NAV + """

    <script>
        function getPref(addr) {
            const m = (addr || "").match(/(東京都|北海道|(?:京都|大阪)府|.{2,3}県)/);
            return m ? m[1] : "未設定";
        }

        function renderFavs() {
            const list = document.getElementById('fav-container');
            const favs = JSON.parse(localStorage.getItem('eatmap_favs') || '[]');
            
            const visitedSet = new Set();
            favs.forEach(s => {
                s.pref = getPref(s.address);
                if(s.visited && s.pref !== "未設定") visitedSet.add(s.pref);
            });
            const rate = ((visitedSet.size / 47) * 100).toFixed(1);
            document.getElementById('pref-status').innerText = `${visitedSet.size} / 47 都道府県 (${rate}%)`;
            document.getElementById('pref-bar').style.width = Math.min(100, Math.max(3, (visitedSet.size / 47) * 100)) + "%";

            if(favs.length === 0) {
                list.innerHTML = `<div class="card" style="text-align:center; color:var(--text-muted); padding:30px; font-weight:700;">保存したお店がまだありません</div>`;
                return;
            }

            list.innerHTML = favs.map((s, i) => `
                <div class="shop-card">
                    <button class="fav-btn active" onclick="deleteFav(${i})">✕</button>
                    <span class="btn-sm" style="background:var(--primary-light); color:var(--primary); border-color:var(--primary); font-size:11px; padding:4px 8px; margin-bottom:6px;">📍 ${s.pref}</span>
                    ${s.my_photo ? `<img src="${s.my_photo}" class="shop-img" style="border:2px solid var(--accent-yellow);">` : (s.photo ? `<img src="${s.photo}" class="shop-img">` : '')}
                    <h3 class="shop-title" style="margin-top:6px;">${s.name}</h3>
                    <div class="shop-meta">📍 ${s.address}</div>

                    <div style="display:grid; grid-template-columns: 1fr 1fr; gap:6px; margin:8px 0;">
                        <button class="btn-sm ${s.visited ? 'btn-green' : ''}" style="justify-content:center;" onclick="toggleVisit(${i})">
                            ${s.visited ? '🏁 制覇済み！' : '🚩 行ってみたい'}
                        </button>
                        <button class="btn-sm" style="justify-content:center;" onclick="editShopMemo(${i})">✏️ メモ</button>
                    </div>

                    <label class="btn-sm" style="width:100%; justify-content:center; cursor:pointer;">
                        📷 料理の写真を追加
                        <input type="file" accept="image/*" style="display:none;" onchange="savePhoto(event, ${i})">
                    </label>

                    ${s.memo ? `<div style="background:var(--tag-bg); padding:10px; border-radius:10px; font-size:12px; margin-top:8px; border-left:3px solid var(--primary); font-weight:700;">${s.memo}</div>` : ''}
                </div>
            `).join('');
        }

        function toggleVisit(i) {
            let favs = JSON.parse(localStorage.getItem('eatmap_favs') || '[]');
            favs[i].visited = !favs[i].visited;
            localStorage.setItem('eatmap_favs', JSON.stringify(favs));
            renderFavs();
        }
        function editShopMemo(i) {
            let favs = JSON.parse(localStorage.getItem('eatmap_favs') || '[]');
            const m = prompt("お店のメモ (食べた料理・感想など):", favs[i].memo || "");
            if(m !== null) { favs[i].memo = m; localStorage.setItem('eatmap_favs', JSON.stringify(favs)); renderFavs(); }
        }
        function deleteFav(i) {
            if(!confirm("このお店の記録を削除しますか？")) return;
            let favs = JSON.parse(localStorage.getItem('eatmap_favs') || '[]');
            favs.splice(i, 1);
            localStorage.setItem('eatmap_favs', JSON.stringify(favs));
            renderFavs();
        }
        function savePhoto(e, i) {
            const file = e.target.files[0];
            if(!file) return;
            const r = new FileReader();
            r.onload = ev => {
                const img = new Image();
                img.onload = () => {
                    const canvas = document.createElement('canvas');
                    const max = 400;
                    let w = img.width, h = img.height;
                    if(w > h) { if(w > max) { h = Math.round((h * max)/w); w = max; } }
                    else { if(h > max) { w = Math.round((w * max)/h); h = max; } }
                    canvas.width = w; canvas.height = h;
                    canvas.getContext('2d').drawImage(img, 0, 0, w, h);
                    let favs = JSON.parse(localStorage.getItem('eatmap_favs') || '[]');
                    favs[i].my_photo = canvas.toDataURL('image/jpeg', 0.65);
                    try { localStorage.setItem('eatmap_favs', JSON.stringify(favs)); renderFavs(); }
                    catch(err) { alert("容量制限のため写真を保存できませんでした"); }
                };
                img.src = ev.target.result;
            };
            r.readAsDataURL(file);
        }

        function exportData() {
            const data = localStorage.getItem('eatmap_favs') || '[]';
            const code = btoa(unescape(encodeURIComponent(data)));
            if(navigator.clipboard) navigator.clipboard.writeText(code).then(() => alert("バックアップコードをコピーしました！"));
            else prompt("控えてください:", code);
        }
        function importData() {
            const code = prompt("バックアップコードを貼り付けてください:");
            if(!code) return;
            try {
                const jsonStr = decodeURIComponent(escape(atob(code.trim())));
                JSON.parse(jsonStr);
                localStorage.setItem('eatmap_favs', jsonStr);
                alert("復元が完了しました！");
                renderFavs();
            } catch(e) { alert("コードが無効です。"); }
        }

        window.addEventListener('DOMContentLoaded', renderFavs);
    </script>
</body>
</html>
"""

# --- 画面4: 店決めルーレット ---
GAME_HTML = """
<!DOCTYPE html>
<html lang="ja">
<head>
    """ + COMMON_HEAD + """
    <title>抽選 - EAT MAP</title>
    <style>
        .wheel-box { position: relative; width: 280px; height: 280px; margin: 14px auto; display: flex; align-items: center; justify-content: center; }
        .pointer { position: absolute; top: -10px; left: 50%; transform: translateX(-50%); width: 0; height: 0; border-left: 10px solid transparent; border-right: 10px solid transparent; border-top: 20px solid var(--primary); z-index: 20; filter: drop-shadow(0 2px 4px rgba(0,0,0,0.2)); }
        #wheel-canvas { border-radius: 50%; border: 3px solid var(--card-border); box-shadow: var(--shadow); transition: transform 4s cubic-bezier(0.15, 0.9, 0.2, 1); }
    </style>
</head>
<body>
    <div class="max-w">
        <div class="top-bar">
            <div class="brand">🎯 店決めルーレット</div>
            <button class="btn-sm" onclick="editItems()">✏️ 項目編集</button>
        </div>

        <div class="wheel-box">
            <div class="pointer"></div>
            <canvas id="wheel-canvas" width="280" height="280"></canvas>
        </div>

        <button class="btn-block btn-primary" id="spin-btn" onclick="spin()">🎯 ルーレットを回す！</button>

        <div class="card" id="result-card" style="display:none; text-align:center;">
            <div style="font-size:12px; font-weight:800; color:var(--text-muted);">運命のジャンルは...</div>
            <div style="font-size:24px; font-weight:900; color:var(--primary); margin:8px 0;" id="result-label">--</div>
            <button class="btn-block btn-green" id="search-decided-btn">このジャンルでお店を探す ↗</button>
        </div>
    </div>
    """ + BOTTOM_NAV + """

    <script>
        let items = JSON.parse(localStorage.getItem('eatmap_roulette') || '["焼肉 🥩", "居酒屋 🍺", "カフェ ☕", "ラーメン 🍜", "海鮮 🐟", "カレー 🍛", "イタリアン 🍕", "中華 🥟"]');
        const colors = ["#ffc9c9", "#ffe3a8", "#fff3bf", "#bbf7d0", "#c5f6fa", "#d0ebff", "#dbe4ff", "#f3d9fa"];
        const canvas = document.getElementById('wheel-canvas');
        const ctx = canvas.getContext('2d');
        let curAngle = 0, isSpinning = false;

        function drawWheel() {
            ctx.clearRect(0, 0, 280, 280);
            const num = items.length, arc = (2 * Math.PI) / num;
            for(let i = 0; i < num; i++) {
                const a = i * arc;
                ctx.fillStyle = colors[i % colors.length];
                ctx.beginPath();
                ctx.arc(140, 140, 136, a, a + arc, false);
                ctx.arc(140, 140, 0, a + arc, a, true);
                ctx.fill();
                ctx.save();
                ctx.fillStyle = "#2d3142";
                ctx.font = "bold 13px sans-serif";
                ctx.translate(140 + Math.cos(a + arc/2) * 88, 140 + Math.sin(a + arc/2) * 88);
                ctx.rotate(a + arc/2 + Math.PI/2);
                ctx.fillText(items[i], -ctx.measureText(items[i]).width / 2, 0);
                ctx.restore();
            }
        }
        drawWheel();

        function spin() {
            if(isSpinning) return;
            isSpinning = true;
            document.getElementById('spin-btn').disabled = true;
            document.getElementById('result-card').style.display = 'none';

            const extra = Math.floor(Math.random() * 360);
            curAngle += 360 * 5 + extra;
            canvas.style.transform = `rotate(${curAngle}deg)`;

            setTimeout(() => {
                isSpinning = false;
                document.getElementById('spin-btn').disabled = false;
                const deg = curAngle % 360;
                const step = 360 / items.length;
                const idx = Math.floor((360 - deg + 270) % 360 / step);
                const picked = items[idx];
                const clean = picked.split(' ')[0];
                document.getElementById('result-label').innerText = picked;
                document.getElementById('search-decided-btn').onclick = () => {
                    window.location.href = `/search?keyword=${encodeURIComponent(clean)}`;
                };
                document.getElementById('result-card').style.display = 'block';
            }, 4000);
        }

        function editItems() {
            const str = prompt("カンマ区切りで項目を入力してください:", items.join(','));
            if(str) {
                const arr = str.split(',').map(s => s.trim()).filter(s => s);
                if(arr.length >= 2) {
                    items = arr;
                    localStorage.setItem('eatmap_roulette', JSON.stringify(items));
                    drawWheel();
                } else { alert("2項目以上入力してください"); }
            }
        }
    </script>
</body>
</html>
"""

# --- 画面5: ツール (ダブルタイマー & 傾斜割り勘 & 幹事チェックリスト) ---
TOOLS_HTML = """
<!DOCTYPE html>
<html lang="ja">
<head>
    """ + COMMON_HEAD + """
    <title>ツール - EAT MAP</title>
    <style>
        .timer-display { font-size: 26px; font-weight: 900; font-family: monospace; letter-spacing: 1px; color: var(--primary); text-align: center; }
        .todo-item { display: flex; align-items: center; gap: 10px; font-size: 13px; font-weight: 700; padding: 8px 0; border-bottom: 1.5px dashed var(--card-border); }
    </style>
</head>
<body>
    <div class="max-w">
        <div class="top-bar">
            <div class="brand">🧮 おでかけツール</div>
        </div>

        <div class="card">
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:10px;">
                <span style="font-size:12px; font-weight:800; color:var(--text-muted);">⏱️ 席・コース時間管理</span>
                <span id="current-clock" style="font-size:12px; font-weight:800; color:var(--primary);">--:--</span>
            </div>
            <div style="display:grid; grid-template-columns: 1fr 1fr; gap:8px; margin-bottom:10px;">
                <div style="background:var(--tag-bg); padding:12px; border-radius:12px; text-align:center;">
                    <div style="font-size:11px; font-weight:800; color:var(--text-muted);">🍺 ラストオーダー</div>
                    <div class="timer-display" style="color:var(--accent-yellow);" id="timer-lo">--:--</div>
                </div>
                <div style="background:var(--tag-bg); padding:12px; border-radius:12px; text-align:center;">
                    <div style="font-size:11px; font-weight:800; color:var(--text-muted);">🚪 完全退席</div>
                    <div class="timer-display" id="timer-exit">--:--</div>
                </div>
            </div>
            <div style="display:flex; gap:6px;">
                <button class="btn-sm" style="flex:1; justify-content:center;" onclick="setTimer(120, 90)">2時間(LO90分)</button>
                <button class="btn-sm btn-primary" style="flex:1; justify-content:center;" onclick="toggleTimer()" id="btn-timer-run">開始</button>
                <button class="btn-sm" onclick="resetTimer()">リセット</button>
            </div>
        </div>

        <div class="card">
            <div style="font-size:12px; font-weight:800; color:var(--text-muted); margin-bottom:10px;">💸 傾斜割り勘計算</div>
            <div class="input-group">
                <input type="number" id="split-total" placeholder="合計お会計 (円)">
            </div>
            <div style="display:grid; grid-template-columns: 1fr 1fr; gap:8px;">
                <div class="input-group"><input type="number" id="split-drinkers" value="2" placeholder="飲む人"><small style="font-size:11px; font-weight:700; color:var(--text-muted);">飲む人数</small></div>
                <div class="input-group"><input type="number" id="split-nondrinkers" value="1" placeholder="飲まない人"><small style="font-size:11px; font-weight:700; color:var(--text-muted);">飲まない人数</small></div>
            </div>
            <div style="display:grid; grid-template-columns: 1fr 1fr; gap:8px;">
                <div class="input-group"><input type="number" id="split-discount" value="1000" placeholder="割引額"><small style="font-size:11px; font-weight:700; color:var(--text-muted);">飲まない人の割引額</small></div>
                <div class="input-group"><input type="number" id="split-kanji" value="0" placeholder="幹事負担"><small style="font-size:11px; font-weight:700; color:var(--text-muted);">幹事の追加負担</small></div>
            </div>
            <button class="btn-block btn-primary" onclick="calcSplit()">計算する</button>

            <div id="split-res" style="display:none; background:var(--tag-bg); padding:12px; border-radius:12px; margin-top:10px; font-size:13px; font-weight:700;">
                <div style="display:flex; justify-content:space-between; margin-bottom:6px;"><span>🍺 飲んだ人:</span><b style="color:var(--primary); font-size:16px;" id="res-drinker">0円</b></div>
                <div style="display:flex; justify-content:space-between; margin-bottom:6px;" id="box-nondrinker"><span>🍵 飲まない人:</span><b style="color:var(--accent-green); font-size:16px;" id="res-nondrinker">0円</b></div>
                <div style="font-size:11px; color:var(--text-muted); text-align:right;" id="res-diff">余剰: 0円</div>
                <div class="input-group" style="margin-top:8px;">
                    <input type="text" id="paypay-link" placeholder="送金先PayPay ID・リンク(任意)">
                </div>
                <button class="btn-block btn-green" style="margin-top:6px;" onclick="shareSplit()">💬 LINEに結果を共有</button>
            </div>
        </div>

        <div class="card">
            <div style="font-size:12px; font-weight:800; color:var(--text-muted); margin-bottom:10px;">📝 幹事ToDoチェックリスト</div>
            <div id="todo-box"></div>
            <div style="display:flex; gap:6px; margin-top:10px;">
                <input type="text" id="todo-input" placeholder="やること追加..." style="flex:1; padding:10px; border:1.5px solid var(--card-border); border-radius:10px; font-size:12px; background:var(--input-bg); color:var(--text-main); font-weight:700;">
                <button class="btn-sm btn-primary" onclick="addTodo()">追加</button>
            </div>
        </div>
    </div>
    """ + BOTTOM_NAV + """

    <script>
        setInterval(() => {
            const d = new Date();
            document.getElementById('current-clock').innerText = d.toTimeString().split(' ')[0].substring(0, 5);
        }, 1000);

        let exitSec = 7200, loSec = 5400, timerId = null, running = false;
        function setTimer(ex, lo) { exitSec = ex * 60; loSec = lo * 60; updateTimerUI(); }
        function toggleTimer() {
            running = !running;
            const b = document.getElementById('btn-timer-run');
            if(running) {
                b.innerText = "停止";
                timerId = setInterval(() => {
                    if(exitSec > 0) exitSec--;
                    if(loSec > 0) loSec--;
                    updateTimerUI();
                }, 1000);
            } else { b.innerText = "再開"; clearInterval(timerId); }
        }
        function resetTimer() {
            running = false; clearInterval(timerId);
            document.getElementById('btn-timer-run').innerText = "開始";
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
            const tot = parseInt(document.getElementById('split-total').value) || 0;
            const dr = parseInt(document.getElementById('split-drinkers').value) || 0;
            const ndr = parseInt(document.getElementById('split-nondrinkers').value) || 0;
            const disc = parseInt(document.getElementById('split-discount').value) || 0;
            const kj = parseInt(document.getElementById('split-kanji').value) || 0;
            const num = dr + ndr;
            if(!tot || num <= 0) return alert("金額と人数を入力してください");

            const adj = tot - kj + (disc * ndr);
            const base = Math.ceil((adj / num) / 100) * 100;
            const nonBase = Math.max(0, base - disc);
            const collected = (base * dr) + (nonBase * ndr) + kj;

            document.getElementById('res-drinker').innerText = `${base.toLocaleString()} 円`;
            document.getElementById('res-nondrinker').innerText = `${nonBase.toLocaleString()} 円`;
            document.getElementById('res-diff').innerText = `集金合計: ${collected.toLocaleString()}円 (お釣り: ${collected - tot}円)`;
            document.getElementById('split-res').style.display = 'block';

            splitData = { tot, dr, ndr, base, nonBase, kj };
        }

        function shareSplit() {
            if(!splitData) return;
            const pay = document.getElementById('paypay-link').value.trim();
            let msg = `🍻 お会計の割り勘まとめ\\n合計: ${splitData.tot.toLocaleString()}円\\n---\\n・飲む人: 各 ${splitData.base.toLocaleString()}円 (${splitData.dr}名)\\n`;
            if(splitData.ndr > 0) msg += `・飲まない人: 各 ${splitData.nonBase.toLocaleString()}円 (${splitData.ndr}名)\\n`;
            if(pay) msg += `\\n💰 送金先: ${pay}\\n`;
            msg += `よろしくお願いします！`;

            const u = `https://line.me/R/msg/text/?${encodeURIComponent(msg)}`;
            if(navigator.share) navigator.share({title: 'お会計割り勘', text: msg});
            else window.open(u, '_blank');
        }

        let todos = JSON.parse(localStorage.getItem('eatmap_todos') || '["お店の予約確認", "アレルギーの有無確認", "集金・PayPay回収"]');
        function renderTodos() {
            const box = document.getElementById('todo-box');
            box.innerHTML = todos.map((t, idx) => `
                <div class="todo-item">
                    <input type="checkbox" onchange="removeTodo(${idx})" style="width:16px; height:16px; accent-color:var(--primary);">
                    <span>${t}</span>
                </div>
            `).join('');
        }
        function addTodo() {
            const input = document.getElementById('todo-input');
            const v = input.value.trim();
            if(!v) return;
            todos.push(v);
            localStorage.setItem('eatmap_todos', JSON.stringify(todos));
            input.value = "";
            renderTodos();
        }
        function removeTodo(i) {
            setTimeout(() => {
                todos.splice(i, 1);
                localStorage.setItem('eatmap_todos', JSON.stringify(todos));
                renderTodos();
            }, 300);
        }
        renderTodos();
    </script>
</body>
</html>
"""

# --- 画面6: AI相談 ---
CHAT_HTML = """
<!DOCTYPE html>
<html lang="ja">
<head>
    """ + COMMON_HEAD + """
    <title>AI相談 - EAT MAP</title>
</head>
<body>
    <div class="max-w" style="padding-bottom:70px;">
        <div class="top-bar">
            <div class="brand">💬 AIコンシェルジュ</div>
        </div>

        <div class="card" style="min-height:300px; max-height:450px; overflow-y:auto;" id="chat-box">
            <div style="background:var(--tag-bg); padding:12px; border-radius:12px; font-size:13px; line-height:1.6; font-weight:700;">
                こんにちは！お店選びの相談相手です。「姫路駅の近くで個室居酒屋」「23時以降に入れる静かなカフェ」など、気軽にお聞きください。
            </div>
        </div>

        <div style="display:flex; gap:6px; margin-top:8px;">
            <input type="text" id="chat-txt" placeholder="相談内容を入力..." style="flex:1; padding:12px 14px; border:1.5px solid var(--card-border); border-radius:12px; font-size:13px; background:var(--input-bg); color:var(--text-main); font-weight:700;">
            <button class="btn-sm btn-primary" onclick="sendChat()" style="width:70px; justify-content:center;">送信</button>
        </div>
    </div>
    """ + BOTTOM_NAV + """

    <script>
        async function sendChat() {
            const input = document.getElementById('chat-txt');
            const txt = input.value.trim();
            if(!txt) return;
            const box = document.getElementById('chat-box');
            box.innerHTML += `<div style="text-align:right; margin:8px 0;"><span style="background:var(--primary); color:white; padding:9px 14px; border-radius:14px; font-size:13px; display:inline-block; font-weight:700;">${txt}</span></div>`;
            input.value = "";
            box.scrollTop = box.scrollHeight;

            try {
                const res = await fetch('/api/chat', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({message: txt})
                });
                const d = await res.json();
                box.innerHTML += `<div style="text-align:left; margin:8px 0;"><span style="background:var(--tag-bg); color:var(--text-main); padding:9px 14px; border-radius:14px; font-size:13px; display:inline-block; font-weight:700; line-height:1.5;">${d.reply.replace(/\\n/g, '<br>')}</span></div>`;
                box.scrollTop = box.scrollHeight;
            } catch(e) {
                box.innerHTML += `<div style="color:var(--primary); font-size:12px; font-weight:700;">通信エラーが発生しました</div>`;
            }
        }
    </script>
</body>
</html>
"""

# --- 画面7: LINE投票ページ ---
VOTE_HTML = """
<!DOCTYPE html>
<html lang="ja">
<head>""" + COMMON_HEAD + """<title>投票 - EAT MAP</title></head>
<body>
    <div class="max-w card" style="margin-top:20px; text-align:center;">
        <h2 style="font-size:18px; font-weight:900; margin:0 0 8px 0; color:var(--primary);">🗳️ どのお店に行きたい？</h2>
        <p style="font-size:12px; color:var(--text-muted); margin-bottom:14px; font-weight:700;">友達が選んだ候補リストです！</p>
        {% for name in shop_names %}
            <div style="background:var(--tag-bg); border:1.5px solid var(--card-border); padding:12px; border-radius:12px; margin-bottom:8px; font-weight:800; font-size:14px;">{{ loop.index }}. {{ name }}</div>
        {% endfor %}
        <a href="/" class="btn-block btn-primary" style="margin-top:16px;">EAT MAPアプリを開く</a>
    </div>
</body>
</html>
"""

# ================= 5. ロジック & エンドポイント =================

def extract_budget(b_str):
    if not b_str: return 99999
    nums = re.findall(r'\d+', str(b_str).replace(',', ''))
    return int(nums[0]) if nums else 99999

def fetch_shops(keyword="", area="", lat=None, lng=None, budget_filter="", count=15):
    keyword = html.escape(keyword[:50])
    area = html.escape(area[:50])
    cache_key = f"{area}:{keyword}:{lat}:{lng}:{budget_filter}:{count}"
    now = time.time()
    
    if cache_key in SEARCH_CACHE:
        c_time, c_data = SEARCH_CACHE[cache_key]
        if now - c_time < CACHE_TTL:
            return c_data

    shops = list(DEFAULT_SHOPS)
    if not HOTPEPPER_API_KEY or "ここに" in HOTPEPPER_API_KEY:
        return shops

    params = {"key": HOTPEPPER_API_KEY, "count": min(int(count), 30), "format": "json"}
    if lat and lng:
        params["lat"] = lat
        params["lng"] = lng
        params["range"] = 4
        if keyword: params["keyword"] = keyword
    else:
        parts = [p for p in [area, keyword] if p]
        params["keyword"] = " ".join(parts) if parts else "居酒屋 グルメ"

    url = f"https://webservice.recruit.co.jp/hotpepper/gourmet/v1/?{urllib.parse.urlencode(params)}"
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=5) as res:
            data = json.loads(res.read().decode('utf-8'))
            api_shops = []
            for s in data.get("results", {}).get("shop", []):
                b_str = (s.get("budget") or {}).get("name", "")
                min_b = extract_budget(b_str)
                if budget_filter and min_b > int(budget_filter):
                    continue
                api_shops.append({
                    "name": s.get("name", "店舗名不明"),
                    "genre": (s.get("genre") or {}).get("name", "グルメ"),
                    "address": s.get("address", ""),
                    "budget": b_str or "要確認",
                    "min_budget": min_b,
                    "lat": s.get("lat"),
                    "lng": s.get("lng"),
                    "tel": s.get("tel", "0000000000"),
                    "photo": ((s.get("photo") or {}).get("pc") or {}).get("l", ""),
                    "url": (s.get("urls") or {}).get("pc", "#"),
                    "is_special": False
                })
            result = api_shops if api_shops else shops
            if len(SEARCH_CACHE) > MAX_CACHE_SIZE:
                SEARCH_CACHE.clear()
            SEARCH_CACHE[cache_key] = (now, result)
            return result
    except Exception:
        return shops

# UptimeRobot死活監視用 (最小負荷 0.001秒応答)
@app.route('/ping')
def ping():
    return "OK", 200

@app.route('/')
def home():
    return render_template_string(HOME_HTML)

@app.route('/search')
def search():
    k = request.args.get('keyword', '')
    a = request.args.get('area', '')
    b = request.args.get('budget_filter', '')
    c = request.args.get('count', '15')
    lat = request.args.get('lat')
    lng = request.args.get('lng')
    title = f"{a} {k}".strip() or "おすすめ店舗"
    shops = fetch_shops(keyword=k, area=a, lat=lat, lng=lng, budget_filter=b, count=c)
    return render_template_string(RESULT_HTML, shops=shops, search_title=title)

@app.route('/favorites')
def favorites():
    return render_template_string(FAVORITES_HTML)

@app.route('/chat')
def chat():
    return render_template_string(CHAT_HTML)

@app.route('/game')
def game():
    return render_template_string(GAME_HTML)

@app.route('/tools')
def tools():
    return render_template_string(TOOLS_HTML)

@app.route('/vote')
def vote():
    names = request.args.get('shops', '').split(',')
    clean_names = [html.escape(n.strip()) for n in names if n.strip()]
    return render_template_string(VOTE_HTML, shop_names=clean_names)

# Gemini API 対話
@app.route('/api/chat', methods=['POST'])
def api_chat():
    data = request.get_json(silent=True) or {}
    msg = html.escape(data.get('message', '')[:120])
    if GEMINI_API_KEY and "ここに" not in GEMINI_API_KEY:
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
            prompt = f"あなたは親しみやすいグルメコンシェルジュです。日本の飲食店選びの相談に答えてください。ユーザーの質問:「{msg}」。120文字以内で親切かつ簡潔に答えてください。"
            payload = json.dumps({"contents": [{"parts": [{"text": prompt}]}]}).encode('utf-8')
            req = urllib.request.Request(url, data=payload, headers={'Content-Type': 'application/json'})
            with urllib.request.urlopen(req, timeout=5) as res:
                res_data = json.loads(res.read().decode('utf-8'))
                reply = res_data['candidates'][0]['content']['parts'][0]['text']
                return jsonify({"reply": reply})
        except Exception:
            pass
    return jsonify({"reply": f"「{msg}」ですね！ご予算やお好みに合わせたおすすめ店を検索タブからすぐにお探しいただけます。"})

@app.route('/manifest.json')
def manifest():
    return jsonify({
        "name": "EAT MAP - お店探し", "short_name": "EAT MAP", "start_url": "/", "display": "standalone",
        "background_color": "#16181f", "theme_color": "#ff6b6b",
        "icons": [{"src": "data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 100 100%22><text y=%22.9em%22 font-size=%2290%22>🍽️</text></svg>", "sizes": "192x192", "type": "image/svg+xml"}]
    })

@app.route('/sw.js')
def sw():
    sw_code = """
    const CACHE_NAME = 'eatmap-v11';
    self.addEventListener('install', e => self.skipWaiting());
    self.addEventListener('activate', e => e.waitUntil(
        caches.keys().then(keys => Promise.all(keys.map(k => k !== CACHE_NAME && caches.delete(k)))).then(() => self.clients.claim())
    ));
    self.addEventListener('fetch', e => {
        if (e.request.method !== 'GET') return;
        if (e.request.headers.get('accept') && e.request.headers.get('accept').includes('text/html')) {
            e.respondWith(
                fetch(e.request).then(res => {
                    const cl = res.clone();
                    caches.open(CACHE_NAME).then(c => c.put(e.request, cl));
                    return res;
                }).catch(() => caches.match(e.request).then(c => c || caches.match('/')))
            );
            return;
        }
        e.respondWith(caches.match(e.request).then(c => c || fetch(e.request)));
    });
    """
    return Response(sw_code, mimetype="application/javascript")

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
