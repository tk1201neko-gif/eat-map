import os
from flask import Flask, request, render_template_string

app = Flask(__name__)

# ==========================================
# 1. ホーム画面（ポップ＆カフェ風デザイン）
# ==========================================
@app.route('/')
def home():
    html_content = '''
    <!DOCTYPE html>
    <html lang="ja">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>EAT MAP - 誰と行く？</title>
        <link href="https://fonts.googleapis.com/css2?family=Zen+Maru+Gothic:wght@400;700&display=swap" rel="stylesheet">
        <style>
            body {
                font-family: 'Zen Maru Gothic', sans-serif;
                background-color: #FFF9E6;
                color: #5A4A42;
                margin: 0;
                padding: 30px 20px;
                display: flex;
                justify-content: center;
                align-items: center;
                min-height: 85vh;
            }
            .card {
                background: white;
                padding: 35px 25px;
                border-radius: 24px;
                box-shadow: 0 8px 0 #FFE0B2;
                border: 3px solid #FFE0B2;
                max-width: 420px;
                width: 100%;
                text-align: center;
                box-sizing: border-box;
            }
            .logo-icon { font-size: 42px; margin-bottom: 5px; }
            h1 {
                color: #FF9B50;
                font-size: 30px;
                margin: 0 0 10px 0;
                letter-spacing: 2px;
                text-shadow: 1px 1px 0 #FFE0B2;
            }
            p.subtitle {
                color: #8C6A53;
                font-size: 14px;
                margin-bottom: 25px;
                font-weight: bold;
                line-height: 1.5;
            }
            .input-box {
                width: 100%;
                padding: 14px 16px;
                border: 2px solid #FFD1A4;
                border-radius: 16px;
                font-size: 16px;
                font-family: inherit;
                outline: none;
                box-sizing: border-box;
                background-color: #FFFDF9;
                transition: 0.2s;
            }
            .input-box:focus {
                border-color: #FF9B50;
                box-shadow: 0 0 8px rgba(255, 155, 80, 0.3);
            }
            .tag-label {
                font-size: 13px;
                color: #A08573;
                text-align: left;
                margin: 18px 0 8px 5px;
                font-weight: bold;
            }
            .tags {
                display: flex;
                gap: 8px;
                flex-wrap: wrap;
                margin-bottom: 25px;
            }
            .tag {
                background: #FFF0E0;
                color: #D97330;
                padding: 8px 14px;
                border-radius: 20px;
                font-size: 13px;
                font-weight: bold;
                cursor: pointer;
                border: 1px solid #FFD1A4;
                transition: 0.15s;
                user-select: none;
            }
            .tag:hover {
                background: #FF9B50;
                color: white;
                transform: translateY(-2px);
            }
            .submit-btn {
                background-color: #FF9B50;
                color: white;
                border: none;
                padding: 15px;
                font-size: 18px;
                font-weight: bold;
                font-family: inherit;
                border-radius: 30px;
                cursor: pointer;
                width: 100%;
                box-shadow: 0 5px 0 #D97330;
                transition: 0.1s;
            }
            .submit-btn:active {
                transform: translateY(5px);
                box-shadow: none;
            }
        </style>
    </head>
    <body>
        <div class="card">
            <div class="logo-icon">🍴</div>
            <h1>EAT MAP</h1>
            <p class="subtitle">今日は誰とごはん行く？<br>一緒に行く人にぴったりなお店をご提案！</p>

            <form action="/search" method="POST">
                <input type="text" id="companionInput" name="companion" class="input-box" placeholder="例: 恋人と / 友達と4人で" required>

                <div class="tag-label">👇 タップで簡単入力！</div>
                <div class="tags">
                    <span class="tag" onclick="setTag('恋人と')">#恋人と 🍷</span>
                    <span class="tag" onclick="setTag('友達と')">#友達と 🎉</span>
                    <span class="tag" onclick="setTag('上司・先輩と')">#上司と 👔</span>
                    <span class="tag" onclick="setTag('家族と')">#家族と 👨‍👩‍👧</span>
                    <span class="tag" onclick="setTag('ひとりで')">#ひとりごはん ☕</span>
                </div>

                <button type="submit" class="submit-btn">ぴったりなお店を探す ✨</button>
            </form>
        </div>

        <script>
            function setTag(text) {
                document.getElementById('companionInput').value = text;
            }
        </script>
    </body>
    </html>
    '''
    return render_template_string(html_content)


# ==========================================
# 2. 検索処理と結果画面（ポップ＆カフェ風デザイン）
# ==========================================
@app.route('/search', methods=['POST'])
def search():
    companion = request.form.get('companion')

    dummy_places = [
        {"name": "ダイニングバー Luce", "rating": 4.5, "distance": "徒歩5分", "reason": "照明が暗く、落ち着いた個室があるため、特別な日のディナーに最適です。"},
        {"name": "和食割烹 ひめじ", "rating": 4.8, "distance": "徒歩8分", "reason": "個室完備で静かな空間。周囲を気にせずゆっくり会話を楽しめます。"},
        {"name": "イタリアン Vino", "rating": 4.2, "distance": "徒歩3分", "reason": "おしゃれな内装とワインが豊富で、会話が弾むカジュアルな雰囲気です。"}
    ]

    html_content = f'''
    <!DOCTYPE html>
    <html lang="ja">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>検索結果 - EAT MAP</title>
        <link href="https://fonts.googleapis.com/css2?family=Zen+Maru+Gothic:wght@400;700&display=swap" rel="stylesheet">
        <style>
            body {{ font-family: 'Zen Maru Gothic', sans-serif; background-color: #FFF9E6; color: #5A4A42; margin: 0; padding: 0; }}
            .header {{ background-color: #FF9B50; color: white; padding: 15px 20px; text-align: center; border-bottom: 4px dashed #FFF; }}
            .header h1 {{ margin: 0; font-size: 24px; letter-spacing: 2px; }}
            .search-keyword {{ font-size: 15px; margin-top: 8px; font-weight: bold; background: white; color: #FF9B50; display: inline-block; padding: 4px 15px; border-radius: 20px; }}
            .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
            .map-placeholder {{
                width: 100%; height: 220px; background-color: #E8D3B9;
                border-radius: 16px; margin-bottom: 25px;
                display: flex; align-items: center; justify-content: center;
                color: #8C6A53; font-weight: bold; font-size: 18px;
                border: 3px solid #D4B499; position: relative;
            }}
            .map-placeholder::before {{ content: "📍"; font-size: 30px; position: absolute; top: -15px; left: 50%; transform: translateX(-50%); }}
            .shop-card {{ background: white; border-radius: 20px; padding: 20px; margin-bottom: 20px; box-shadow: 0 6px 0 #FFE0B2; border: 2px solid #FFE0B2; position: relative; }}
            .rank-badge {{ position: absolute; top: -12px; left: -10px; background: #FF6B6B; color: white; font-weight: bold; width: 36px; height: 36px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 18px; box-shadow: 0 3px 0 #D93838; transform: rotate(-10deg); }}
            .shop-header {{ display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 12px; border-bottom: 2px dashed #EEE; padding-bottom: 10px; margin-left: 20px; }}
            .shop-name {{ font-size: 20px; font-weight: bold; color: #5A4A42; margin: 0; }}
            .shop-meta {{ font-size: 14px; color: #888; font-weight: bold; }}
            .rating {{ color: #FFB300; font-size: 16px; }}
            .ai-reason {{ background-color: #F0F8FF; padding: 15px; border-radius: 15px; font-size: 15px; line-height: 1.6; position: relative; margin-top: 15px; }}
            .ai-reason::before {{ content: ''; position: absolute; top: -10px; left: 20px; border-width: 0 10px 10px 10px; border-style: solid; border-color: transparent transparent #F0F8FF transparent; }}
            .ai-icon {{ color: #0088CC; font-weight: bold; display: block; margin-bottom: 5px; }}
            .back-btn {{ display: block; text-align: center; margin-top: 30px; padding: 15px; background: #FF9B50; color: white; text-decoration: none; border-radius: 30px; font-weight: bold; font-size: 18px; box-shadow: 0 5px 0 #D97330; transition: 0.1s; }}
            .back-btn:active {{ transform: translateY(5px); box-shadow: none; }}
        </style>
    </head>
    <body>
        <div class="header">
            <h1>🍴 EAT MAP</h1>
            <div class="search-keyword">「{companion}」におすすめ！</div>
        </div>
        <div class="container">
            <div class="map-placeholder">
                地図は準備中だよ！
            </div>
    '''

    for i, place in enumerate(dummy_places):
        rank = i + 1
        html_content += f'''
            <div class="shop-card">
                <div class="rank-badge">{rank}</div>
                <div class="shop-header">
                    <h2 class="shop-name">{place['name']}</h2>
                    <span class="shop-meta"><span class="rating">★{place['rating']}</span> / {place['distance']}</span>
                </div>
                <div class="ai-reason">
                    <span class="ai-icon">💡 AIのおすすめ！</span>
                    {place['reason']}
                </div>
            </div>
        '''

    html_content += '''
            <a href="/" class="back-btn">もういちど探す ↩️</a>
        </div>
    </body>
    </html>
    '''
    return render_template_string(html_content)


# ==========================================
# 3. 起動処理
# ==========================================
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)