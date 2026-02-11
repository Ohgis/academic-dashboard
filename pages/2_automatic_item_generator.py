import streamlit as st
import json
from openai import OpenAI

# ページ設定
st.set_page_config(
    page_title="自動作問アプリ",
    page_icon="💡",
    layout="wide"
)

# --- 資料データの定義 ---
HISTORY_DATA = [
    {
        "topic": "元寇",
        "content": """元寇とは、モンゴル帝国をもとに中国を支配していた元が、日本に対して行った二回の大規模な侵略のことです。元はアジアの大部分を支配しており、日本にも服属を求めました。しかし、鎌倉幕府はこの要求を拒否したため、元は武力による侵略を行いました。
最初の侵略は、1274年に起こった「文永の役」です。約3〜4万人といわれる元の軍勢が、九州の博多湾に上陸しました。元軍は集団で戦う戦法や火薬を使った武器を用いて、日本の武士たちを苦しめました。これに対し、執権の北条時宗は御家人に出陣を命じ、御恩と奉公の関係にもとづいて迎え撃たせました。その後、元軍は撤退しようとしましたが、暴風雨によって多くの船が沈没し、侵略は失敗に終わりました。
二回目の侵略は、1281年に起こった「弘安の役」です。元は10万人以上ともいわれる大軍で再び日本を攻撃しました。鎌倉幕府は前回の経験を活かし、博多湾の海岸に防御用の石塁を築いて備えていました。御家人たちはこの石塁を拠点にして激しく抵抗しましたが、戦いが長引く中で大きな台風が発生し、元の船は大量に沈没しました。
元寇は外国からの侵略を防ぐ戦いであったため、勝利しても新たな土地を得ることができませんでした。そのため、御家人たちは十分な恩賞を受け取れず、幕府への不満を強めていきました。このことは、やがて鎌倉幕府が衰退していく原因の一つとなりました。"""
    },
    {
        "topic": "日清・日露戦争",
        "content": """日清戦争と日露戦争は、日本が近代国家として成長していく中で起こった二つの大きな戦争です。
1894年に始まった日清戦争は、朝鮮半島をめぐって日本と清(中国)が対立したことが原因です。当時、朝鮮は清の影響を強く受けていましたが、日本は朝鮮を独立した国として自国の影響下に置こうとしました。日本は近代的な軍隊と装備を持っていたため戦争に勝利し、下関条約によって台湾や遼東半島などを得ました。しかし、ロシア・ドイツ・フランスの三国干渉により、遼東半島は返還させられました。
その後、ロシアが満州や朝鮮へ勢力を広げたため、日本はこれに強い危機感を抱き、1904年に日露戦争が始まりました。日本は苦しい戦いを続けましたが、旅順港の戦いや日本海海戦で勝利し、1905年のポーツマス条約で戦争は終結しました。この結果、日本は韓国に対する優越権などを認められ、国際的な地位を高めました。しかし、多くの犠牲と大きな国民負担をともなった戦争でもありました。"""
    }
]

# --- 能力とタイプの定義 ---
ABILITY_DEFINITIONS = {
    "知識": "年号、出来事、用語など、個別的な知識を問う。事実確認が中心。",
    "概念": "個別の知識を組み合わせて形成される概念理解を問う。原理や背景の把握を確認する。",
    "思考": "個別の知識の運用など、限定された範囲での思考や判断を問う。論理的な推論を求める。",
    "問題解決": "知識、概念、思考・判断を統合的に運用して行う問題解決を問う。複合的な状況での最適解を求める。"
}

TYPE_DEFINITIONS = {
    "〇×": "提示された文の正誤を判定する形式。",
    "短答": "語句、年号、用語など、短いフレーズで解答させる形式。",
    "選択": "4つの選択肢の中から、最も適切な記述を1つ選ばせる形式。",
    "記述": "与えられた条件に従い、200字程度の文章で論理的に解答させる形式。"
}

# --- メイン部分 ---
st.title("💡 自動作問アプリ【MVP版】")

# APIキーの確認
try:
    api_key = st.secrets["OPENAI_API_KEY"]
    client = OpenAI(api_key=api_key)
    api_key_available = True
except (KeyError, FileNotFoundError):
    st.error("⚠️ OpenAI APIキーが設定されていません。Streamlit Cloudのsecretsに `OPENAI_API_KEY` を追加してください。")
    api_key_available = False

if api_key_available:
    # UI部分
    st.markdown("### Q1. 学習範囲を選択")
    topic_num = st.selectbox(
        "学習項目",
        ["1: 元寇", "2: 日清・日露戦争"],
        index=0
    )
    topic = "元寇" if "1:" in topic_num else "日清・日露戦争"
    
    st.markdown("### Q2. ターゲット能力を選択")
    ability_key = st.radio(
        "測定したい能力",
        list(ABILITY_DEFINITIONS.keys()),
        horizontal=True
    )
    st.caption(f"定義: {ABILITY_DEFINITIONS[ability_key]}")
    
    st.markdown("### Q3. 問題タイプを選択")
    type_key = st.radio(
        "回答形式",
        list(TYPE_DEFINITIONS.keys()),
        horizontal=True
    )
    st.caption(f"形式: {TYPE_DEFINITIONS[type_key]}")
    
    # デバッグモードの追加（オプション）
    show_debug = st.checkbox("デバッグモードを表示", value=False)
    
    if st.button("🚀 問題を作成", type="primary"):
        with st.spinner("AIが問題を練り上げています..."):
            # データのフィルタリング
            filtered = [d for d in HISTORY_DATA if d['topic'] == topic]
            
            if filtered:
                # プロンプトの構成
                prompt_content = f"""以下の【資料】に基づき、指定された【能力】を測定するための【問題タイプ】の問題を3問作成してください。

### 1. 【資料】
{filtered[0]['content']}

### 2. 測定すべき能力：{ability_key}
【定義】: {ABILITY_DEFINITIONS[ability_key]}

### 3. 問題形式：{type_key}
【形式の指定】: {TYPE_DEFINITIONS[type_key]}

### 4. 作成ルール
- **妥当性**: 指定された「能力」を正しく測るための問いにしてください。
- **根拠**: すべて【資料】にある内容に基づき作成してください。
- **構成**: 各問題に「問題文」「正解」「詳細な解説」を付けてください。
- **記述型の場合**: 採点時に含めるべきキーワードや評価基準も併記してください。"""
                
                # デバッグモード表示
                if show_debug:
                    with st.expander("📋 デバッグ情報：送信プロンプト", expanded=False):
                        st.text_area(
                            "プロンプト内容",
                            value=prompt_content,
                            height=300,
                            disabled=True
                        )
                
                try:
                    # OpenAI APIの呼び出し
                    res = client.chat.completions.create(
                        model="gpt-4o",
                        messages=[
                            {
                                "role": "system",
                                "content": "あなたは教育測定学に基づき、正確で妥当性の高い試験問題を作成する専門家です。"
                            },
                            {
                                "role": "user",
                                "content": prompt_content
                            }
                        ]
                    )
                    
                    # 結果の表示
                    st.markdown("---")
                    st.subheader("📝 生成された問題")
                    st.markdown(res.choices[0].message.content)
                    
                    # 使用トークン数の表示（オプション）
                    if show_debug:
                        with st.expander("📊 API使用情報", expanded=False):
                            st.write(f"- 入力トークン数: {res.usage.prompt_tokens}")
                            st.write(f"- 出力トークン数: {res.usage.completion_tokens}")
                            st.write(f"- 合計トークン数: {res.usage.total_tokens}")
                
                except Exception as e:
                    st.error(f"❌ APIエラーが発生しました: {str(e)}")
            else:
                st.warning(f"選択されたトピック「{topic}」のデータが見つかりませんでした。")
else:
    st.info("👆 APIキーを設定すると、アプリが使用可能になります。")

# サイドバーに使い方を表示
with st.sidebar:
    st.markdown("## 📖 使い方")
    st.markdown("""
    1. **学習範囲**を選択
    2. **測定したい能力**を選択
    3. **問題タイプ**を選択
    4. 「問題を作成」ボタンをクリック
    
    ---
    
    ### 💡 ヒント
    - デバッグモードで送信プロンプトを確認できます
    - 各能力・形式の定義を参考にしてください
    """)
    
    st.markdown("---")
    st.markdown("### ⚙️ 設定方法")
    st.markdown("""
    **OpenAI APIキーの設定:**
    
    Streamlit Cloudの設定で以下を追加:
    ```toml
    [default]
    OPENAI_API_KEY = "sk-proj-..."
    ```
    """)
