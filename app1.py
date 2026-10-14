from flask import Flask, request, render_template_string, jsonify, Response
import urllib.request
import urllib.parse
import json
import random
import re

app = Flask(__name__)

HOTPEPPER_API_KEY = "16ba3d78b920bcc"

# 独自のおすすめ店舗データ
MY_SECRET_SHOPS = [
    {
        "name": "俺の秘密基地カフェ (殿堂入り)",
        "genre": "カフェ・隠れ家",
        "catch": "オーナーこだわりの自家焙煎コーヒー。誰にも教えたくない秘密の場所。",
        "address": "兵庫県姫路市本町000",
        "access": "姫路駅から徒歩15分、路地裏",
        "budget": "1,000円〜2,000円",
        "min_budget": 1000,
        "lat": 34.835, "lng": 134.692,
        "photo": "https://images.unsplash.com/photo-1497935586351-b67a49e012bf?w=500",
        "url": "#",
        "is_special": True
    }
]

COMMON_HEAD = """
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <link rel="icon" href="data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 100 100%22><text y=%22.9em%22 font-size=%2290%22>🍽️</text></svg>">
    <link rel="manifest" href="/manifest.json">
    <meta name="theme-color" content="#d48a6e">
    <meta name="apple-mobile-web-app-capable" content="yes">
    <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
    <link rel="apple-touch-icon" href="https://placehold.co/192x192/d48a6e/ffffff?text=%F0%9F%8D%BD%EF%B8%8F">
    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
    <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
"""

COMMON_CSS = """
    body { background-color: #fdfaf6; color: #5a4a42; font-family: 'Helvetica Neue', Arial, sans-serif; margin: 0; padding: 15px; -webkit-tap-highlight-color: transparent; }
    .header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; }
    .nav-btn { text-decoration: none; color: #d48a6e; font-size: 14px; font-weight: bold; background-color: #f2e9e1; padding: 8px 15px; border-radius: 20px; box-shadow: 0 2px 5px rgba(0,0,0,0.05); border: none; cursor: pointer; }

    @keyframes fadeInUp { from { opacity: 0; transform: translateY(20px); } to { opacity: 1; transform: translateY(0); } }
    .shop-card { background-color: #ffffff; border-radius: 15px; padding: 15px; margin-bottom: 15px; box-shadow: 0 3px 10px rgba(0,0,0,0.04); position: relative; border: 1px solid #f0e6dd; display: flex; flex-direction: column; animation: fadeInUp 0.5s ease-out forwards; opacity: 0; }
    .shop-card.special { border: 2px solid #ffd166; background-color: #fffbf0; }
    .special-badge { position: absolute; top: -10px; left: 15px; background: #ffd166; color: #b87c00; font-size: 11px; font-weight: bold; padding: 4px 10px; border-radius: 10px; box-shadow: 0 2px 5px rgba(0,0,0,0.1); z-index: 10; }

    .shop-img { width: 100%; height: 160px; object-fit: cover; border-radius: 10px; margin-bottom: 10px; background-color: #eee; }
    .shop-name { font-size: 17px; font-weight: bold; color: #d48a6e; margin: 0 0 5px 0; padding-right: 35px; }
    .shop-genre { font-size: 12px; color: #8c7a6b; margin-bottom: 8px; }
    .shop-desc { font-size: 13px; line-height: 1.5; margin-bottom: 10px; color: #444; }
    .shop-info { font-size: 12px; color: #777; margin-bottom: 12px; line-height: 1.4; background-color:#faf7f2; padding:10px; border-radius:8px;}

    .btn-group { display: flex; gap: 8px; margin-top: auto; }
    .link-btn { flex: 1; background-color: #d48a6e; color: white; text-decoration: none; font-size: 13px; padding: 10px; border-radius: 25px; font-weight: bold; text-align: center; }
    .navi-btn { flex: 1; background-color: #4CAF50; color: white; text-decoration: none; font-size: 13px; padding: 10px; border-radius: 25px; font-weight: bold; text-align: center; }

    .fav-btn { position: absolute; top: 15px; right: 15px; font-size: 24px; cursor: pointer; color: #ccc; background: white; border: none; border-radius: 50%; width: 40px; height: 40px; box-shadow: 0 2px 6px rgba(0,0,0,0.1); display: flex; align-items: center; justify-content: center; outline: none; transition: transform 0.2s; }
    .fav-btn:active { transform: scale(1.2); }
    .fav-btn.active { color: #ff6b6b; }

    #loading-overlay { position: fixed; top: 0; left: 0; width: 100vw; height: 100vh; background-color: rgba(253, 250, 246, 0.95); display: none; justify-content: center; align-items: center; flex-direction: column; z-index: 9999; }
    .loader { border: 5px solid #f2e9e1; border-top: 5px solid #d48a6e; border-radius: 50%; width: 50px; height: 50px; animation: spin 1s linear infinite; margin-bottom: 20px; }
    @keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }
    .loading-text { color: #d48a6e; font-weight: bold; font-size: 16px; letter-spacing: 1px; }
    #dice-animation { font-size: 60px; display: none; margin-bottom: 10px; animation: bounce 0.5s infinite alternate; }
    @keyframes bounce { from { transform: translateY(0); } to { transform: translateY(-20px) rotate(20deg); } }

    .history-section { margin-top: 30px; padding-top: 20px; border-top: 2px dashed #e8e0d9; }
    .history-title { font-size: 14px; font-weight: bold; color: #8c7a6b; margin-bottom: 10px; }
    .history-scroll { display: flex; overflow-x: auto; gap: 10px; padding-bottom: 10px; -webkit-overflow-scrolling: touch; }
    .history-card { min-width: 140px; background: white; border-radius: 10px; padding: 10px; box-shadow: 0 2px 5px rgba(0,0,0,0.05); font-size: 12px; }
    .history-img { width: 100%; height: 80px; object-fit: cover; border-radius: 6px; margin-bottom: 5px; }

    /* バックアップ・引き継ぎ用デザイン */
    .backup-panel { background: #ffffff; border: 1px dashed #d48a6e; border-radius: 15px; padding: 15px; margin-bottom: 20px; font-size: 13px; }
    .backup-btn-row { display: flex; gap: 8px; margin-top: 10px; }
    .action-btn { flex: 1; border: none; padding: 10px; border-radius: 10px; font-weight: bold; font-size: 12px; cursor: pointer; transition: 0.2s; }
    .btn-export { background-color: #d48a6e; color: white; }
    .btn-import { background-color: #f2e9e1; color: #5a4a42; border: 1px solid #d48a6e; }
    .backup-textarea { width: 100%; height: 60px; border: 1px solid #e8e0d9; border-radius: 8px; padding: 8px; font-size: 11px; box-sizing: border-box; margin-top: 8px; font-family: monospace; resize: none; }
"""

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

        .quick-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 10px; margin-bottom: 20px; }
        .quick-btn {
            background-color: #faf7f2; border: 1px solid #e8e0d9; border-radius: 12px;
            padding: 12px 5px; text-align: center; font-size: 13px; font-weight: bold;
            color: #5a4a42; text-decoration: none; display: flex; align-items: center;
            justify-content: center; gap: 6px; box-sizing: border-box; transition: background 0.2s;
        }
        .quick-btn:active { background-color: #f2e9e1; transform: scale(0.98); }
        .gacha-btn { background-color: #f2e9e1; color: #d48a6e; border: 2px solid #d48a6e; padding: 12px; width: 100%; border-radius: 25px; font-size: 14px; font-weight: bold; cursor: pointer; margin-top: 15px; }
    </style>
</head>
<body>
    <div id="loading-overlay"><div id="loader-spinner" class="loader"></div><div id="dice-animation">🎲</div><div id="loading-message" class="loading-text">お店を探しています...</div></div>

    <div class="container">
        <div class="header">
            <button class="nav-btn" onclick="shareApp()">📤 友達にシェア</button>
            <a href="/favorites" class="nav-btn">💖 保存一覧</a>
        </div>
        <h1>EAT MAP</h1>
        <p class="subtitle">姫路のぴったりなお店を見つけよう</p>

        <label>⚡ ワンタップで探す</label>
        <div class="quick-grid">
            <a href="/search?keyword=%E3%82%AB%E3%83%95%E3%82%A7&area=%E5%A7%AB%E8%B7%AF%E9%A7%85&people=2%E5%90%8D" class="quick-btn" onclick="showLoading('search')"><span>☕</span>カフェ</a>
            <a href="/search?keyword=%E3%81%8A%E3%81%A7%E3%82%93&area=%E5%A7%AB%E8%B7%AF%E9%A7%85&people=2%E5%90%8D" class="quick-btn" onclick="showLoading('search')"><span>🍢</span>姫路おでん</a>
            <a href="/search?keyword=%E5%A4%9C%E3%82%AB%E3%83%95%E3%82%A7&area=%E5%A7%AB%E8%B7%AF%E9%A7%85&people=2%E5%90%8D" class="quick-btn" onclick="showLoading('search')"><span>🌙</span>夜カフェ</a>
            <a href="/search?keyword=Wi-Fi+%E9%9B%BB%E6%BA%90&area=%E5%A7%AB%E8%B7%AF%E5%B8%82&people=1%E5%90%8D" class="quick-btn" onclick="showLoading('search')"><span>💻</span>電源・Wi-Fi</a>
        </div>

        <form action="/search" method="GET" id="main-form" onsubmit="showLoading('search')">
            <div class="form-group"><label>🔍 こだわり検索</label><input type="text" name="keyword" id="keyword-input" placeholder="例：スイーツ、デート、夜景"></div>

            <div class="form-group"><label>📍 エリア</label>
                <select name="area" id="area-select">
                    <option value="姫路駅">姫路駅周辺</option><option value="姫路城">姫路城・本町周辺</option><option value="飾磨">飾磨・広畑エリア</option><option value="姫路市">姫路市全域</option>
                </select>
            </div>

            <div class="form-group">
                <label>👥 人数</label>
                <select name="people" id="people-select">
                    <option value="1名">1名（ひとりカフェ・ソロ活）</option>
                    <option value="2名" selected>2名（デート・友人）</option>
                    <option value="3〜4名">3〜4名（女子会・グループ）</option>
                    <option value="5名以上">5名以上（宴会・打ち上げ）</option>
                </select>
            </div>

            <button type="submit" class="submit-btn">お店を検索する</button>
        </form>

        <form action="/gacha" method="GET" onsubmit="return showLoading('gacha')">
            <button type="submit" class="gacha-btn">🎲 迷ったらこれ！お店ガチャ</button>
        </form>
    </div>

    <script>
        if ('serviceWorker' in navigator) navigator.serviceWorker.register('/sw.js');

        function showLoading(type) {
            const overlay = document.getElementById('loading-overlay');
            if (overlay) overlay.style.display = 'flex';
            if (type === 'gacha') {
                document.getElementById('loader-spinner').style.display = 'none';
                document.getElementById('dice-animation').style.display = 'block';
                document.getElementById('loading-message').innerText = "運命のお店を抽選中...";
                setTimeout(() => document.forms[1].submit(), 2000);
                return false;
            } else {
                document.getElementById('loader-spinner').style.display = 'block';
                document.getElementById('dice-animation').style.display = 'none';
                document.getElementById('loading-message').innerText = "🔎 お店を探しています...";
                return true;
            }
        }

        async function shareApp() {
            if (navigator.share) {
                try {
                    await navigator.share({
                        title: 'EAT MAP - 姫路のお店探し',
                        text: '姫路のおすすめカフェや隠れ家店が見つかるアプリ！',
                        url: window.location.origin
                    });
                } catch (err) {}
            } else {
                alert("URLをコピーして友達に送ってください！\\n" + window.location.origin);
            }
        }
    </script>
</body>
</html>
"""

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
        .condition-box { background-color: #f2e9e1; padding: 12px; border-radius: 10px; margin-bottom: 20px; font-size: 13px; line-height: 1.6; }
        .gacha-result-title { color: #d48a6e; text-align:center; animation: popIn 0.5s cubic-bezier(0.175, 0.885, 0.32, 1.275); }
        @keyframes popIn { 0% { transform: scale(0.5); opacity: 0; } 100% { transform: scale(1); opacity: 1; } }
    </style>
</head>
<body>
    <div class="max-w">
        <div class="header">
            <a href="/" class="nav-btn">← 戻る</a>
            <button class="nav-btn" onclick="shareApp()">📤 シェア</button>
            <a href="/favorites" class="nav-btn">💖 保存一覧</a>
        </div>

        {% if is_gacha %}
            <h2 class="gacha-result-title">🎉 ジャーン！<br>運命のお店はこちら！</h2>
        {% else %}
            <div class="condition-box">
                探した条件：<br>
                キーワード「<span style="color:#d48a6e;font-weight:bold;">{{ keyword if keyword else '指定なし' }}</span>」<br>
                エリア: <span style="color:#d48a6e;font-weight:bold;">{{ area }}</span> / 利用人数: <span style="color:#d48a6e;font-weight:bold;">{{ people }}</span>
            </div>
            <div style="font-weight:bold; color:#d48a6e; margin-bottom:10px;">📍 見つかったお店マップ</div>
            <div id="map" class="map-container"></div>
        {% endif %}

        <div id="shop-list">
            {% for shop in shops %}
            <div class="shop-card {% if shop.is_special %}special{% endif %}" style="animation-delay: {{ loop.index0 * 0.1 }}s">
                {% if shop.is_special %}<div class="special-badge">✨ 殿堂入りおすすめ</div>{% endif %}
                <button class="fav-btn" onclick='toggleFavorite(this, {{ shop | tojson }})'>♡</button>

                {% if shop.photo %}<img src="{{ shop.photo }}" class="shop-img">{% endif %}
                <h4 class="shop-name">{{ shop.name }}</h4>
                <div class="shop-genre">🏷️ {{ shop.genre }}</div>
                <div class="shop-desc">{{ shop.catch }}</div>
                <div class="shop-info">📍 {{ shop.address }}<br>🚶 {{ shop.access }}<br>💰 予算：{{ shop.budget }}</div>

                <div class="btn-group">
                    <a href="{{ shop.url }}" target="_blank" class="link-btn">詳細・予約 ↗</a>
                    <a href="https://www.google.com/maps/dir/?api=1&destination={{ shop.address | urlencode }}" target="_blank" class="navi-btn">📍 ルート案内</a>
                </div>
            </div>
            {% endfor %}
        </div>

        <div class="history-section" id="history-section" style="display:none;">
            <div class="history-title">🕒 最近見たお店</div>
            <div class="history-scroll" id="history-scroll"></div>
        </div>
    </div>

    <script>
        const shops = {{ shops | tojson | safe }};
        const isGacha = {{ is_gacha | tojson }};

        if (!isGacha && shops.length > 0) {
            const map = L.map('map').setView([shops[0].lat, shops[0].lng], 15);
            L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', { attribution: '&copy; OpenStreetMap' }).addTo(map);
            shops.forEach(shop => { if(shop.lat && shop.lng) L.marker([shop.lat, shop.lng]).addTo(map).bindPopup(`<b>${shop.name}</b><br>${shop.genre}`); });
        }

        function toggleFavorite(btn, shop) {
            let favs = JSON.parse(localStorage.getItem('eatmap_favs') || '[]');
            const index = favs.findIndex(item => item.name === shop.name);
            if (index > -1) { favs.splice(index, 1); btn.innerHTML = '♡'; btn.classList.remove('active'); }
            else { shop.memo = ""; favs.push(shop); btn.innerHTML = '♥'; btn.classList.add('active'); }
            localStorage.setItem('eatmap_favs', JSON.stringify(favs));
        }

        function saveHistory(newShops) {
            let history = JSON.parse(localStorage.getItem('eatmap_history') || '[]');
            newShops.forEach(s => { history = history.filter(h => h.name !== s.name); history.unshift(s); });
            history = history.slice(0, 5); localStorage.setItem('eatmap_history', JSON.stringify(history));
        }

        function renderHistory() {
            const history = JSON.parse(localStorage.getItem('eatmap_history') || '[]');
            if (history.length > 0) {
                document.getElementById('history-section').style.display = 'block';
                document.getElementById('history-scroll').innerHTML = history.map(h => `
                    <div class="history-card">
                        ${h.photo ? `<img src="${h.photo}" class="history-img">` : ''}
                        <div style="font-weight:bold; color:#d48a6e; margin-bottom:3px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;">${h.name}</div>
                        <div style="color:#777;">${h.genre}</div>
                    </div>
                `).join('');
            }
        }

        async function shareApp() {
            if (navigator.share) {
                try {
                    await navigator.share({
                        title: 'EAT MAP - 姫路のお店探し',
                        text: '姫路のおすすめカフェや隠れ家店が見つかるアプリ！',
                        url: window.location.origin
                    });
                } catch (err) {}
            } else { alert("URLをコピーして友達に送ってください！\\n" + window.location.origin); }
        }

        window.addEventListener('DOMContentLoaded', () => {
            const favs = JSON.parse(localStorage.getItem('eatmap_favs') || '[]');
            document.querySelectorAll('.shop-card').forEach(card => {
                if (favs.some(item => item.name === card.querySelector('.shop-name').innerText)) {
                    const btn = card.querySelector('.fav-btn'); btn.innerHTML = '♥'; btn.classList.add('active');
                }
            });
            saveHistory(shops);
            renderHistory();
        });
    </script>
</body>
</html>
"""

FAVORITES_HTML = """
<!DOCTYPE html>
<html lang="ja">
<head>
    """ + COMMON_HEAD + """
    <title>保存一覧 - EAT MAP</title>
    <style>""" + COMMON_CSS + """.max-w { max-width: 450px; margin: 0 auto; }</style>
    <style>
        .memo-area { margin-top: 10px; background-color: #fff9e6; border-left: 4px solid #ffd166; padding: 10px; border-radius: 4px; font-size: 13px; color: #666; display: none; }
        .memo-btn { background: none; border: 1px solid #d48a6e; color: #d48a6e; font-size: 11px; padding: 4px 10px; border-radius: 10px; cursor: pointer; margin-top: 5px; float: right; }
    </style>
</head>
<body>
    <div class="max-w">
        <div class="header">
            <a href="/" class="nav-btn">← ホームへ戻る</a>
            <h2 style="font-size: 18px; margin: 0; color: #d48a6e;">💖 保存一覧</h2>
        </div>

        <!-- バックアップ・引き継ぎパネル -->
        <div class="backup-panel">
            <div style="font-weight: bold; color: #d48a6e; margin-bottom: 5px;">📦 データのバックアップ・引き継ぎ</div>
            <div style="color: #777; font-size: 11px; line-height: 1.4;">
                アプリを削除したりスマホを替えても、引き継ぎコードがあれば保存したお店とメモを元通り復元できます。
            </div>

            <div class="backup-btn-row">
                <button class="action-btn btn-export" onclick="exportBackup()">📋 コードを発行・コピー</button>
                <button class="action-btn btn-import" onclick="toggleImportArea()">📥 コードから復元</button>
            </div>

            <!-- 復元用テキストエリア（初期状態は非表示） -->
            <div id="import-area" style="display: none; margin-top: 10px;">
                <textarea id="import-code-input" class="backup-textarea" placeholder="控えておいた引き継ぎコードをここに貼り付けてください"></textarea>
                <button class="action-btn btn-export" style="width: 100%; margin-top: 5px;" onclick="importBackup()">データを復元する</button>
            </div>
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
                <div class="shop-card" style="animation-delay: ${index * 0.1}s">
                    <button class="fav-btn active" onclick="removeFavorite(${index})">♥</button>
                    ${shop.photo ? `<img src="${shop.photo}" class="shop-img">` : ''}
                    <h4 class="shop-name">${shop.name}</h4>
                    <div class="shop-info">📍 ${shop.address}<br>🚶 ${shop.access}</div>

                    <button class="memo-btn" onclick="editMemo(${index})">✏️ メモを書く</button>
                    <div class="memo-area" id="memo-${index}" style="display: ${shop.memo ? 'block' : 'none'}">${shop.memo || ''}</div>

                    <div class="btn-group" style="margin-top:15px;">
                        <a href="${shop.url}" target="_blank" class="link-btn">詳細・予約 ↗</a>
                        <a href="https://www.google.com/maps/dir/?api=1&destination=${encodeURIComponent(shop.address)}" target="_blank" class="navi-btn">📍 ルート案内</a>
                    </div>
                </div>
            `).join('');
        }

        function removeFavorite(index) {
            let favs = JSON.parse(localStorage.getItem('eatmap_favs') || '[]');
            favs.splice(index, 1);
            localStorage.setItem('eatmap_favs', JSON.stringify(favs));
            renderFavorites();
        }

        function editMemo(index) {
            let favs = JSON.parse(localStorage.getItem('eatmap_favs') || '[]');
            let currentMemo = favs[index].memo || "";
            let newMemo = prompt("このお店のメモを入力してください（例: 窓際の席がいい、オムライスを頼む）", currentMemo);
            if (newMemo !== null) { favs[index].memo = newMemo; localStorage.setItem('eatmap_favs', JSON.stringify(favs)); renderFavorites(); }
        }

        // --- バックアップ（コード発行）処理 ---
        function exportBackup() {
            const favs = localStorage.getItem('eatmap_favs');
            if (!favs || JSON.parse(favs).length === 0) {
                alert("保存されているお店がありません。まずはお店をお気に入りに追加してください！");
                return;
            }
            // データを安全なBase64文字列に変換
            const code = btoa(unescape(encodeURIComponent(favs)));

            if (navigator.clipboard) {
                navigator.clipboard.writeText(code).then(() => {
                    alert("引き継ぎコードをクリップボードにコピーしました！\\nLINEのKeepやメモ帳などに貼り付けて大切に保管してください。");
                }).catch(() => {
                    prompt("以下のコードをコピーしてメモ帳などに保管してください：", code);
                });
            } else {
                prompt("以下のコードをコピーしてメモ帳などに保管してください：", code);
            }
        }

        // --- 復元入力エリアの開閉 ---
        function toggleImportArea() {
            const area = document.getElementById('import-area');
            area.style.display = area.style.display === 'none' ? 'block' : 'none';
        }

        // --- 復元処理 ---
        function importBackup() {
            const input = document.getElementById('import-code-input').value.trim();
            if (!input) {
                alert("引き継ぎコードを入力してください。");
                return;
            }
            try {
                // Base64を元のJSONデータに戻す
                const jsonStr = decodeURIComponent(escape(atob(input)));
                const restoredData = JSON.parse(jsonStr);

                if (!Array.isArray(restoredData)) {
                    throw new Error("無効なフォーマットです");
                }

                if (confirm(`${restoredData.length} 件のお気に入りデータを復元しますか？\\n（現在の保存データは上書きされます）`)) {
                    localStorage.setItem('eatmap_favs', JSON.stringify(restoredData));
                    alert("復元が完了しました！");
                    document.getElementById('import-code-input').value = "";
                    document.getElementById('import-area').style.display = "none";
                    renderFavorites();
                }
            } catch (e) {
                alert("コードが正しくないか破損しています。正しくコピーされているかご確認ください。");
            }
        }

        window.addEventListener('DOMContentLoaded', renderFavorites);
    </script>
</body>
</html>
"""

def extract_min_budget(budget_str):
    numbers = re.findall(r'\d+', budget_str.replace(',', ''))
    return int(numbers[0]) if numbers else 99999

def fetch_hotpepper_shops(keyword, area):
    shops = []
    if "隠れ家" in keyword or "カフェ" in keyword or keyword == "":
        shops.extend(MY_SECRET_SHOPS)

    if not HOTPEPPER_API_KEY or HOTPEPPER_API_KEY == "ここにAPIキーを入力":
        shops.append({ "name": "姫路 カフェ・ド・シラサギ (仮)", "genre": "カフェ", "catch": "姫路城を望む落ち着いた空間。", "address": "兵庫県姫路市本町68", "access": "JR姫路駅徒歩10分", "budget": "1000円〜2000円", "min_budget": 1000, "lat": 34.836, "lng": 134.693, "photo": "https://images.unsplash.com/photo-1554118811-1e0d58224f24?w=500", "url": "https://www.hotpepper.jp/" })
        shops.append({ "name": "播州 個室居酒屋 姫路丸 (仮)", "genre": "居酒屋", "catch": "新鮮な瀬戸内鮮魚！", "address": "兵庫県姫路市駅前町222", "access": "姫路駅徒歩2分", "budget": "3000円〜4000円", "min_budget": 3000, "lat": 34.827, "lng": 134.690, "photo": "https://images.unsplash.com/photo-1517248135467-4c7edcad34c4?w=500", "url": "https://www.hotpepper.jp/" })
        return shops

    query = f"姫路 {area} {keyword}"
    url = f"https://webservice.recruit.co.jp/hotpepper/gourmet/v1/?key={HOTPEPPER_API_KEY}&keyword={urllib.parse.quote(query)}&count=10&format=json"

    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req) as res:
            data = json.loads(res.read().decode('utf-8'))
            for s in data.get("results", {}).get("shop", []):
                budget_str = s.get("budget", {}).get("name", "")
                shops.append({
                    "name": s.get("name"), "genre": s.get("genre", {}).get("name", ""), "catch": s.get("catch", ""),
                    "address": s.get("address", ""), "access": s.get("mobile_access", s.get("access", "")), "budget": budget_str,
                    "min_budget": extract_min_budget(budget_str), "lat": s.get("lat"), "lng": s.get("lng"),
                    "photo": s.get("photo", {}).get("pc", {}).get("l", ""), "url": s.get("urls", {}).get("pc", "https://www.hotpepper.jp/")
                })
            return shops
    except Exception as e:
        print("API Error:", e)
        return shops

@app.route('/')
def home(): return render_template_string(HOME_HTML)

@app.route('/search', methods=['GET'])
def search():
    keyword = request.args.get('keyword', '')
    area = request.args.get('area', '姫路駅')
    people = request.args.get('people', '2名')
    shops = fetch_hotpepper_shops(keyword, area)
    return render_template_string(RESULT_HTML, is_gacha=False, keyword=keyword, area=area, people=people, shops=shops)

@app.route('/gacha', methods=['GET'])
def gacha():
    genres = ["カフェ", "居酒屋", "焼肉", "ラーメン", "洋食"]
    shops = fetch_hotpepper_shops(random.choice(genres), "姫路駅")
    picked_shop = [random.choice(shops)] if shops else []
    return render_template_string(RESULT_HTML, is_gacha=True, shops=picked_shop, keyword="ガチャ", area="姫路駅", people="2名")

@app.route('/favorites')
def favorites(): return render_template_string(FAVORITES_HTML)

@app.route('/manifest.json')
def manifest():
    return jsonify({
        "name": "EAT MAP 姫路", "short_name": "EAT MAP", "start_url": "/",
        "display": "standalone", "background_color": "#fdfaf6", "theme_color": "#d48a6e",
        "icons": [{"src": "https://placehold.co/192x192/d48a6e/ffffff?text=%F0%9F%8D%BD%EF%B8%8F", "sizes": "192x192", "type": "image/png"}]
    })

@app.route('/sw.js')
def sw(): return Response("self.addEventListener('fetch', function(event) {});", mimetype="application/javascript")

if __name__ == '__main__': app.run(host='0.0.0.0', port=5000)
