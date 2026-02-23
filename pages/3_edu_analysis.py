"""
教育データ分析ツール v2
- 分析メニューをDBで管理（analysis_menus テーブル）
- 領域・能力をDBから動的取得
- グラフ種類: bar / radar / heatmap / metric / table
"""
import streamlit as st
import pandas as pd
import psycopg2
import json
import subprocess
import tempfile
import os
import anthropic
import plotly.express as px
import plotly.graph_objects as go

# ─── ページ設定 ───────────────────────────────────────
st.set_page_config(
    page_title="教育データ分析ツール",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Noto+Sans+JP:wght@300;400;700&family=IBM+Plex+Mono:wght@400;600&display=swap');
html, body, [class*="css"] { font-family: 'Noto Sans JP', sans-serif; }
.main-header {
    background: linear-gradient(135deg, #0f2027, #203a43, #2c5364);
    padding: 2rem 2.5rem; border-radius: 12px;
    margin-bottom: 2rem; color: white;
}
.main-header h1 { font-size: 1.8rem; font-weight: 700; margin: 0; }
.main-header p  { color: #a8c4d4; margin: 0.3rem 0 0; font-size: 0.9rem; }
.ai-response {
    background: #f0f9ff; border-left: 4px solid #0284c7;
    padding: 1.2rem 1.5rem; border-radius: 0 8px 8px 0;
    font-size: 0.92rem; line-height: 1.7; white-space: pre-wrap;
}
</style>
""", unsafe_allow_html=True)

# ─── Rパッケージのインストール ───────────────────────
@st.cache_resource
def install_r_packages():
    subprocess.run(
        ["Rscript", "-e",
         "install.packages(c('jsonlite', 'dplyr', 'tidyr'), repos='https://cran.rstudio.com/')"],
        capture_output=True
    )

install_r_packages()

# ─── DB接続 ──────────────────────────────────────────
@st.cache_resource
def get_conn():
    return psycopg2.connect(
        host=st.secrets["DB_HOST"], port=st.secrets.get("DB_PORT", 5432),
        database=st.secrets["DB_NAME"], user=st.secrets["DB_USER"],
        password=st.secrets["DB_PASSWORD"],
    )

def qdf(sql, params=None):
    return pd.read_sql_query(sql, get_conn(), params=params)

# ─── マスタデータ取得（動的） ──────────────────────────
@st.cache_data(ttl=600)
def get_analysis_menus() -> pd.DataFrame:
    """analysis_menus テーブルから有効なメニューを取得"""
    return qdf("""
        SELECT id, name, r_function, chart_type, axis, description
        FROM analysis_menus
        WHERE is_active = TRUE
        ORDER BY display_order
    """)

@st.cache_data(ttl=600)
def get_domains() -> list:
    """item_params から domain 一覧を動的取得"""
    return qdf("SELECT DISTINCT domain FROM item_params ORDER BY domain")["domain"].tolist()

@st.cache_data(ttl=600)
def get_abilities() -> list:
    """item_params から ability 一覧を動的取得"""
    return qdf("SELECT DISTINCT ability FROM item_params ORDER BY ability")["ability"].tolist()

@st.cache_data(ttl=600)
def get_item_params() -> pd.DataFrame:
    return qdf("SELECT item_no, domain, ability FROM item_params ORDER BY item_no")

@st.cache_data(ttl=300)
def get_filter_options():
    grades   = qdf("SELECT DISTINCT grade FROM students ORDER BY grade")["grade"].tolist()
    classes  = qdf("SELECT DISTINCT class FROM students ORDER BY class")["class"].tolist()
    subjects = qdf("SELECT DISTINCT subject FROM test_responses ORDER BY subject")["subject"].tolist()
    dates    = qdf("SELECT DISTINCT test_date FROM test_responses ORDER BY test_date DESC")["test_date"].tolist()
    return grades, classes, subjects, dates

@st.cache_data(ttl=300)
def get_response_data(grade=None, class_=None, subject=None, test_date=None) -> pd.DataFrame:
    cond, params = [], []
    if grade:     cond.append("s.grade = %s");     params.append(grade)
    if class_:    cond.append("s.class = %s");     params.append(class_)
    if subject:   cond.append("tr.subject = %s");  params.append(subject)
    if test_date: cond.append("tr.test_date = %s"); params.append(test_date)
    where = ("WHERE " + " AND ".join(cond)) if cond else ""
    sql = f"""
        SELECT s.student_id, s.grade, s.class, tr.subject,
               tr.item_no, tr.response
        FROM test_responses tr
        JOIN students s ON tr.student_id = s.student_id
        {where}
        ORDER BY s.student_id, tr.item_no
    """
    return qdf(sql, params or None)

def pivot_wide(df: pd.DataFrame) -> pd.DataFrame:
    pivot = df.pivot_table(
        index=["student_id", "grade", "class", "subject"],
        columns="item_no", values="response"
    ).reset_index()
    pivot.columns = [f"x{c}" if isinstance(c, int) else c for c in pivot.columns]
    return pivot

# ─── R実行 ───────────────────────────────────────────
def run_r(r_function: str, df_wide: pd.DataFrame,
          item_params_df: pd.DataFrame = None) -> dict:
    ip_records = None
    if item_params_df is not None:
        ip = item_params_df.copy()
        ip["item"] = "x" + ip["item_no"].astype(str)
        ip_records = ip[["item_no", "item", "domain", "ability"]].to_dict(orient="records")

    payload = {
        "analysis_type": r_function,
        "data": df_wide.to_dict(orient="records"),
        "item_params": ip_records,
    }
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json",
                                    delete=False, encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False)
        tmp = f.name
    try:
        RSCRIPT = r"C:\Program Files\R\R-4.4.2\bin\x64\Rscript.exe"
        R_SCRIPT = os.path.join(os.path.dirname(os.path.dirname(__file__)), "analyze_v2.R")
        res = subprocess.run([RSCRIPT, R_SCRIPT, tmp],
                             capture_output=True, text=True, timeout=120)
        if res.returncode != 0:
            return {"error": res.stderr}
        return json.loads(res.stdout)
    except subprocess.TimeoutExpired:
        return {"error": "R分析がタイムアウトしました"}
    except json.JSONDecodeError:
        return {"error": f"Rの出力をパースできません: {res.stdout[:300]}"}
    finally:
        os.unlink(tmp)

# ─── グラフ描画（chart_type で振り分け） ──────────────
def build_color_map(keys: list, palette: list = None) -> dict:
    """キーのリストに対してカラーマップを動的生成"""
    default_palette = [
        "#2563eb", "#16a34a", "#dc2626", "#d97706",
        "#7c3aed", "#0891b2", "#be185d", "#65a30d"
    ]
    p = palette or default_palette
    return {k: p[i % len(p)] for i, k in enumerate(keys)}


def render_bar(result: dict, menu: dict, item_params_df: pd.DataFrame,
               domains: list, abilities: list):
    axis = menu.get("axis")

    if axis is None:
        # 得点分布 or 問題別正答率
        if "distribution" in result:
            df = pd.DataFrame(result["distribution"])
            fig = px.bar(df, x="score", y="count",
                         labels={"score": "得点", "count": "人数"},
                         color_discrete_sequence=["#2563eb"], title="得点分布")
        else:
            df = pd.DataFrame(result["difficulty"])
            # domain カラーマップを動的生成
            color_map = build_color_map(domains)
            df2 = df.merge(item_params_df, on="item_no", how="left")
            df2["color"] = df2["domain"].map(color_map).fillna("#94a3b8")
            fig = go.Figure()
            for d in domains:
                sub = df2[df2["domain"] == d]
                fig.add_trace(go.Bar(
                    x=sub["item_no"], y=sub["correct_rate"],
                    name=f"領域{d}", marker_color=color_map[d],
                    hovertemplate="問%{x}: %{y:.1%}<extra></extra>",
                ))
            fig.update_layout(
                title="問題別正答率（領域別）",
                xaxis_title="問題番号", yaxis_title="正答率",
                yaxis=dict(tickformat=".0%", range=[0, 1]),
                barmode="group", plot_bgcolor="white",
                font_family="Noto Sans JP",
            )
        st.plotly_chart(fig, use_container_width=True)

    elif axis == "ability":
        df = pd.DataFrame(result["ability_scores"])
        color_map = build_color_map(abilities)
        fig = px.bar(df, x="ability", y="avg_pct", color="class",
                     barmode="group",
                     labels={"ability": "能力", "avg_pct": "平均正答率(%)", "class": "クラス"},
                     title="能力別正答率（クラス比較）",
                     color_discrete_sequence=list(color_map.values()))
        fig.update_layout(plot_bgcolor="white", font_family="Noto Sans JP")
        st.plotly_chart(fig, use_container_width=True)
        st.dataframe(df, hide_index=True, use_container_width=True)


def render_radar(result: dict, domains: list):
    df = pd.DataFrame(result["domain_scores"])
    classes = df["class"].unique().tolist()
    color_map = build_color_map(classes)

    fig = go.Figure()
    for cls in classes:
        sub = df[df["class"] == cls].sort_values("domain")
        r     = sub["avg_pct"].tolist()
        theta = [f"領域{d}" for d in sub["domain"].tolist()]
        r += r[:1]; theta += theta[:1]
        fig.add_trace(go.Scatterpolar(
            r=r, theta=theta, fill="toself",
            name=f"{cls}組", line_color=color_map[cls]
        ))
    fig.update_layout(
        polar=dict(radialaxis=dict(visible=True, range=[0, 100])),
        title="クラス別 領域ごと正答率レーダー",
        font_family="Noto Sans JP",
    )
    st.plotly_chart(fig, use_container_width=True)
    st.dataframe(df.assign(domain=df["domain"].apply(lambda x: f"領域{x}")),
                 hide_index=True, use_container_width=True)


def render_heatmap(result: dict):
    df = pd.DataFrame(result["cross_scores"])
    pivot = df.pivot(index="domain", columns="ability", values="avg_pct")
    pivot.index = [f"領域{d}" for d in pivot.index]

    fig = px.imshow(
        pivot, text_auto=".1f",
        color_continuous_scale="Blues",
        labels=dict(x="能力", y="領域", color="正答率(%)"),
        title="領域 × 能力 クロス集計（平均正答率%）",
        aspect="auto",
    )
    fig.update_layout(font_family="Noto Sans JP")
    st.plotly_chart(fig, use_container_width=True)

    # 注記：問題数ゼロのセルは空白
    n_items_df = df.pivot(index="domain", columns="ability", values="n_items")
    n_items_df.index = [f"領域{d}" for d in n_items_df.index]
    with st.expander("各セルの問題数"):
        st.dataframe(n_items_df, use_container_width=True)


def render_metric(result: dict):
    col1, col2 = st.columns(2)
    col1.metric("Cronbach's α", f"{result['alpha']:.4f}")
    col2.metric("解釈", result["interpretation"])
    st.info(f"問題数: {result['k']} 問  |  α係数は1.0に近いほど内的整合性が高いことを示します。")


def render_result(result: dict, menu: dict,
                  item_params_df: pd.DataFrame, domains: list, abilities: list):
    """chart_type に応じてグラフ描画を振り分け"""
    if "error" in result:
        st.error(f"R分析エラー: {result['error']}")
        return

    chart = menu["chart_type"]
    if chart == "bar":
        render_bar(result, menu, item_params_df, domains, abilities)
    elif chart == "radar":
        render_radar(result, domains)
    elif chart == "heatmap":
        render_heatmap(result)
    elif chart == "metric":
        render_metric(result)
    elif chart == "table":
        # 汎用テーブル表示（将来の拡張用）
        for key, val in result.items():
            if isinstance(val, list):
                st.dataframe(pd.DataFrame(val), hide_index=True, use_container_width=True)

# ─── Claude API ──────────────────────────────────────
def ask_claude(prompt: str, context: str) -> str:
    client = anthropic.Anthropic(api_key=st.secrets["ANTHROPIC_API_KEY"])
    msg = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=1024,
        system="""あなたは教育データ分析の専門家です。
小中学校の教師が理解しやすいように、統計分析の結果を平易な日本語で解説してください。
数字の羅列より、授業改善に直結する具体的な示唆を優先してください。""",
        messages=[{"role": "user",
                   "content": f"【分析結果データ】\n{context}\n\n【質問】\n{prompt}"}]
    )
    return msg.content[0].text

# ─── メインUI ────────────────────────────────────────
st.markdown("""
<div class="main-header">
  <h1>📊 教育データ分析ツール</h1>
  <p>テスト結果の統計分析・AI解釈・可視化を一元管理</p>
</div>
""", unsafe_allow_html=True)

# DB接続確認
try:
    menus_df   = get_analysis_menus()
    domains    = get_domains()
    abilities  = get_abilities()
    item_params_df = get_item_params()
    db_ok = True
except Exception as e:
    st.error(f"DB接続エラー: {e}")
    db_ok = False
    st.stop()

# サイドバー
with st.sidebar:
    st.markdown("### 🔍 データ絞り込み")
    grades, classes, subjects, dates = get_filter_options()
    sel_grade   = st.selectbox("学年",     ["全体"] + [str(g) for g in grades])
    sel_class   = st.selectbox("クラス",   ["全体"] + classes)
    sel_subject = st.selectbox("教科",     ["全体"] + subjects)
    sel_date    = st.selectbox("テスト日", ["全体"] + [str(d) for d in dates])

    st.divider()
    # メニュー選択（DBから動的に取得）
    st.markdown("### ⚙️ 実行する分析")
    selected_menus = []
    for _, row in menus_df.iterrows():
        if st.checkbox(row["name"], value=True, key=f"menu_{row['id']}"):
            selected_menus.append(row)

    st.divider()
    analyze_btn = st.button("▶ 分析実行", type="primary", use_container_width=True)
    if analyze_btn:                              # ← 追加
        st.session_state.analyzed = True        # ← 追加

    # 管理者向け情報
    with st.expander("📋 分析メニュー情報", expanded=False):
        st.caption("このメニューは analysis_menus テーブルで管理されています")
        st.dataframe(menus_df[["name", "r_function", "chart_type", "axis"]],
                     hide_index=True, use_container_width=True)

# メインエリア
if not st.session_state.get("analyzed", False):
    st.markdown("""
    #### 使い方
    1. 左のサイドバーでデータを絞り込む
    2. 実行する分析にチェックを入れる
    3. **▶ 分析実行** をクリック
    """)
    st.stop()

# データ取得
with st.spinner("データを取得中..."):
    df_long = get_response_data(
        grade     = None if sel_grade   == "全体" else int(sel_grade),
        class_    = None if sel_class   == "全体" else sel_class,
        subject   = None if sel_subject == "全体" else sel_subject,
        test_date = None if sel_date    == "全体" else sel_date,
    )

if df_long.empty:
    st.warning("条件に合うデータが見つかりませんでした。")
    st.stop()

df_wide = pivot_wide(df_long)
score_cols = [c for c in df_wide.columns if c.startswith("x")]

# サマリ
c1, c2, c3, c4 = st.columns(4)
c1.metric("対象生徒数", f"{df_wide['student_id'].nunique()} 名")
c2.metric("問題数",     f"{len(score_cols)} 問")
c3.metric("領域数",     f"{len(domains)} 領域")
c4.metric("能力数",     f"{len(abilities)} 能力")
st.divider()

# 動的タブ生成（選択されたメニューのみ）
needs_item_params = {"item_difficulty", "domain_analysis",
                     "ability_analysis", "cross_analysis"}
results_summary = {}

if not selected_menus:
    st.info("左のサイドバーで分析を選択してください。")
    st.stop()

# AI解釈タブを末尾に追加
tab_names = [m["name"] for m in selected_menus] + ["🤖 AI解釈"]
tabs = st.tabs(tab_names)

for i, menu in enumerate(selected_menus):
    with tabs[i]:
        with st.spinner(f"{menu['name']} を計算中..."):
            ip = item_params_df if menu["r_function"] in needs_item_params else None
            result = run_r(menu["r_function"], df_wide, ip)

        render_result(result, menu, item_params_df, domains, abilities)

        # AI解釈用にサマリを蓄積
        if "error" not in result:
            # 数値データを文字列化してコンテキストに追加
            for key, val in result.items():
                if isinstance(val, list) and val:
                    results_summary[menu["name"]] = pd.DataFrame(val).to_string()
                elif isinstance(val, (int, float, str)):
                    results_summary.setdefault(menu["name"], "")
                    results_summary[menu["name"]] += f"{key}: {val}\n"

# session_state の初期化
if "ai_answer" not in st.session_state:
    st.session_state.ai_answer = None
if "results_summary" not in st.session_state:
    st.session_state.results_summary = {}

# 分析結果をsession_stateに保存
st.session_state.results_summary = results_summary

# AI解釈タブ
with tabs[-1]:
    st.markdown("#### 🤖 Claude AIに分析結果を解釈してもらう")
    if not st.session_state.results_summary:
        st.info("他のタブで分析を実行すると、AIが結果を解釈できます。")
    else:
        context_str = "\n\n".join([f"【{k}】\n{v}" for k, v in st.session_state.results_summary.items()])

        preset_q = [
            "この結果から、どのクラスが最も支援を必要としていますか？",
            "正答率の低い問題の傾向と、授業改善のヒントを教えてください。",
            "領域・能力別の強みと弱みを比較し、重点指導領域を提案してください。",
            "保護者向けに分かりやすく結果を要約してください。",
            "管理職への報告用に簡潔にまとめてください。",
        ]
        sel_q = st.selectbox("よくある質問", ["（カスタム入力）"] + preset_q)
        user_q = st.text_area(
            "AIへの質問",
            value="" if sel_q == "（カスタム入力）" else sel_q,
            height=80,
        )
        if st.button("🤖 AIに質問する", type="primary"):
            if user_q.strip():
                with st.spinner("Claude AIが分析中..."):
                    st.session_state.ai_answer = ask_claude(user_q, context_str)
            else:
                st.warning("質問を入力してください。")

        # 回答を常に表示（session_stateに保持されている限り）
        if st.session_state.ai_answer:
            with st.container(border=True):
                st.markdown(st.session_state.ai_answer)
            
st.divider()
st.caption("教育データ分析ツール v2 | Streamlit + R + Claude API + PostgreSQL")
