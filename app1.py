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

# APIキー設定（未入力時は安全なサンプルデータでフル動作します）
GEMINI_API_KEY = "ここにGeminiAPIキーを入力"
HOTPEPPER_API_KEY = "ここにAPIキーを入力"

# --- サーバー内インメモリキャッシュ設定（軽量・高速化） ---
SEARCH_CACHE = {}
CACHE_TTL = 600  # キャッシュ有効時間: 10分（秒）
MAX_CACHE_SIZE = 100  # キャッシュ最大保持数（メモリ節約）

# --- 全国のサンプル店舗マスターデータ ---
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
        "name": "純喫茶 播州アーモンドトースト (仮)", "genre": "カフェ・喫茶", "catch": "名物自家製アーモンドバターたっぷり。",
        "address": "兵庫県姫路市本町12", "access": "姫路駅徒歩5分", "budget": "600円〜1,200円", "min_budget": 600,
        "lat": 34.832, "lng": 134.692, "tel": "079-000-0003", "is_indoor": True,
        "photo": "https://images.unsplash.com/photo-1554118811-1e0d58224f24?w=600", "url": "https://www.hotpepper.jp/", "is_special": True
    },
    {
        "name": "博多炉端・水炊き 華", "genre": "居酒屋・鍋", "catch": "じっくり煮込んだ秘伝白濁スープの本格水炊き。",
        "address": "福岡県福岡市博多区博多駅前2-3-4", "access": "博多駅博多口徒歩4分", "budget": "3,000円〜4,500円", "min_budget": 3000,
        "lat": 33.5902, "lng": 130.4207, "tel": "092-0000-0004", "is_indoor": True,
        "photo": "https://images.unsplash.com/photo-1541544741938-0af808871cc0?w=600", "url": "https://www.hotpepper.jp/", "is_special": False
    }
]

# ================= Gzip自動通信圧縮ミドルウェア =================
@app.after_request
def compress_response(response):
    accept_encoding = request.headers.get('Accept-Encoding', '')
    if 'gzip' not in accept_encoding.lower() or response.status_code < 200 or response.status_code >= 300:
        return response
    if response.headers.get('Content-Encoding'):
        return response
    
    # 500バイト未満の極小レスポンスはそのまま返す
    data = response.get_data()
    if len(data) < 500:
        return response
    
    compressed_data = gzip.compress(data)
    response.set_data(compressed_data)
    response.headers['Content-Encoding'] = 'gzip'
    response.headers['Content-Length'] = len(compressed_data)
    return response

# ================= 共通ヘッダー・CSS =================
COMMON_HEAD = """
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <link rel="icon" href="data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 100 100%22><text y=%22.9em%22 font-size=%2290%22>🍽️</text></svg>">
    <link rel="manifest" href="/manifest.json">
    <meta name="theme-color" content="#c2785c">
    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
    <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
    <style>
        :root {
            --primary: #c2785c;
            --primary-light: #fbeee8;
            --primary-dark: #8c4c32;
            --accent: #f59e0b;
            --bg: #faf6f0;
            --card-bg: rgba(255, 255, 255, 0.95);
            --text-main: #4a382e;
            --text-sub: #8c766b;
            --glass-border: rgba(230, 215, 205, 0.85);
        }
        body { 
            background: linear-gradient(180deg, #f7efe6 0%, var(--bg) 100%); 
            color: var(--text-main); 
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Hiragino Sans", "Hiragino Kaku Gothic ProN", Meiryo, sans-serif;
            margin: 0; padding: 16px; padding-bottom: 95px; 
            -webkit-tap-highlight-color: transparent; min-height: 100vh; box-sizing: border-box;
        }
        .max-w { max-width: 460px; margin: 0 auto; }
        
        .glass-card {
            background: var(--card-bg); backdrop-filter: blur(12px); -webkit-backdrop-filter: blur(12px);
            border: 1px solid var(--glass-border); border-radius: 20px;
            box-shadow: 0 10px 25px rgba(140, 76, 50, 0.06); padding: 18px; margin-bottom: 16px; position: relative;
        }
        .top-bar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 15px; }
        .app-brand { font-size: 24px; font-weight: 900; letter-spacing: 1.5px; color: var(--primary); }
        .pill-btn {
            background: var(--primary-light); color: var(--primary); border: 1px solid rgba(194, 120, 92, 0.25);
            padding: 8px 14px; border-radius: 25px; font-size: 12px; font-weight: 700; cursor: pointer; text-decoration: none;
            display: inline-flex; align-items: center; gap: 4px;
        }
        .pill-btn:active { transform: scale(0.96); background: var(--primary); color: white; }

        .bottom-nav { 
            position: fixed; bottom: 0; left: 0; width: 100%; 
            background: rgba(255, 255, 255, 0.94); backdrop-filter: blur(16px); -webkit-backdrop-filter: blur(16px);
            box-shadow: 0 -4px 20px rgba(74, 56, 46, 0.08); display: flex; justify-content: space-around; 
            padding: 8px 0; padding-bottom: calc(8px + env(safe-area-inset-bottom)); z-index: 1000; border-top: 1px solid var(--glass-border); 
        }
        .bottom-nav a { 
            color: var(--text-sub); text-decoration: none; font-size: 10px; display: flex; flex-direction: column; 
            align-items: center; gap: 3px; font-weight: 700; width: 20%; 
        }
        .bottom-nav a.active { color: var(--primary); }
        .bottom-nav span.icon { font-size: 22px; }

        .shop-card {
            background: white; border-radius: 18px; padding: 14px; margin-bottom: 15px;
            box-shadow: 0 4px 15px rgba(0,0,0,0.04); border: 1px solid #f0e6dd; position: relative; display: flex; flex-direction: column;
        }
        .shop-card.special { border: 2px solid var(--accent); background: linear-gradient(180deg, #fffcf5 0%, #ffffff 100%); }
        .special-badge {
            position: absolute; top: -10px; left: 14px; background: linear-gradient(135deg, #f59e0b, #d97706);
            color: white; font-size: 10px; font-weight: 800; padding: 4px 10px; border-radius: 20px;
        }
        .shop-img { width: 100%; height: 160px; object-fit: cover; border-radius: 12px; margin-bottom: 10px; background-color: #eee; }
        .shop-name { font-size: 17px; font-weight: 800; color: var(--primary); margin: 0 0 4px 0; padding-right: 40px; }
        .shop-genre { font-size: 12px; color: var(--text-sub); margin-bottom: 6px; }
        .shop-info { font-size: 12px; color: #666; line-height: 1.5; background: #faf7f2; padding: 8px 12px; border-radius: 10px; margin-bottom: 10px; }
        
        .btn-group { display: flex; gap: 8px; margin-top: auto; }
        .btn-act {
            flex: 1; padding: 10px; border-radius: 20px; font-size: 12px; font-weight: 800; text-align: center;
            text-decoration: none; border: none; cursor: pointer;
        }
        .btn-primary { background: linear-gradient(135deg, #c2785c, #a85d43); color: white; }
        .btn-green { background: linear-gradient(135deg, #10b981, #059669); color: white; }
        .btn-sub { background: #f2e9e1; color: var(--text-main); }
        .fav-btn {
            position: absolute; top: 12px; right: 12px; font-size: 22px; cursor: pointer;
            background: white; border: none; border-radius: 50%; width: 38px; height: 38px;
            box-shadow: 0 3px 8px rgba(0,0,0,0.1); display: flex; align-items: center; justify-content: center; outline: none;
        }
        .fav-btn.active { color: #f43f5e; }

        .modal-overlay {
            position: fixed; top: 0; left: 0; width: 100vw; height: 100vh; background: rgba(0,0,0,0.5);
            backdrop-filter: blur(4px); display: none; align-items: center; justify-content: center; z-index: 2000; padding: 20px; box-sizing: border-box;
        }
        .modal-box { background: white; border-radius: 20px; width: 100%; max-width: 400px; padding: 20px; }

        #loading-overlay { 
            position: fixed; top: 0; left: 0; width: 100vw; height: 100vh; background: rgba(250, 246, 240, 0.95);
            display: none; justify-content: center; align-items: center; flex-direction: column; z-index: 9999;
        }
        .loader-ring { 
            width: 50px; height: 50px; border: 4px solid var(--primary-light); border-top: 4px solid var(--primary);
            border-radius: 50%; animation: spin 0.9s linear infinite; margin-bottom: 15px; 
        }
        @keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }
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
    </script>
"""

# ================= 画面1: ホーム =================
HOME_HTML = """
<!DOCTYPE html>
<html lang="ja">
<head>
    """ + COMMON_HEAD + """
    <title>EAT MAP - 全国の美味しいお店探し</title>
    <style>
        .time-banner {
            background: linear-gradient(135deg, rgba(194, 120, 92, 0.15), rgba(245, 158, 11, 0.15));
            border-radius: 16px; padding: 14px 18px; margin-bottom: 16px; display: flex; align-items: center; justify-content: space-between;
        }
        .rain-toggle {
            display: flex; align-items: center; justify-content: space-between;
            background: #e8f3fa; border: 1px solid #c8e1f2; border-radius: 12px; padding: 10px 14px; margin-bottom: 14px; font-size: 12px; font-weight: 700; color: #1e5a80;
        }
        .switch { position: relative; display: inline-block; width: 44px; height: 24px; }
        .switch input { opacity: 0; width: 0; height: 0; }
        .slider { position: absolute; cursor: pointer; top: 0; left: 0; right: 0; bottom: 0; background-color: #cbd5e1; transition: .3s; border-radius: 24px; }
        .slider:before { position: absolute; content: ""; height: 18px; width: 18px; left: 3px; bottom: 3px; background-color: white; transition: .3s; border-radius: 50%; }
        input:checked + .slider { background-color: #0284c7; }
        input:checked + .slider:before { transform: translateX(20px); }

        .gps-search-btn {
            background: linear-gradient(135deg, #10b981 0%, #059669 100%); color: white; border: none;
            padding: 12px; width: 100%; border-radius: 14px; font-size: 13px; font-weight: 800; cursor: pointer;
            margin-bottom: 14px; display: flex; align-items: center; justify-content: center; gap: 6px; box-shadow: 0 4px 12px rgba(16, 185, 129, 0.25);
        }

        .quick-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 10px; margin-bottom: 15px; }
        .quick-item { 
            background: white; border: 1px solid var(--glass-border); border-radius: 14px; padding: 14px 10px;
            text-align: center; font-size: 13px; font-weight: 800; color: var(--text-main); text-decoration: none;
            display: flex; align-items: center; justify-content: center; gap: 8px;
        }

        input, select {
            width: 100%; padding: 12px 14px; border: 1.5px solid var(--glass-border); border-radius: 12px;
            font-size: 14px; background-color: white; box-sizing: border-box; margin-bottom: 12px; outline: none;
        }
        .submit-main {
            background: linear-gradient(135deg, #c2785c 0%, #a85d43 100%); color: white; border: none;
            padding: 15px; width: 100%; border-radius: 25px; font-size: 15px; font-weight: 800; cursor: pointer;
            box-shadow: 0 6px 18px rgba(194, 120, 92, 0.35);
        }
    </style>
</head>
<body>
    <div id="loading-overlay"><div class="loader-ring"></div><div id="loading-msg" style="color:var(--primary); font-weight:800;">お店を探しています...</div></div>
    
    <div class="max-w">
        <div class="top-bar">
            <div class="app-brand">🍽️ EAT MAP</div>
            <button class="pill-btn" onclick="shareApp()">📤 シェア</button>
        </div>

        <div class="time-banner">
            <div>
                <div style="font-size: 14px; font-weight: 800; color: var(--primary);" id="time-greeting">日本全国のお店探しへ</div>
                <div style="font-size: 11px; color: var(--text-sub);" id="time-sub">旅先でも、いつもの街でもサクッと検索</div>
            </div>
            <div style="font-size: 28px;" id="time-emoji">✨</div>
        </div>

        <button class="gps-search-btn" onclick="searchCurrentLocation()">
            <span>📍</span> 現在地周辺から一発検索
        </button>

        <div class="rain-toggle">
            <span>☔ 雨の日モード（濡れずに歩ける駅ナカ・地下街優先）</span>
            <label class="switch">
                <input type="checkbox" id="rain-mode" onchange="toggleRainMode(this)">
                <span class="slider"></span>
            </label>
        </div>

        <div class="glass-card">
            <div style="font-size:12px; font-weight:800; margin-bottom:10px; color:var(--text-sub);">⭐ よく使うジャンル</div>
            <div class="quick-grid">
                <a href="javascript:void(0)" onclick="quickCategory('カフェ')" class="quick-item">☕ カフェ</a>
                <a href="javascript:void(0)" onclick="quickCategory('居酒屋 個室')" class="quick-item">🍺 個室居酒屋</a>
                <a href="javascript:void(0)" onclick="quickCategory('焼肉')" class="quick-item">🍖 焼肉</a>
                <a href="javascript:void(0)" onclick="quickCategory('ラーメン')" class="quick-item">🍜 ラーメン</a>
            </div>
            
            <form action="/search" method="GET" id="search-form" onsubmit="showLoading()">
                <input type="hidden" name="rain" id="form-rain" value="0">
                <input type="hidden" name="lat" id="form-lat" value="">
                <input type="hidden" name="lng" id="form-lng" value="">

                <label style="font-size:12px; font-weight:800; display:block; margin-bottom:4px;">📍 エリア・駅名（全国どこでもOK）</label>
                <input type="text" name="area" id="area-input" placeholder="例: 渋谷、梅田、姫路、博多、大通">

                <label style="font-size:12px; font-weight:800; display:block; margin-bottom:4px;">🔍 気分・こだわり</label>
                <input type="text" name="keyword" id="keyword-input" placeholder="例: 静かなテラス、海鮮丼、スイーツ、デート">

                <div style="display: flex; gap: 8px;">
                    <select name="people" style="flex: 1;">
                        <option value="1名">1名（ソロ活）</option>
                        <option value="2名" selected>2名（ペア・デート）</option>
                        <option value="3〜4名">3〜4名（グループ）</option>
                        <option value="5名以上">5名以上（宴会）</option>
                    </select>
                </div>
                <button type="submit" class="submit-main">条件でお店を探す</button>
            </form>

            <form action="/gacha" method="GET" onsubmit="showLoading()" style="margin-top: 10px;">
                <input type="hidden" name="area" id="gacha-area" value="">
                <button type="submit" class="submit-main" style="background: var(--primary-light); color: var(--primary); box-shadow: none; border: 1.5px solid var(--primary);">🎲 迷ったら運命の店ガチャ</button>
            </form>
        </div>
    </div>
    """ + BOTTOM_NAV + """

    <script>
        if ('serviceWorker' in navigator) navigator.serviceWorker.register('/sw.js');
        function showLoading() { document.getElementById('loading-overlay').style.display = 'flex'; }
        function toggleRainMode(cb) { document.getElementById('form-rain').value = cb.checked ? '1' : '0'; }

        function searchCurrentLocation() {
            if (!navigator.geolocation) return alert("お使いの端末はGPS機能に対応していません。");
            showLoading();
            navigator.geolocation.getCurrentPosition(pos => {
                const lat = pos.coords.latitude;
                const lng = pos.coords.longitude;
                window.location.href = `/search?lat=${lat}&lng=${lng}&area=現在地周辺`;
            }, err => {
                document.getElementById('loading-overlay').style.display = 'none';
                alert("位置情報の取得が許可されませんでした。エリア名を入力して検索してください。");
            }, { timeout: 8000 });
        }

        function quickCategory(cat) {
            document.getElementById('keyword-input').value = cat;
            showLoading();
            document.getElementById('search-form').submit();
        }

        window.addEventListener('DOMContentLoaded', () => {
            const h = new Date().getHours();
            const g = document.getElementById('time-greeting');
            const s = document.getElementById('time-sub');
            const e = document.getElementById('time-emoji');
            if (h >= 5 && h < 11) {
                g.innerText = "おはようございます！"; s.innerText = "朝食やモーニングカフェをサクッとチェック"; e.innerText = "☕";
            } else if (h >= 11 && h < 14) {
                g.innerText = "お昼のランチタイム！"; s.innerText = "今日の美味しいランチを見つけよう"; e.innerText = "🍽️";
            } else if (h >= 14 && h < 18) {
                g.innerText = "午後のカフェタイム"; s.innerText = "スイーツや作業用カフェでひと息"; e.innerText = "🧁";
            } else {
                g.innerText = "ディナー＆バータイム"; s.innerText = "乾杯のお店や深夜営業スポットを探そう"; e.innerText = "🍸";
            }
        });

        async function shareApp() {
            if (navigator.share) navigator.share({title: 'EAT MAP - 全国の美味しいお店探し', url: window.location.origin});
            else prompt("このURLをコピーしてシェア:", window.location.origin);
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
        .toggle-view-btn { background: white; border: 1px solid var(--glass-border); border-radius: 10px; padding: 6px 10px; font-size: 11px; font-weight: 700; cursor: pointer; color: var(--text-main); }
        
        .shop-grid-mode { display: grid; grid-template-columns: repeat(2, 1fr); gap: 10px; }
        .shop-grid-mode .shop-card { padding: 8px; margin-bottom: 0; }
        .shop-grid-mode .shop-img { height: 110px; margin-bottom: 6px; }
        .shop-grid-mode .shop-name { font-size: 13px; padding-right: 0; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
        .shop-grid-mode .shop-genre, .shop-grid-mode .shop-info, .shop-grid-mode .btn-group { display: none; }
        .shop-grid-mode .fav-btn { width: 28px; height: 28px; font-size: 16px; top: 6px; right: 6px; }
        
        #vote-float-bar {
            position: fixed; bottom: 80px; left: 50%; transform: translateX(-50%);
            background: linear-gradient(135deg, #f59e0b, #d97706); color: white;
            padding: 10px 22px; border-radius: 30px; font-size: 13px; font-weight: 800;
            box-shadow: 0 4px 15px rgba(217, 119, 6, 0.4); display: none; z-index: 900; cursor: pointer;
        }
    </style>
</head>
<body>
    <div class="modal-overlay" id="tel-modal">
        <div class="modal-box">
            <h3 style="margin-top:0; color:var(--primary); font-size:16px;">📞 お電話でのご予約・空席確認</h3>
            <div style="background:#faf7f2; padding:12px; border-radius:10px; font-size:12px; line-height:1.6; margin-bottom:15px;" id="tel-script">
                「お電話ありがとうございます。EAT MAPを見て電話したのですが、本日のお席は空いていますか？」
            </div>
            <a href="#" id="tel-link" class="btn-act btn-primary" style="display:block; margin-bottom:8px;">そのまま発信する</a>
            <button class="btn-act btn-sub" style="width:100%;" onclick="closeTelModal()">閉じる</button>
        </div>
    </div>

    <div class="max-w">
        <div class="top-bar">
            <a href="/" class="pill-btn">← 条件変更</a>
            <div style="font-size:13px; font-weight:800; color:var(--primary);">{{ search_title }} ({{ shops|length }}件)</div>
            <button class="pill-btn" onclick="shareApp()">📤 シェア</button>
        </div>

        <div id="map" class="map-box"></div>

        <div class="view-controls">
            <div style="display:flex; gap:6px;">
                <button class="toggle-view-btn" onclick="sortByLocation()">📍 近い順</button>
                <button class="toggle-view-btn" onclick="sortByBudget()">💰 予算順</button>
            </div>
            <button class="toggle-view-btn" id="view-mode-btn" onclick="toggleViewMode()">🖼️ 飯テロ写真一覧</button>
        </div>

        <div id="shop-container" class="shop-list-mode">
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
                    <button class="btn-act btn-sub" onclick="openTelModal('{{ shop.name }}', '{{ shop.tel }}')">📞 電話確認</button>
                    <a href="https://www.google.com/maps/dir/?api=1&destination={{ shop.address | urlencode }}" target="_blank" class="btn-act btn-green">📍 道案内</a>
                    <a href="{{ shop.url }}" target="_blank" class="btn-act btn-primary">詳細・予約 ↗</a>
                </div>
                <div style="margin-top:8px; font-size:11px; text-align:center; color:#b45309; cursor:pointer;" onclick="toggleVoteList('{{ shop.name }}', this)">🗳️ 投票候補に追加</div>
            </div>
            {% endfor %}
        </div>
    </div>

    <div id="vote-float-bar" onclick="sendVoteLink()">🗳️ 候補を決めてLINE投票 (<span id="v-count">0</span>件)</div>

    """ + BOTTOM_NAV + """

    <script>
        const shops = {{ shops | tojson | safe }};
        let isGrid = false;
        let selectedVotes = [];

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

        function toggleViewMode() {
            const container = document.getElementById('shop-container');
            const btn = document.getElementById('view-mode-btn');
            isGrid = !isGrid;
            if(isGrid) {
                container.className = 'shop-grid-mode';
                btn.innerText = "📋 詳細リスト表示";
            } else {
                container.className = 'shop-list-mode';
                btn.innerText = "🖼️ 飯テロ写真一覧";
            }
        }

        function openTelModal(name, tel) {
            document.getElementById('tel-link').href = "tel:" + (tel || "0000000000");
            document.getElementById('tel-modal').style.display = 'flex';
        }
        function closeTelModal() { document.getElementById('tel-modal').style.display = 'none'; }

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
            if(navigator.share) navigator.share({title: 'どのお店にする？投票しよう！', url: u});
            else prompt("このURLをLINEで送って投票してもらおう:", u);
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

# ================= 画面3: マイデータ（★画像自動リサイズ圧縮対応★） =================
FAVORITES_HTML = """
<!DOCTYPE html>
<html lang="ja">
<head>
    """ + COMMON_HEAD + """
    <title>マイデータ - EAT MAP</title>
    <style>
        .stamp-card {
            background: linear-gradient(135deg, #10b981 0%, #059669 100%); color: white;
            border-radius: 18px; padding: 18px; margin-bottom: 16px; box-shadow: 0 6px 18px rgba(16, 185, 129, 0.25);
        }
        .progress-bar { background: rgba(255,255,255,0.3); border-radius: 10px; height: 10px; overflow: hidden; margin: 8px 0; }
        .progress-fill { background: #fde047; height: 100%; width: 0%; transition: width 0.4s; }
        
        .pref-filter-bar {
            display: flex; gap: 6px; overflow-x: auto; padding-bottom: 8px; margin-bottom: 14px;
        }
        .pref-btn {
            background: white; border: 1px solid var(--glass-border); border-radius: 16px;
            padding: 6px 12px; font-size: 11px; font-weight: 700; white-space: nowrap; cursor: pointer; color: var(--text-main);
        }
        .pref-btn.active { background: var(--primary); color: white; border-color: var(--primary); }

        .tag-pill { display: inline-block; background: #faf7f2; border: 1px solid #e8e0d9; border-radius: 12px; padding: 2px 8px; font-size: 11px; color: var(--text-sub); margin-right: 4px; margin-top: 4px; }
        .upload-btn { background: #faf7f2; border: 1px dashed var(--primary); padding: 6px; border-radius: 8px; font-size: 11px; cursor: pointer; text-align: center; color: var(--primary); font-weight: 700; margin-top: 6px; display: block; }
        .pref-badge { font-size: 10px; background: #f2e9e1; color: var(--primary-dark); padding: 2px 8px; border-radius: 6px; font-weight: 800; display: inline-block; margin-bottom: 4px; }
    </style>
</head>
<body>
    <div class="max-w">
        <div class="top-bar">
            <h2 style="font-size: 18px; margin: 0; color: var(--primary);">👑 グルメマイデータ</h2>
            <button class="pill-btn" onclick="exportBackup()">📋 引き継ぎ</button>
        </div>

        <div class="stamp-card">
            <div style="font-size:12px; font-weight:700;">🗾 47都道府県 グルメ全国制覇度</div>
            <div style="font-size:24px; font-weight:900; margin:4px 0;" id="conquer-title">0 / 47 都道府県 (0%)</div>
            <div class="progress-bar"><div class="progress-fill" id="progress-fill"></div></div>
            <div style="font-size:11px; opacity:0.95;" id="conquer-desc">訪れたお店を「制覇済み」にして全国を塗りつぶそう！</div>
        </div>

        <div class="pref-filter-bar" id="pref-tabs"></div>

        <div id="favorites-list"></div>
    </div>
    """ + BOTTOM_NAV + """

    <script>
        let currentPref = "すべて";

        function getPrefecture(addr) {
            if(!addr) return "その他";
            const m = addr.match(/(東京都|北海道|(?:京都|大阪)府|.{2,3}県)/);
            return m ? m[1] : "その他";
        }

        function renderFavorites() {
            const list = document.getElementById('favorites-list');
            const tabsContainer = document.getElementById('pref-tabs');
            const favs = JSON.parse(localStorage.getItem('eatmap_favs') || '[]');
            
            favs.forEach(s => { s.pref = getPrefecture(s.address); });

            const visitedPrefs = new Set();
            favs.forEach(s => { if(s.visited && s.pref !== "その他") visitedPrefs.add(s.pref); });
            const prefCount = visitedPrefs.size;
            const rate = ((prefCount / 47) * 100).toFixed(1);

            document.getElementById('conquer-title').innerText = `${prefCount} / 47 都道府県 (${rate}%)`;
            document.getElementById('progress-fill').style.width = Math.min(100, Math.max(3, (prefCount / 47) * 100)) + "%";

            const allPrefs = ["すべて", ...Array.from(new Set(favs.map(s => s.pref)))];
            tabsContainer.innerHTML = allPrefs.map(p => `
                <button class="pref-btn ${currentPref === p ? 'active' : ''}" onclick="selectPref('${p}')">
                    ${p} ${p !== 'すべて' ? '(' + favs.filter(s => s.pref === p).length + ')' : ''}
                </button>
            `).join('');

            const filteredFavs = currentPref === "すべて" ? favs : favs.filter(s => s.pref === currentPref);

            if (filteredFavs.length === 0) {
                list.innerHTML = `<div style="text-align:center; padding:40px 0; color:var(--text-sub);">店舗データがありません</div>`;
                return;
            }

            list.innerHTML = filteredFavs.map((shop, i) => {
                const realIndex = favs.findIndex(item => item.name === shop.name);
                return `
                <div class="shop-card">
                    <button class="fav-btn active" onclick="removeFavorite(${realIndex})">♥</button>
                    <div><span class="pref-badge">📍 ${shop.pref}</span></div>
                    
                    ${shop.my_photo ? `<img src="${shop.my_photo}" class="shop-img" style="border: 2px solid var(--accent);">` : (shop.photo ? `<img src="${shop.photo}" class="shop-img">` : '')}
                    
                    <label class="upload-btn">
                        📸 食べた料理の写真を登録
                        <input type="file" accept="image/*" style="display:none;" onchange="uploadMyPhoto(event, ${realIndex})">
                    </label>

                    <h4 class="shop-name" style="margin-top:6px;">${shop.name}</h4>
                    <div class="shop-info">📍 ${shop.address}</div>

                    <div>
                        ${(shop.tags || []).map(t => `<span class="tag-pill">#${t}</span>`).join('')}
                        <button style="border:none; background:none; font-size:11px; color:var(--primary); font-weight:700; cursor:pointer;" onclick="addTag(${realIndex})">＋ タグ追加</button>
                    </div>

                    <div style="display:flex; gap:8px; margin-top:10px;">
                        <button class="btn-act ${shop.visited ? 'btn-green' : 'btn-sub'}" onclick="toggleVisited(${realIndex})">
                            ${shop.visited ? '🏁 制覇済み！' : '🚩 行ってみたい'}
                        </button>
                        <button class="btn-act btn-sub" onclick="editMemo(${realIndex})">✏️ メモ</button>
                    </div>
                    ${shop.memo ? `<div style="background:#fff9e6; border-left:3px solid #f59e0b; padding:8px; font-size:12px; margin-top:8px;">${shop.memo}</div>` : ''}
                </div>
                `;
            }).join('');
        }

        function selectPref(pref) {
            currentPref = pref;
            renderFavorites();
        }

        // ★軽量化処理：Canvasで長辺500pxのJPEG(0.7)に圧縮して容量を98%削減★
        function uploadMyPhoto(e, idx) {
            const file = e.target.files[0];
            if (!file) return;
            const reader = new FileReader();
            reader.onload = function(evt) {
                const img = new Image();
                img.onload = function() {
                    const canvas = document.createElement('canvas');
                    const maxDim = 500;
                    let width = img.width;
                    let height = img.height;
                    if (width > height) {
                        if (width > maxDim) {
                            height = Math.round((height * maxDim) / width);
                            width = maxDim;
                        }
                    } else {
                        if (height > maxDim) {
                            width = Math.round((width * maxDim) / height);
                            height = maxDim;
                        }
                    }
                    canvas.width = width;
                    canvas.height = height;
                    const ctx = canvas.getContext('2d');
                    ctx.drawImage(img, 0, 0, width, height);
                    const resizedDataUrl = canvas.toDataURL('image/jpeg', 0.7);

                    let favs = JSON.parse(localStorage.getItem('eatmap_favs') || '[]');
                    favs[idx].my_photo = resizedDataUrl;
                    try {
                        localStorage.setItem('eatmap_favs', JSON.stringify(favs));
                        renderFavorites();
                    } catch(err) {
                        alert("端末の保存容量が一杯です。不要な写真やメモを整理してください。");
                    }
                };
                img.src = evt.target.result;
            };
            reader.readAsDataURL(file);
        }

        function addTag(idx) {
            let favs = JSON.parse(localStorage.getItem('eatmap_favs') || '[]');
            const t = prompt("追加したいタグを入力（例: デート、リピ確定、激ウマ）");
            if (t) {
                if (!favs[idx].tags) favs[idx].tags = [];
                favs[idx].tags.push(t);
                localStorage.setItem('eatmap_favs', JSON.stringify(favs));
                renderFavorites();
            }
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
        .roulette-wrapper {
            position: relative; width: 310px; height: 310px; margin: 15px auto;
            display: flex; align-items: center; justify-content: center;
        }
        .roulette-pointer {
            position: absolute; top: -14px; left: 50%; transform: translateX(-50%);
            width: 0; height: 0;
            border-left: 14px solid transparent; border-right: 14px solid transparent;
            border-top: 24px solid #ef4444; z-index: 20; filter: drop-shadow(0 2px 4px rgba(0,0,0,0.3));
        }
        .roulette-center {
            position: absolute; width: 44px; height: 44px; border-radius: 50%;
            background: white; border: 3px solid var(--primary);
            box-shadow: 0 2px 8px rgba(0,0,0,0.2); z-index: 10;
            display: flex; align-items: center; justify-content: center; font-size: 18px;
        }
        #roulette-canvas {
            border-radius: 50%; box-shadow: 0 8px 24px rgba(140, 76, 50, 0.2);
            transition: transform cubic-bezier(0.15, 0.9, 0.2, 1);
        }
        .spin-btn {
            background: linear-gradient(135deg, #c2785c 0%, #a85d43 100%); color: white; border: none;
            padding: 16px; width: 100%; border-radius: 30px; font-size: 16px; font-weight: 900;
            cursor: pointer; box-shadow: 0 6px 18px rgba(194, 120, 92, 0.4); margin-top: 15px;
            letter-spacing: 1px;
        }
        .spin-btn:disabled { background: #cbd5e1; box-shadow: none; cursor: not-allowed; }
        
        .result-card {
            background: #fffdfa; border: 2px solid var(--accent); border-radius: 16px;
            padding: 16px; text-align: center; margin-top: 15px; display: none;
            box-shadow: 0 6px 20px rgba(245, 158, 11, 0.15); animation: pop 0.3s ease;
        }
        @keyframes pop { 0% { transform: scale(0.9); opacity: 0; } 100% { transform: scale(1); opacity: 1; } }

        .edit-toggle-btn {
            background: white; border: 1.5px solid var(--glass-border); border-radius: 20px;
            padding: 8px 14px; font-size: 12px; font-weight: 800; color: var(--primary);
            cursor: pointer; display: flex; align-items: center; justify-content: center; gap: 6px;
            margin: 0 auto; margin-top: 10px;
        }
        .editor-panel {
            display: none; background: white; border: 1px solid var(--glass-border);
            border-radius: 16px; padding: 14px; margin-top: 12px;
        }
        .item-chip-box {
            display: flex; flex-wrap: wrap; gap: 6px; margin: 10px 0; max-height: 140px; overflow-y: auto;
        }
        .item-chip {
            background: #faf7f2; border: 1px solid #e8e0d9; border-radius: 16px;
            padding: 4px 10px; font-size: 12px; font-weight: 700; color: var(--text-main);
            display: flex; align-items: center; gap: 6px;
        }
        .chip-del-btn {
            background: #cbd5e1; color: white; border-radius: 50%; width: 16px; height: 16px;
            display: inline-flex; align-items: center; justify-content: center; font-size: 10px; cursor: pointer;
        }
        .add-row { display: flex; gap: 6px; margin-top: 8px; }
        .add-input {
            flex: 1; border: 1.5px solid var(--glass-border); border-radius: 10px;
            padding: 8px 12px; font-size: 13px; outline: none;
        }
        .add-btn {
            background: var(--primary); color: white; border: none; border-radius: 10px;
            padding: 8px 16px; font-size: 12px; font-weight: 800; cursor: pointer;
        }
    </style>
</head>
<body>
    <div class="max-w">
        <h2 style="font-size: 18px; color: var(--primary); text-align: center; margin-top: 10px; margin-bottom: 4px;">🎰 運命の店決めルーレット</h2>
        <p style="font-size: 12px; text-align: center; color: var(--text-sub); margin-top: 0;">何を食べるか迷ったら回そう！中身は自由に設定OK！</p>

        <div class="roulette-wrapper">
            <div class="roulette-pointer"></div>
            <div class="roulette-center">🍽️</div>
            <canvas id="roulette-canvas" width="300" height="300"></canvas>
        </div>

        <button class="spin-btn" id="spin-btn" onclick="spinRoulette()">🎯 ルーレットを回す！</button>

        <button class="edit-toggle-btn" onclick="toggleEditor()">
            <span>⚙️</span> ルーレットの中身を編集する (<span id="item-count-label">8</span>項目)
        </button>

        <div class="editor-panel" id="editor-panel">
            <div style="font-size: 12px; font-weight: 800; color: var(--text-main);">📝 ルーレットの選択肢（2〜16個）</div>
            <div class="item-chip-box" id="chip-box"></div>
            
            <div class="add-row">
                <input type="text" id="new-item-input" class="add-input" placeholder="新しい項目（例: マクド、うどん、焼肉）" onkeypress="if(event.key==='Enter') addNewItem()">
                <button class="add-btn" onclick="addNewItem()">追加</button>
            </div>

            <div style="display:flex; justify-content:space-between; align-items:center; margin-top:10px;">
                <span style="font-size:11px; color:#94a3b8;">変更は自動保存されます</span>
                <button style="background:none; border:none; font-size:11px; color:var(--primary); font-weight:700; cursor:pointer;" onclick="resetDefaultItems()">標準ジャンルに戻す</button>
            </div>
        </div>

        <div class="result-card" id="result-box">
            <div style="font-size: 12px; color: var(--text-sub);">今日の運命のジャンルは...</div>
            <div style="font-size: 24px; font-weight: 900; color: var(--primary); margin: 6px 0;" id="result-name">--</div>
            <div style="display: flex; gap: 8px; margin-top: 10px;">
                <button class="btn-act btn-primary" id="search-genre-btn" style="width: 100%;">このジャンルでお店を探す ↗</button>
            </div>
        </div>
    </div>
    """ + BOTTOM_NAV + """

    <script>
        const canvas = document.getElementById('roulette-canvas');
        const ctx = canvas.getContext('2d');
        
        const DEFAULT_ITEMS = ["焼肉", "カフェ", "ラーメン", "居酒屋", "海鮮・寿司", "カレー", "イタリアン", "中華"];
        const COLOR_PALETTE = ["#fca5a5", "#fed7aa", "#fef08a", "#bbf7d0", "#a7f3d0", "#bae6fd", "#c7d2fe", "#fbcfe8", "#fde047", "#86efac", "#93c5fd", "#d8b4fe"];
        
        let items = [];
        let currentRotation = 0;
        let isSpinning = false;

        function loadItems() {
            const saved = localStorage.getItem('eatmap_roulette_items');
            if (saved) {
                try {
                    items = JSON.parse(saved);
                    if (!Array.isArray(items) || items.length < 2) items = [...DEFAULT_ITEMS];
                } catch(e) { items = [...DEFAULT_ITEMS]; }
            } else {
                items = [...DEFAULT_ITEMS];
            }
            renderChips();
            drawRoulette();
        }

        function saveItems() {
            localStorage.setItem('eatmap_roulette_items', JSON.stringify(items));
            renderChips();
            drawRoulette();
        }

        function toggleEditor() {
            const panel = document.getElementById('editor-panel');
            panel.style.display = panel.style.display === 'block' ? 'none' : 'block';
        }

        function renderChips() {
            const box = document.getElementById('chip-box');
            document.getElementById('item-count-label').innerText = items.length;
            box.innerHTML = items.map((it, idx) => `
                <div class="item-chip">
                    <span>${it}</span>
                    <span class="chip-del-btn" onclick="removeItem(${idx})">×</span>
                </div>
            `).join('');
        }

        function addNewItem() {
            const input = document.getElementById('new-item-input');
            const val = input.value.trim();
            if (!val) return;
            if (items.length >= 16) return alert("項目は最大16個までです");
            items.push(val);
            input.value = "";
            saveItems();
        }

        function removeItem(idx) {
            if (items.length <= 2) return alert("ルーレットには最低2つの項目が必要です");
            items.splice(idx, 1);
            saveItems();
        }

        function resetDefaultItems() {
            if(confirm("標準の8ジャンルに戻しますか？")) {
                items = [...DEFAULT_ITEMS];
                saveItems();
            }
        }

        function drawRoulette() {
            ctx.clearRect(0, 0, 300, 300);
            const num = items.length;
            const arc = (2 * Math.PI) / num;

            for (let i = 0; i < num; i++) {
                const angle = i * arc;
                ctx.fillStyle = COLOR_PALETTE[i % COLOR_PALETTE.length];
                ctx.beginPath();
                ctx.arc(150, 150, 145, angle, angle + arc, false);
                ctx.arc(150, 150, 0, angle + arc, angle, true);
                ctx.fill();
                ctx.save();
                
                ctx.strokeStyle = "rgba(255,255,255,0.85)";
                ctx.lineWidth = 2;
                ctx.stroke();

                ctx.fillStyle = "#4a382e";
                const fontSize = num > 10 ? 11 : (num > 6 ? 12 : 14);
                ctx.font = `bold ${fontSize}px -apple-system, sans-serif`;
                
                const textDist = num > 8 ? 95 : 90;
                ctx.translate(150 + Math.cos(angle + arc / 2) * textDist, 150 + Math.sin(angle + arc / 2) * textDist);
                ctx.rotate(angle + arc / 2 + Math.PI / 2);
                
                let text = items[i];
                if (text.length > 7) text = text.substring(0, 6) + "…";
                ctx.fillText(text, -ctx.measureText(text).width / 2, 0);
                ctx.restore();
            }
        }

        function spinRoulette() {
            if (isSpinning) return;
            if (items.length < 2) return alert("最低2つの項目が必要です");
            isSpinning = true;
            
            const btn = document.getElementById('spin-btn');
            const resBox = document.getElementById('result-box');
            btn.disabled = true;
            btn.innerText = "抽選中...";
            resBox.style.display = "none";

            const randomExtra = Math.floor(Math.random() * 360);
            const totalDegrees = 360 * 6 + randomExtra;
            currentRotation += totalDegrees;

            const duration = 4.5;
            canvas.style.transition = `transform ${duration}s cubic-bezier(0.15, 0.9, 0.2, 1)`;
            canvas.style.transform = `rotate(${currentRotation}deg)`;

            setTimeout(() => {
                isSpinning = false;
                btn.disabled = false;
                btn.innerText = "🎯 もう一度回す！";

                const actualDeg = (currentRotation % 360);
                const step = 360 / items.length;
                const index = Math.floor((360 - actualDeg + 270) % 360 / step);
                const picked = items[index];
                
                const cleanGenre = picked.split(' ')[0] || picked;

                document.getElementById('result-name').innerText = picked;
                document.getElementById('search-genre-btn').onclick = () => {
                    window.location.href = `/search?keyword=${encodeURIComponent(cleanGenre)}`;
                };
                resBox.style.display = "block";
            }, duration * 1000);
        }

        window.addEventListener('DOMContentLoaded', loadItems);
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
            border-radius: 20px; padding: 18px; margin-bottom: 18px; box-shadow: 0 10px 25px rgba(15, 23, 42, 0.3);
            border: 1px solid rgba(255, 255, 255, 0.1);
        }
        .timer-tabs {
            display: flex; gap: 6px; background: rgba(255, 255, 255, 0.1); padding: 4px; border-radius: 12px; margin-bottom: 14px;
        }
        .timer-tab-btn {
            flex: 1; padding: 8px 0; border: none; background: transparent; color: #94a3b8;
            font-size: 11px; font-weight: 800; border-radius: 8px; cursor: pointer; transition: 0.2s;
        }
        .timer-tab-btn.active { background: #38bdf8; color: #0f172a; }

        .time-picker-row {
            display: flex; align-items: center; justify-content: space-between; gap: 10px; margin-bottom: 12px;
        }
        .time-input {
            background: #334155; border: 1px solid #475569; color: white; padding: 8px 12px;
            border-radius: 10px; font-size: 18px; font-weight: 900; outline: none; text-align: center; flex: 1;
        }
        .preset-chips {
            display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 14px;
        }
        .preset-chip {
            background: rgba(255, 255, 255, 0.12); border: 1px solid rgba(255, 255, 255, 0.2);
            color: #e2e8f0; padding: 5px 10px; border-radius: 14px; font-size: 11px; font-weight: 700; cursor: pointer;
        }
        .preset-chip:active { background: #38bdf8; color: #0f172a; }

        .countdown-display {
            text-align: center; padding: 12px 0 6px 0; border-top: 1px dashed rgba(255, 255, 255, 0.15);
        }
        .countdown-digits {
            font-size: 38px; font-weight: 900; color: #38bdf8; font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
            letter-spacing: 2px; text-shadow: 0 0 15px rgba(56, 189, 248, 0.35);
        }
        .countdown-digits.warning { color: #facc15; text-shadow: 0 0 15px rgba(250, 204, 21, 0.4); }
        .countdown-digits.danger { color: #f87171; text-shadow: 0 0 15px rgba(248, 113, 113, 0.4); animation: blink 1s infinite; }
        @keyframes blink { 50% { opacity: 0.6; } }

        .status-badge {
            display: inline-block; font-size: 11px; padding: 3px 10px; border-radius: 20px;
            background: rgba(56, 189, 248, 0.15); color: #38bdf8; font-weight: 800; margin-bottom: 6px;
        }
        .progress-bar-wrap {
            height: 6px; background: rgba(255, 255, 255, 0.15); border-radius: 10px; overflow: hidden; margin: 10px 0 6px 0;
        }
        .progress-bar-inner {
            height: 100%; width: 100%; background: #38bdf8; transition: width 1s linear;
        }

        .ctrl-btns { display: flex; gap: 8px; margin-top: 10px; }
        .ctrl-btn {
            flex: 1; padding: 10px; border-radius: 12px; font-size: 12px; font-weight: 800; border: none; cursor: pointer;
        }
    </style>
</head>
<body>
    <div class="max-w">
        <h2 style="font-size: 18px; color: var(--primary); margin-bottom: 15px;">🧮 おでかけ・飲み会サポート</h2>

        <div class="timer-panel">
            <div class="timer-tabs">
                <button class="timer-tab-btn active" id="tab-clock-btn" onclick="switchTimerMode('clock')">⏱️ 目標時刻・終電</button>
                <button class="timer-tab-btn" id="tab-duration-btn" onclick="switchTimerMode('duration')">🍻 飲み放題・席時間</button>
            </div>

            <div id="mode-clock">
                <div class="time-picker-row">
                    <span style="font-size: 12px; font-weight: 700; color: #cbd5e1;">目標時刻:</span>
                    <input type="time" id="target-time-input" class="time-input" onchange="setCustomTargetTime()">
                </div>
                <div class="preset-chips">
                    <span class="preset-chip" onclick="quickSetAddMinutes(30)">+30分後</span>
                    <span class="preset-chip" onclick="quickSetAddMinutes(60)">+1時間後</span>
                    <span class="preset-chip" onclick="quickSetAddMinutes(120)">+2時間後</span>
                    <span class="preset-chip" onclick="quickSetExactTime('22:30')">22:30</span>
                    <span class="preset-chip" onclick="quickSetExactTime('23:00')">23:00</span>
                    <span class="preset-chip" onclick="quickSetExactTime('23:30')">終電(23:30)</span>
                    <span class="preset-chip" onclick="quickSetExactTime('00:00')">24:00</span>
                </div>
            </div>

            <div id="mode-duration" style="display: none;">
                <div class="preset-chips" style="margin-bottom: 8px;">
                    <span class="preset-chip" onclick="setDurationTimer(60)">60分コース</span>
                    <span class="preset-chip" onclick="setDurationTimer(90)">90分(ラスト60分)</span>
                    <span class="preset-chip" onclick="setDurationTimer(120)">120分(2時間)</span>
                    <span class="preset-chip" onclick="setDurationTimer(180)">180分(3時間)</span>
                </div>
                <div class="time-picker-row">
                    <span style="font-size: 12px; font-weight: 700; color: #cbd5e1;">分数指定:</span>
                    <input type="number" id="custom-minutes-input" class="time-input" placeholder="例: 90" style="font-size:16px;">
                    <button class="ctrl-btn" style="background:#38bdf8; color:#0f172a; flex:0.6; padding:8px;" onclick="applyCustomDuration()">セット</button>
                </div>
            </div>

            <div class="countdown-display">
                <div class="status-badge" id="timer-status-badge">目標時刻までカウントダウン中</div>
                <div class="countdown-digits" id="countdown-timer">--:--:--</div>
                <div class="progress-bar-wrap"><div class="progress-bar-inner" id="timer-progress"></div></div>
                <div style="font-size: 11px; color: #94a3b8;" id="timer-sub-text">日またぎ・深夜時間にも全自動対応</div>
            </div>

            <div class="ctrl-btns" id="duration-ctrls" style="display: none;">
                <button class="ctrl-btn" style="background:#10b981; color:white;" id="d-start-btn" onclick="toggleDurationTimer()">一時停止 / 再開</button>
                <button class="ctrl-btn" style="background:#475569; color:white;" onclick="resetDurationTimer()">リセット</button>
            </div>
        </div>

        <div class="glass-card">
            <h3 style="font-size: 15px; margin-top:0; color:var(--text-main);">💸 サクッと割り勘計算</h3>
            <input type="number" id="t-amount" placeholder="お会計合計（円）">
            <input type="number" id="t-people" placeholder="人数（人）">
            <select id="t-round">
                <option value="100">100円単位で集金</option>
                <option value="500">500円単位で集金</option>
                <option value="1">1円単位（きっちり）</option>
            </select>
            <button class="submit-main" onclick="calcSplit()">計算する</button>
            
            <div id="split-res" style="display:none; background:#fff9e6; border:1px solid #fde68a; border-radius:12px; padding:12px; text-align:center; margin-top:12px;">
                <div style="font-size:11px; color:var(--text-sub);">1人あたりのお支払い額</div>
                <div style="font-size:24px; font-weight:900; color:#b45309;" id="res-per">0円</div>
                <div style="font-size:11px; color:#999;" id="res-extra"></div>
            </div>
        </div>
    </div>
    """ + BOTTOM_NAV + """

    <script>
        let currentMode = "clock";
        let clockTargetDate = null;
        let durationTotalSecs = 5400;
        let durationRemainingSecs = 5400;
        let durationRunning = false;
        let durationInterval = null;

        function switchTimerMode(mode) {
            currentMode = mode;
            document.querySelectorAll('.timer-tab-btn').forEach(b => b.classList.remove('active'));
            if(mode === 'clock') {
                document.getElementById('tab-clock-btn').classList.add('active');
                document.getElementById('mode-clock').style.display = 'block';
                document.getElementById('mode-duration').style.display = 'none';
                document.getElementById('duration-ctrls').style.display = 'none';
                document.getElementById('timer-status-badge').innerText = "目標時刻までカウントダウン中";
                updateClockDisplay();
            } else {
                document.getElementById('tab-duration-btn').classList.add('active');
                document.getElementById('mode-clock').style.display = 'none';
                document.getElementById('mode-duration').style.display = 'block';
                document.getElementById('duration-ctrls').style.display = 'flex';
                document.getElementById('timer-status-badge').innerText = "コース・滞在時間タイマー";
                updateDurationDisplay();
            }
        }

        function initClockTarget() {
            const now = new Date();
            clockTargetDate = new Date();
            clockTargetDate.setHours(23, 30, 0, 0);
            if (clockTargetDate <= now) {
                clockTargetDate.setDate(clockTargetDate.getDate() + 1);
            }
            syncTimeInput();
        }

        function syncTimeInput() {
            if(!clockTargetDate) return;
            const hh = String(clockTargetDate.getHours()).padStart(2, '0');
            const mm = String(clockTargetDate.getMinutes()).padStart(2, '0');
            document.getElementById('target-time-input').value = `${hh}:${mm}`;
        }

        function setCustomTargetTime() {
            const val = document.getElementById('target-time-input').value;
            if(!val) return;
            const [h, m] = val.split(':').map(Number);
            const now = new Date();
            const target = new Date();
            target.setHours(h, m, 0, 0);
            if (target <= now) {
                target.setDate(target.getDate() + 1);
            }
            clockTargetDate = target;
            updateClockDisplay();
        }

        function quickSetExactTime(timeStr) {
            document.getElementById('target-time-input').value = timeStr;
            setCustomTargetTime();
        }

        function quickSetAddMinutes(mins) {
            const target = new Date(Date.now() + mins * 60 * 1000);
            clockTargetDate = target;
            syncTimeInput();
            updateClockDisplay();
        }

        function updateClockDisplay() {
            if(currentMode !== 'clock' || !clockTargetDate) return;
            const now = new Date();
            const diff = clockTargetDate - now;

            const digitsEl = document.getElementById('countdown-timer');
            const subEl = document.getElementById('timer-sub-text');
            const progEl = document.getElementById('timer-progress');

            if (diff <= 0) {
                digitsEl.innerText = "00:00:00";
                digitsEl.className = "countdown-digits danger";
                subEl.innerText = "⚠️ お時間になりました！スマートに解散しましょう";
                progEl.style.width = "0%";
                if (navigator.vibrate) navigator.vibrate([200, 100, 200]);
                return;
            }

            const hrs = String(Math.floor(diff / 3600000)).padStart(2, '0');
            const mins = String(Math.floor((diff % 3600000) / 60000)).padStart(2, '0');
            const secs = String(Math.floor((diff % 60000) / 1000)).padStart(2, '0');
            digitsEl.innerText = `${hrs}:${mins}:${secs}`;

            const totalMinsLeft = diff / 60000;
            if (totalMinsLeft <= 10) {
                digitsEl.className = "countdown-digits danger";
                subEl.innerText = "🚨 終電・お開き間近です！お会計の確認を";
            } else if (totalMinsLeft <= 30) {
                digitsEl.className = "countdown-digits warning";
                subEl.innerText = "⏳ 残り30分を切りました（そろそろお開きの準備）";
            } else {
                digitsEl.className = "countdown-digits";
                const isTomorrow = clockTargetDate.getDate() !== now.getDate();
                subEl.innerText = `目標時刻: ${isTomorrow ? '明日 ' : ''}${String(clockTargetDate.getHours()).padStart(2,'0')}:${String(clockTargetDate.getMinutes()).padStart(2,'0')}`;
            }

            const maxWindow = 3 * 3600 * 1000;
            const progress = Math.min(100, Math.max(0, (diff / maxWindow) * 100));
            progEl.style.width = progress + "%";
        }

        function setDurationTimer(mins) {
            durationTotalSecs = mins * 60;
            durationRemainingSecs = durationTotalSecs;
            durationRunning = true;
            updateDurationDisplay();
            startDurationInterval();
        }

        function applyCustomDuration() {
            const v = parseInt(document.getElementById('custom-minutes-input').value);
            if(!v || v <= 0) return alert("有効な分数を入力してください");
            setDurationTimer(v);
        }

        function toggleDurationTimer() {
            durationRunning = !durationRunning;
            if(durationRunning) startDurationInterval();
            else clearInterval(durationInterval);
        }

        function resetDurationTimer() {
            durationRunning = false;
            clearInterval(durationInterval);
            durationRemainingSecs = durationTotalSecs;
            updateDurationDisplay();
        }

        function startDurationInterval() {
            clearInterval(durationInterval);
            durationInterval = setInterval(() => {
                if(!durationRunning) return;
                if(durationRemainingSecs > 0) {
                    durationRemainingSecs--;
                    updateDurationDisplay();
                } else {
                    durationRunning = false;
                    clearInterval(durationInterval);
                    updateDurationDisplay();
                    if(navigator.vibrate) navigator.vibrate([400, 200, 400]);
                }
            }, 1000);
        }

        function updateDurationDisplay() {
            if(currentMode !== 'duration') return;
            const digitsEl = document.getElementById('countdown-timer');
            const subEl = document.getElementById('timer-sub-text');
            const progEl = document.getElementById('timer-progress');

            const hrs = String(Math.floor(durationRemainingSecs / 3600)).padStart(2, '0');
            const mins = String(Math.floor((durationRemainingSecs % 3600) / 60)).padStart(2, '0');
            const secs = String(Math.floor(durationRemainingSecs % 60)).padStart(2, '0');
            digitsEl.innerText = `${hrs}:${mins}:${secs}`;

            const percent = durationTotalSecs > 0 ? (durationRemainingSecs / durationTotalSecs) * 100 : 0;
            progEl.style.width = percent + "%";

            if (durationRemainingSecs === 0) {
                digitsEl.className = "countdown-digits danger";
                subEl.innerText = "🛑 コース時間終了です！お疲れ様でした！";
            } else if (durationRemainingSecs <= 1800) {
                digitsEl.className = "countdown-digits warning";
                subEl.innerText = "🍻 残り30分以内（ラストオーダー目安時間）";
            } else {
                digitsEl.className = "countdown-digits";
                subEl.innerText = durationRunning ? "▶ 計測中（ラストオーダー30分前をお知らせ）" : "⏸ 一時停止中";
            }
        }

        setInterval(() => {
            if(currentMode === 'clock') updateClockDisplay();
        }, 1000);

        window.addEventListener('DOMContentLoaded', () => {
            initClockTarget();
            updateClockDisplay();
        });

        function calcSplit() {
            const a = parseInt(document.getElementById('t-amount').value);
            const p = parseInt(document.getElementById('t-people').value);
            const r = parseInt(document.getElementById('t-round').value);
            if(!a || !p) return alert("金額と人数を入力してください");
            const per = Math.ceil((a / p) / r) * r;
            const extra = (per * p) - a;
            document.getElementById('res-per').innerText = per.toLocaleString() + " 円";
            document.getElementById('res-extra').innerText = extra > 0 ? `(お釣り/予備費: +${extra}円)` : "ぴったりです！";
            document.getElementById('split-res').style.display = 'block';
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
    <style>
        body { padding: 0; margin: 0; background: #fdfaf6; height: 100vh; display: flex; flex-direction: column; }
        .chat-header { background: white; border-bottom: 1px solid var(--glass-border); padding: 14px; text-align: center; font-weight: 800; color: var(--primary); }
        .chat-stream { flex: 1; padding: 15px; overflow-y: auto; display: flex; flex-direction: column; gap: 14px; padding-bottom: 85px; }
        .msg { display: flex; gap: 8px; max-width: 85%; }
        .msg-ai { align-self: flex-start; }
        .msg-user { align-self: flex-end; flex-direction: row-reverse; }
        .bubble { padding: 12px 16px; border-radius: 18px; font-size: 13px; line-height: 1.5; }
        .bubble-ai { background: white; border: 1px solid var(--glass-border); color: var(--text-main); border-top-left-radius: 4px; }
        .bubble-user { background: var(--primary); color: white; border-top-right-radius: 4px; }
        .chat-dock { position: fixed; bottom: 65px; left: 0; width: 100%; background: white; border-top: 1px solid var(--glass-border); padding: 8px 12px; display: flex; gap: 8px; box-sizing: border-box; }
        .chat-input { flex: 1; border: 1px solid var(--glass-border); background: #faf7f2; border-radius: 20px; padding: 10px 14px; font-size: 14px; outline: none; }
        .btn-circle { width: 40px; height: 40px; border-radius: 50%; border: none; background: var(--primary); color: white; display: flex; align-items: center; justify-content: center; cursor: pointer; }
    </style>
</head>
<body>
    <div class="chat-header">🤖 EAT MAP 全国コンシェルジュ</div>
    <div class="chat-stream" id="chat-stream">
        <div class="msg msg-ai">
            <div style="font-size:24px;">🤖</div>
            <div class="bubble bubble-ai">全国どこのお店でもご相談ください！「新宿駅近くで静かなカフェ」「大阪駅で美味しい串カツ」「博多の屋台」など、地名と一緒に話しかけてみてくださいね。</div>
        </div>
    </div>
    <div class="chat-dock">
        <button class="btn-circle" style="background:#f2e9e1; color:var(--primary);" onclick="startDictation()" id="mic-btn">🎤</button>
        <input type="text" id="chat-input" class="chat-input" placeholder="メッセージを入力..." onkeypress="if(event.key==='Enter') sendChat()">
        <button class="btn-circle" onclick="sendChat()">➤</button>
    </div>
    """ + BOTTOM_NAV + """

    <script>
        const stream = document.getElementById('chat-stream');
        const input = document.getElementById('chat-input');
        
        const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
        let recog;
        if(SR) {
            recog = new SR(); recog.lang = 'ja-JP';
            recog.onresult = (e) => { input.value = e.results[0][0].transcript; sendChat(); };
            recog.onend = () => { document.getElementById('mic-btn').innerText = '🎤'; };
        }
        function startDictation() {
            if(!recog) return alert("音声入力非対応のブラウザです");
            document.getElementById('mic-btn').innerText = '🔴';
            recog.start();
        }

        async function sendChat() {
            const txt = input.value.trim(); if(!txt) return;
            stream.innerHTML += `<div class="msg msg-user"><div class="bubble bubble-user">${txt}</div></div>`;
            input.value = ''; stream.scrollTop = stream.scrollHeight;
            
            const typing = document.createElement('div');
            typing.className = "msg msg-ai";
            typing.innerHTML = `<div style="font-size:24px;">🤖</div><div class="bubble bubble-ai">全国の店舗データを検索中...</div>`;
            stream.appendChild(typing);
            stream.scrollTop = stream.scrollHeight;

            try {
                const res = await fetch('/api/chat', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({message: txt}) });
                const d = await res.json();
                typing.remove();
                stream.innerHTML += `<div class="msg msg-ai"><div style="font-size:24px;">🤖</div><div class="bubble bubble-ai">${d.reply.replace(/\\n/g, "<br>")}</div></div>`;
                stream.scrollTop = stream.scrollHeight;
            } catch(e) { typing.remove(); }
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
        <p style="font-size:12px; color:var(--text-sub);">友達が選んだ候補リストです！</p>
        {% for name in shop_names %}
            <div style="background:white; border:1.5px solid var(--glass-border); padding:14px; border-radius:14px; margin-bottom:8px; font-weight:800; color:var(--primary);">{{ loop.index }}. {{ name }}</div>
        {% endfor %}
        <a href="/" class="btn-act btn-primary" style="display:inline-block; margin-top:20px; text-decoration:none;">EAT MAPアプリを開く</a>
    </div>
</body>
</html>
"""

# ----------------- キャッシュ対応・高速検索ロジック -----------------
def extract_min_budget(b_str):
    if not b_str: return 99999
    nums = re.findall(r'\d+', str(b_str).replace(',', ''))
    return int(nums[0]) if nums else 99999

def fetch_shops(keyword="", area="", lat=None, lng=None, rain_mode=False):
    # 1. キャッシュチェック（同じ条件ならAPIを叩かず即座に返却）
    cache_key = f"{area}:{keyword}:{lat}:{lng}:{rain_mode}"
    now = time.time()
    if cache_key in SEARCH_CACHE:
        cached_time, cached_data = SEARCH_CACHE[cache_key]
        if now - cached_time < CACHE_TTL:
            return cached_data

    shops = list(DEFAULT_SHOPS)
    if rain_mode:
        shops = [s for s in shops if s.get('is_indoor')] + [s for s in shops if not s.get('is_indoor')]
    
    if not HOTPEPPER_API_KEY or HOTPEPPER_API_KEY == "ここにAPIキーを入力":
        return shops

    params = {
        "key": HOTPEPPER_API_KEY,
        "count": 15,
        "format": "json"
    }

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
                api_shops.append({
                    "name": s.get("name", "店舗名不明"),
                    "genre": genre_str,
                    "address": s.get("address", ""),
                    "budget": b_str,
                    "min_budget": extract_min_budget(b_str),
                    "lat": s.get("lat"),
                    "lng": s.get("lng"),
                    "tel": s.get("tel", "0000000000"),
                    "photo": photo_str,
                    "url": url_str,
                    "is_special": False
                })
            result = api_shops if api_shops else shops

            # キャッシュに保存（メモリ肥大化防止のため最大100件でリフレッシュ）
            if len(SEARCH_CACHE) > MAX_CACHE_SIZE:
                SEARCH_CACHE.clear()
            SEARCH_CACHE[cache_key] = (now, result)
            return result
    except Exception:
        return shops

# エラーハンドラー
@app.errorhandler(500)
def internal_error(error):
    return render_template_string(HOME_HTML), 200

@app.route('/')
def home():
    try:
        return render_template_string(HOME_HTML)
    except Exception:
        return render_template_string(HOME_HTML), 200

@app.route('/search')
def search():
    try:
        k = request.args.get('keyword', '')
        a = request.args.get('area', '')
        lat = request.args.get('lat')
        lng = request.args.get('lng')
        r = request.args.get('rain', '0') == '1'

        search_title = f"{a} {k}".strip() or "おすすめ店舗"
        shops = fetch_shops(keyword=k, area=a, lat=lat, lng=lng, rain_mode=r)
        return render_template_string(RESULT_HTML, shops=shops, search_title=search_title)
    except Exception:
        return render_template_string(HOME_HTML)

@app.route('/gacha')
def gacha():
    try:
        a = request.args.get('area', '')
        genres = ["カフェ", "焼肉", "居酒屋", "ラーメン", "洋食", "寿司", "イタリアン"]
        chosen = random.choice(genres)
        shops = fetch_shops(keyword=chosen, area=a)
        return render_template_string(RESULT_HTML, shops=[random.choice(shops)] if shops else [], search_title=f"🎲 ガチャ: {chosen}")
    except Exception:
        return render_template_string(HOME_HTML)

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
    return render_template_string(VOTE_HTML, shop_names=[n for n in names if n])

@app.route('/api/chat', methods=['POST'])
def api_chat():
    msg = request.json.get('message', '') if request.json else ''
    reply = f"「{msg}」ですね！\n全国の店舗情報からご希望にぴったりなお店をチェックしました。お近くのエリアや気になる条件があればさらに詳しくお答えします！"
    return jsonify({"reply": reply})

@app.route('/manifest.json')
def manifest():
    return jsonify({
        "name": "EAT MAP - 全国の美味しいお店探し", "short_name": "EAT MAP", "start_url": "/", "display": "standalone",
        "background_color": "#faf6f0", "theme_color": "#c2785c",
        "icons": [{"src": "https://placehold.co/192x192/c2785c/ffffff?text=%F0%9F%8D%BD%EF%B8%8F", "sizes": "192x192", "type": "image/png"}]
    })

@app.route('/sw.js')
def sw():
    return Response("self.addEventListener('fetch', function(event) {});", mimetype="application/javascript")

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
