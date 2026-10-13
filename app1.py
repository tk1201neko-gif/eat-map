from flask import Flask, request, render_template_string

app = Flask(__name__)

# トップ画面のHTMLテンプレート（カフェ風デザイン）
HOME_HTML = """
<!DOCTYPE html>
<html lang="ja">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>EAT MAP - 姫路のお店探し</title>
    <style>
        body {
            background-color: #fdfaf6; /* カフェ風の温かみのある背景色 */
            color: #5a4a42; /* ダークブラウンの文字色 */
            font-family: 'Helvetica Neue', Arial, 'Hiragino Kaku Gothic ProN', 'Hiragino Sans', Meiryo, sans-serif;
            margin: 0;
            padding: 0;
            display: flex;
            justify-content: center;
            align-items: center;
            min-height: 100vh;
        }
        .container {
            background-color: #ffffff;
            width: 90%;
            max-width: 400px;
            padding: 30px 20px;
            border-radius: 20px;
            box-shadow: 0 8px 16px rgba(0,0,0,0.05);
            text-align: center;
        }
        h1 {
            font-size: 28px;
            font-weight: 800;
            margin-bottom: 5px;
            color: #d48a6e; /* アクセントカラーのオレンジブラウン */
            letter-spacing: 2px;
        }
        p.subtitle {
            font-size: 13px;
            color: #8c7a6b;
            margin-bottom: 25px;
        }
        .form-group {
            margin-bottom: 20px;
            text-align: left;
        }
        label {
            font-weight: bold;
            font-size: 14px;
            display: block;
            margin-bottom: 8px;
            color: #5a4a42;
        }
        input[type="text"], select {
            width: 100%;
            padding: 14px;
            border: 2px solid #e8e0d9;
            border-radius: 12px;
            font-size: 15px;
            background-color: #faf7f2;
            color: #4a3b32;
            box-sizing: border-box; /* パディングを含めて幅を100%にする */
            outline: none;
            transition: border-color 0.3s ease;
        }
        input[type="text"]:focus, select:focus {
            border-color: #d48a6e;
        }
        .submit-btn {
            background-color: #d48a6e;
            color: white;
            border: none;
            padding: 15px 0;
            width: 100%;
            border-radius: 25px;
            font-size: 16px;
            font-weight: bold;
            cursor: pointer;
            box-shadow: 0 4px 10px rgba(212, 138, 110, 0.3);
            transition: transform 0.2s ease, box-shadow 0.2s ease;
        }
        .submit-btn:active {
            transform: translateY(2px);
            box-shadow: 0 2px 5px rgba(212, 138, 110, 0.3);
        }
        .tags-container {
            margin-top: 25px;
            text-align: left;
        }
        .tags-title {
            font-size: 12px;
            color: #8c7a6b;
            margin-bottom: 10px;
        }
        .tag {
            display: inline-block;
            background-color: #f2e9e1;
            color: #8c7a6b;
            padding: 6px 12px;
            border-radius: 15px;
            font-size: 12px;
            margin-right: 5px;
            margin-bottom: 8px;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>EAT MAP</h1>
        <p class="subtitle">姫路のぴったりなお店を見つけよう</p>

        <form action="/search" method="post">
            <!-- キーワード入力 -->
            <div class="form-group">
                <label>🔍 どんなお店を探してる？</label>
                <input type="text" name="keyword" placeholder="例：静かなカフェ、焼肉、夜景" required>
            </div>

            <!-- 人数選択（今回追加した部分） -->
            <div class="form-group">
                <label>👥 利用人数</label>
                <select name="people">
                    <option value="1名">1名（ひとりカフェ・ソロ活）</option>
                    <option value="2名" selected>2名（デート・友人）</option>
                    <option value="3〜4名">3〜4名（女子会・グループ）</option>
                    <option value="5名以上">5名以上（宴会・打ち上げ）</option>
                </select>
            </div>

            <button type="submit" class="submit-btn">お店を検索する</button>
        </form>

        <div class="tags-container">
            <div class="tags-title">人気のキーワード</div>
            <span class="tag">#駅チカ</span>
            <span class="tag">#個室あり</span>
            <span class="tag">#インスタ映え</span>
            <span class="tag">#コスパ最強</span>
        </div>
    </div>
</body>
</html>
"""

# 検索結果画面のHTMLテンプレート（ダミーデータ表示）
RESULT_HTML = """
<!DOCTYPE html>
<html lang="ja">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>検索結果 - EAT MAP</title>
    <style>
        body {
            background-color: #fdfaf6;
            color: #5a4a42;
            font-family: 'Helvetica Neue', Arial, sans-serif;
            margin: 0;
            padding: 20px 15px;
        }
        .header {
            display: flex;
            align-items: center;
            margin-bottom: 20px;
        }
        .back-btn {
            text-decoration: none;
            color: #d48a6e;
            font-size: 24px;
            margin-right: 15px;
        }
        h2 {
            font-size: 20px;
            margin: 0;
            color: #5a4a42;
        }
        .condition-box {
            background-color: #f2e9e1;
            padding: 12px 15px;
            border-radius: 12px;
            margin-bottom: 20px;
            font-size: 14px;
        }
        .condition-box span {
            font-weight: bold;
            color: #d48a6e;
        }
        .map-placeholder {
            background-color: #e8e0d9;
            height: 200px;
            border-radius: 15px;
            display: flex;
            justify-content: center;
            align-items: center;
            color: #8c7a6b;
            margin-bottom: 20px;
            font-size: 14px;
            border: 2px dashed #d0c5bc;
            text-align: center;
        }
        .shop-card {
            background-color: #ffffff;
            border-radius: 15px;
            padding: 15px;
            margin-bottom: 15px;
            box-shadow: 0 4px 10px rgba(0,0,0,0.03);
            border: 1px solid #f2e9e1;
        }
        .shop-name {
            font-size: 18px;
            font-weight: bold;
            color: #d48a6e;
            margin: 0 0 5px 0;
        }
        .shop-category {
            font-size: 12px;
            color: #8c7a6b;
            margin-bottom: 10px;
        }
        .shop-desc {
            font-size: 14px;
            line-height: 1.5;
            margin-bottom: 10px;
        }
        .shop-tag {
            display: inline-block;
            background-color: #faf7f2;
            color: #a49182;
            padding: 4px 8px;
            border-radius: 10px;
            font-size: 11px;
            margin-right: 5px;
        }
    </style>
</head>
<body>
    <div class="header">
        <a href="/" class="back-btn">←</a>
        <h2>検索結果</h2>
    </div>

    <div class="condition-box">
        探した条件：<br>
        キーワード「<span>{{ keyword }}</span>」<br>
        利用人数「<span>{{ people }}</span>」
    </div>

    <!-- 地図表示エリア（今後のGoogle Maps連携用） -->
    <div class="map-placeholder">
        📍 地図は準備中だよ！<br>
        （ここにGoogleマップが入ります）
    </div>

    <h3>おすすめのお店</h3>

    <!-- ダミーの店舗データ 1 -->
    <div class="shop-card">
        <h4 class="shop-name">Himeji Cafe & Dining (仮)</h4>
        <div class="shop-category">カフェ・洋食</div>
        <div class="shop-desc">
            {{ people }}での利用にぴったりな、おしゃれなカフェです。「{{ keyword }}」の雰囲気を楽しめるよ！
        </div>
        <div>
            <span class="shop-tag">おしゃれ</span>
            <span class="shop-tag">駅徒歩5分</span>
        </div>
    </div>

    <!-- ダミーの店舗データ 2 -->
    <div class="shop-card">
        <h4 class="shop-name">和食処 しらさぎ (仮)</h4>
        <div class="shop-category">和食・居酒屋</div>
        <div class="shop-desc">
            落ち着いた空間でゆったり過ごせるお店です。
        </div>
        <div>
            <span class="shop-tag">個室あり</span>
            <span class="shop-tag">落ち着く</span>
        </div>
    </div>

</body>
</html>
"""

@app.route('/')
def home():
    return render_template_string(HOME_HTML)

@app.route('/search', methods=['POST'])
def search():
    # フォームからキーワードと人数を受け取る
    keyword = request.form.get('keyword', '')
    people = request.form.get('people', '2名')

    # 検索結果画面のテンプレートに値を渡して表示
    return render_template_string(RESULT_HTML, keyword=keyword, people=people)

if __name__ == '__main__':
    # Render環境でも動くように host='0.0.0.0' を指定しています
    app.run(host='0.0.0.0', port=5000, debug=True)
