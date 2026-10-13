import json
import random
import urllib.parse
import urllib.request
from flask import Flask, render_template_string, request

app = Flask(__name__)

# ==========================================
# 取得したホットペッパーAPIキーをここに入力
# ==========================================
HOTPEPPER_API_KEY = "16ba3d78b920bccf"

# ----------------- HTMLテンプレート -----------------
HOME_HTML = """
<!DOCTYPE html>
<html lang="ja">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>EAT MAP - 姫路のお店探し</title>
    <style>
        body { background-color: #fdfaf6; color: #5a4a42; font-family: 'Helvetica Neue', Arial, sans-serif; margin: 0; padding: 0; display: flex; justify-content: center; min-height: 100vh; }
        .container { background-color: #ffffff; width: 100%; max-width: 450px; padding: 25px 20px; box-shadow: 0 4px 15px rgba(0,0,0,0.05); }
        h1 { font-size: 26px; font-weight: 800; color: #d48a6e; text-align: center; margin-bottom: 5px; }
        p.subtitle { font-size: 13px; color: #8c7a6b; text-align: center; margin-bottom: 25px; }
        .form-group { margin-bottom: 15px; }
        label { font-weight: bold; font-size: 13px; display: block; margin-bottom: 5px; }
        input[type="text"], select { width: 100%; padding: 12px; border: 2px solid #e8e0d9; border-radius: 8px; font-size: 14px; background-color: #faf7f2; box-sizing: border-box; outline: none; }
        .submit-btn { background-color: #d48a6e; color: white; border: none; padding: 14px; width: 100%; border-radius: 25px; font-size: 16px; font-weight: bold; cursor: pointer; box-shadow: 0 4px 10px rgba(212, 138, 110, 0.3); margin-top: 10px; }
        .gacha-btn { background-color: #f2e9e1; color: #d48a6e; border: 2px solid #d48a6e; padding: 14px; width: 100%; border-radius: 25px; font-size: 15px; font-weight: bold; cursor: pointer; margin-top: 15px; width: 100%; }
        .tag-group { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 5px; }
        .tag-checkbox { display: none; }
        .tag-label { display: inline-block; background-color: #f2e9e1; color: #8c7a6b; padding: 6px 12px; border-radius: 15px; font-size: 12px; cursor: pointer; transition: 0.2s; }
        .tag-checkbox:checked + .tag-label { background-color: #d48a6e; color: white; font-weight: bold; }
    </style>
</head>
<body>
    <div class="container">
        <h1>EAT MAP</h1>
        <p class="subtitle">姫路の実店舗からぴったりなお店を探そう</p>

        <form action="/search" method="post">
            <div class="form-group">
                <label>🔍 探したいジャンル・料理名</label>
                <input type="text" name="keyword" placeholder="例：カフェ、居酒屋、焼肉、スイーツ" required>
            </div>

            <div class="form-group">
                <label>📍 エリア</label>
                <select name="area">
                    <option value="姫路駅">姫路駅周辺</option>
                    <option value="姫路城">姫路城・本町周辺</option>
                    <option value="飾磨">飾磨・広畑エリア</option>
                    <option value="姫路市">姫路市全域</option>
                </select>
            </div>

            <div class="form-group">
                <label>👥 人数</label>
                <select name="people">
                    <option value="1名">1名（ひとりカフェ・ソロ活）</option>
                    <option value="2名" selected>2名（デート・友人）</option>
                    <option value="3〜4名">3〜4名（女子会・グループ）</option>
                    <option value="5名以上">5名以上（宴会・打ち上げ）</option>
                </select>
            </div>

            <div class="form-group">
                <label>💰 予算イメージ</label>
                <select name="budget">
                    <option value="指定なし">こだわらない</option>
                    <option value="〜1500円">ランチ（〜1,500円）</option>
                    <option value="2001〜3000円">ディナー（2,000〜3,000円）</option>
                    <option value="4001〜5000円">ディナー（4,000〜5,000円）</option>
                </select>
            </div>

            <div class="form-group">
                <label>✨ こだわり条件</label>
                <div class="tag-group">
                    <input type="checkbox" id="tag1" name="tags" value="個室あり" class="tag-checkbox"><label for="tag1" class="tag-label">🚪 個室あり</label>
                    <input type="checkbox" id="tag2" name="tags" value="飲み放題" class="tag-checkbox"><label for="tag2" class="tag-label">🍻 飲み放題</label>
                    <input type="checkbox" id="tag3" name="tags" value="駐車場" class="tag-checkbox"><label for="tag3" class="tag-label">🚗 駐車場あり</label>
                </div>
            </div>

            <button type="submit" class="submit-btn">姫路のお店を検索する</button>
        </form>

        <form action="/gacha" method="post">
            <button type="submit" class="gacha-btn">🎲 迷ったらこれ！姫路のお店ガチャ</button>
        </form>
    </div>
</body>
</html>
"""

RESULT_HTML = """
<!DOCTYPE html>
<html lang="ja">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>検索結果 - EAT MAP</title>
    <style>
        body { background-color: #fdfaf6; color: #5a4a42; font-family: 'Helvetica Neue', Arial, sans-serif; margin: 0; padding: 15px; }
        .header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 15px; }
        .back-btn { text-decoration: none; color: #d48a6e; font-size: 18px; font-weight: bold; }
        .line-share { background-color: #06C755; color: white; padding: 6px 12px; border-radius: 5px; text-decoration: none; font-size: 12px; font-weight: bold; }
        .condition-box { background-color: #f2e9e1; padding: 12px; border-radius: 10px; margin-bottom: 20px; font-size: 13px; line-height: 1.5; }
        .condition-box span { font-weight: bold; color: #d48a6e; }

        .shop-card { background-color: #ffffff; border-radius: 12px; padding: 15px; margin-bottom: 15px; box-shadow: 0 2px 8px rgba(0,0,0,0.05); position: relative; border: 1px solid #eee; }
        .shop-img { width: 100%; height: 180px; object-fit: cover; border-radius: 8px; margin-bottom: 10px; background-color: #eee; }
        .shop-name { font-size: 17px; font-weight: bold; color: #d48a6e; margin: 0 0 5px 0; }
        .shop-genre { font-size: 12px; color: #8c7a6b; margin-bottom: 8px; }
        .shop-desc { font-size: 13px; line-height: 1.5; margin-bottom: 8px; color: #444; }
        .shop-info { font-size: 12px; color: #777; margin-bottom: 10px; }
        .link-btn { display: inline-block; background-color: #d48a6e; color: white; text-decoration: none; font-size: 13px; padding: 8px 15px; border-radius: 20px; font-weight: bold; }

        .save-btn { position: absolute; top: 20px; right: 20px; font-size: 22px; cursor: pointer; color: #ff6b6b; background: white; border: none; border-radius: 50%; width: 36px; height: 36px; box-shadow: 0 2px 5px rgba(0,0,0,0.15); display: flex; align-items: center; justify-content: center; }
        .credit { font-size: 11px; text-align: center; color: #aaa; margin-top: 30px; }
    </style>
</head>
<body>
    <div class="header">
        <a href="/" class="back-btn">← 条件を変える</a>
        <a href="https://line.me/R/msg/text/?{{ share_text }}" class="line-share" target="_blank">LINEで送る</a>
    </div>

    {% if is_gacha %}
        <h2 style="color: #d48a6e; text-align:center;">🎲 今日の運勢ガチャ結果！</h2>
    {% else %}
        <div class="condition-box">
            探した条件：<br>
            キーワード「<span>{{ keyword }}</span>」 / <span>{{ area }}</span><br>
            <span>{{ people }}</span> / 予算: <span>{{ budget }}</span>
        </div>
        <h3 style="font-size:16px;">姫路のおすすめ店舗（{{ shops|length }}件）</h3>
    {% endif %}

    {% for shop in shops %}
    <div class="shop-card">
        <button class="save-btn" onclick="toggleSave(this)">♡</button>
        {% if shop.photo %}
            <img src="{{ shop.photo }}" alt="{{ shop.name }}" class="shop-img">
        {% endif %}
        <h4 class="shop-name">{{ shop.name }}</h4>
        <div class="shop-genre">🏷️ {{ shop.genre }}</div>
        <div class="shop-desc">{{ shop.catch }}</div>
        <div class="shop-info">
            📍 {{ shop.address }}<br>
            🚶 {{ shop.access }}<br>
            💰 予算：{{ shop.budget }}
        </div>
        <a href="{{ shop.url }}" target="_blank" class="link-btn">ホットペッパーで詳細・予約 ↗</a>
    </div>
    {% endfor %}

    <div class="credit">
        Powered by <a href="http://webservice.recruit.co.jp/" style="color:#aaa;">ホットペッパー Webサービス</a>
    </div>

    <script>
        function toggleSave(btn) {
            btn.innerHTML = btn.innerHTML === '♡' ? '♥' : '♡';
        }
    </script>
</body>
</html>
"""

# ----------------- ホットペッパーAPI呼び出し関数 -----------------
def fetch_hotpepper_shops(keyword, area):
    # APIキーが未入力の場合はモック（ダミー）データを返す
    if not HOTPEPPER_API_KEY or HOTPEPPER_API_KEY == "ここにAPIキーを入力":
        return [
            {
                "name": "姫路 カフェ・ド・シラサギ (仮)",
                "genre": "カフェ・スイーツ",
                "catch": "姫路城を望む落ち着いた空間でこだわりの自家製スイーツを。",
                "address": "兵庫県姫路市本町68",
                "access": "JR姫路駅より徒歩10分",
                "budget": "1,000円〜2,000円",
                "photo": "https://images.unsplash.com/photo-1554118811-1e0d58224f24?w=500",
                "url": "https://www.hotpepper.jp/"
            }
        ]

    base_url = "https://webservice.recruit.co.jp/hotpepper/gourmet/v1/"
    # 検索キーワード（姫路 + エリア + ユーザー指定語）
    query = f"姫路 {area} {keyword}"
    params = {
        "key": HOTPEPPER_API_KEY,
        "keyword": query,
        "count": 5,
        "format": "json"
    }
    url = f"{base_url}?{urllib.parse.urlencode(params)}"

    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req) as res:
            data = json.loads(res.read().decode('utf-8'))
            raw_shops = data.get("results", {}).get("shop", [])

            shops = []
            for s in raw_shops:
                shops.append({
                    "name": s.get("name"),
                    "genre": s.get("genre", {}).get("name", ""),
                    "catch": s.get("catch", s.get("genre", {}).get("catch", "")),
                    "address": s.get("address", ""),
                    "access": s.get("mobile_access", s.get("access", "")),
                    "budget": s.get("budget", {}).get("name", "店舗にお問い合わせください"),
                    "photo": s.get("photo", {}).get("pc", {}).get("l", ""),
                    "url": s.get("urls", {}).get("pc", "https://www.hotpepper.jp/")
                })
            return shops
    except Exception as e:
        print("APIエラー:", e)
        return []

# ----------------- ルーティング -----------------
@app.route('/')
def home():
    return render_template_string(HOME_HTML)

@app.route('/search', methods=['POST'])
def search():
    keyword = request.form.get('keyword', '')
    area = request.form.get('area', '姫路駅')
    people = request.form.get('people', '2名')
    budget = request.form.get('budget', '指定なし')

    # APIから店舗取得
    shops = fetch_hotpepper_shops(keyword, area)

    share_text = urllib.parse.quote(f"姫路で良さそうなお店を見つけたよ！\n条件: {area} / {keyword}\nhttps://eat-map-YOURAPPNAME.onrender.com")

    return render_template_string(
        RESULT_HTML,
        is_gacha=False,
        keyword=keyword,
        area=area,
        people=people,
        budget=budget,
        shops=shops,
        share_text=share_text
    )

@app.route('/gacha', methods=['POST'])
def gacha():
    # ガチャ用：姫路の人気ジャンルからランダムに1軒抽出
    genres = ["カフェ", "居酒屋", "焼肉", "ラーメン", "洋食"]
    chosen_genre = random.choice(genres)
    shops = fetch_hotpepper_shops(chosen_genre, "姫路駅")

    picked_shop = [random.choice(shops)] if shops else []
    shop_title = picked_shop[0]['name'] if picked_shop else chosen_genre
    share_text = urllib.parse.quote(f"運勢ガチャで「{shop_title}」が出たよ！行ってみない？\nhttps://eat-map-YOURAPPNAME.onrender.com")

    return render_template_string(
        RESULT_HTML,
        is_gacha=True,
        shops=picked_shop,
        share_text=share_text
    )

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
