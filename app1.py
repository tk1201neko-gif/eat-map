from flask import Flask, request, render_template_string
import random
import urllib.parse

app = Flask(__name__)

# トップ画面のHTMLテンプレート
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
        .gacha-btn { background-color: #f2e9e1; color: #d48a6e; border: 2px solid #d48a6e; padding: 14px; width: 100%; border-radius: 25px; font-size: 15px; font-weight: bold; cursor: pointer; margin-top: 15px; text-decoration: none; display: block; text-align: center; box-sizing: border-box; }
        
        /* タグ選択用スタイル */
        .tag-group { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 5px; }
        .tag-checkbox { display: none; }
        .tag-label { display: inline-block; background-color: #f2e9e1; color: #8c7a6b; padding: 6px 12px; border-radius: 15px; font-size: 12px; cursor: pointer; border: 1px solid transparent; transition: 0.2s; }
        .tag-checkbox:checked + .tag-label { background-color: #d48a6e; color: white; font-weight: bold; }
    </style>
</head>
<body>
    <div class="container">
        <h1>EAT MAP</h1>
        <p class="subtitle">姫路のぴったりなお店を見つけよう</p>
        
        <form action="/search" method="post">
            <div class="form-group">
                <label>🔍 どんなお店？ (フリーワード)</label>
                <input type="text" name="keyword" placeholder="例：静かなカフェ、焼肉、夜景" required>
            </div>

            <div class="form-group">
                <label>📍 エリア</label>
                <select name="area">
                    <option value="姫路駅周辺">姫路駅周辺（みゆき通り・お溝筋など）</option>
                    <option value="姫路駅南">姫路駅南エリア</option>
                    <option value="姫路城周辺">姫路城・本町エリア</option>
                    <option value="飾磨・広畑">飾磨・広畑エリア</option>
                    <option value="野里・砥堀">野里・砥堀エリア</option>
                    <option value="その他">その他・郊外</option>
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
                <label>💰 予算</label>
                <select name="budget">
                    <option value="こだわらない">こだわらない</option>
                    <option value="〜1,000円">〜1,000円（サクッと）</option>
                    <option value="1,000円〜2,000円">1,000円〜2,000円（ランチなど）</option>
                    <option value="2,000円〜4,000円">2,000円〜4,000円（飲み会など）</option>
                    <option value="5,000円以上">5,000円以上（贅沢・記念日）</option>
                </select>
            </div>

            <div class="form-group">
                <label>✨ こだわり条件 (複数選択可)</label>
                <div class="tag-group">
                    <input type="checkbox" id="tag1" name="tags" value="子連れOK" class="tag-checkbox"><label for="tag1" class="tag-label">👶 子連れOK</label>
                    <input type="checkbox" id="tag2" name="tags" value="個室あり" class="tag-checkbox"><label for="tag2" class="tag-label">🚪 個室あり</label>
                    <input type="checkbox" id="tag3" name="tags" value="Wi-Fi・電源" class="tag-checkbox"><label for="tag3" class="tag-label">💻 Wi-Fi・電源</label>
                    <input type="checkbox" id="tag4" name="tags" value="深夜営業" class="tag-checkbox"><label for="tag4" class="tag-label">🌙 深夜営業</label>
                    <input type="checkbox" id="tag5" name="tags" value="駐車場あり" class="tag-checkbox"><label for="tag5" class="tag-label">🚗 駐車場あり</label>
                </div>
            </div>

            <button type="submit" class="submit-btn">条件で検索する</button>
        </form>
        
        <form action="/gacha" method="post">
            <button type="submit" class="gacha-btn">🎲 迷ったらこれ！お店ガチャ</button>
        </form>
    </div>
</body>
</html>
"""

# 検索結果・ガチャ画面のHTMLテンプレート
RESULT_HTML = """
<!DOCTYPE html>
<html lang="ja">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>検索結果 - EAT MAP</title>
    <style>
        body { background-color: #fdfaf6; color: #5a4a42; font-family: 'Helvetica Neue', Arial, sans-serif; margin: 0; padding: 20px 15px; }
        .header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; }
        .back-btn { text-decoration: none; color: #d48a6e; font-size: 20px; font-weight:bold; }
        .line-share { background-color: #06C755; color: white; padding: 6px 12px; border-radius: 5px; text-decoration: none; font-size: 12px; font-weight: bold; }
        .condition-box { background-color: #f2e9e1; padding: 12px 15px; border-radius: 12px; margin-bottom: 20px; font-size: 13px; line-height:1.6; }
        .condition-box span { font-weight: bold; color: #d48a6e; }
        
        .shop-card { background-color: #ffffff; border-radius: 15px; padding: 15px; margin-bottom: 15px; box-shadow: 0 4px 10px rgba(0,0,0,0.03); border: 1px solid #f2e9e1; position: relative; }
        .shop-name { font-size: 18px; font-weight: bold; color: #d48a6e; margin: 0 0 5px 0; }
        .shop-category { font-size: 12px; color: #8c7a6b; margin-bottom: 10px; }
        .shop-desc { font-size: 14px; line-height: 1.5; margin-bottom: 15px; }
        .shop-tag { display: inline-block; background-color: #faf7f2; color: #a49182; padding: 4px 8px; border-radius: 10px; font-size: 11px; margin-right: 5px; margin-bottom:5px; }
        
        /* お気に入りボタン */
        .save-btn { position: absolute; top: 15px; right: 15px; font-size: 20px; cursor: pointer; color: #e8e0d9; transition: color 0.3s; background: none; border: none; outline: none; }
        .save-btn.active { color: #ff6b6b; }
    </style>
</head>
<body>
    <div class="header">
        <a href="/" class="back-btn">← 戻る</a>
        <!-- LINEで送るリンク（実際のURLを含める） -->
        <a href="https://line.me/R/msg/text/?{{ share_text }}" class="line-share" target="_blank">LINEで共有</a>
    </div>

    {% if is_gacha %}
        <h2 style="color: #d48a6e; text-align:center;">🎲 今日の運勢ガチャ結果！</h2>
    {% else %}
        <div class="condition-box">
            探した条件：<br>
            キーワード「<span>{{ keyword }}</span>」 / <span>{{ area }}</span><br>
            <span>{{ people }}</span> / <span>{{ budget }}</span><br>
            {% if tags %}
                タグ: <span>{{ tags | join(', ') }}</span>
            {% endif %}
        </div>
        <h3>おすすめのお店</h3>
    {% endif %}

    <!-- ダミー店舗表示 -->
    <div class="shop-card">
        <button class="save-btn" onclick="toggleSave(this)">♡</button>
        <h4 class="shop-name">{{ shop_name }} (仮)</h4>
        <div class="shop-category">{{ area }}</div>
        <div class="shop-desc">
            {% if is_gacha %}
                ガチャで選ばれた運命のお店です！思い切って行ってみては？
            {% else %}
                {{ people }}での利用にぴったりな、{{ budget }}の予算で楽しめるお店です。「{{ keyword }}」の雰囲気を探している方に最適です。
            {% endif %}
        </div>
        <div>
            {% if tags %}
                {% for tag in tags %}
                    <span class="shop-tag">{{ tag }}</span>
                {% endfor %}
            {% else %}
                 <span class="shop-tag">おすすめ</span>
            {% endif %}
        </div>
    </div>

    <script>
        // お気に入りボタンの切り替え（見た目だけ）
        function toggleSave(btn) {
            btn.classList.toggle('active');
            if(btn.classList.contains('active')){
                btn.innerHTML = '♥';
            } else {
                btn.innerHTML = '♡';
            }
        }
    </script>
</body>
</html>
"""

@app.route('/')
def home():
    return render_template_string(HOME_HTML)

@app.route('/search', methods=['POST'])
def search():
    keyword = request.form.get('keyword', '')
    area = request.form.get('area', '姫路駅周辺')
    people = request.form.get('people', '2名')
    budget = request.form.get('budget', 'こだわらない')
    tags = request.form.getlist('tags') # チェックボックスはリストで受け取る
    
    # LINEシェア用のテキストをURLエンコード
    share_text = urllib.parse.quote(f"姫路で良さそうなお店見つけたよ！\n条件: {area} / {people} / {budget}\nhttps://eat-map-YOURAPPNAME.onrender.com")

    return render_template_string(RESULT_HTML, 
                                  is_gacha=False,
                                  keyword=keyword, 
                                  area=area, 
                                  people=people, 
                                  budget=budget,
                                  tags=tags,
                                  shop_name="テストカフェ姫路",
                                  share_text=share_text)

@app.route('/gacha', methods=['POST'])
def gacha():
    # ガチャ用のランダム店舗名（ダミー）
    shop_list = ["隠れ家バル HIMEJI", "カフェ・ド・シラサギ", "焼肉 姫路苑", "スパイスカレー 駅前亭", "純喫茶 昭和"]
    random_shop = random.choice(shop_list)
    
    share_text = urllib.parse.quote(f"お店ガチャで「{random_shop}」が出たよ！行ってみない？\nhttps://eat-map-YOURAPPNAME.onrender.com")
    
    return render_template_string(RESULT_HTML, 
                                  is_gacha=True,
                                  area="姫路市内のどこか",
                                  shop_name=random_shop,
                                  share_text=share_text)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
