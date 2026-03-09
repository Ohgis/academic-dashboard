"""
教育データ分析ツール v4
- DB: Supabase PostgreSQL (v3と同じ接続)
- IRT θ推定: 既存困難度パラメータ固定 WLE (analyze_v4.R)
- タブ: 集団分析 / 小問分析 / 意識調査 / 学力×意識 / 個人票 / AI解釈
- ドリルダウン: 学校→クラス→個人（サイドバー + タブ内切替）
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
from plotly.subplots import make_subplots

# ════════════════════════════════════════════════════════
# ページ設定
# ════════════════════════════════════════════════════════
st.set_page_config(
    page_title="学力分析ダッシュボード v4",
    page_icon="🎓",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─── デザインテーマ ─────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Noto+Sans+JP:wght@300;400;500;700&family=DM+Mono:wght@400;500&display=swap');

html, body, [class*="css"] {
    font-family: 'Noto Sans JP', sans-serif;
}

/* ヘッダー */
.v4-header {
    background: linear-gradient(135deg, #0a0f1e 0%, #0d2137 50%, #0a1628 100%);
    border: 1px solid rgba(56, 189, 248, 0.2);
    border-radius: 16px;
    padding: 2rem 2.5rem;
    margin-bottom: 1.5rem;
    position: relative;
    overflow: hidden;
}
.v4-header::before {
    content: '';
    position: absolute;
    top: -50%;
    left: -50%;
    width: 200%;
    height: 200%;
    background: radial-gradient(ellipse at 30% 50%, rgba(56,189,248,0.06) 0%, transparent 60%),
                radial-gradient(ellipse at 70% 50%, rgba(99,102,241,0.06) 0%, transparent 60%);
}
.v4-header h1 {
    font-size: 1.7rem; font-weight: 700;
    color: #f0f9ff; margin: 0; letter-spacing: -0.02em;
}
.v4-header p {
    color: #7dd3fc; margin: 0.4rem 0 0;
    font-size: 0.85rem; font-weight: 300;
}

/* メトリクスカード */
.metric-card {
    background: linear-gradient(135deg, #0f172a, #1e293b);
    border: 1px solid rgba(56,189,248,0.15);
    border-radius: 12px;
    padding: 1.2rem 1.4rem;
    text-align: center;
}
.metric-card .val {
    font-size: 2rem; font-weight: 700;
    color: #38bdf8; font-family: 'DM Mono', monospace;
    line-height: 1;
}
.metric-card .lbl {
    font-size: 0.75rem; color: #94a3b8;
    margin-top: 0.3rem; letter-spacing: 0.05em;
}
.metric-card .sub {
    font-size: 0.8rem; color: #64748b; margin-top: 0.1rem;
}

/* セクションヘッダー */
.section-head {
    display: flex; align-items: center; gap: 0.6rem;
    border-bottom: 1px solid rgba(56,189,248,0.15);
    padding-bottom: 0.5rem; margin: 1.5rem 0 1rem;
}
.section-head span {
    font-size: 0.95rem; font-weight: 600; color: #e2e8f0;
}

/* サイドバー */
[data-testid="stSidebar"] > div:first-child {
    background: linear-gradient(180deg, #0a0f1e 0%, #0d1b2e 100%);
    border-right: 1px solid rgba(56,189,248,0.1);
}
section[data-testid="stSidebar"] label { color: #94a3b8 !important; }
section[data-testid="stSidebar"] p { color: #94a3b8; }

/* AI 回答ボックス */
.ai-box {
    background: linear-gradient(135deg, #0d1b2e, #0f2037);
    border: 1px solid rgba(99,102,241,0.3);
    border-left: 3px solid #6366f1;
    border-radius: 8px;
    padding: 1.4rem 1.6rem;
    color: #e2e8f0;
    font-size: 0.92rem;
    line-height: 1.75;
}

/* タブ */
.stTabs [data-baseweb="tab"] {
    font-size: 0.85rem;
    padding: 0.5rem 1rem;
}
</style>
""", unsafe_allow_html=True)

# ════════════════════════════════════════════════════════
# Rパッケージインストール（キャッシュ）
# ════════════════════════════════════════════════════════
@st.cache_resource
def install_r_packages():
    subprocess.run(
        ["Rscript", "-e",
         "dir.create(Sys.getenv('R_LIBS_USER'), recursive=TRUE, showWarnings=FALSE);"
         "pkgs <- c('jsonlite','dplyr','tidyr');"
         "inst <- pkgs[!pkgs %in% installed.packages()[,'Package']];"
         "if(length(inst)) install.packages(inst, lib=Sys.getenv('R_LIBS_USER'), repos='https://cran.rstudio.com/')"],
        capture_output=True, text=True
    )

install_r_packages()

# ════════════════════════════════════════════════════════
# DB接続
# ════════════════════════════════════════════════════════
@st.cache_resource
def get_conn():
    return psycopg2.connect(
        host=st.secrets["V4_DB_HOST"],
        port=st.secrets.get("V4_DB_PORT", 5432),
        database=st.secrets["V4_DB_NAME"],
        user=st.secrets["V4_DB_USER"],
        password=st.secrets["V4_DB_PASSWORD"],
    )

def qdf(sql, params=None):
    return pd.read_sql_query(sql, get_conn(), params=params)

# ════════════════════════════════════════════════════════
# マスタデータ取得
# ════════════════════════════════════════════════════════
@st.cache_data(ttl=600)
def get_schools():
    return qdf("SELECT DISTINCT school FROM test_results ORDER BY school")["school"].tolist()

@st.cache_data(ttl=600)
def get_classes(school=None):
    if school:
        return qdf("SELECT DISTINCT class_id FROM test_results WHERE school=%s ORDER BY class_id",
                   (school,))["class_id"].tolist()
    return qdf("SELECT DISTINCT class_id FROM test_results ORDER BY class_id")["class_id"].tolist()

@st.cache_data(ttl=600)
def get_subjects():
    return qdf("SELECT DISTINCT subject FROM test_results ORDER BY subject")["subject"].tolist()

@st.cache_data(ttl=600)
def get_students(school=None, class_id=None):
    cond, params = [], []
    if school:    cond.append("school=%s");    params.append(school)
    if class_id:  cond.append("class_id=%s");  params.append(class_id)
    where = ("WHERE " + " AND ".join(cond)) if cond else ""
    return qdf(
        f"SELECT DISTINCT student_id, student_no FROM test_results {where} ORDER BY student_no",
        params or None
    )

@st.cache_data(ttl=600)
def get_question_master():
    return qdf("""
        SELECT question_id, subject, "大領域", "中領域", "観点",
               "知識理解", "資質能力", "全国値", "困難度", "解答形式"
        FROM question_master
        ORDER BY question_id
    """)

@st.cache_data(ttl=600)
def get_attitude_master():
    return qdf("SELECT question_id, subject, \"全国値\" FROM attitude_master ORDER BY question_id")

# ════════════════════════════════════════════════════════
# データ取得
# ════════════════════════════════════════════════════════
@st.cache_data(ttl=300)
def get_test_results(school=None, class_id=None, subject=None):
    cond, params = [], []
    if school:    cond.append("school=%s");    params.append(school)
    if class_id:  cond.append("class_id=%s");  params.append(int(class_id))
    if subject:   cond.append("subject=%s");   params.append(subject)
    where = ("WHERE " + " AND ".join(cond)) if cond else ""
    return qdf(
        f"SELECT student_id, school, class_id, student_no, subject, question_id, correct "
        f"FROM test_results {where} ORDER BY student_id, question_id",
        params or None
    )

@st.cache_data(ttl=300)
def get_attitude_results(school=None, class_id=None, subject=None):
    cond, params = [], []
    if school:    cond.append("school=%s");    params.append(school)
    if class_id:  cond.append("class_id=%s");  params.append(int(class_id))
    if subject:   cond.append("subject=%s");   params.append(subject)
    where = ("WHERE " + " AND ".join(cond)) if cond else ""
    return qdf(
        f"SELECT student_id, school, class_id, student_no, subject, question_id, score "
        f"FROM attitude_results {where} ORDER BY student_id, question_id",
        params or None
    )

# ════════════════════════════════════════════════════════
# R実行ユーティリティ
# ════════════════════════════════════════════════════════
R_SCRIPT = os.path.join(os.path.dirname(os.path.dirname(__file__)), "analyze_v4.R")

def run_r(analysis_type: str, data: pd.DataFrame,
          item_params: pd.DataFrame = None,
          extra: dict = None) -> dict:
    payload = {
        "analysis_type": analysis_type,
        "data": data.to_dict(orient="records"),
    }
    if item_params is not None:
        payload["item_params"] = item_params.to_dict(orient="records")
    if extra:
        payload.update(extra)

    with tempfile.NamedTemporaryFile(mode="w", suffix=".json",
                                     delete=False, encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False)
        tmp = f.name
    try:
        res = subprocess.run(
            ["Rscript", R_SCRIPT, tmp],
            capture_output=True, timeout=120
        )
        stdout = res.stdout.decode("utf-8", errors="replace")
        stderr = res.stderr.decode("utf-8", errors="replace")
        if res.returncode != 0:
            return {"error": stderr[-500:]}
        return json.loads(stdout)
    except subprocess.TimeoutExpired:
        return {"error": "R分析がタイムアウトしました（120秒）"}
    except json.JSONDecodeError:
        return {"error": f"Rの出力をパースできません: {res.stdout[:300]}"}
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)

# ════════════════════════════════════════════════════════
# カラーパレット・グラフユーティリティ
# ════════════════════════════════════════════════════════
PALETTE = ["#38bdf8", "#818cf8", "#34d399", "#fb923c",
           "#f472b6", "#a78bfa", "#facc15", "#2dd4bf"]
PLOTLY_TEMPLATE = "plotly_dark"

def group_label(row, group_by):
    if group_by == "class":
        return f"{row['school']}-{row['class_id']}"
    return str(row["school"])

def color_map(keys):
    return {k: PALETTE[i % len(PALETTE)] for i, k in enumerate(keys)}

def err(msg):
    st.error(f"⚠️ {msg}")

# ════════════════════════════════════════════════════════
# グラフ描画関数
# ════════════════════════════════════════════════════════

def plot_theta_distribution(result: dict, group_by: str):
    """θ分布: ヒストグラム + 箱ひげ図"""
    if "error" in result:
        return err(result["error"])

    ind_df = pd.DataFrame(result["individual"])
    sum_df = pd.DataFrame(result["summary"])

    if group_by == "class":
        ind_df["group"] = ind_df["school"].astype(str) + "-" + ind_df["class_id"].astype(str)
        sum_df["group"] = sum_df["school"].astype(str) + "-" + sum_df["class_id"].astype(str)
    else:
        ind_df["group"] = ind_df["school"].astype(str)
        sum_df["group"] = sum_df["school"].astype(str)

    groups = sorted(ind_df["group"].unique())
    cmap   = color_map(groups)

    # ── ヒストグラム + 箱ひげ図（横並び）
    col1, col2 = st.columns(2)

    with col1:
        fig_hist = go.Figure()
        for g in groups:
            sub = ind_df[ind_df["group"] == g]["theta"].dropna()
            fig_hist.add_trace(go.Histogram(
                x=sub, name=g, opacity=0.75,
                marker_color=cmap[g], nbinsx=20,
            ))
        fig_hist.update_layout(
            title="θ分布（ヒストグラム）", barmode="overlay",
            xaxis_title="θ値", yaxis_title="人数",
            template=PLOTLY_TEMPLATE, font_family="Noto Sans JP",
            legend=dict(orientation="h", y=-0.2),
        )
        st.plotly_chart(fig_hist, use_container_width=True)

    with col2:
        fig_box = go.Figure()
        for g in groups:
            sub = ind_df[ind_df["group"] == g]["theta"].dropna()
            fig_box.add_trace(go.Box(
                y=sub, name=g, marker_color=cmap[g],
                boxmean="sd", jitter=0.3, pointpos=-1.5,
                marker=dict(size=4, opacity=0.5),
            ))
        fig_box.update_layout(
            title="θ分布（箱ひげ図）",
            yaxis_title="θ値",
            template=PLOTLY_TEMPLATE, font_family="Noto Sans JP",
        )
        st.plotly_chart(fig_box, use_container_width=True)

    # ── 基本統計テーブル
    st.markdown("##### 基本統計量")
    disp_cols = {
        "group": "グループ", "n": "人数",
        "mean_theta": "平均θ", "sd_theta": "SD",
        "median_theta": "中央値", "q25": "Q1",
        "q75": "Q3", "min_theta": "最小", "max_theta": "最大"
    }
    show_df = sum_df.rename(columns=disp_cols)[[c for c in disp_cols.values() if c in show_df.columns or c in sum_df.rename(columns=disp_cols).columns]]
    st.dataframe(show_df, hide_index=True, use_container_width=True)


def plot_domain(result: dict, group_by: str, chart_type: str = "bar"):
    if "error" in result:
        return err(result["error"])

    df = pd.DataFrame(result["domain_scores"])
    if group_by == "class":
        df["group"] = df["school"].astype(str) + "-" + df["class_id"].astype(str)
    else:
        df["group"] = df["school"].astype(str)

    domain_col = result.get("domain_level", "大領域")
    groups = sorted(df["group"].unique())
    cmap   = color_map(groups)

    col1, col2 = st.columns([3, 2])
    with col1:
        fig = px.bar(
            df, x=domain_col, y="avg_correct_rate",
            color="group", barmode="group",
            color_discrete_map=cmap,
            labels={domain_col: "領域", "avg_correct_rate": "正答率(%)", "group": "グループ"},
            title=f"{domain_col}別 正答率比較",
            template=PLOTLY_TEMPLATE,
        )
        fig.update_layout(font_family="Noto Sans JP",
                          legend=dict(orientation="h", y=-0.25))
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        # レーダーチャート（グループ別）
        domains = sorted(df[domain_col].unique())
        fig_r = go.Figure()
        for g in groups:
            sub = df[df["group"] == g].sort_values(domain_col)
            r     = sub["avg_correct_rate"].tolist()
            theta = sub[domain_col].astype(str).tolist()
            r += r[:1]; theta += theta[:1]
            fig_r.add_trace(go.Scatterpolar(
                r=r, theta=theta, fill="toself",
                name=g, line_color=cmap[g], opacity=0.8,
            ))
        fig_r.update_layout(
            polar=dict(radialaxis=dict(visible=True, range=[0, 100])),
            title="レーダーチャート",
            template=PLOTLY_TEMPLATE, font_family="Noto Sans JP",
        )
        st.plotly_chart(fig_r, use_container_width=True)

    st.dataframe(df, hide_index=True, use_container_width=True)


def plot_attribute(result: dict, key: str, x_col: str,
                   title: str, group_by: str, label_col: str = None):
    if "error" in result:
        return err(result["error"])

    df = pd.DataFrame(result[key])
    if group_by == "class":
        df["group"] = df["school"].astype(str) + "-" + df["class_id"].astype(str)
    else:
        df["group"] = df["school"].astype(str)

    x = label_col if (label_col and label_col in df.columns) else x_col
    cmap = color_map(sorted(df["group"].unique()))

    fig = px.bar(
        df, x=x, y="avg_correct_rate", color="group",
        barmode="group", color_discrete_map=cmap,
        labels={x: "", "avg_correct_rate": "正答率(%)", "group": "グループ"},
        title=title, template=PLOTLY_TEMPLATE,
        text="avg_correct_rate",
    )
    fig.update_traces(texttemplate="%{text:.1f}%", textposition="outside")
    fig.update_layout(font_family="Noto Sans JP", yaxis_range=[0, 110],
                      legend=dict(orientation="h", y=-0.25))
    st.plotly_chart(fig, use_container_width=True)
    st.dataframe(df, hide_index=True, use_container_width=True)


def plot_item_analysis(result: dict):
    if "error" in result:
        return err(result["error"])

    df = pd.DataFrame(result["item_scores"])

    # 全国値との差分
    fig1 = go.Figure()
    fig1.add_trace(go.Bar(
        x=df["question_id"], y=df["correct_rate"],
        name="自校正答率", marker_color="#38bdf8", opacity=0.8,
    ))
    fig1.add_trace(go.Scatter(
        x=df["question_id"], y=df["全国値"],
        mode="markers", name="全国値",
        marker=dict(color="#fb923c", size=7, symbol="diamond"),
    ))
    fig1.update_layout(
        title="小問別 正答率 vs 全国値",
        xaxis_title="問題ID", yaxis_title="正答率(%)",
        template=PLOTLY_TEMPLATE, font_family="Noto Sans JP",
        legend=dict(orientation="h", y=-0.25),
    )
    st.plotly_chart(fig1, use_container_width=True)

    # 差分（全国値との乖離）
    df_sorted = df.sort_values("diff_from_national")
    fig2 = px.bar(
        df_sorted, x="question_id", y="diff_from_national",
        color="diff_from_national",
        color_continuous_scale=["#ef4444", "#f97316", "#94a3b8", "#34d399", "#38bdf8"],
        color_continuous_midpoint=0,
        labels={"diff_from_national": "全国値との差(pp)", "question_id": "問題ID"},
        title="全国値との乖離（プラス=上回り）",
        template=PLOTLY_TEMPLATE,
    )
    fig2.update_layout(font_family="Noto Sans JP")
    st.plotly_chart(fig2, use_container_width=True)

    # 困難度マップ（散布図）
    fig3 = px.scatter(
        df, x="困難度", y="correct_rate",
        color="大領域", size_max=12,
        hover_data=["question_id", "全国値", "解答形式"],
        labels={"困難度": "困難度(b)", "correct_rate": "正答率(%)"},
        title="困難度 × 正答率 マップ",
        template=PLOTLY_TEMPLATE,
        color_discrete_sequence=PALETTE,
    )
    fig3.update_layout(font_family="Noto Sans JP")
    st.plotly_chart(fig3, use_container_width=True)

    st.dataframe(df, hide_index=True, use_container_width=True)


def plot_attitude(result: dict, group_by: str):
    if "error" in result:
        return err(result["error"])

    df = pd.DataFrame(result["attitude_dist"])
    if group_by == "class":
        df["group"] = df["school"].astype(str) + "-" + df["class_id"].astype(str)
    else:
        df["group"] = df["school"].astype(str)

    score_labels = {0: "0:まったくない", 1: "1:あまりない",
                    2: "2:ときどきある", 3: "3:よくある", 4: "4:いつもある"}
    df["score_label"] = df["score"].map(score_labels)

    groups = sorted(df["group"].unique())
    sel_group = st.selectbox("表示グループ", groups, key="att_group")
    sub = df[df["group"] == sel_group]

    questions = sorted(sub["question_id"].unique())
    sel_q = st.multiselect("表示する質問", questions,
                           default=questions[:6], key="att_q")
    sub = sub[sub["question_id"].isin(sel_q)]

    # 積み上げ棒グラフ
    pivot = sub.pivot_table(index="question_id", columns="score_label",
                            values="pct", aggfunc="sum").fillna(0)
    pivot = pivot.reindex(columns=[v for v in score_labels.values() if v in pivot.columns])

    fig = go.Figure()
    att_colors = ["#ef4444", "#fb923c", "#94a3b8", "#34d399", "#38bdf8"]
    for i, col in enumerate(pivot.columns):
        fig.add_trace(go.Bar(
            name=col, x=pivot.index, y=pivot[col],
            marker_color=att_colors[i % len(att_colors)],
            text=pivot[col].round(1), texttemplate="%{text}%",
            textposition="inside",
        ))
    fig.update_layout(
        barmode="stack", title="意識調査 項目別選択割合（%）",
        xaxis_title="質問ID", yaxis_title="%",
        template=PLOTLY_TEMPLATE, font_family="Noto Sans JP",
        legend=dict(orientation="h", y=-0.3),
    )
    st.plotly_chart(fig, use_container_width=True)

    # 全国値との比較（スコア平均で）
    nat_df = result.get("attitude_master")
    if nat_df:
        nat = pd.DataFrame(nat_df)
        avg_df = sub.groupby("question_id").apply(
            lambda x: (x["score"] * x["pct"] / 100).sum()
        ).reset_index(name="avg_score")
        avg_df = avg_df.merge(nat, on="question_id", how="left")
        avg_df["diff"] = (avg_df["avg_score"] - avg_df["全国値"] / 25).round(2)
        st.markdown("##### 全国値との比較（平均スコア換算）")
        st.dataframe(avg_df, hide_index=True, use_container_width=True)


def plot_attitude_x_theta(result: dict):
    if "error" in result:
        return err(result["error"])

    col1, col2 = st.columns(2)
    with col1:
        cross = pd.DataFrame(result["cross_summary"])
        fig = px.bar(
            cross, x="question_id", y="avg_score", color="level_label",
            barmode="group",
            color_discrete_map={"低位": "#ef4444", "中位": "#fb923c", "高位": "#38bdf8"},
            labels={"level_label": "学力層", "avg_score": "平均態度スコア", "question_id": "質問"},
            title="学力層別 意識調査スコア",
            template=PLOTLY_TEMPLATE,
        )
        fig.update_layout(font_family="Noto Sans JP",
                          legend=dict(orientation="h", y=-0.3))
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        scatter = pd.DataFrame(result["scatter"])
        fig2 = px.scatter(
            scatter, x="theta", y="avg_attitude",
            color="school" if "school" in scatter.columns else None,
            color_discrete_sequence=PALETTE,
            labels={"theta": "θ値（学力）", "avg_attitude": "平均態度スコア"},
            title="θ × 意識スコア 散布図",
            template=PLOTLY_TEMPLATE,
            trendline="ols",
        )
        fig2.update_layout(font_family="Noto Sans JP")
        st.plotly_chart(fig2, use_container_width=True)

    st.dataframe(cross, hide_index=True, use_container_width=True)


def plot_individual(result: dict, student_id: str):
    if "error" in result:
        return err(result["error"])

    # ── メトリクス
    theta = result.get("theta", 0)
    cr    = result.get("correct_rate", 0)
    rank  = result.get("rank_in_group", "-")
    total = result.get("n_total", "-")

    c1, c2, c3, c4 = st.columns(4)
    for col, val, lbl, sub in [
        (c1, f"{theta:+.3f}", "θ値（IRT）", "能力推定値"),
        (c2, f"{cr:.1f}%",   "正答率",     ""),
        (c3, str(rank),      "順位",        f"全{total}名中"),
        (c4, student_id,     "生徒ID",      ""),
    ]:
        col.markdown(f"""
        <div class="metric-card">
            <div class="val">{val}</div>
            <div class="lbl">{lbl}</div>
            <div class="sub">{sub}</div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("---")

    # ── プロファイルチャート
    tab_names = ["大領域", "中領域", "観点", "資質能力", "解答形式"]
    tabs = st.tabs(tab_names)

    profile_configs = [
        ("domain_大領域",  "大領域",  "大領域",  "大領域別プロファイル",  True),
        ("domain_中領域",  "中領域",  "中領域",  "中領域別プロファイル",  False),
        ("domain_観点",    "観点",    "観点名",   "観点別プロファイル",   False),
        ("domain_資質能力","資質能力","資質能力", "資質能力別プロファイル",False),
        ("domain_解答形式","解答形式","形式名",   "解答形式別プロファイル",False),
    ]

    for tab, (key, x_col, label_col, title, use_radar) in zip(tabs, profile_configs):
        with tab:
            if key not in result or not result[key]:
                st.info("データなし")
                continue
            df = pd.DataFrame(result[key])
            lbl = label_col if label_col in df.columns else x_col

            if use_radar and len(df) >= 3:
                col_l, col_r = st.columns(2)
                with col_l:
                    r     = df["rate"].tolist()
                    theta = df[lbl].astype(str).tolist()
                    r += r[:1]; theta += theta[:1]
                    fig = go.Figure(go.Scatterpolar(
                        r=r, theta=theta, fill="toself",
                        line_color="#38bdf8", fillcolor="rgba(56,189,248,0.15)",
                    ))
                    fig.update_layout(
                        polar=dict(radialaxis=dict(range=[0, 100])),
                        title=title, template=PLOTLY_TEMPLATE,
                        font_family="Noto Sans JP",
                    )
                    st.plotly_chart(fig, use_container_width=True)
                with col_r:
                    fig2 = px.bar(df, x=lbl, y="rate",
                                  color="rate",
                                  color_continuous_scale=["#ef4444","#fb923c","#38bdf8"],
                                  range_color=[0, 100],
                                  labels={lbl: "", "rate": "正答率(%)"},
                                  template=PLOTLY_TEMPLATE)
                    fig2.update_layout(font_family="Noto Sans JP")
                    st.plotly_chart(fig2, use_container_width=True)
            else:
                fig = px.bar(
                    df, x=lbl, y="rate",
                    color="rate",
                    color_continuous_scale=["#ef4444","#fb923c","#38bdf8"],
                    range_color=[0, 100],
                    labels={lbl: "", "rate": "正答率(%)"},
                    title=title, template=PLOTLY_TEMPLATE,
                    text="rate",
                )
                fig.update_traces(texttemplate="%{text:.1f}%", textposition="outside")
                fig.update_layout(font_family="Noto Sans JP", yaxis_range=[0, 115])
                st.plotly_chart(fig, use_container_width=True)

            st.dataframe(df, hide_index=True, use_container_width=True)


# ════════════════════════════════════════════════════════
# Claude AI解釈
# ════════════════════════════════════════════════════════
def ask_claude(prompt: str, context: str) -> str:
    client = anthropic.Anthropic(api_key=st.secrets["ANTHROPIC_API_KEY"])
    msg = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=1500,
        system="""あなたは小中学校の学力テストデータ分析の専門家です。
教師・指導主事・管理職が実際に活用できる、具体的で実践的なアドバイスを提供してください。
【回答形式】
- 📊 分析結果の読み取り（何が起きているか）
- 💡 解釈（なぜそうなっているか・仮説）
- 🎯 ネクストアクション（授業・指導での具体的な改善策を3点）
数値の羅列より、現場が動ける提案を優先してください。日本語で回答してください。""",
        messages=[{"role": "user",
                   "content": f"【分析データ】\n{context}\n\n【質問】\n{prompt}"}]
    )
    return msg.content[0].text


# ════════════════════════════════════════════════════════
# ヘッダー
# ════════════════════════════════════════════════════════
st.markdown("""
<div class="v4-header">
  <h1>🎓 学力分析ダッシュボード v4</h1>
  <p>IRT θ推定 × ドリルダウン分析 × AI解釈サポート</p>
</div>
""", unsafe_allow_html=True)

# ════════════════════════════════════════════════════════
# サイドバー: グローバルフィルタ
# ════════════════════════════════════════════════════════
with st.sidebar:
    st.markdown("## 🔍 絞り込み")

    try:
        schools  = get_schools()
        subjects = get_subjects()
        db_ok = True
    except Exception as e:
        st.error(f"DB接続エラー: {e}")
        st.stop()

    sel_subject = st.selectbox("📚 教科", subjects)
    st.divider()

    st.markdown("#### 比較単位")
    group_by = st.radio("", ["school", "class"], format_func=lambda x: "学校比較" if x == "school" else "クラス比較")

    sel_school = None
    if group_by == "class":
        sel_school = st.selectbox("学校", schools)

    st.divider()
    st.caption("個人票タブでは別途生徒を選択します")

# ════════════════════════════════════════════════════════
# メインタブ
# ════════════════════════════════════════════════════════
TAB_NAMES = ["📊 集団分析", "🔬 小問分析", "💭 意識調査", "🔗 学力×意識", "👤 個人票", "🤖 AI解釈"]
tabs = st.tabs(TAB_NAMES)

# ── セッションステート
if "analysis_results" not in st.session_state:
    st.session_state.analysis_results = {}

# ════════════════════════════════════════════════════
# TAB 1: 集団分析
# ════════════════════════════════════════════════════
with tabs[0]:
    st.markdown("#### 📊 集団分析")
    st.caption(f"教科: {sel_subject} ／ 比較単位: {'学校' if group_by == 'school' else f'{sel_school} 各クラス'}")

    if st.button("▶ 分析実行", key="run_group", type="primary"):
        with st.spinner("データ取得中..."):
            tr = get_test_results(
                school=sel_school if group_by == "class" else None,
                subject=sel_subject
            )
            qm = get_question_master()
            qm_sub = qm[qm["subject"] == sel_subject].copy()

        if tr.empty:
            st.warning("データが見つかりません")
        else:
            sub_tabs = st.tabs(["θ分布", "大領域", "中領域", "観点", "資質能力", "解答形式"])

            with sub_tabs[0]:
                with st.spinner("θ推定中（WLE）..."):
                    r = run_r("irt_theta", tr, qm_sub, {"group_by": group_by})
                st.session_state.analysis_results["θ分布"] = r
                plot_theta_distribution(r, group_by)

            with sub_tabs[1]:
                with st.spinner("大領域別集計中..."):
                    r = run_r("domain_analysis", tr, qm_sub,
                              {"group_by": group_by, "domain_level": "large"})
                st.session_state.analysis_results["大領域"] = r
                plot_domain(r, group_by)

            with sub_tabs[2]:
                with st.spinner("中領域別集計中..."):
                    r = run_r("domain_analysis", tr, qm_sub,
                              {"group_by": group_by, "domain_level": "mid"})
                st.session_state.analysis_results["中領域"] = r
                plot_domain(r, group_by)

            with sub_tabs[3]:
                with st.spinner("観点別集計中..."):
                    r = run_r("viewpoint_analysis", tr, qm_sub, {"group_by": group_by})
                st.session_state.analysis_results["観点"] = r
                plot_attribute(r, "viewpoint_scores", "観点", "観点別 正答率", group_by, "観点名")

            with sub_tabs[4]:
                with st.spinner("資質能力別集計中..."):
                    r = run_r("competency_analysis", tr, qm_sub, {"group_by": group_by})
                st.session_state.analysis_results["資質能力"] = r
                plot_attribute(r, "competency_scores", "資質能力", "資質能力別 正答率", group_by)

            with sub_tabs[5]:
                with st.spinner("解答形式別集計中..."):
                    r = run_r("format_analysis", tr, qm_sub, {"group_by": group_by})
                st.session_state.analysis_results["解答形式"] = r
                plot_attribute(r, "format_scores", "解答形式", "解答形式別 正答率", group_by, "形式名")

# ════════════════════════════════════════════════════
# TAB 2: 小問分析
# ════════════════════════════════════════════════════
with tabs[1]:
    st.markdown("#### 🔬 小問分析")

    col1, col2 = st.columns(2)
    with col1:
        item_school = st.selectbox("学校", ["全体"] + schools, key="item_school")
    with col2:
        classes = get_classes(item_school if item_school != "全体" else None)
        item_class  = st.selectbox("クラス", ["全体"] + [str(c) for c in classes], key="item_class")

    if st.button("▶ 小問分析実行", key="run_item", type="primary"):
        with st.spinner("データ取得中..."):
            tr = get_test_results(
                school=None if item_school == "全体" else item_school,
                class_id=None if item_class == "全体" else int(item_class),
                subject=sel_subject,
            )
            qm = get_question_master()
            qm_sub = qm[qm["subject"] == sel_subject]

        if tr.empty:
            st.warning("データが見つかりません")
        else:
            with st.spinner("小問分析中..."):
                r = run_r("item_analysis", tr, qm_sub)
            st.session_state.analysis_results["小問分析"] = r
            plot_item_analysis(r)

# ════════════════════════════════════════════════════
# TAB 3: 意識調査
# ════════════════════════════════════════════════════
with tabs[2]:
    st.markdown("#### 💭 意識調査")

    col1, col2 = st.columns(2)
    with col1:
        att_school = st.selectbox("学校", ["全体"] + schools, key="att_school")
    with col2:
        att_classes = get_classes(att_school if att_school != "全体" else None)
        att_class   = st.selectbox("クラス", ["全体"] + [str(c) for c in att_classes], key="att_class")

    if st.button("▶ 意識調査分析実行", key="run_att", type="primary"):
        with st.spinner("データ取得中..."):
            ar = get_attitude_results(
                school=None if att_school == "全体" else att_school,
                class_id=None if att_class == "全体" else int(att_class),
                subject=sel_subject,
            )
            am = get_attitude_master()
            am_sub = am[am["subject"] == sel_subject]

        if ar.empty:
            st.warning("データが見つかりません")
        else:
            att_group = "class" if att_class != "全体" else ("class" if att_school != "全体" else "school")
            with st.spinner("意識調査集計中..."):
                r = run_r("attitude_analysis", ar, extra={
                    "group_by": att_group,
                    "attitude_master": am_sub.to_dict(orient="records"),
                })
            st.session_state.analysis_results["意識調査"] = r
            plot_attitude(r, att_group)

# ════════════════════════════════════════════════════
# TAB 4: 学力×意識
# ════════════════════════════════════════════════════
with tabs[3]:
    st.markdown("#### 🔗 学力 × 意識 クロス分析")

    col1, col2 = st.columns(2)
    with col1:
        cx_school = st.selectbox("学校", ["全体"] + schools, key="cx_school")
    with col2:
        cx_classes = get_classes(cx_school if cx_school != "全体" else None)
        cx_class   = st.selectbox("クラス", ["全体"] + [str(c) for c in cx_classes], key="cx_class")

    if st.button("▶ クロス分析実行", key="run_cross", type="primary"):
        with st.spinner("データ取得中..."):
            tr = get_test_results(
                school=None if cx_school == "全体" else cx_school,
                class_id=None if cx_class == "全体" else int(cx_class),
                subject=sel_subject,
            )
            ar = get_attitude_results(
                school=None if cx_school == "全体" else cx_school,
                class_id=None if cx_class == "全体" else int(cx_class),
                subject=sel_subject,
            )
            qm = get_question_master()
            qm_sub = qm[qm["subject"] == sel_subject]

        if tr.empty or ar.empty:
            st.warning("学力または意識調査データが見つかりません")
        else:
            with st.spinner("クロス分析中（θ推定含む）..."):
                r = run_r("attitude_x_theta", ar, qm_sub,
                          {"test_data": tr.to_dict(orient="records")})
            st.session_state.analysis_results["学力×意識"] = r
            plot_attitude_x_theta(r)

# ════════════════════════════════════════════════════
# TAB 5: 個人票
# ════════════════════════════════════════════════════
with tabs[4]:
    st.markdown("#### 👤 個人票")

    col1, col2, col3 = st.columns(3)
    with col1:
        ind_school = st.selectbox("学校", schools, key="ind_school")
    with col2:
        ind_classes = get_classes(ind_school)
        ind_class   = st.selectbox("クラス", ind_classes, key="ind_class")
    with col3:
        ind_subject = st.selectbox("教科", subjects, key="ind_subject")

    students_df = get_students(ind_school, ind_class)
    if students_df.empty:
        st.warning("生徒データが見つかりません")
    else:
        student_options = {
            row["student_id"]: f"No.{row['student_no']} ({row['student_id']})"
            for _, row in students_df.iterrows()
        }
        sel_student = st.selectbox("生徒", list(student_options.keys()),
                                   format_func=lambda x: student_options[x])

        if st.button("▶ 個人票表示", key="run_ind", type="primary"):
            with st.spinner("データ取得中..."):
                # 同クラス全員のデータ（θ順位算出用）
                tr_all = get_test_results(school=ind_school, class_id=ind_class,
                                          subject=ind_subject)
                qm = get_question_master()
                qm_sub = qm[qm["subject"] == ind_subject]

            if tr_all.empty:
                st.warning("データが見つかりません")
            else:
                with st.spinner("個人プロファイル生成中..."):
                    r = run_r("individual_profile", tr_all, qm_sub,
                              {"student_id": sel_student})
                plot_individual(r, sel_student)

                # 意識調査も表示
                ar_ind = get_attitude_results(school=ind_school, class_id=ind_class,
                                              subject=ind_subject)
                if not ar_ind.empty:
                    ar_ind_s = ar_ind[ar_ind["student_id"] == sel_student]
                    if not ar_ind_s.empty:
                        st.markdown("##### 💭 意識調査スコア（個人）")
                        fig_att = px.bar(
                            ar_ind_s, x="question_id", y="score",
                            color="score",
                            color_continuous_scale=["#ef4444","#fb923c","#94a3b8","#34d399","#38bdf8"],
                            range_color=[0, 4],
                            labels={"question_id": "質問ID", "score": "スコア"},
                            title="意識調査 個人スコア（0〜4）",
                            template=PLOTLY_TEMPLATE,
                        )
                        fig_att.update_layout(font_family="Noto Sans JP")
                        st.plotly_chart(fig_att, use_container_width=True)

# ════════════════════════════════════════════════════
# TAB 6: AI解釈
# ════════════════════════════════════════════════════
with tabs[5]:
    st.markdown("#### 🤖 Claude AI 解釈・提案")

    if not st.session_state.analysis_results:
        st.info("他のタブで分析を実行すると、AIが結果を解釈できます。")
    else:
        available = list(st.session_state.analysis_results.keys())
        sel_targets = st.multiselect("解釈対象の分析結果", available, default=available[:2])

        context_parts = []
        for k in sel_targets:
            r = st.session_state.analysis_results[k]
            if "error" not in r:
                context_parts.append(f"【{k}】\n" + json.dumps(r, ensure_ascii=False)[:1500])
        context_str = "\n\n".join(context_parts)

        preset_q = [
            "この結果から、最も支援が必要なグループはどこですか？具体的な根拠とともに教えてください。",
            "正答率の低い領域・観点について、授業改善の具体的な方策を提案してください。",
            "学力と意識調査の関係から、どのような指導上の示唆が得られますか？",
            "管理職・指導主事向けの報告用に、結果を簡潔にまとめてください。",
            "保護者向けに分かりやすく結果を説明する文章を作成してください。",
            "次の単元設計に活かすべきポイントを教えてください。",
        ]

        sel_preset = st.selectbox("よくある質問", ["（カスタム入力）"] + preset_q)
        user_q = st.text_area(
            "AIへの質問",
            value="" if sel_preset == "（カスタム入力）" else sel_preset,
            height=90,
        )

        if st.button("🤖 AIに質問する", type="primary"):
            if user_q.strip() and context_str:
                with st.spinner("Claude が分析中..."):
                    answer = ask_claude(user_q, context_str)
                    st.session_state["ai_answer"] = answer
            elif not context_str:
                st.warning("解釈対象の分析結果を選択してください。")
            else:
                st.warning("質問を入力してください。")

        if st.session_state.get("ai_answer"):
            st.markdown(f'<div class="ai-box">{st.session_state["ai_answer"]}</div>',
                        unsafe_allow_html=True)

# ════════════════════════════════════════════════════
# フッター
# ════════════════════════════════════════════════════
st.divider()
st.caption("学力分析ダッシュボード v4 ｜ Streamlit + R (WLE-IRT) + Claude API + Supabase PostgreSQL")
