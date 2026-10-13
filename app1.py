from flask import Flask, request, render_template_string, jsonify, Response
import urllib.request
import urllib.parse
import json
import random
import re

app = Flask(__name__)

# ホットペッパーAPIキー
HOTPEPPER_API_KEY = "16ba3d78b920bcc"

# ----------------- 共通要素（PWAメタタグ・CSS） -----------------
COMMON_HEAD = """
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <!-- PWA用設定 -->
    <link rel="manifest" href="/manifest.json">
    <meta name="theme-color" content="#d48a6e">
    <meta name="apple-mobile-web-app-capable" content="yes">
    <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
    <link rel="apple-touch-icon" href="https://placehold.co/192x192/d48a6e/ffffff?text=EAT">
    <!-- 地図用（Leaflet） -->
    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
    <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
"""

COMMON_CSS = """
    body { background-color: #fdfaf6; color: #5a4a42; font-family: 'Helvetica Neue', Arial, sans-serif; margin: 0; padding: 15px; -webkit-tap-highlight-color: transparent; }
    .header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; }
    .nav-btn { text-decoration: none; color: #d48a6e; font-size: 14px; font-weight: bold; background-color: #f2e9e1; padding: 8px 15px; border-radius: 20px; box-shadow: 0 2px 5px rgba(0,0,0,0.05); }
    .shop-card { background-color: #ffffff; border-radius: 15px; padding: 15px; margin-bottom: 15px; box-shadow: 0 3px 10px rgba(0,0,0,0.04); position: relative; border: 1px solid #f0e6dd; display: flex; flex-direction: column; }
    .shop-img { width: 100%; height: 160px; object-fit: cover; border-radius: 10px; margin-bottom: 10px; background-color: #eee; }
    .shop-name { font-size: 17px; font-weight: bold; color: #d48a6e; margin: 0 0 5px 0; padding-right: 35px; }
    .shop-genre { font-size: 12px; color: #8c7a6b; margin-bottom: 8px; }
    .shop-desc { font-size: 13px; line-height: 1.5; margin-bottom: 10px; color: #444; }
    .shop-info { font-size: 12px; color: #777; margin-bottom: 12px; line-height: 1.4; background-color:#faf7f2; padding:10px; border-radius:8px;}
    .link-btn { display: inline-block; background-color: #d48a6e; color: white; text-decoration: none; font-size: 13px; padding: 10px; border-radius: 25px; font-weight: bold; text-align: center; margin-top: auto; }
    .fav-btn { position: absolute; top: 15px; right: 15px; font-size: 24px; cursor: pointer; color: #ccc; background: white; border: none; border-radius: 50%; width: 40px; height: 40px; box-shadow: 0 2px 6px rgba(0,0,0,0.1); display: flex; align-items: center; justify-content: center; outline: none; }
    .fav-btn.active { color: #ff6b6b; }
"""

# ----------------- トップ画面 -----------------
HOME_HTML = """
<!DOCTYPE html>
<html lang="ja">
<head>
    """ + COMMON_HEAD + """
    <title>EAT MAP - 姫路のお店探し</title>
    <style>
        """ + COMMON_CSS + """
        .container { background-color: #ffffff; max-width: 450px; margin: 0 auto; padding: 25px 20px; border-radius: 20px; box-shadow: 0 4px 15px rgba(0,0,0,0.05); }
        h1 { font-size: 28px; font-weight: 800; color: #d48a6e; text-align: center; margin-bottom: 5px; }
        p.subtitle { font-size: 13px; color: #8c7a6b; text-align: center; margin-bottom: 25px; }
        .form-group { margin-bottom: 15px; }
        label { font-weight: bold; font-size: 13px; display: block; margin-bottom: 5px; }
        input[type="text"], select { width: 100%; padding: 12px; border: 2px solid #e8e0d9; border-radius: 8px; font-size: 14px; background-color: #faf7f2; box-sizing: border-box; outline: none; }
        .submit-btn { background-color: #d48a6e; color: white; border: none; padding: 14px; width: 100%; border-radius: 25px; font-size: 16px; font-weight: bold; cursor: pointer; margin-top: 10px; }

        /* クイック検索ボタン */
        .quick-grid { display: flex; justify-content: space-between; margin-bottom: 20px; gap: 8px; }
        .quick-btn { flex: 1; background-color: #faf7f2; border: 1px solid #e8e0d9; border-radius: 12px; padding: 10px 5px; text-align: center; font-size: 11px; font-weight: bold; color: #5a4a42; cursor: pointer; transition: 0.2s; }
        .quick-btn:active { background-color: #f2e9e1; }
        .quick-icon { font-size: 20px; margin-bottom: 3px; display: block; }
    </style>
</head>
<body>
    <div class="container">
        <div style="text-align: right; margin-bottom: 15px;">
            <a href="/favorites" class="nav-btn">💖 保存一覧</a>
        </div>
        <h1>EAT MAP</h1>
        <p class="subtitle">姫路のぴったりなお店を見つけよう</p>

        <!-- クイック検索エリア -->
        <label>⚡ ワンタップで探す</label>
        <div class="quick-grid">
            <div class="quick-btn" onclick="quickSearch('カフェ', '姫路駅')"><span class="quick-icon">☕</span>カフェ</div>
            <div class="quick-btn" onclick="quickSearch('ランチ', '姫路駅')"><span class="quick-icon">☀️</span>ランチ</div>
            <div class="quick-btn" onclick="quickSearch('居酒屋 個室', '姫路駅')"><span class="quick-icon">🍻</span>個室飲み</div>
            <div class="quick-btn" onclick="quickSearch('焼肉', '姫路市')"><span class="quick-icon">🍖</span>焼肉</div>
        </div>

        <form action="/search" method="post" id="main-form">
            <div class="form-group">
                <label>🔍 こだわり検索</label>
                <input type="text" name="keyword" id="keyword-input" placeholder="例：スイーツ、デート、夜景">
            </div>
            <div class="form-group">
                <label>📍 エリア</label>
                <select name="area" id="area-select">
                    <option value="姫路駅">姫路駅周辺</option>
                    <option value="姫路城">姫路城・本町周辺</option>
                    <option value="飾磨">飾磨・広畑エリア</option>
                    <option value="姫路市">姫路市全域</option>
                </select>
            </div>
            <button type="submit" class="submit-btn">お店を検索する</button>
        </form>
    </div>

    <!-- PWA用 Service Worker登録 -->
    <script>
        if ('serviceWorker' in navigator) {
            navigator.serviceWorker.register('/sw.js');
        }
        function quickSearch(keyword, area) {
            document.getElementById('keyword-input').value = keyword;
            document.getElementById('area-select').value = area;
            document.getElementById('main-form').submit();
        }
    </script>
</body>
</html>
"""

# ----------------- 検索結果画面 -----------------
RESULT_HTML = """
<!DOCTYPE html>
<html lang="ja">
<head>
    """ + COMMON_HEAD + """
    <title>検索結果 - EAT MAP</title>
    <style>
        """ + COMMON_CSS + """
        .max-w { max-width: 450px; margin: 0 auto; }
        .map-container { height: 220px; width: 100%; border-radius: 12px; margin-bottom: 20px; z-index: 1; border: 2px solid #e8e0d9;}
        .sort-box { text-align: right; margin-bottom: 15px; }
        .sort-select { padding: 6px 10px; border-radius: 8px; border: 1px solid #d48a6e; color: #d48a6e; background: white; outline: none; font-size: 12px; font-weight:bold;}
    </style>
</head>
<body>
    <div class="max-w">
        <div class="header">
            <a href="/" class="nav-btn">← 戻る</a>
            <a href="/favorites" class="nav-btn">💖 保存一覧</a>
        </div>

        <div style="font-weight:bold; color:#d48a6e; margin-bottom:10px;">📍 見つかったお店マップ</div>
        <div id="map" class="map-container"></div>

        <div class="sort-box">
            <select class="sort-select" id="sort-select" onchange="sortCards()">
                <option value="default">⭐ おすすめ順</option>
                <option value="cheap">💰 予算が安い順</option>
            </select>
        </div>

        <div id="shop-list">
            {% for shop in shops %}
            <div class="shop-card" data-budget="{{ shop.min_budget }}">
                <button class="fav-btn" onclick='toggleFavorite(this, {{ shop | tojson }})'>♡</button>
                {% if shop.photo %}<img src="{{ shop.photo }}" class="shop-img">{% endif %}
                <h4 class="shop-name">{{ shop.name }}</h4>
                <div class="shop-genre">🏷️ {{ shop.genre }}</div>
                <div class="shop-desc">{{ shop.catch }}</div>
                <div class="shop-info">
                    📍 {{ shop.address }}<br>
                    🚶 {{ shop.access }}<br>
                    💰 予算：{{ shop.budget }}
                </div>
                <a href="{{ shop.url }}" target="_blank" class="link-btn">詳細・予約 ↗</a>
            </div>
            {% endfor %}
        </div>
    </div>

    <script>
        const shops = {{ shops | tojson | safe }};

        // --- Leaflet地図の設定 ---
        if (shops.length > 0) {
            // 中心点を最初のお店に設定
            const map = L.map('map').setView([shops[0].lat, shops[0].lng], 15);
            L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
                attribution: '&copy; OpenStreetMap'
            }).addTo(map);

            // お店ごとにピンを立てる
            shops.forEach(shop => {
                if(shop.lat && shop.lng) {
                    L.marker([shop.lat, shop.lng]).addTo(map)
                        .bindPopup(`<b>${shop.name}</b><br>${shop.genre}`);
                }
            });
        } else {
            document.getElementById('map').innerHTML = "<div style='text-align:center; padding-top:100px;'>お店が見つかりませんでした</div>";
        }

        // --- 並び替え機能（フロントエンド） ---
        function sortCards() {
            const list = document.getElementById('shop-list');
            const cards = Array.from(list.getElementsByClassName('shop-card'));
            const sortType = document.getElementById('sort-select').value;

            if (sortType === 'cheap') {
                cards.sort((a, b) => parseInt(a.dataset.budget) - parseInt(b.dataset.budget));
            } else {
                // デフォルトは元の順序に戻すための簡単なリロード
                location.reload();
            }
            cards.forEach(card => list.appendChild(card));
        }

        // --- 保存機能 ---
        function toggleFavorite(btn, shop) {
            let favs = JSON.parse(localStorage.getItem('eatmap_favs') || '[]');
            const index = favs.findIndex(item => item.name === shop.name);
            if (index > -1) {
                favs.splice(index, 1);
                btn.innerHTML = '♡'; btn.classList.remove('active');
            } else {
                favs.push(shop);
                btn.innerHTML = '♥'; btn.classList.add('active');
            }
            localStorage.setItem('eatmap_favs', JSON.stringify(favs));
        }

        window.addEventListener('DOMContentLoaded', () => {
            const favs = JSON.parse(localStorage.getItem('eatmap_favs') || '[]');
            document.querySelectorAll('.shop-card').forEach(card => {
                const name = card.querySelector('.shop-name').innerText;
                if (favs.some(item => item.name === name)) {
                    card.querySelector('.fav-btn').innerHTML = '♥';
                    card.querySelector('.fav-btn').classList.add('active');
                }
            });
        });
    </script>
</body>
</html>
"""

# ----------------- お気に入り画面 -----------------
# （コード量削減のため、FAVORITES_HTMLはRESULT_HTMLと同じデザイン体系で動的に構築します）
FAVORITES_HTML = """
<!DOCTYPE html>
<html lang="ja">
<head>
    """ + COMMON_HEAD + """
    <title>保存一覧 - EAT MAP</title>
    <style>
        """ + COMMON_CSS + """
        .max-w { max-width: 450px; margin: 0 auto; }
    </style>
</head>
<body>
    <div class="max-w">
        <div class="header">
            <a href="/" class="nav-btn">← ホームへ</a>
            <h2 style="font-size: 18px; margin: 0; color: #d48a6e;">💖 保存一覧</h2>
        </div>
        <div id="favorites-container"></div>
    </div>
    <script>
        function renderFavorites() {
            const container = document.getElementById('favorites-container');
            const favs = JSON.parse(localStorage.getItem('eatmap_favs') || '[]');
            if (favs.length === 0) {
                container.innerHTML = `<div style="text-align:center; padding:50px 0; color:#8c7a6b;">保存したお店はありません</div>`;
                return;
            }
            container.innerHTML = favs.map((shop, index) => `
                <div class="shop-card">
                    <button class="fav-btn active" onclick="removeFavorite(${index})">♥</button>
                    ${shop.photo ? `<img src="${shop.photo}" class="shop-img">` : ''}
                    <h4 class="shop-name">${shop.name}</h4>
                    <div class="shop-info">📍 ${shop.address}<br>🚶 ${shop.access}</div>
                    <a href="${shop.url}" target="_blank" class="link-btn">詳細・予約 ↗</a>
                </div>
            `).join('');
        }
        function removeFavorite(index) {
            let favs = JSON.parse(localStorage.getItem('eatmap_favs') || '[]');
            favs.splice(index, 1);
            localStorage.setItem('eatmap_favs', JSON.stringify(favs));
            renderFavorites();
        }
        window.addEventListener('DOMContentLoaded', renderFavorites);
    </script>
</body>
</html>
"""

# ----------------- データ取得ロジック -----------------
def extract_min_budget(budget_str):
    # 予算文字列から最低金額の数字だけを抽出（ソート用）
    numbers = re.findall(r'\d+', budget_str.replace(',', ''))
    return int(numbers[0]) if numbers else 99999

def fetch_hotpepper_shops(keyword, area):
    # API未設定時のモックデータ（地図用の緯度経度付き）
    if not HOTPEPPER_API_KEY or HOTPEPPER_API_KEY == "16ba3d78b920bcc":
        return [
            {
                "name": "姫路 カフェ・ド・シラサギ (仮)", "genre": "カフェ", "catch": "姫路城を望む落ち着いた空間。",
                "address": "兵庫県姫路市本町68", "access": "JR姫路駅徒歩10分", "budget": "1000円〜2000円", "min_budget": 1000,
                "lat": 34.836, "lng": 134.693, # 姫路城付近の緯度経度
                "photo": "https://images.unsplash.com/photo-1554118811-1e0d58224f24?w=500", "url": "#"
            },
            {
                "name": "播州 個室居酒屋 姫路丸 (仮)", "genre": "居酒屋", "catch": "新鮮な瀬戸内鮮魚！",
                "address": "兵庫県姫路市駅前町222", "access": "姫路駅徒歩2分", "budget": "3000円〜4000円", "min_budget": 3000,
                "lat": 34.827, "lng": 134.690, # 姫路駅付近の緯度経度
                "photo": "https://images.unsplash.com/photo-1517248135467-4c7edcad34c4?w=500", "url": "#"
            }
        ]

    query = f"姫路 {area} {keyword}"
    url = f"https://webservice.recruit.co.jp/hotpepper/gourmet/v1/?key={HOTPEPPER_API_KEY}&keyword={urllib.parse.quote(query)}&count=10&format=json"

    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req) as res:
            data = json.loads(res.read().decode('utf-8'))
            shops = []
            for s in data.get("results", {}).get("shop", []):
                budget_str = s.get("budget", {}).get("name", "")
                shops.append({
                    "name": s.get("name"),
                    "genre": s.get("genre", {}).get("name", ""),
                    "catch": s.get("catch", ""),
                    "address": s.get("address", ""),
                    "access": s.get("mobile_access", s.get("access", "")),
                    "budget": budget_str,
                    "min_budget": extract_min_budget(budget_str),
                    "lat": s.get("lat"), # 緯度取得（地図用）
                    "lng": s.get("lng"), # 経度取得（地図用）
                    "photo": s.get("photo", {}).get("pc", {}).get("l", ""),
                    "url": s.get("urls", {}).get("pc", "#")
                })
            return shops
    except Exception as e:
        print("API Error:", e)
        return []

# ----------------- ルーティング -----------------
@app.route('/')
def home():
    return render_template_string(HOME_HTML)

@app.route('/search', methods=['POST'])
def search():
    keyword = request.form.get('keyword', '')
    area = request.form.get('area', '姫路駅')
    shops = fetch_hotpepper_shops(keyword, area)
    return render_template_string(RESULT_HTML, is_gacha=False, keyword=keyword, area=area, shops=shops)

@app.route('/favorites')
def favorites():
    return render_template_string(FAVORITES_HTML)

# --- PWA用ファイル生成 ---
@app.route('/manifest.json')
def manifest():
    return jsonify({
        "name": "EAT MAP 姫路",
        "short_name": "EAT MAP",
        "start_url": "/",
        "display": "standalone",
        "background_color": "#fdfaf6",
        "theme_color": "#d48a6e",
        "icons": [{
            "src": "https://placehold.co/192x192/d48a6e/ffffff?text=EAT",
            "sizes": "192x192",
            "type": "image/png"
        }]
    })

@app.route('/sw.js')
def sw():
    # 空のService Worker（PWAインストールの必須条件を満たすため）
    js_code = "self.addEventListener('fetch', function(event) {});"
    return Response(js_code, mimetype="application/javascript")

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
