# ==============================================================================
# 【★ 最重要設定：APIキー入力エリア ★】
# ------------------------------------------------------------------------------
import os

HOTPEPPER_API_KEY = os.environ.get("HOTPEPPER_API_KEY", "ここにホットペッパーAPIキーを入力")
GEMINI_API_KEY    = os.environ.get("GEMINI_API_KEY", "ここにGeminiAPIキーを入力")
# ==============================================================================

from flask import Flask, request, render_template_string, jsonify, Response
import urllib.request
import urllib.parse
import json
import random
import re
import time
import gzip
import io

app = Flask(__name__)

# サーバー内インメモリキャッシュ
SEARCH_CACHE = {}
CACHE_TTL = 600
MAX_CACHE_SIZE = 100

DEFAULT_SHOPS = [
    {
        "name": "CAFÉ DE ÉTOILE (おすすめ)", "genre": "カフェ・スイーツ", "catch": "こだわりの自家焙煎コーヒーと落ち着いたテラス席。",
        "address": "東京都渋谷区神南1-2-3", "access": "渋谷駅ハチ公口から徒歩5分", "budget": "1,000円〜2,000円", "min_budget": 1000,
        "lat": 35.6618, "lng": 139.7011, "tel": "03-0000-0001", "is_indoor": False,
        "photo": "https://images.unsplash.com/photo-1554118811-1e0d58224f24?w=600", "url": "https://www.hotpepper.jp/", "is_special": True
    },
    {
        "name": "個室和食 旬彩庵 (おすすめ)", "genre": "和食・居酒屋", "catch": "旬の厳選鮮魚と地酒を嗜むプライベート個室空間。",
        "address": "大阪府大阪市北区梅田1-1-1", "access": "梅田駅・大阪駅直結 地下街", "budget": "3,500円〜5,000円", "min_budget": 3500,
        "lat": 34.7024, "lng": 135.4959, "tel": "06-0000-0002", "is_indoor": True,
        "photo": "https://images.unsplash.com/photo-1517248135467-4c7edcad34c4?w=600", "url": "https://www.hotpepper.jp/", "is_special": True
    },
    {
        "name": "深夜営業 BAR 夜行列車", "genre": "バー・お酒", "catch": "朝5時まで営業。二次会に最適な大人の隠れ家バー。",
        "address": "東京都新宿区歌舞伎町1-2-3", "access": "新宿駅東口徒歩3分", "budget": "2,000円〜3,500円", "min_budget": 2000,
        "lat": 35.6938, "lng": 139.7034, "tel": "03-0000-0003", "is_indoor": True,
        "photo": "https://images.unsplash.com/photo-1514933651103-005eec06c04b?w=600", "url": "https://www.hotpepper.jp/", "is_special": True
    }
]

# Gzip自動圧縮 & キャッシュ制御
@app.after_request
def add_header_and_compress(response):
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
    compressed_data = gzip.compress(data)
    response.set_data(compressed_data)
    response.headers['Content-Encoding'] = 'gzip'
    response.headers['Content-Length'] = len(compressed_data)
    return response

# ================= 共通CSS・ヘッダー =================
COMMON_HEAD = """
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <link rel="icon" href="data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 100 100%22><text y=%22.9em%22 font-size=%2290%22>🍽️</text></svg>">
    <link rel="manifest" href="/manifest.json">
    <meta name="theme-color" content="#c2785c">
    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
    <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
    <script>
        const savedTheme = localStorage.getItem('eatmap_theme') || (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
        document.documentElement.setAttribute('data-theme', savedTheme);
    </script>
    <style>
        :root {
            --primary: #c2785c;
            --primary-light: #fbeee8;
            --primary-dark: #8c4c32;
            --accent: #f59e0b;
            --bg: #faf6f0;
            --card-bg: rgba(255, 255, 255, 0.96);
            --text-main: #4a382e;
            --text-sub: #8c766b;
            --glass-border: rgba(230, 215, 205, 0.85);
            --input-bg: #ffffff;
            --info-box: #faf7f2;
        }
        [data-theme="dark"] {
            --primary: #e09f80;
            --primary-light: #2c211c;
            --primary-dark: #f0bfa8;
            --accent: #fbbf24;
            --bg: #121214;
            --card-bg: rgba(24, 24, 28, 0.96);
            --text-main: #f3ede8;
            --text-sub: #a89a90;
            --glass-border: rgba(65, 55, 50, 0.85);
            --input-bg: #1e1e24;
            --info-box: #1e1b19;
        }
        body { 
            background: linear-gradient(180deg, #f7efe6 0%, var(--bg) 100%); 
            color: var(--text-main); 
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Hiragino Sans", "Hiragino Kaku Gothic ProN", Meiryo, sans-serif;
            margin: 0; padding: 16px; padding-bottom: 95px; 
            -webkit-tap-highlight-color: transparent; min-height: 100vh; box-sizing: border-box;
        }
        [data-theme="dark"] body { background: linear-gradient(180deg, #1a1715 0%, var(--bg) 100%); }
        .max-w { max-width: 480px; margin: 0 auto; }
        
        .glass-card {
            background: var(--card-bg); backdrop-filter: blur(12px); -webkit-backdrop-filter: blur(12px);
            border: 1px solid var(--glass-border); border-radius: 20px;
            box-shadow: 0 10px 25px rgba(0, 0, 0, 0.08); padding: 20px; margin-bottom: 16px; position: relative;
        }
        .top-bar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 15px; }
        .app-brand { font-size: 24px; font-weight: 900; letter-spacing: 1.5px; color: var(--primary); }
        .pill-btn {
            background: var(--primary-light); color: var(--primary); border: 1px solid var(--glass-border);
            padding: 8px 14px; border-radius: 25px; font-size: 12px; font-weight: 800; cursor: pointer; text-decoration: none;
            display: inline-flex; align-items: center; gap: 4px;
        }
        .icon-circle-btn {
            background: var(--primary-light); color: var(--primary); border: 1px solid var(--glass-border);
            border-radius: 50%; width: 38px; height: 38px; display: flex; align-items: center; justify-content: center;
            font-size: 16px; cursor: pointer;
        }

        .bottom-nav { 
            position: fixed; bottom: 0; left: 0; width: 100%; 
            background: var(--card-bg); backdrop-filter: blur(16px); -webkit-backdrop-filter: blur(16px);
            box-shadow: 0 -4px 20px rgba(0, 0, 0, 0.12); display: flex; justify-content: space-around; 
            padding: 8px 0; padding-bottom: calc(8px + env(safe-area-inset-bottom)); z-index: 1000; border-top: 1px solid var(--glass-border); 
        }
        .bottom-nav a { 
            color: var(--text-sub); text-decoration: none; font-size: 11px; display: flex; flex-direction: column; 
            align-items: center; gap: 3px; font-weight: 800; width: 20%; 
        }
        .bottom-nav a.active { color: var(--primary); }
        .bottom-nav span.icon { font-size: 22px; }

        .input-group { position: relative; display: flex; align-items: center; margin-bottom: 14px; }
        .input-group input, .input-group select {
            width: 100%; padding: 14px 44px 14px 14px; border: 1.5px solid var(--glass-border); border-radius: 12px;
            font-size: 16px; background-color: var(--input-bg); color: var(--text-main); box-sizing: border-box; outline: none; font-weight: 700;
        }
        .input-unit { position: absolute; right: 14px; font-size: 14px; font-weight: 800; color: var(--text-sub); pointer-events: none; }

        .btn-large {
            min-height: 52px; width: 100%; border-radius: 26px; font-size: 16px; font-weight: 900;
            display: flex; align-items: center; justify-content: center; gap: 8px; border: none; cursor: pointer;
            box-shadow: 0 6px 18px rgba(194, 120, 92, 0.35); text-decoration: none; box-sizing: border-box; transition: transform 0.1s;
        }
        .btn-large:active { transform: scale(0.98); }
        .btn-primary { background: linear-gradient(135deg, #c2785c 0%, #a85d43 100%); color: white; }
        .btn-green { background: linear-gradient(135deg, #10b981 0%, #059669 100%); color: white; box-shadow: 0 6px 18px rgba(16, 185, 129, 0.3); }
        .btn-accent { background: linear-gradient(135deg, #f59e0b 0%, #d97706 100%); color: white; box-shadow: 0 6px 18px rgba(245, 158, 11, 0.3); }

        .shop-card {
            background: var(--card-bg); border-radius: 18px; padding: 14px; margin-bottom: 15px;
            box-shadow: 0 4px 15px rgba(0,0,0,0.06); border: 1px solid var(--glass-border); position: relative; display: flex; flex-direction: column;
        }
        .shop-card.special { border: 2px solid var(--accent); }
        .shop-img { width: 100%; height: 160px; object-fit: cover; border-radius: 12px; margin-bottom: 10px; background-color: #333; }
        .shop-name { font-size: 17px; font-weight: 800; color: var(--primary); margin: 0 0 4px 0; padding-right: 40px; }
        .shop-genre { font-size: 12px; color: var(--text-sub); margin-bottom: 6px; }
        .shop-info { font-size: 12px; color: var(--text-sub); line-height: 1.5; background: var(--info-box); padding: 8px 12px; border-radius: 10px; margin-bottom: 10px; }
        .btn-group { display: flex; gap: 8px; margin-top: auto; }
        .btn-act { flex: 1; min-height: 44px; padding: 10px 6px; border-radius: 20px; font-size: 12px; font-weight: 800; text-align: center; text-decoration: none; border: none; cursor: pointer; display: flex; align-items: center; justify-content: center; }
        .fav-btn { position: absolute; top: 12px; right: 12px; font-size: 22px; cursor: pointer; background: var(--card-bg); border: 1px solid var(--glass-border); border-radius: 50%; width: 40px; height: 40px; display: flex; align-items: center; justify-content: center; outline: none; }
        .fav-btn.active { color: #f43f5e; }

        #loading-overlay { position: fixed; top: 0; left: 0; width: 100vw; height: 100vh; background: var(--bg); opacity: 0.95; display: none; justify-content: center; align-items: center; flex-direction: column; z-index: 9999; }
        .loader-ring { width: 50px; height: 50px; border: 4px solid var(--primary-light); border-top: 4px solid var(--primary); border-radius: 50%; animation: spin 0.9s linear infinite; margin-bottom: 15px; }
        @keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }
        #offline-alert-bar { display: none; background: #e11d48; color: white; font-size: 11px; font-weight: 800; text-align: center; padding: 6px 10px; border-radius: 8px; margin-bottom: 12px; }
    </style>
"""

BOTTOM_NAV = """
    <div class="bottom-nav">
        <a href="/" id="nav-home"><span class="icon">🏠</span><span>ホーム</span></a>
        <a href="/chat" id="nav-chat"><span class="icon">🤖</span><span>AI相談</span></a>
        <a href="/favorites" id="nav-fav"><span class="icon">👑</span><span>マイデータ</span></a>
        <a href="/game" id="nav-game"><span class="icon">🎰</span><span>店決め</span></a>
        <a href="/tools" id="nav-tools"><span class="icon">🧮</span><span>ツール</span></a>
    </div>
    <script>
        const p = window.location.pathname;
        if(p==='/') document.getElementById('nav-home').classList.add('active');
        if(p==='/chat') document.getElementById('nav-chat').classList.add('active');
        if(p==='/favorites') document.getElementById('nav-fav').classList.add('active');
        if(p==='/game') document.getElementById('nav-game').classList.add('active');
        if(p==='/tools') document.getElementById('nav-tools').classList.add('active');

        function toggleDarkMode() {
            const cur = document.documentElement.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
            document.documentElement.setAttribute('data-theme', cur);
            localStorage.setItem('eatmap_theme', cur);
            updateThemeIcons();
        }
        function updateThemeIcons() {
            const isDark = document.documentElement.getAttribute('data-theme') === 'dark';
            document.querySelectorAll('.theme-toggle-btn').forEach(b => b.innerText = isDark ? '☀️' : '🌙');
        }
        window.addEventListener('DOMContentLoaded', updateThemeIcons);

        function checkNetworkStatus() {
            const bar = document.getElementById('offline-alert-bar');
            if (bar) bar.style.display = navigator.onLine ? 'none' : 'block';
        }
        window.addEventListener('online', checkNetworkStatus);
        window.addEventListener('offline', checkNetworkStatus);
        window.addEventListener('DOMContentLoaded', checkNetworkStatus);

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
                    const installing = reg.installing;
                    installing.onstatechange = () => {
                        if (installing.state === 'installed' && navigator.serviceWorker.controller) {
                            window.location.reload();
                        }
                    };
                };
            });
        }
    </script>
"""

# ================= 画面1: ホーム =================
HOME_HTML = """
<!DOCTYPE html>
<html lang="ja">
<head>
    """ + COMMON_HEAD + """
    <title>EAT MAP - 全国の美味しいお店探し</title>
</head>
<body>
    <div id="loading-overlay"><div class="loader-ring"></div><div id="loading-msg" style="color:var(--primary); font-weight:800;">お店を探しています...</div></div>
    
    <div class="max-w">
        <div id="offline-alert-bar">📡 現在オフラインです</div>

        <div class="top-bar">
            <div class="app-brand">🍽️ EAT MAP</div>
            <div style="display:flex; gap:6px;">
                <button class="icon-circle-btn reload-btn" onclick="forceUpdateApp()" title="最新版に更新">🔄</button>
                <button class="icon-circle-btn theme-toggle-btn" onclick="toggleDarkMode()">🌙</button>
                <button class="pill-btn" onclick="shareApp()">📤 シェア</button>
            </div>
        </div>

        <a href="javascript:void(0)" onclick="searchNijikai()" class="btn-large btn-accent" style="margin-bottom:14px;">
            <span>🍻</span> 現在地付近で二次会を探す（バー・深夜）
        </a>

        <button class="btn-large btn-green" onclick="searchCurrentLocation()" style="margin-bottom:14px;">
            <span>📍</span> 現在地周辺から一発検索
        </button>

        <div class="glass-card">
            <div style="font-size:13px; font-weight:800; margin-bottom:10px; color:var(--text-sub);">⭐ よく使うジャンル</div>
            <div style="display:grid; grid-template-columns: repeat(2, 1fr); gap:10px; margin-bottom:16px;">
                <button type="button" class="btn-act btn-sub" onclick="quickCategory('居酒屋 個室')">🍺 個室居酒屋</button>
                <button type="button" class="btn-act btn-sub" onclick="quickCategory('カフェ')">☕ カフェ</button>
                <button type="button" class="btn-act btn-sub" onclick="quickCategory('焼肉')">🍖 焼肉</button>
                <button type="button" class="btn-act btn-sub" onclick="quickCategory('ラーメン')">🍜 ラーメン</button>
            </div>
            
            <form action="/search" method="GET" id="search-form" onsubmit="showLoading()">
                <input type="hidden" name="rain" id="form-rain" value="0">
                <input type="hidden" name="lat" id="form-lat" value="">
                <input type="hidden" name="lng" id="form-lng" value="">

                <label style="font-size:12px; font-weight:800; display:block; margin-bottom:4px;">📍 エリア・駅名</label>
                <div class="input-group">
                    <input type="text" name="area" id="area-input" placeholder="例: 渋谷、梅田、姫路、博多">
                    <span class="input-unit">駅・街</span>
                </div>

                <label style="font-size:12px; font-weight:800; display:block; margin-bottom:4px;">🔍 気分・こだわり・予算</label>
                <div class="input-group">
                    <input type="text" name="keyword" id="keyword-input" placeholder="例: 個室、飲み放題、テラス">
                    <span class="input-unit">条件</span>
                </div>

                <div style="display: flex; gap: 8px;">
                    <div class="input-group" style="flex: 1;">
                        <select name="budget_filter">
                            <option value="">予算指定なし</option>
                            <option value="2000">〜2,000円 (サク飲み)</option>
                            <option value="4000">〜4,000円 (定番)</option>
                            <option value="6000">〜6,000円 (ご褒美)</option>
                        </select>
                    </div>
                    <div class="input-group" style="flex: 1;">
                        <select name="people">
                            <option value="1名">1名 (ソロ)</option>
                            <option value="2名" selected>2名 (ペア)</option>
                            <option value="3〜4名">3〜4名 (グループ)</option>
                            <option value="5名以上">5名以上 (宴会)</option>
                        </select>
                    </div>
                </div>

                <button type="submit" class="btn-large btn-primary" style="margin-top:6px;">条件でお店を探す</button>
            </form>
        </div>
    </div>
    """ + BOTTOM_NAV + """

    <script>
        function showLoading() {
            if (!navigator.onLine) { alert("現在オフラインです。"); return false; }
            document.getElementById('loading-overlay').style.display = 'flex';
        }

        function searchCurrentLocation() {
            if (!navigator.onLine) return alert("現在オフラインです。");
            if (!navigator.geolocation) return alert("端末のGPS機能が利用できません。");
            document.getElementById('loading-overlay').style.display = 'flex';
            navigator.geolocation.getCurrentPosition(pos => {
                window.location.href = `/search?lat=${pos.coords.latitude}&lng=${pos.coords.longitude}&area=現在地周辺`;
            }, err => {
                document.getElementById('loading-overlay').style.display = 'none';
                alert("位置情報の取得が許可されませんでした。エリア名を入力してください。");
            }, { timeout: 8000 });
        }

        function searchNijikai() {
            if (!navigator.onLine) return alert("現在オフラインです。");
            if (!navigator.geolocation) {
                window.location.href = `/search?keyword=${encodeURIComponent("二次会 バー 深夜")}`;
                return;
            }
            document.getElementById('loading-overlay').style.display = 'flex';
            navigator.geolocation.getCurrentPosition(pos => {
                window.location.href = `/search?lat=${pos.coords.latitude}&lng=${pos.coords.longitude}&keyword=${encodeURIComponent("二次会 バー 深夜")}&area=現在地近く`;
            }, () => {
                window.location.href = `/search?keyword=${encodeURIComponent("二次会 バー 深夜")}`;
            }, { timeout: 6000 });
        }

        function quickCategory(cat) {
            document.getElementById('keyword-input').value = cat;
            document.getElementById('loading-overlay').style.display = 'flex';
            document.getElementById('search-form').submit();
        }

        async function shareApp() {
            if (navigator.share) navigator.share({title: 'EAT MAP', url: window.location.origin});
            else prompt("URLをコピーしてシェア:", window.location.origin);
        }
    </script>
</body>
</html>
"""

# ================= 画面2: 検索結果 =================
RESULT_HTML = """
<!DOCTYPE html>
<html lang="ja">
<head>
    """ + COMMON_HEAD + """
    <title>検索結果 - EAT MAP</title>
    <style>
        .map-box { height: 210px; width: 100%; border-radius: 16px; margin-bottom: 14px; border: 1.5px solid var(--glass-border); }
        .view-controls { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
        .toggle-view-btn { background: var(--input-bg); border: 1px solid var(--glass-border); border-radius: 10px; padding: 8px 12px; font-size: 12px; font-weight: 800; cursor: pointer; color: var(--text-main); }
        #vote-float-bar {
            position: fixed; bottom: 80px; left: 50%; transform: translateX(-50%);
            background: linear-gradient(135deg, #f59e0b, #d97706); color: white;
            padding: 12px 26px; border-radius: 30px; font-size: 14px; font-weight: 900;
            box-shadow: 0 4px 15px rgba(217, 119, 6, 0.4); display: none; z-index: 900; cursor: pointer;
        }
    </style>
</head>
<body>
    <div class="max-w">
        <div id="offline-alert-bar">📡 現在オフラインです</div>

        <div class="top-bar">
            <a href="/" class="pill-btn">← 条件変更</a>
            <div style="font-size:14px; font-weight:900; color:var(--primary);">{{ search_title }} ({{ shops|length }}件)</div>
            <div style="display:flex; gap:6px;">
                <button class="icon-circle-btn reload-btn" onclick="forceUpdateApp()">🔄</button>
                <button class="icon-circle-btn theme-toggle-btn" onclick="toggleDarkMode()">🌙</button>
                <button class="pill-btn" onclick="shareApp()">📤 シェア</button>
            </div>
        </div>

        <div id="map" class="map-box"></div>

        <div class="view-controls">
            <div style="display:flex; gap:6px;">
                <button class="toggle-view-btn" onclick="sortByLocation()">📍 近い順</button>
                <button class="toggle-view-btn" onclick="sortByBudget()">💰 予算順</button>
            </div>
            <a href="/tools" class="toggle-view-btn" style="text-decoration:none; color:var(--primary);">🧮 ツールへ ↗</a>
        </div>

        <div id="shop-container">
            {% for shop in shops %}
            <div class="shop-card {% if shop.is_special %}special{% endif %}" data-lat="{{ shop.lat }}" data-lng="{{ shop.lng }}" data-budget="{{ shop.min_budget }}">
                {% if shop.is_special %}<div class="special-badge">✨ おすすめ</div>{% endif %}
                <button class="fav-btn" onclick='toggleFavorite(this, {{ shop | tojson }})'>♡</button>
                {% if shop.photo %}<img src="{{ shop.photo }}" class="shop-img" loading="lazy">{% endif %}
                <h4 class="shop-name">{{ shop.name }}</h4>
                <div class="shop-genre">🏷️ {{ shop.genre }}</div>
                <div class="shop-info">
                    📍 {{ shop.address }} <span class="loc-dist" style="color:var(--primary); font-weight:800;"></span><br>
                    💰 予算：{{ shop.budget }}
                </div>
                
                <div class="btn-group">
                    <a href="tel:{{ shop.tel }}" class="btn-act btn-sub">📞 電話</a>
                    <a href="https://www.google.com/maps/dir/?api=1&destination={{ shop.address | urlencode }}" target="_blank" class="btn-act btn-green">📍 道案内</a>
                    <a href="{{ shop.url }}" target="_blank" class="btn-act btn-primary">予約 ↗</a>
                </div>
                <button type="button" class="btn-act btn-sub" style="margin-top:8px; border:1px dashed var(--accent); color:var(--accent);" onclick="toggleVoteList('{{ shop.name }}', this)">🗳️ 投票候補に追加</button>
            </div>
            {% endfor %}
        </div>
    </div>

    <div id="vote-float-bar" onclick="sendVoteLink()">🗳️ 候補を決めてLINE投票 (<span id="v-count">0</span>件)</div>

    """ + BOTTOM_NAV + """

    <script>
        const shops = {{ shops | tojson | safe }};
        let selectedVotes = [];

        if (shops.length > 0 && shops[0].lat && shops[0].lng) {
            const map = L.map('map').setView([shops[0].lat, shops[0].lng], 14);
            L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', { attribution: '&copy; OpenStreetMap' }).addTo(map);
            shops.forEach(s => { 
                if(s.lat && s.lng) L.marker([s.lat, s.lng]).addTo(map).bindPopup(`<b>${s.name}</b><br>${s.genre}`); 
            });
        } else {
            const map = L.map('map').setView([35.6812, 139.7671], 12);
            L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', { attribution: '&copy; OpenStreetMap' }).addTo(map);
        }

        function sortByLocation() {
            if (!navigator.geolocation) return alert("GPS非対応です");
            navigator.geolocation.getCurrentPosition(pos => {
                const myLat = pos.coords.latitude, myLng = pos.coords.longitude;
                const container = document.getElementById('shop-container');
                const cards = Array.from(container.getElementsByClassName('shop-card'));
                cards.forEach(card => {
                    const lat = parseFloat(card.dataset.lat), lng = parseFloat(card.dataset.lng);
                    if(lat && lng) {
                        const dist = calcDist(myLat, myLng, lat, lng);
                        card.dataset.dist = dist;
                        const label = card.querySelector('.loc-dist');
                        if (label) label.innerText = `(約${(dist*1000).toFixed(0)}m)`;
                    } else { card.dataset.dist = 9999; }
                });
                cards.sort((a,b) => parseFloat(a.dataset.dist) - parseFloat(b.dataset.dist));
                cards.forEach(c => container.appendChild(c));
            });
        }
        function calcDist(lat1, lon1, lat2, lon2) {
            const R = 6371, dLat = (lat2-lat1)*Math.PI/180, dLon = (lon2-lon1)*Math.PI/180;
            const a = Math.sin(dLat/2)*Math.sin(dLat/2) + Math.cos(lat1*Math.PI/180)*Math.cos(lat2*Math.PI/180)*Math.sin(dLon/2)*Math.sin(dLon/2);
            return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1-a));
        }

        function sortByBudget() {
            const container = document.getElementById('shop-container');
            const cards = Array.from(container.getElementsByClassName('shop-card'));
            cards.sort((a,b) => parseInt(a.dataset.budget) - parseInt(b.dataset.budget));
            cards.forEach(c => container.appendChild(c));
        }

        function toggleVoteList(name, el) {
            const idx = selectedVotes.indexOf(name);
            if(idx > -1) { selectedVotes.splice(idx, 1); el.innerText = "🗳️ 投票候補に追加"; }
            else { selectedVotes.push(name); el.innerText = "✅ 候補追加済み"; }
            document.getElementById('v-count').innerText = selectedVotes.length;
            document.getElementById('vote-float-bar').style.display = selectedVotes.length > 0 ? 'block' : 'none';
        }
        function sendVoteLink() {
            const u = window.location.origin + "/vote?shops=" + encodeURIComponent(selectedVotes.join(','));
            if(navigator.share) navigator.share({title: 'どのお店にする？LINE投票！', url: u});
            else prompt("このURLをLINEに送って投票してもらおう:", u);
        }

        function toggleFavorite(btn, shop) {
            let favs = JSON.parse(localStorage.getItem('eatmap_favs') || '[]');
            const idx = favs.findIndex(i => i.name === shop.name);
            if (idx > -1) { favs.splice(idx, 1); btn.innerHTML = '♡'; btn.classList.remove('active'); }
            else { shop.memo = ""; shop.tags = []; shop.visited = false; shop.my_photo = ""; favs.push(shop); btn.innerHTML = '♥'; btn.classList.add('active'); }
            localStorage.setItem('eatmap_favs', JSON.stringify(favs));
        }
        window.addEventListener('DOMContentLoaded', () => {
            const favs = JSON.parse(localStorage.getItem('eatmap_favs') || '[]');
            document.querySelectorAll('.shop-card').forEach(card => {
                const name = card.querySelector('.shop-name').innerText;
                if(favs.some(i => i.name === name)) {
                    card.querySelector('.fav-btn').innerHTML = '♥'; card.querySelector('.fav-btn').classList.add('active');
                }
            });
        });
        async function shareApp() {
            if (navigator.share) navigator.share({title: 'EAT MAP', url: window.location.href});
        }
    </script>
</body>
</html>
"""

# ================= 画面3: マイデータ =================
FAVORITES_HTML = """
<!DOCTYPE html>
<html lang="ja">
<head>
    """ + COMMON_HEAD + """
    <title>マイデータ - EAT MAP</title>
</head>
<body>
    <div class="max-w">
        <div id="offline-alert-bar">📡 現在オフラインです（保存済みデータは閲覧可能）</div>

        <div class="top-bar">
            <h2 style="font-size: 18px; margin: 0; color: var(--primary);">👑 グルメマイデータ</h2>
            <div style="display:flex; gap:6px;">
                <button class="icon-circle-btn reload-btn" onclick="forceUpdateApp()">🔄</button>
                <button class="icon-circle-btn theme-toggle-btn" onclick="toggleDarkMode()">🌙</button>
                <button class="pill-btn" onclick="exportBackup()">📋 引き継ぎ</button>
            </div>
        </div>

        <div style="background:linear-gradient(135deg, #10b981 0%, #059669 100%); color:white; border-radius:18px; padding:18px; margin-bottom:16px;">
            <div style="font-size:12px; font-weight:800;">🗾 47都道府県 グルメ全国制覇度</div>
            <div style="font-size:24px; font-weight:900; margin:4px 0;" id="conquer-title">0 / 47 都道府県 (0%)</div>
            <div style="background:rgba(255,255,255,0.3); border-radius:10px; height:10px; overflow:hidden;"><div id="progress-fill" style="background:#fde047; height:100%; width:0%; transition:width 0.4s;"></div></div>
        </div>

        <div id="favorites-list"></div>
    </div>
    """ + BOTTOM_NAV + """

    <script>
        function getPrefecture(addr) {
            if(!addr) return "その他";
            const m = addr.match(/(東京都|北海道|(?:京都|大阪)府|.{2,3}県)/);
            return m ? m[1] : "その他";
        }

        function renderFavorites() {
            const list = document.getElementById('favorites-list');
            const favs = JSON.parse(localStorage.getItem('eatmap_favs') || '[]');
            
            favs.forEach(s => { s.pref = getPrefecture(s.address); });
            const visitedPrefs = new Set();
            favs.forEach(s => { if(s.visited && s.pref !== "その他") visitedPrefs.add(s.pref); });
            const prefCount = visitedPrefs.size;
            const rate = ((prefCount / 47) * 100).toFixed(1);

            document.getElementById('conquer-title').innerText = `${prefCount} / 47 都道府県 (${rate}%)`;
            document.getElementById('progress-fill').style.width = Math.min(100, Math.max(3, (prefCount / 47) * 100)) + "%";

            if (favs.length === 0) {
                list.innerHTML = `<div style="text-align:center; padding:40px 0; color:var(--text-sub);">店舗データがありません</div>`;
                return;
            }

            list.innerHTML = favs.map((shop, i) => `
                <div class="shop-card">
                    <button class="fav-btn active" onclick="removeFavorite(${i})">♥</button>
                    <div><span style="font-size:11px; background:var(--primary-light); color:var(--primary); padding:3px 8px; border-radius:6px; font-weight:800;">📍 ${shop.pref}</span></div>
                    
                    ${shop.my_photo ? `<img src="${shop.my_photo}" class="shop-img" style="border: 2px solid var(--accent); margin-top:8px;">` : (shop.photo ? `<img src="${shop.photo}" class="shop-img" style="margin-top:8px;">` : '')}
                    
                    <label class="btn-act btn-sub" style="margin-top:6px; cursor:pointer;">
                        📸 料理の写真を登録
                        <input type="file" accept="image/*" style="display:none;" onchange="uploadMyPhoto(event, ${i})">
                    </label>

                    <h4 class="shop-name" style="margin-top:8px;">${shop.name}</h4>
                    <div class="shop-info">📍 ${shop.address}</div>

                    <div style="display:flex; gap:8px; margin-top:8px;">
                        <button class="btn-act ${shop.visited ? 'btn-green' : 'btn-sub'}" onclick="toggleVisited(${i})">
                            ${shop.visited ? '🏁 制覇済み！' : '🚩 行ってみたい'}
                        </button>
                        <button class="btn-act btn-sub" onclick="editMemo(${i})">✏️ メモ</button>
                    </div>
                    ${shop.memo ? `<div style="background:var(--info-box); border-left:3px solid var(--accent); padding:8px; font-size:12px; margin-top:8px;">${shop.memo}</div>` : ''}
                </div>
            `).join('');
        }

        function uploadMyPhoto(e, idx) {
            const file = e.target.files[0];
            if (!file) return;
            const reader = new FileReader();
            reader.onload = function(evt) {
                const img = new Image();
                img.onload = function() {
                    const canvas = document.createElement('canvas');
                    const maxDim = 500;
                    let width = img.width, height = img.height;
                    if (width > height) {
                        if (width > maxDim) { height = Math.round((height * maxDim) / width); width = maxDim; }
                    } else {
                        if (height > maxDim) { width = Math.round((width * maxDim) / height); height = maxDim; }
                    }
                    canvas.width = width; canvas.height = height;
                    const ctx = canvas.getContext('2d');
                    ctx.drawImage(img, 0, 0, width, height);
                    const resizedDataUrl = canvas.toDataURL('image/jpeg', 0.7);

                    let favs = JSON.parse(localStorage.getItem('eatmap_favs') || '[]');
                    favs[idx].my_photo = resizedDataUrl;
                    try { localStorage.setItem('eatmap_favs', JSON.stringify(favs)); renderFavorites(); }
                    catch(err) { alert("保存容量が一杯です。不要なデータを削除してください。"); }
                };
                img.src = evt.target.result;
            };
            reader.readAsDataURL(file);
        }

        function toggleVisited(idx) {
            let favs = JSON.parse(localStorage.getItem('eatmap_favs') || '[]');
            favs[idx].visited = !favs[idx].visited;
            localStorage.setItem('eatmap_favs', JSON.stringify(favs));
            renderFavorites();
        }
        function editMemo(idx) {
            let favs = JSON.parse(localStorage.getItem('eatmap_favs') || '[]');
            const m = prompt("店舗メモを記入:", favs[idx].memo || "");
            if(m !== null) { favs[idx].memo = m; localStorage.setItem('eatmap_favs', JSON.stringify(favs)); renderFavorites(); }
        }
        function removeFavorite(idx) {
            let favs = JSON.parse(localStorage.getItem('eatmap_favs') || '[]');
            favs.splice(idx, 1);
            localStorage.setItem('eatmap_favs', JSON.stringify(favs));
            renderFavorites();
        }
        function exportBackup() {
            const d = localStorage.getItem('eatmap_favs');
            if(!d || JSON.parse(d).length === 0) return alert("保存データがありません");
            const code = btoa(unescape(encodeURIComponent(d)));
            if(navigator.clipboard) navigator.clipboard.writeText(code).then(() => alert("引き継ぎコードをコピーしました！"));
            else prompt("控えて保管してください:", code);
        }

        window.addEventListener('DOMContentLoaded', renderFavorites);
    </script>
</body>
</html>
"""

# ================= 画面4: 店決めルーレット =================
GAME_HTML = """
<!DOCTYPE html>
<html lang="ja">
<head>
    """ + COMMON_HEAD + """
    <title>店決めルーレット - EAT MAP</title>
    <style>
        .roulette-wrapper { position: relative; width: 310px; height: 310px; margin: 15px auto; display: flex; align-items: center; justify-content: center; }
        .roulette-pointer { position: absolute; top: -14px; left: 50%; transform: translateX(-50%); width: 0; height: 0; border-left: 14px solid transparent; border-right: 14px solid transparent; border-top: 24px solid #ef4444; z-index: 20; filter: drop-shadow(0 2px 4px rgba(0,0,0,0.3)); }
        .roulette-center { position: absolute; width: 44px; height: 44px; border-radius: 50%; background: var(--card-bg); border: 3px solid var(--primary); box-shadow: 0 2px 8px rgba(0,0,0,0.2); z-index: 10; display: flex; align-items: center; justify-content: center; font-size: 18px; }
        #roulette-canvas { border-radius: 50%; box-shadow: 0 8px 24px rgba(0, 0, 0, 0.25); transition: transform cubic-bezier(0.15, 0.9, 0.2, 1); }
        .result-card { background: var(--card-bg); border: 2px solid var(--accent); border-radius: 16px; padding: 18px; text-align: center; margin-top: 15px; display: none; box-shadow: 0 6px 20px rgba(245, 158, 11, 0.15); }
    </style>
</head>
<body>
    <div class="max-w">
        <div class="top-bar">
            <h2 style="font-size: 18px; color: var(--primary); margin: 0;">🎰 店決めルーレット</h2>
            <div style="display:flex; gap:6px;">
                <button class="icon-circle-btn reload-btn" onclick="forceUpdateApp()">🔄</button>
                <button class="icon-circle-btn theme-toggle-btn" onclick="toggleDarkMode()">🌙</button>
            </div>
        </div>

        <div class="roulette-wrapper">
            <div class="roulette-pointer"></div>
            <div class="roulette-center">🍽️</div>
            <canvas id="roulette-canvas" width="300" height="300"></canvas>
        </div>

        <button class="btn-large btn-primary" id="spin-btn" onclick="spinRoulette()">🎯 ルーレットを回す！</button>

        <div class="result-card" id="result-box">
            <div style="font-size: 13px; color: var(--text-sub);">今日の運命のジャンルは...</div>
            <div style="font-size: 26px; font-weight: 900; color: var(--primary); margin: 8px 0;" id="result-name">--</div>
            
            <button class="btn-large btn-primary" id="search-genre-btn" style="margin-bottom:10px;">このジャンルでお店を探す ↗</button>
            <a href="/tools" class="btn-large btn-green">🧮 決定！滞在タイマー・割り勘ツールを開く</a>
        </div>
    </div>
    """ + BOTTOM_NAV + """

    <script>
        const canvas = document.getElementById('roulette-canvas');
        const ctx = canvas.getContext('2d');
        const items = ["焼肉 🥩", "居酒屋 🍺", "カフェ ☕", "ラーメン 🍜", "海鮮・寿司 🐟", "カレー 🍛", "イタリアン 🍕", "中華 🥟"];
        const COLOR_PALETTE = ["#fca5a5", "#fed7aa", "#fef08a", "#bbf7d0", "#a7f3d0", "#bae6fd", "#c7d2fe", "#fbcfe8"];
        let currentRotation = 0, isSpinning = false;

        function drawRoulette() {
            ctx.clearRect(0, 0, 300, 300);
            const num = items.length, arc = (2 * Math.PI) / num;
            for (let i = 0; i < num; i++) {
                const angle = i * arc;
                ctx.fillStyle = COLOR_PALETTE[i % COLOR_PALETTE.length];
                ctx.beginPath();
                ctx.arc(150, 150, 145, angle, angle + arc, false);
                ctx.arc(150, 150, 0, angle + arc, angle, true);
                ctx.fill();
                ctx.save();
                ctx.strokeStyle = "rgba(255,255,255,0.85)"; ctx.lineWidth = 2; ctx.stroke();
                ctx.fillStyle = "#332219"; ctx.font = "bold 13px -apple-system, sans-serif";
                ctx.translate(150 + Math.cos(angle + arc / 2) * 95, 150 + Math.sin(angle + arc / 2) * 95);
                ctx.rotate(angle + arc / 2 + Math.PI / 2);
                ctx.fillText(items[i], -ctx.measureText(items[i]).width / 2, 0);
                ctx.restore();
            }
        }
        drawRoulette();

        function spinRoulette() {
            if (isSpinning) return;
            isSpinning = true;
            const btn = document.getElementById('spin-btn');
            btn.disabled = true; btn.innerText = "抽選中...";
            document.getElementById('result-box').style.display = "none";

            const randomExtra = Math.floor(Math.random() * 360);
            currentRotation += 360 * 6 + randomExtra;
            canvas.style.transition = "transform 4.5s cubic-bezier(0.15, 0.9, 0.2, 1)";
            canvas.style.transform = `rotate(${currentRotation}deg)`;

            setTimeout(() => {
                isSpinning = false; btn.disabled = false; btn.innerText = "🎯 もう一度回す！";
                const actualDeg = (currentRotation % 360);
                const step = 360 / items.length;
                const index = Math.floor((360 - actualDeg + 270) % 360 / step);
                const picked = items[index];
                const cleanGenre = picked.split(' ')[0];

                document.getElementById('result-name').innerText = picked;
                document.getElementById('search-genre-btn').onclick = () => {
                    window.location.href = `/search?keyword=${encodeURIComponent(cleanGenre)}`;
                };
                document.getElementById('result-box').style.display = "block";
            }, 4500);
        }
    </script>
</body>
</html>
"""

# ================= 画面5: ツール =================
TOOLS_HTML = """
<!DOCTYPE html>
<html lang="ja">
<head>
    """ + COMMON_HEAD + """
    <title>ツール - EAT MAP</title>
    <style>
        .timer-panel {
            background: linear-gradient(145deg, #1e293b, #0f172a); color: white;
            border-radius: 20px; padding: 18px; margin-bottom: 18px; box-shadow: 0 10px 25px rgba(0, 0, 0, 0.3);
            border: 1px solid rgba(255, 255, 255, 0.1);
        }
        .clock-header {
            display: flex; justify-content: space-between; align-items: center; background: rgba(255,255,255,0.08);
            padding: 8px 14px; border-radius: 12px; margin-bottom: 14px; font-weight: 800;
        }
        .timer-card-dual {
            background: rgba(255,255,255,0.05); border: 1px solid rgba(255,255,255,0.1);
            border-radius: 14px; padding: 14px; margin-bottom: 12px;
        }
        .digits-big {
            font-size: 34px; font-weight: 900; color: #38bdf8; font-family: ui-monospace, SFMono-Regular, monospace;
            text-align: center; letter-spacing: 2px; margin: 4px 0;
        }
        .digits-lo { color: #facc15; }
        .digits-danger { color: #f87171; animation: blink 1s infinite; }
        @keyframes blink { 50% { opacity: 0.6; } }

        .split-card-result {
            background: var(--info-box); border: 2px solid var(--accent); border-radius: 16px;
            padding: 16px; margin-top: 16px; display: none;
        }
        .split-row {
            display: flex; justify-content: space-between; align-items: baseline; padding: 8px 0; border-bottom: 1px dashed var(--glass-border);
        }
        .split-val-big {
            font-size: 28px; font-weight: 900; color: var(--accent); font-family: ui-monospace, sans-serif;
        }
    </style>
</head>
<body>
    <div class="max-w">
        <div class="top-bar">
            <h2 style="font-size: 18px; color: var(--primary); margin: 0;">🧮 おでかけ・飲み会サポート</h2>
            <div style="display:flex; gap:6px;">
                <button class="icon-circle-btn reload-btn" onclick="forceUpdateApp()">🔄</button>
                <button class="icon-circle-btn theme-toggle-btn" onclick="toggleDarkMode()">🌙</button>
            </div>
        </div>

        <div class="timer-panel">
            <div class="clock-header">
                <span style="color:#94a3b8; font-size:12px;">⏰ 現在時刻</span>
                <span style="font-size:16px; color:#38bdf8;" id="clock-now">--:--:--</span>
            </div>

            <div class="timer-card-dual">
                <div style="display:flex; justify-content:space-between; align-items:center;">
                    <span style="font-size:13px; font-weight:800; color:#cbd5e1;">🎯 目標終電・お開きまで</span>
                    <input type="time" id="clock-target-input" value="23:30" onchange="updateTargetTimeManual()" style="background:#334155; color:white; border:none; padding:4px 8px; border-radius:8px; font-weight:800;">
                </div>
                <div class="digits-big" id="digits-target-remain">--:--:--</div>
                <div style="font-size:11px; text-align:center; color:#94a3b8;" id="target-sub-label">目標時刻: 23:30</div>
            </div>

            <div class="timer-card-dual">
                <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
                    <span style="font-size:13px; font-weight:800; color:#cbd5e1;">⏱️ 席・コース管理（ダブルタイマー）</span>
                </div>
                <div style="display:flex; gap:6px; margin-bottom:10px;">
                    <button class="pill-btn" style="background:#334155; color:white;" onclick="setCourseDuration(90, 60)">90分 (L.O.60分)</button>
                    <button class="pill-btn" style="background:#334155; color:white;" onclick="setCourseDuration(120, 90)">120分 (L.O.90分)</button>
                    <button class="pill-btn" style="background:#334155; color:white;" onclick="setCourseDuration(180, 150)">180分 (L.O.150分)</button>
                </div>

                <div style="display:grid; grid-template-columns: 1fr 1fr; gap:8px;">
                    <div style="background:rgba(0,0,0,0.25); padding:10px; border-radius:10px; text-align:center;">
                        <div style="font-size:11px; font-weight:800; color:#facc15;">🍺 ラストオーダー</div>
                        <div class="digits-big digits-lo" style="font-size:24px;" id="digits-lo">--:--</div>
                    </div>
                    <div style="background:rgba(0,0,0,0.25); padding:10px; border-radius:10px; text-align:center;">
                        <div style="font-size:11px; font-weight:800; color:#38bdf8;">🚪 完全退席</div>
                        <div class="digits-big" style="font-size:24px;" id="digits-exit">--:--</div>
                    </div>
                </div>

                <div style="display:flex; gap:6px; margin-top:10px;">
                    <button class="btn-act btn-primary" onclick="toggleCourseTimer()" id="btn-course-toggle">タイマー開始</button>
                    <button class="btn-act btn-sub" onclick="resetCourseTimer()">リセット</button>
                </div>
            </div>
        </div>

        <div class="glass-card">
            <h3 style="font-size: 16px; margin-top:0; color:var(--primary);">💸 サクッと傾斜割り勘計算</h3>

            <label style="font-size:12px; font-weight:800; display:block; margin-bottom:4px;">会計合計金額</label>
            <div class="input-group">
                <input type="number" id="split-total" placeholder="例: 18500">
                <span class="input-unit">円</span>
            </div>

            <div style="display:grid; grid-template-columns: 1fr 1fr; gap:10px;">
                <div>
                    <label style="font-size:12px; font-weight:800; display:block; margin-bottom:4px;">🍺 お酒を飲んだ人</label>
                    <div class="input-group">
                        <input type="number" id="split-drinkers" value="2">
                        <span class="input-unit">人</span>
                    </div>
                </div>
                <div>
                    <label style="font-size:12px; font-weight:800; display:block; margin-bottom:4px;">🍵 飲まない人 (少食)</label>
                    <div class="input-group">
                        <input type="number" id="split-non-drinkers" value="1">
                        <span class="input-unit">人</span>
                    </div>
                </div>
            </div>

            <div style="display:grid; grid-template-columns: 1fr 1fr; gap:10px;">
                <div>
                    <label style="font-size:12px; font-weight:800; display:block; margin-bottom:4px;">飲まない人の割引額</label>
                    <div class="input-group">
                        <input type="number" id="split-discount" value="1000">
                        <span class="input-unit">円引</span>
                    </div>
                </div>
                <div>
                    <label style="font-size:12px; font-weight:800; display:block; margin-bottom:4px;">幹事の追加負担</label>
                    <div class="input-group">
                        <input type="number" id="split-kanji-extra" value="0">
                        <span class="input-unit">円</span>
                    </div>
                </div>
            </div>

            <label style="font-size:12px; font-weight:800; display:block; margin-bottom:4px;">端数処理単位</label>
            <div class="input-group">
                <select id="split-round">
                    <option value="500">500円単位で切り上げ（小銭いらず）</option>
                    <option value="100" selected>100円単位で切り上げ</option>
                    <option value="1">1円単位（きっちり）</option>
                </select>
            </div>

            <button type="button" class="btn-large btn-primary" onclick="calcSmartSplit()">割り勘を計算する</button>

            <div class="split-card-result" id="split-result-box">
                <div style="text-align:center; font-size:13px; font-weight:800; color:var(--text-sub); margin-bottom:8px;">お支払い内訳</div>
                
                <div class="split-row">
                    <span style="font-weight:800;">🍺 飲んだ人 (1人)</span>
                    <span class="split-val-big"><span id="res-drinker-per">0</span> <small style="font-size:14px;">円</small></span>
                </div>
                <div class="split-row" id="row-non-drinker">
                    <span style="font-weight:800;">🍵 飲まない人 (1人)</span>
                    <span class="split-val-big" style="color:#10b981;"><span id="res-nondrinker-per">0</span> <small style="font-size:14px;">円</small></span>
                </div>
                <div class="split-row" id="row-kanji" style="display:none;">
                    <span style="font-weight:800;">👑 幹事のお支払い</span>
                    <span class="split-val-big" style="color:var(--primary);"><span id="res-kanji-total">0</span> <small style="font-size:14px;">円</small></span>
                </div>
                <div style="font-size:12px; color:var(--text-sub); text-align:right; margin-top:8px;" id="res-extra-diff">集金合計: 0円 (お釣り: 0円)</div>

                <div class="input-group" style="margin-top:14px;">
                    <input type="text" id="paypay-id" placeholder="PayPayリンクやID（任意）">
                    <span class="input-unit">送金用</span>
                </div>

                <button type="button" class="btn-large btn-green" onclick="shareSplitLINE()">
                    <span>💬</span> LINEに結果を共有する
                </button>
            </div>
        </div>
    </div>
    """ + BOTTOM_NAV + """

    <script>
        function updateClock() {
            const now = new Date();
            document.getElementById('clock-now').innerText = now.toTimeString().split(' ')[0];
            if (targetTime) {
                const diff = targetTime - now;
                const digits = document.getElementById('digits-target-remain');
                if (diff <= 0) {
                    digits.innerText = "00:00:00";
                    digits.className = "digits-big digits-danger";
                } else {
                    const h = String(Math.floor(diff / 3600000)).padStart(2, '0');
                    const m = String(Math.floor((diff % 3600000) / 60000)).padStart(2, '0');
                    const s = String(Math.floor((diff % 60000) / 1000)).padStart(2, '0');
                    digits.innerText = `${h}:${m}:${s}`;
                    digits.className = diff <= 600000 ? "digits-big digits-danger" : (diff <= 1800000 ? "digits-big digits-lo" : "digits-big");
                }
            }
        }
        setInterval(updateClock, 1000);

        let targetTime = null;
        function updateTargetTimeManual() {
            const val = document.getElementById('clock-target-input').value;
            if(!val) return;
            const [h, m] = val.split(':').map(Number);
            const now = new Date();
            const t = new Date();
            t.setHours(h, m, 0, 0);
            if (t <= now) t.setDate(t.getDate() + 1);
            targetTime = t;
            document.getElementById('target-sub-label').innerText = `目標時刻: ${val}`;
        }
        updateTargetTimeManual();

        let courseExitSecs = 7200, courseLoSecs = 5400;
        let courseRunning = false, courseInterval = null;

        function setCourseDuration(exitMins, loMins) {
            courseExitSecs = exitMins * 60;
            courseLoSecs = loMins * 60;
            updateCourseDigits();
        }

        function toggleCourseTimer() {
            courseRunning = !courseRunning;
            const btn = document.getElementById('btn-course-toggle');
            if (courseRunning) {
                btn.innerText = "一時停止";
                btn.className = "btn-act btn-accent";
                courseInterval = setInterval(() => {
                    if (courseExitSecs > 0) courseExitSecs--;
                    if (courseLoSecs > 0) courseLoSecs--;
                    updateCourseDigits();
                }, 1000);
            } else {
                btn.innerText = "再開";
                btn.className = "btn-act btn-primary";
                clearInterval(courseInterval);
            }
        }

        function resetCourseTimer() {
            courseRunning = false;
            clearInterval(courseInterval);
            document.getElementById('btn-course-toggle').innerText = "タイマー開始";
            document.getElementById('btn-course-toggle').className = "btn-act btn-primary";
            setCourseDuration(120, 90);
        }

        function updateCourseDigits() {
            const loM = String(Math.floor(courseLoSecs / 60)).padStart(2, '0');
            const loS = String(courseLoSecs % 60).padStart(2, '0');
            const exM = String(Math.floor(courseExitSecs / 60)).padStart(2, '0');
            const exS = String(courseExitSecs % 60).padStart(2, '0');
            document.getElementById('digits-lo').innerText = `${loM}:${loS}`;
            document.getElementById('digits-exit').innerText = `${exM}:${exS}`;
        }
        updateCourseDigits();

        let lastSplitData = null;
        function calcSmartSplit() {
            const total = parseInt(document.getElementById('split-total').value);
            const drinkers = parseInt(document.getElementById('split-drinkers').value) || 0;
            const nonDrinkers = parseInt(document.getElementById('split-non-drinkers').value) || 0;
            const discount = parseInt(document.getElementById('split-discount').value) || 0;
            const kanjiExtra = parseInt(document.getElementById('split-kanji-extra').value) || 0;
            const roundUnit = parseInt(document.getElementById('split-round').value) || 100;

            const numPeople = drinkers + nonDrinkers;
            if (!total || numPeople <= 0) return alert("合計金額と人数を入力してください");

            const adjustedTotal = total - (kanjiExtra) + (discount * nonDrinkers);
            let baseDrinker = Math.ceil((adjustedTotal / numPeople) / roundUnit) * roundUnit;
            let baseNonDrinker = Math.max(0, baseDrinker - discount);

            let collected = (baseDrinker * drinkers) + (baseNonDrinker * nonDrinkers) + kanjiExtra;
            let diff = collected - total;

            document.getElementById('res-drinker-per').innerText = baseDrinker.toLocaleString();
            document.getElementById('res-nondrinker-per').innerText = baseNonDrinker.toLocaleString();
            
            if (nonDrinkers === 0) document.getElementById('row-non-drinker').style.display = 'none';
            else document.getElementById('row-non-drinker').style.display = 'flex';

            if (kanjiExtra > 0) {
                document.getElementById('row-kanji').style.display = 'flex';
                document.getElementById('res-kanji-total').innerText = (baseDrinker + kanjiExtra).toLocaleString();
            } else {
                document.getElementById('row-kanji').style.display = 'none';
            }

            document.getElementById('res-extra-diff').innerText = `集金合計: ${collected.toLocaleString()}円 (余剰・お釣り: +${diff.toLocaleString()}円)`;
            document.getElementById('split-result-box').style.display = 'block';

            lastSplitData = { total, drinkers, nonDrinkers, baseDrinker, baseNonDrinker, kanjiExtra, collected };
        }

        function shareSplitLINE() {
            if (!lastSplitData) return;
            const paypay = document.getElementById('paypay-id').value.trim();
            let text = `🍻 本日のお会計まとめ 🍻\\n` +
                       `合計: ${lastSplitData.total.toLocaleString()}円\\n` +
                       `-----------------------\\n` +
                       `🍺 飲んだ人: 各 ${lastSplitData.baseDrinker.toLocaleString()}円 (${lastSplitData.drinkers}名)\\n`;
            if (lastSplitData.nonDrinkers > 0) {
                text += `🍵 飲まない人: 各 ${lastSplitData.baseNonDrinker.toLocaleString()}円 (${lastSplitData.nonDrinkers}名)\\n`;
            }
            if (lastSplitData.kanjiExtra > 0) {
                text += `👑 幹事: ${(lastSplitData.baseDrinker + lastSplitData.kanjiExtra).toLocaleString()}円\\n`;
            }
            if (paypay) {
                text += `-----------------------\\n💰 送金先: ${paypay}\\n`;
            }
            text += `よろしくお願いいたします！`;

            const lineUrl = `https://line.me/R/msg/text/?${encodeURIComponent(text)}`;
            if (navigator.share) {
                navigator.share({ title: '本日のお会計まとめ', text: text });
            } else {
                window.open(lineUrl, '_blank');
            }
        }
    </script>
</body>
</html>
"""

# ================= 画面6: AIチャット =================
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
            <h2 style="font-size: 18px; color: var(--primary); margin: 0;">🤖 AIコンシェルジュ</h2>
            <div style="display:flex; gap:6px;">
                <button class="icon-circle-btn reload-btn" onclick="forceUpdateApp()">🔄</button>
                <button class="icon-circle-btn theme-toggle-btn" onclick="toggleDarkMode()">🌙</button>
            </div>
        </div>

        <div class="glass-card" style="min-height:350px;" id="chat-stream">
            <div style="background:var(--info-box); padding:12px; border-radius:12px; margin-bottom:10px; font-size:13px; line-height:1.6;">
                こんにちは！「新宿で静かな個室居酒屋」「23時以降も入れるカフェ」など、どんなお店でもお気軽にご相談ください。
            </div>
        </div>

        <div style="display:flex; gap:8px;">
            <input type="text" id="chat-input" placeholder="お店の相談を入力..." style="flex:1; padding:14px; border-radius:14px; border:1px solid var(--glass-border); font-size:14px; background:var(--input-bg); color:var(--text-main);">
            <button class="btn-large btn-primary" style="width:70px;" onclick="sendChat()">送信</button>
        </div>
    </div>
    """ + BOTTOM_NAV + """

    <script>
        async function sendChat() {
            const input = document.getElementById('chat-input');
            const txt = input.value.trim();
            if(!txt) return;
            const stream = document.getElementById('chat-stream');
            stream.innerHTML += `<div style="text-align:right; margin:10px 0;"><span style="background:var(--primary); color:white; padding:8px 14px; border-radius:14px; font-size:13px; display:inline-block;">${txt}</span></div>`;
            input.value = "";

            try {
                const res = await fetch('/api/chat', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({message:txt}) });
                const d = await res.json();
                stream.innerHTML += `<div style="text-align:left; margin:10px 0;"><span style="background:var(--info-box); color:var(--text-main); border:1px solid var(--glass-border); padding:8px 14px; border-radius:14px; font-size:13px; display:inline-block;">${d.reply.replace(/\\n/g, '<br>')}</span></div>`;
            } catch(e) {
                stream.innerHTML += `<div style="color:red; font-size:12px;">通信エラーが発生しました</div>`;
            }
        }
    </script>
</body>
</html>
"""

# ================= 画面7: 投票ページ =================
VOTE_HTML = """
<!DOCTYPE html>
<html lang="ja">
<head>""" + COMMON_HEAD + """<title>投票</title></head>
<body style="text-align:center;">
    <div class="max-w glass-card" style="margin-top:20px;">
        <h2 style="color:var(--primary);">🗳️ どのお店に行きたい？</h2>
        <p style="font-size:13px; color:var(--text-sub);">友達が選んだ候補リストです！</p>
        {% for name in shop_names %}
            <div style="background:var(--card-bg); border:1.5px solid var(--glass-border); padding:16px; border-radius:14px; margin-bottom:10px; font-weight:800; font-size:15px; color:var(--primary);">{{ loop.index }}. {{ name }}</div>
        {% endfor %}
        <a href="/" class="btn-large btn-primary" style="margin-top:20px;">EAT MAPアプリを開く</a>
    </div>
</body>
</html>
"""

# ----------------- 検索ロジック & API -----------------
def extract_min_budget(b_str):
    if not b_str: return 99999
    nums = re.findall(r'\d+', str(b_str).replace(',', ''))
    return int(nums[0]) if nums else 99999

def fetch_shops(keyword="", area="", lat=None, lng=None, budget_filter="", rain_mode=False):
    cache_key = f"{area}:{keyword}:{lat}:{lng}:{budget_filter}:{rain_mode}"
    now = time.time()
    if cache_key in SEARCH_CACHE:
        cached_time, cached_data = SEARCH_CACHE[cache_key]
        if now - cached_time < CACHE_TTL:
            return cached_data

    shops = list(DEFAULT_SHOPS)
    if rain_mode:
        shops = [s for s in shops if s.get('is_indoor')] + [s for s in shops if not s.get('is_indoor')]
    
    if not HOTPEPPER_API_KEY or "ここに" in HOTPEPPER_API_KEY:
        return shops

    params = {"key": HOTPEPPER_API_KEY, "count": 15, "format": "json"}
    if lat and lng:
        params["lat"] = lat
        params["lng"] = lng
        params["range"] = 4
        if keyword: params["keyword"] = keyword
    else:
        parts = [p for p in [area, keyword] if p]
        params["keyword"] = " ".join(parts) if parts else "グルメ"

    url = f"https://webservice.recruit.co.jp/hotpepper/gourmet/v1/?{urllib.parse.urlencode(params)}"
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=5) as res:
            data = json.loads(res.read().decode('utf-8'))
            api_shops = []
            for s in data.get("results", {}).get("shop", []):
                b_str = (s.get("budget") or {}).get("name", "")
                genre_str = (s.get("genre") or {}).get("name", "")
                photo_str = ((s.get("photo") or {}).get("pc") or {}).get("l", "")
                url_str = ((s.get("urls") or {}).get("pc")) or "#"
                min_b = extract_min_budget(b_str)

                if budget_filter and min_b > int(budget_filter):
                    continue

                api_shops.append({
                    "name": s.get("name", "店舗名不明"),
                    "genre": genre_str,
                    "address": s.get("address", ""),
                    "budget": b_str,
                    "min_budget": min_b,
                    "lat": s.get("lat"),
                    "lng": s.get("lng"),
                    "tel": s.get("tel", "0000000000"),
                    "photo": photo_str,
                    "url": url_str,
                    "is_special": False
                })
            result = api_shops if api_shops else shops
            if len(SEARCH_CACHE) > MAX_CACHE_SIZE:
                SEARCH_CACHE.clear()
            SEARCH_CACHE[cache_key] = (now, result)
            return result
    except Exception:
        return shops

# ================= UptimeRobot死活監視用エンドポイント =================
@app.route('/ping')
def ping():
    return "OK", 200

@app.errorhandler(500)
def internal_error(error):
    return render_template_string(HOME_HTML), 200

@app.route('/')
def home():
    try: return render_template_string(HOME_HTML)
    except: return render_template_string(HOME_HTML), 200

@app.route('/search')
def search():
    try:
        k = request.args.get('keyword', '')
        a = request.args.get('area', '')
        b = request.args.get('budget_filter', '')
        lat = request.args.get('lat')
        lng = request.args.get('lng')
        r = request.args.get('rain', '0') == '1'
        search_title = f"{a} {k}".strip() or "おすすめ店舗"
        shops = fetch_shops(keyword=k, area=a, lat=lat, lng=lng, budget_filter=b, rain_mode=r)
        return render_template_string(RESULT_HTML, shops=shops, search_title=search_title)
    except:
        return render_template_string(HOME_HTML)

@app.route('/favorites')
def favorites(): return render_template_string(FAVORITES_HTML)

@app.route('/chat')
def chat(): return render_template_string(CHAT_HTML)

@app.route('/game')
def game(): return render_template_string(GAME_HTML)

@app.route('/tools')
def tools(): return render_template_string(TOOLS_HTML)

@app.route('/vote')
def vote():
    names = request.args.get('shops', '').split(',')
    return render_template_string(VOTE_HTML, shop_names=[n for n in names if n])

# Gemini API 実装
@app.route('/api/chat', methods=['POST'])
def api_chat():
    msg = request.json.get('message', '') if request.json else ''
    if GEMINI_API_KEY and "ここに" not in GEMINI_API_KEY:
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
            prompt = f"あなたは親しみやすいグルメコンシェルジュです。日本の飲食店の提案・相談に乗ってください。ユーザーの要望: 「{msg}」。150文字以内で魅力的に返答してください。"
            payload = json.dumps({"contents": [{"parts": [{"text": prompt}]}]}).encode('utf-8')
            req = urllib.request.Request(url, data=payload, headers={'Content-Type': 'application/json'})
            with urllib.request.urlopen(req, timeout=5) as res:
                res_data = json.loads(res.read().decode('utf-8'))
                ai_text = res_data['candidates'][0]['content']['parts'][0]['text']
                return jsonify({"reply": ai_text})
        except Exception:
            pass

    reply = f"「{msg}」ですね！\\nご希望の条件に合うおすすめの店舗をピックアップしました。ご予算や終電時間に合わせて調整できますのでお気軽にどうぞ！"
    return jsonify({"reply": reply})

@app.route('/manifest.json')
def manifest():
    return jsonify({
        "name": "EAT MAP - 全国の美味しいお店探し", "short_name": "EAT MAP", "start_url": "/", "display": "standalone",
        "background_color": "#121214", "theme_color": "#c2785c",
        "icons": [{"src": "https://placehold.co/192x192/c2785c/ffffff?text=%F0%9F%8D%BD%EF%B8%8F", "sizes": "192x192", "type": "image/png"}]
    })

# PWA Service Worker
@app.route('/sw.js')
def sw():
    sw_code = """
    const CACHE_NAME = 'eatmap-cache-v7';

    self.addEventListener('install', (e) => {
      self.skipWaiting();
    });

    self.addEventListener('activate', (e) => {
      e.waitUntil(
        caches.keys().then(keys => Promise.all(
          keys.map(k => k !== CACHE_NAME && caches.delete(k))
        )).then(() => self.clients.claim())
      );
    });

    self.addEventListener('fetch', (e) => {
      if (e.request.method !== 'GET') return;
      if (e.request.headers.get('accept') && e.request.headers.get('accept').includes('text/html')) {
        e.respondWith(
          fetch(e.request).then(res => {
            const clone = res.clone();
            caches.open(CACHE_NAME).then(c => c.put(e.request, clone));
            return res;
          }).catch(() => caches.match(e.request).then(c => c || caches.match('/')))
        );
        return;
      }
      e.respondWith(
        caches.match(e.request).then(cached => cached || fetch(e.request))
      );
    });
    """
    return Response(sw_code, mimetype="application/javascript")

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
