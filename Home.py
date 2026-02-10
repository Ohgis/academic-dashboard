import streamlit as st

st.set_page_config(
    page_title="PoC試作アプリ集",
    page_icon="🎓",
    layout="wide"
)

st.title("🎓 PoC試作アプリ集")

st.markdown("""
## ようこそ！

サイドバーから利用したいツールを選択してください。

### 📊 利用可能なツール

**Dashboard** - 学力データ分析ダッシュボード
- 学習者の習熟度パターンを可視化
- 観点別・領域別の分析が可能

---

### 今後の追加予定
- 自動採点ツール
- 自動作問ツール
- その他アプリケーション
""")

st.info("💡 左サイドバーから「dashboard」を選択して開始してください。")