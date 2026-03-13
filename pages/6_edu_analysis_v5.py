"""
教育データ分析ツール v5
- サイドバー廃止 → メイン画面上部の共通フィルター（学校→クラス→教科 連動）
- 集団分析タブ廃止 → θ分布・大領域・中領域・小問分析・観点・資質能力・解答形式をフラット化
- タブ順: θ分布|大領域|中領域|小問分析|観点|資質能力|解答形式|意識調査|学力×意識|個人票|AI解釈
- 比較単位は絞り込み状態から自動推定:
    全体/全体     → 全校を学校単位で比較
    学校/全体     → その学校のクラス単位で比較
    学校/クラス   → 単一クラスの集計（比較なし）
- 個人票のみ追加で生徒セレクタを表示
"""

import streamlit as st
import pandas as pd
import psycopg2
import json
import subprocess
import tempfile
import os
import math
import anthropic
import plotly.express as px
import plotly.graph_objects as go

# ════════════════════════════════════════════════════════
# ページ設定
# ════════════════════════════════════════════════════════
st.set_page_config(
    page_title="学力分析ダッシュボード v5",
    page_icon="🎓",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Noto+Sans+JP:wght@300;400;500;700&family=DM+Mono:wght@400;500&display=swap');

html, body, [class*="css"] { font-family: 'Noto Sans JP', sans-serif; }

.v5-header {
    background: linear-gradient(135deg, #0a0f1e 0%, #0d2137 50%, #0a1628 100%);
    border: 1px solid rgba(56,189,248,0.2);
    border-radius: 16px;
    padding: 1.6rem 2.2rem;
    margin-bottom: 1.2rem;
    position: relative; overflow: hidden;
}
.v5-header::before {
    content: '';
    position: absolute; top: -50%; left: -50%;
    width: 200%; height: 200%;
    background: radial-gradient(ellipse at 30% 50%, rgba(56,189,248,0.06) 0%, transparent 60%),
                radial-gradient(ellipse at 70% 50%, rgba(99,102,241,0.06) 0%, transparent 60%);
}
.v5-header h1 { font-size: 1.6rem; font-weight: 700; color: #f0f9ff; margin: 0; letter-spacing: -0.02em; }
.v5-header p  { color: #7dd3fc; margin: 0.3rem 0 0; font-size: 0.82rem; font-weight: 300; }

/* 共通フィルターエリア */
.filter-bar {
    background: linear-gradient(135deg, #0f172a, #1e293b);
    border: 1px solid rgba(56,189,248,0.15);
    border-radius: 12px;
    padding: 1rem 1.4rem 0.8rem;
    margin-bottom: 1.2rem;
}
.filter-label {
    font-size: 0.7rem; color: #64748b;
    letter-spacing: 0.08em; text-transform: uppercase;
    margin-bottom: 0.2rem;
}
/* 比較単位バッジ */
.badge {
    display: inline-block;
    background: rgba(56,189,248,0.12);
    border: 1px solid rgba(56,189,248,0.3);
    color: #38bdf8;
    border-radius: 20px;
    padding: 0.15rem 0.7rem;
    font-size: 0.75rem;
    font-weight: 500;
    margin-left: 0.5rem;
}

/* メトリクスカード */
.metric-card {
    background: linear-gradient(135deg, #0f172a, #1e293b);
    border: 1px solid rgba(56,189,248,0.15);
    border-radius: 12px;
    padding: 1.2rem 1.4rem;
    text-align: center;
}
.metric-card .val { font-size: 2rem; font-weight: 700; color: #38bdf8; font-family: 'DM Mono', monospace; line-height: 1; }
.metric-card .lbl { font-size: 0.75rem; color: #94a3b8; margin-top: 0.3rem; letter-spacing: 0.05em; }
.metric-card .sub { font-size: 0.8rem; color: #64748b; margin-top: 0.1rem; }

/* AI 回答ボックス */
.ai-box {
    background: linear-gradient(135deg, #0d1b2e, #0f2037);
    border: 1px solid rgba(99,102,241,0.3);
    border-left: 3px solid #6366f1;
    border-radius: 8px;
    padding: 1.4rem 1.6rem;
    color: #e2e8f0; font-size: 0.92rem; line-height: 1.75;
}

.stTabs [data-baseweb="tab"] { font-size: 0.82rem; padding: 0.4rem 0.8rem; }
</style>
""", unsafe_allow_html=True)

# ════════════════════════════════════════════════════════
# Rパッケージ
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
# マスタ取得（連動セレクタ用）
# ════════════════════════════════════════════════════════
@st.cache_data(ttl=600)
def get_all_schools():
    return qdf("SELECT DISTINCT school FROM test_results ORDER BY school")["school"].tolist()

@st.cache_data(ttl=600)
def get_classes_for(school: str | None):
    """学校を指定するとその学校のクラス一覧、Noneなら全クラス"""
    if school:
        return qdf(
            "SELECT DISTINCT class_id FROM test_results WHERE school=%s ORDER BY class_id",
            (school,)
        )["class_id"].tolist()
    return qdf("SELECT DISTINCT class_id FROM test_results ORDER BY class_id")["class_id"].tolist()

@st.cache_data(ttl=600)
def get_subjects_for(school: str | None, class_id: int | None):
    """学校・クラスを指定するとその組み合わせで存在する教科一覧"""
    cond, params = [], []
    if school:    cond.append("school=%s");    params.append(school)
    if class_id:  cond.append("class_id=%s");  params.append(int(class_id))
    where = ("WHERE " + " AND ".join(cond)) if cond else ""
    return qdf(
        f"SELECT DISTINCT subject FROM test_results {where} ORDER BY subject",
        params or None
    )["subject"].tolist()

@st.cache_data(ttl=600)
def get_students_for(school: str, class_id: int, subject: str):
    return qdf(
        "SELECT DISTINCT student_id, student_no FROM test_results "
        "WHERE school=%s AND class_id=%s AND subject=%s ORDER BY student_no",
        (school, int(class_id), subject)
    )

@st.cache_data(ttl=600)
def get_question_master():
    return qdf("""
        SELECT question_id, subject, "大領域", "中領域", "観点",
               "知識理解", "資質能力", "全国値", "困難度", "解答形式"
        FROM question_master ORDER BY question_id
    """)

@st.cache_data(ttl=600)
def get_attitude_master():
    return qdf('SELECT question_id, subject, "全国値" FROM attitude_master ORDER BY question_id')

# ════════════════════════════════════════════════════════
# データ取得
# ════════════════════════════════════════════════════════
@st.cache_data(ttl=300)
def get_test_results(school=None, class_id=None, subject=None):
    cond, params = [], []
    if school:   cond.append("school=%s");   params.append(school)
    if class_id: cond.append("class_id=%s"); params.append(int(class_id))
    if subject:  cond.append("subject=%s");  params.append(subject)
    where = ("WHERE " + " AND ".join(cond)) if cond else ""
    return qdf(
        f"SELECT student_id, school, class_id, student_no, subject, question_id, correct "
        f"FROM test_results {where} ORDER BY student_id, question_id",
        params or None
    )

@st.cache_data(ttl=300)
def get_attitude_results(school=None, class_id=None, subject=None):
    cond, params = [], []
    if school:   cond.append("school=%s");   params.append(school)
    if class_id: cond.append("class_id=%s"); params.append(int(class_id))
    if subject:  cond.append("subject=%s");  params.append(subject)
    where = ("WHERE " + " AND ".join(cond)) if cond else ""
    return qdf(
        f"SELECT student_id, school, class_id, student_no, subject, question_id, score "
        f"FROM attitude_results {where} ORDER BY student_id, question_id",
        params or None
    )

# ════════════════════════════════════════════════════════
# 比較単位の自動推定
# ════════════════════════════════════════════════════════
def resolve_group_by(sel_school, sel_class) -> str:
    """
    全体/全体   → "school"（全校を学校単位で比較）
    学校/全体   → "class"（その学校のクラス単位で比較）
    学校/クラス → "class"（単一クラス集計）
    """
    if sel_school == "全体":
        return "school"
    return "class"

# ════════════════════════════════════════════════════════
# R実行
# ════════════════════════════════════════════════════════
R_SCRIPT = os.path.join(os.path.dirname(os.path.dirname(__file__)), "analyze_v4.R")

def run_r(analysis_type: str, data: pd.DataFrame,
          item_params: pd.DataFrame = None, extra: dict = None) -> dict:
    def sanitize(obj):
        if isinstance(obj, float) and math.isnan(obj): return None
        if isinstance(obj, dict):  return {k: sanitize(v) for k, v in obj.items()}
        if isinstance(obj, list):  return [sanitize(v) for v in obj]
        return obj

    payload = {"analysis_type": analysis_type, "data": data.to_dict(orient="records")}
    if item_params is not None:
        payload["item_params"] = item_params.to_dict(orient="records")
    if extra:
        payload.update(extra)

    with tempfile.NamedTemporaryFile(mode="w", suffix=".json",
                                     delete=False, encoding="utf-8") as f:
        json.dump(sanitize(payload), f, ensure_ascii=False)
        tmp = f.name
    try:
        res = subprocess.run(["Rscript", R_SCRIPT, tmp], capture_output=True, timeout=120)
        stdout = res.stdout.decode("utf-8", errors="replace")
        stderr = res.stderr.decode("utf-8", errors="replace")
        if res.returncode != 0:
            return {"error": stderr[-500:]}
        return json.loads(stdout)
    except subprocess.TimeoutExpired:
        return {"error": "R分析がタイムアウトしました（120秒）"}
    except json.JSONDecodeError:
        return {"error": f"Rの出力をパースできません: {stdout[:300]}"}
    finally:
        if os.path.exists(tmp): os.unlink(tmp)

# ════════════════════════════════════════════════════════
# グラフ定数・ユーティリティ
# ════════════════════════════════════════════════════════
PALETTE = ["#38bdf8","#818cf8","#34d399","#fb923c","#f472b6","#a78bfa","#facc15","#2dd4bf"]
PLOTLY_TEMPLATE = "plotly_dark"

def color_map(keys):
    return {k: PALETTE[i % len(PALETTE)] for i, k in enumerate(keys)}

def err(msg):
    st.error(f"⚠️ {msg}")

# ════════════════════════════════════════════════════════
# グラフ描画（v4から踏襲）
# ════════════════════════════════════════════════════════
def plot_theta_distribution(result, group_by):
    if "error" in result: return err(result["error"])
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

    col1, col2 = st.columns(2)
    with col1:
        fig = go.Figure()
        for g in groups:
            sub = ind_df[ind_df["group"] == g]["theta"].dropna()
            fig.add_trace(go.Histogram(x=sub, name=g, opacity=1.0,
                                       marker_color=cmap[g], nbinsx=20))
        fig.update_layout(title="θ分布（ヒストグラム）", barmode="group",
                          xaxis_title="θ値", yaxis_title="人数",
                          template=PLOTLY_TEMPLATE, font_family="Noto Sans JP",
                          legend=dict(orientation="h", y=-0.2))
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        fig = go.Figure()
        for g in groups:
            sub = ind_df[ind_df["group"] == g]["theta"].dropna()
            fig.add_trace(go.Box(y=sub, name=g, marker_color=cmap[g],
                                 boxmean="sd", jitter=0.3, pointpos=-1.5,
                                 marker=dict(size=4, opacity=0.5)))
        fig.update_layout(title="θ分布（箱ひげ図）", yaxis_title="θ値",
                          template=PLOTLY_TEMPLATE, font_family="Noto Sans JP")
        st.plotly_chart(fig, use_container_width=True)

    disp_cols = {"group":"グループ","n":"人数","mean_theta":"平均θ","sd_theta":"SD",
                 "median_theta":"中央値","q25":"Q1","q75":"Q3","min_theta":"最小","max_theta":"最大"}
    renamed = sum_df.rename(columns=disp_cols)
    st.dataframe(renamed[[c for c in disp_cols.values() if c in renamed.columns]],
                 hide_index=True, use_container_width=True)


def plot_domain(result, group_by):
    if "error" in result: return err(result["error"])
    df = pd.DataFrame(result["domain_scores"])
    if group_by == "class":
        df["group"] = df["school"].astype(str) + "-" + df["class_id"].astype(str)
    else:
        df["group"] = df["school"].astype(str)

    groups = sorted(df["group"].unique())
    cmap   = color_map(groups)

    col1, col2 = st.columns([3, 2])
    with col1:
        fig = px.bar(df, x="domain", y="avg_correct_rate", color="group",
                     barmode="group", color_discrete_map=cmap,
                     labels={"domain":"領域","avg_correct_rate":"正答率(%)","group":"グループ"},
                     title=f"{result.get('domain_col','領域')}別 正答率比較",
                     template=PLOTLY_TEMPLATE)
        fig.update_layout(font_family="Noto Sans JP", legend=dict(orientation="h", y=-0.25))
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        fig_r = go.Figure()
        for g in groups:
            sub = df[df["group"] == g].sort_values("domain")
            r = sub["avg_correct_rate"].tolist(); t = sub["domain"].astype(str).tolist()
            r += r[:1]; t += t[:1]
            fig_r.add_trace(go.Scatterpolar(r=r, theta=t, fill="toself",
                                            name=g, line_color=cmap[g], opacity=0.8))
        fig_r.update_layout(polar=dict(radialaxis=dict(visible=True, range=[0,100])),
                            title="レーダーチャート", template=PLOTLY_TEMPLATE,
                            font_family="Noto Sans JP")
        st.plotly_chart(fig_r, use_container_width=True)

    st.dataframe(df, hide_index=True, use_container_width=True)


def plot_attribute(result, key, x_col, title, group_by, label_col=None):
    if "error" in result: return err(result["error"])
    df = pd.DataFrame(result[key])
    if group_by == "class":
        df["group"] = df["school"].astype(str) + "-" + df["class_id"].astype(str)
    else:
        df["group"] = df["school"].astype(str)

    x    = label_col if (label_col and label_col in df.columns) else x_col
    cmap = color_map(sorted(df["group"].unique()))
    fig  = px.bar(df, x=x, y="avg_correct_rate", color="group",
                  barmode="group", color_discrete_map=cmap, text="avg_correct_rate",
                  labels={x:"","avg_correct_rate":"正答率(%)","group":"グループ"},
                  title=title, template=PLOTLY_TEMPLATE)
    fig.update_traces(texttemplate="%{text:.1f}%", textposition="outside")
    fig.update_layout(font_family="Noto Sans JP", yaxis_range=[0,110],
                      legend=dict(orientation="h", y=-0.25))
    st.plotly_chart(fig, use_container_width=True)
    st.dataframe(df, hide_index=True, use_container_width=True)


def plot_item_analysis(result):
    if "error" in result: return err(result["error"])
    df = pd.DataFrame(result["item_scores"])

    fig1 = go.Figure()
    fig1.add_trace(go.Bar(x=df["question_id"], y=df["correct_rate"],
                          name="自校正答率", marker_color="#38bdf8", opacity=0.8))
    fig1.add_trace(go.Scatter(x=df["question_id"], y=df["全国値"],
                              mode="markers", name="全国値",
                              marker=dict(color="#fb923c", size=7, symbol="diamond")))
    fig1.update_layout(title="小問別 正答率 vs 全国値", xaxis_title="問題ID",
                       yaxis_title="正答率(%)", template=PLOTLY_TEMPLATE,
                       font_family="Noto Sans JP", legend=dict(orientation="h", y=-0.25))
    st.plotly_chart(fig1, use_container_width=True)

    df_sorted = df.sort_values("diff_from_national")
    fig2 = px.bar(df_sorted, x="question_id", y="diff_from_national",
                  color="diff_from_national",
                  color_continuous_scale=["#ef4444","#f97316","#94a3b8","#34d399","#38bdf8"],
                  color_continuous_midpoint=0,
                  labels={"diff_from_national":"全国値との差(pp)","question_id":"問題ID"},
                  title="全国値との乖離（プラス=上回り）", template=PLOTLY_TEMPLATE)
    fig2.update_layout(font_family="Noto Sans JP")
    st.plotly_chart(fig2, use_container_width=True)

    fig3 = px.scatter(df, x="困難度", y="correct_rate", color="大領域",
                      hover_data=["question_id","全国値","解答形式"],
                      labels={"困難度":"困難度(b)","correct_rate":"正答率(%)"},
                      title="困難度 × 正答率 マップ", template=PLOTLY_TEMPLATE,
                      color_discrete_sequence=PALETTE)
    fig3.update_layout(font_family="Noto Sans JP")
    st.plotly_chart(fig3, use_container_width=True)
    st.dataframe(df, hide_index=True, use_container_width=True)


def plot_attitude(result, group_by):
    if "error" in result: return err(result["error"])
    df = pd.DataFrame(result["attitude_dist"])
    if group_by == "class":
        df["group"] = df["school"].astype(str) + "-" + df["class_id"].astype(str)
    else:
        df["group"] = df["school"].astype(str)

    score_labels = {0:"0:まったくない",1:"1:あまりない",2:"2:ときどきある",3:"3:よくある",4:"4:いつもある"}
    df["score_label"] = df["score"].map(score_labels)

    groups    = sorted(df["group"].unique())
    sel_group = st.selectbox("表示グループ", groups, key="att_group")
    sub       = df[df["group"] == sel_group]

    questions = sorted(sub["question_id"].unique())
    sel_q     = st.multiselect("表示する質問", questions, default=questions[:6], key="att_q")
    sub       = sub[sub["question_id"].isin(sel_q)]

    pivot = sub.pivot_table(index="question_id", columns="score_label",
                            values="pct", aggfunc="sum").fillna(0)
    pivot = pivot.reindex(columns=[v for v in score_labels.values() if v in pivot.columns])

    fig = go.Figure()
    att_colors = ["#ef4444","#fb923c","#94a3b8","#34d399","#38bdf8"]
    for i, col in enumerate(pivot.columns):
        fig.add_trace(go.Bar(name=col, x=pivot.index, y=pivot[col],
                             marker_color=att_colors[i % len(att_colors)],
                             text=pivot[col].round(1), texttemplate="%{text}%",
                             textposition="inside"))
    fig.update_layout(barmode="stack", title="意識調査 項目別選択割合（%）",
                      xaxis_title="質問ID", yaxis_title="%",
                      template=PLOTLY_TEMPLATE, font_family="Noto Sans JP",
                      legend=dict(orientation="h", y=-0.3))
    st.plotly_chart(fig, use_container_width=True)

    nat_df = result.get("attitude_master")
    if nat_df:
        nat    = pd.DataFrame(nat_df)
        avg_df = sub.groupby("question_id").apply(
            lambda x: (x["score"] * x["pct"] / 100).sum()
        ).reset_index(name="avg_score")
        avg_df = avg_df.merge(nat, on="question_id", how="left")
        avg_df["diff"] = (avg_df["avg_score"] - avg_df["全国値"] / 25).round(2)
        st.markdown("##### 全国値との比較（平均スコア換算）")
        st.dataframe(avg_df, hide_index=True, use_container_width=True)


def plot_attitude_x_theta(result):
    if "error" in result: return err(result["error"])
    col1, col2 = st.columns(2)
    with col1:
        cross = pd.DataFrame(result["cross_summary"])
        fig   = px.bar(cross, x="question_id", y="avg_score", color="level_label",
                       barmode="group",
                       color_discrete_map={"低位":"#ef4444","中位":"#fb923c","高位":"#38bdf8"},
                       labels={"level_label":"学力層","avg_score":"平均態度スコア","question_id":"質問"},
                       title="学力層別 意識調査スコア", template=PLOTLY_TEMPLATE)
        fig.update_layout(font_family="Noto Sans JP", legend=dict(orientation="h", y=-0.3))
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        scatter = pd.DataFrame(result["scatter"])
        fig2    = px.scatter(scatter, x="theta", y="avg_attitude",
                             color="school" if "school" in scatter.columns else None,
                             color_discrete_sequence=PALETTE,
                             labels={"theta":"θ値（学力）","avg_attitude":"平均態度スコア"},
                             title="θ × 意識スコア 散布図", template=PLOTLY_TEMPLATE,
                             trendline="ols")
        fig2.update_layout(font_family="Noto Sans JP")
        st.plotly_chart(fig2, use_container_width=True)

    st.dataframe(cross, hide_index=True, use_container_width=True)


def plot_individual(result, student_id):
    if "error" in result: return err(result["error"])
    theta = result.get("theta", 0)
    cr    = result.get("correct_rate", 0)
    rank  = result.get("rank_in_group", "-")
    total = result.get("n_total", "-")

    c1, c2, c3, c4 = st.columns(4)
    for col, val, lbl, sub in [
        (c1, f"{theta:+.3f}", "θ値（IRT）", "能力推定値"),
        (c2, f"{cr:.1f}%",   "正答率",      ""),
        (c3, str(rank),      "順位",         f"全{total}名中"),
        (c4, student_id,     "生徒ID",       ""),
    ]:
        col.markdown(f"""
        <div class="metric-card">
            <div class="val">{val}</div>
            <div class="lbl">{lbl}</div>
            <div class="sub">{sub}</div>
        </div>""", unsafe_allow_html=True)

    st.markdown("---")
    tab_names = ["大領域","中領域","観点","資質能力","解答形式"]
    tabs      = st.tabs(tab_names)
    profile_configs = [
        ("domain_大領域",  "大領域",  "大領域",  "大領域別プロファイル",   True),
        ("domain_中領域",  "中領域",  "中領域",  "中領域別プロファイル",   False),
        ("domain_観点",    "観点",    "観点名",  "観点別プロファイル",     False),
        ("domain_資質能力","資質能力","資質能力","資質能力別プロファイル", False),
        ("domain_解答形式","解答形式","形式名",  "解答形式別プロファイル", False),
    ]
    for tab, (key, x_col, label_col, title, use_radar) in zip(tabs, profile_configs):
        with tab:
            if key not in result or not result[key]:
                st.info("データなし"); continue
            df  = pd.DataFrame(result[key])
            lbl = label_col if label_col in df.columns else x_col

            if use_radar and len(df) >= 3:
                cl, cr_ = st.columns(2)
                with cl:
                    r = df["rate"].tolist(); t = df[lbl].astype(str).tolist()
                    r += r[:1]; t += t[:1]
                    fig = go.Figure(go.Scatterpolar(r=r, theta=t, fill="toself",
                                                   line_color="#38bdf8",
                                                   fillcolor="rgba(56,189,248,0.15)"))
                    fig.update_layout(polar=dict(radialaxis=dict(range=[0,100])),
                                      title=title, template=PLOTLY_TEMPLATE,
                                      font_family="Noto Sans JP")
                    st.plotly_chart(fig, use_container_width=True)
                with cr_:
                    fig2 = px.bar(df, x=lbl, y="rate", color="rate",
                                  color_continuous_scale=["#ef4444","#fb923c","#38bdf8"],
                                  range_color=[0,100],
                                  labels={lbl:"","rate":"正答率(%)"},
                                  template=PLOTLY_TEMPLATE)
                    fig2.update_layout(font_family="Noto Sans JP")
                    st.plotly_chart(fig2, use_container_width=True)
            else:
                fig = px.bar(df, x=lbl, y="rate", color="rate",
                             color_continuous_scale=["#ef4444","#fb923c","#38bdf8"],
                             range_color=[0,100], text="rate",
                             labels={lbl:"","rate":"正答率(%)"},
                             title=title, template=PLOTLY_TEMPLATE)
                fig.update_traces(texttemplate="%{text:.1f}%", textposition="outside")
                fig.update_layout(font_family="Noto Sans JP", yaxis_range=[0,115])
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
<div class="v5-header">
  <h1>🎓 学力分析ダッシュボード v5</h1>
  <p>IRT θ推定 × ドリルダウン分析 × AI解釈サポート</p>
</div>
""", unsafe_allow_html=True)

# ════════════════════════════════════════════════════════
# DB接続確認
# ════════════════════════════════════════════════════════
try:
    all_schools = get_all_schools()
except Exception as e:
    st.error(f"DB接続エラー: {e}")
    st.stop()

# ════════════════════════════════════════════════════════
# 共通フィルターバー（メイン画面上部）
# ════════════════════════════════════════════════════════
st.markdown('<div class="filter-bar">', unsafe_allow_html=True)

fc1, fc2, fc3 = st.columns(3)

with fc1:
    st.markdown('<div class="filter-label">🏫 学校</div>', unsafe_allow_html=True)
    sel_school = st.selectbox(
        "学校", ["全体"] + all_schools,
        key="g_school", label_visibility="collapsed"
    )

with fc2:
    st.markdown('<div class="filter-label">🏠 クラス</div>', unsafe_allow_html=True)
    school_for_class = None if sel_school == "全体" else sel_school
    available_classes = get_classes_for(school_for_class)
    sel_class = st.selectbox(
        "クラス", ["全体"] + [str(c) for c in available_classes],
        key="g_class", label_visibility="collapsed"
    )

with fc3:
    st.markdown('<div class="filter-label">📚 教科</div>', unsafe_allow_html=True)
    school_for_subj = None if sel_school == "全体" else sel_school
    class_for_subj  = None if sel_class  == "全体" else int(sel_class)
    available_subjects = get_subjects_for(school_for_subj, class_for_subj)
    sel_subject = st.selectbox(
        "教科", available_subjects,
        key="g_subject", label_visibility="collapsed"
    )

st.markdown('</div>', unsafe_allow_html=True)

# 比較単位を自動推定し、現在の絞り込み状態を表示
group_by = resolve_group_by(sel_school, sel_class)

if sel_school == "全体":
    badge_text = "全校 → 学校単位で比較"
elif sel_class == "全体":
    badge_text = f"{sel_school} → クラス単位で比較"
else:
    badge_text = f"{sel_school} クラス{sel_class} → 単一クラス集計"

st.markdown(
    f'<span style="font-size:0.8rem; color:#94a3b8;">現在の絞り込み：</span>'
    f'<span class="badge">{badge_text}</span>',
    unsafe_allow_html=True
)
st.markdown("")  # 余白

# ════════════════════════════════════════════════════════
# セッションステート
# ════════════════════════════════════════════════════════
if "analysis_results" not in st.session_state:
    st.session_state.analysis_results = {}

# ════════════════════════════════════════════════════════
# メインタブ（フラット構成）
# ════════════════════════════════════════════════════════
TAB_NAMES = [
    "📈 θ分布",
    "🗂 大領域",
    "📂 中領域",
    "🔬 小問分析",
    "👁 観点",
    "💡 資質能力",
    "✏️ 解答形式",
    "💭 意識調査",
    "🔗 学力×意識",
    "👤 個人票",
    "🤖 AI解釈",
]
tabs = st.tabs(TAB_NAMES)

# ────────────────────────────────────────────────────────
# 共通: テストデータ＋問題マスタ取得ヘルパー
# ────────────────────────────────────────────────────────
def fetch_tr_qm():
    """共通フィルターに基づいてテスト結果と問題マスタを返す"""
    school  = None if sel_school == "全体" else sel_school
    cls     = None if sel_class  == "全体" else int(sel_class)
    tr      = get_test_results(school=school, class_id=cls, subject=sel_subject)
    qm      = get_question_master()
    qm_sub  = qm[qm["subject"] == sel_subject].copy()
    return tr, qm_sub

# ════════════════════════════════════════════════════════
# TAB 0: θ分布
# ════════════════════════════════════════════════════════
with tabs[0]:
    st.markdown(f"#### 📈 θ分布　<span class='badge'>{badge_text}</span>", unsafe_allow_html=True)
    if st.button("▶ 分析実行", key="run_theta", type="primary"):
        with st.spinner("データ取得中..."):
            tr, qm_sub = fetch_tr_qm()
        if tr.empty:
            st.warning("データが見つかりません")
        else:
            with st.spinner("θ推定中（WLE）..."):
                r = run_r("irt_theta", tr, qm_sub, {"group_by": group_by})
            st.session_state.analysis_results["θ分布"] = r
            plot_theta_distribution(r, group_by)

# ════════════════════════════════════════════════════════
# TAB 1: 大領域
# ════════════════════════════════════════════════════════
with tabs[1]:
    st.markdown(f"#### 🗂 大領域別分析　<span class='badge'>{badge_text}</span>", unsafe_allow_html=True)
    if st.button("▶ 分析実行", key="run_large", type="primary"):
        with st.spinner("データ取得中..."):
            tr, qm_sub = fetch_tr_qm()
        if tr.empty:
            st.warning("データが見つかりません")
        else:
            with st.spinner("大領域別集計中..."):
                r = run_r("domain_analysis", tr, qm_sub,
                          {"group_by": group_by, "domain_level": "large", "domain_col": "大領域"})
            st.session_state.analysis_results["大領域"] = r
            plot_domain(r, group_by)

# ════════════════════════════════════════════════════════
# TAB 2: 中領域
# ════════════════════════════════════════════════════════
with tabs[2]:
    st.markdown(f"#### 📂 中領域別分析　<span class='badge'>{badge_text}</span>", unsafe_allow_html=True)
    if st.button("▶ 分析実行", key="run_mid", type="primary"):
        with st.spinner("データ取得中..."):
            tr, qm_sub = fetch_tr_qm()
        if tr.empty:
            st.warning("データが見つかりません")
        else:
            with st.spinner("中領域別集計中..."):
                r = run_r("domain_analysis", tr, qm_sub,
                          {"group_by": group_by, "domain_level": "mid", "domain_col": "中領域"})
            st.session_state.analysis_results["中領域"] = r
            plot_domain(r, group_by)

# ════════════════════════════════════════════════════════
# TAB 3: 小問分析（中領域と観点の間）
# ════════════════════════════════════════════════════════
with tabs[3]:
    st.markdown(f"#### 🔬 小問分析　<span class='badge'>{badge_text}</span>", unsafe_allow_html=True)
    if st.button("▶ 分析実行", key="run_item", type="primary"):
        with st.spinner("データ取得中..."):
            tr, qm_sub = fetch_tr_qm()
        if tr.empty:
            st.warning("データが見つかりません")
        else:
            with st.spinner("小問分析中..."):
                r = run_r("item_analysis", tr, qm_sub)
            st.session_state.analysis_results["小問分析"] = r
            plot_item_analysis(r)

# ════════════════════════════════════════════════════════
# TAB 4: 観点
# ════════════════════════════════════════════════════════
with tabs[4]:
    st.markdown(f"#### 👁 観点別分析　<span class='badge'>{badge_text}</span>", unsafe_allow_html=True)
    if st.button("▶ 分析実行", key="run_view", type="primary"):
        with st.spinner("データ取得中..."):
            tr, qm_sub = fetch_tr_qm()
        if tr.empty:
            st.warning("データが見つかりません")
        else:
            with st.spinner("観点別集計中..."):
                r = run_r("viewpoint_analysis", tr, qm_sub, {"group_by": group_by})
            st.session_state.analysis_results["観点"] = r
            plot_attribute(r, "viewpoint_scores", "観点", "観点別 正答率", group_by, "観点名")

# ════════════════════════════════════════════════════════
# TAB 5: 資質能力
# ════════════════════════════════════════════════════════
with tabs[5]:
    st.markdown(f"#### 💡 資質能力別分析　<span class='badge'>{badge_text}</span>", unsafe_allow_html=True)
    if st.button("▶ 分析実行", key="run_comp", type="primary"):
        with st.spinner("データ取得中..."):
            tr, qm_sub = fetch_tr_qm()
        if tr.empty:
            st.warning("データが見つかりません")
        else:
            with st.spinner("資質能力別集計中..."):
                r = run_r("competency_analysis", tr, qm_sub, {"group_by": group_by})
            st.session_state.analysis_results["資質能力"] = r
            plot_attribute(r, "competency_scores", "資質能力", "資質能力別 正答率", group_by)

# ════════════════════════════════════════════════════════
# TAB 6: 解答形式
# ════════════════════════════════════════════════════════
with tabs[6]:
    st.markdown(f"#### ✏️ 解答形式別分析　<span class='badge'>{badge_text}</span>", unsafe_allow_html=True)
    if st.button("▶ 分析実行", key="run_fmt", type="primary"):
        with st.spinner("データ取得中..."):
            tr, qm_sub = fetch_tr_qm()
        if tr.empty:
            st.warning("データが見つかりません")
        else:
            with st.spinner("解答形式別集計中..."):
                r = run_r("format_analysis", tr, qm_sub, {"group_by": group_by})
            st.session_state.analysis_results["解答形式"] = r
            plot_attribute(r, "format_scores", "解答形式", "解答形式別 正答率", group_by, "形式名")

# ════════════════════════════════════════════════════════
# TAB 7: 意識調査
# ════════════════════════════════════════════════════════
with tabs[7]:
    st.markdown(f"#### 💭 意識調査　<span class='badge'>{badge_text}</span>", unsafe_allow_html=True)
    if st.button("▶ 分析実行", key="run_att", type="primary"):
        school = None if sel_school == "全体" else sel_school
        cls    = None if sel_class  == "全体" else int(sel_class)
        with st.spinner("データ取得中..."):
            ar     = get_attitude_results(school=school, class_id=cls, subject=sel_subject)
            am     = get_attitude_master()
            am_sub = am[am["subject"] == sel_subject]
        if ar.empty:
            st.warning("データが見つかりません")
        else:
            with st.spinner("意識調査集計中..."):
                r = run_r("attitude_analysis", ar, extra={
                    "group_by": group_by,
                    "attitude_master": am_sub.to_dict(orient="records"),
                })
            st.session_state.analysis_results["意識調査"] = r
            plot_attitude(r, group_by)

# ════════════════════════════════════════════════════════
# TAB 8: 学力×意識
# ════════════════════════════════════════════════════════
with tabs[8]:
    st.markdown(f"#### 🔗 学力 × 意識 クロス分析　<span class='badge'>{badge_text}</span>", unsafe_allow_html=True)
    if st.button("▶ 分析実行", key="run_cross", type="primary"):
        school = None if sel_school == "全体" else sel_school
        cls    = None if sel_class  == "全体" else int(sel_class)
        with st.spinner("データ取得中..."):
            tr, qm_sub = fetch_tr_qm()
            ar = get_attitude_results(school=school, class_id=cls, subject=sel_subject)
        if tr.empty or ar.empty:
            st.warning("学力または意識調査データが見つかりません")
        else:
            with st.spinner("クロス分析中（θ推定含む）..."):
                r = run_r("attitude_x_theta", ar, qm_sub,
                          {"test_data": tr.to_dict(orient="records")})
            st.session_state.analysis_results["学力×意識"] = r
            plot_attitude_x_theta(r)

# ════════════════════════════════════════════════════════
# TAB 9: 個人票（学校・クラス・教科・生徒 の四段階、全体選択は不可）
# ════════════════════════════════════════════════════════
with tabs[9]:
    st.markdown("#### 👤 個人票")

    # 個人票は学校・クラスの指定が必須
    if sel_school == "全体" or sel_class == "全体":
        st.info("個人票を表示するには、上の共通フィルターで **学校** と **クラス** を指定してください。")
    else:
        students_df = get_students_for(sel_school, int(sel_class), sel_subject)
        if students_df.empty:
            st.warning("生徒データが見つかりません")
        else:
            student_options = {
                row["student_id"]: f"No.{row['student_no']} ({row['student_id']})"
                for _, row in students_df.iterrows()
            }
            sel_student = st.selectbox(
                "👤 生徒", list(student_options.keys()),
                format_func=lambda x: student_options[x],
                key="g_student"
            )

            if st.button("▶ 個人票表示", key="run_ind", type="primary"):
                with st.spinner("データ取得中..."):
                    tr_all, qm_sub = fetch_tr_qm()
                if tr_all.empty:
                    st.warning("データが見つかりません")
                else:
                    with st.spinner("個人プロファイル生成中..."):
                        r = run_r("individual_profile", tr_all, qm_sub,
                                  {"student_id": sel_student})
                    plot_individual(r, sel_student)

                    # 意識調査（個人）
                    ar_all = get_attitude_results(
                        school=sel_school, class_id=int(sel_class), subject=sel_subject
                    )
                    if not ar_all.empty:
                        ar_ind = ar_all[ar_all["student_id"] == sel_student]
                        if not ar_ind.empty:
                            st.markdown("##### 💭 意識調査スコア（個人）")
                            fig_att = px.bar(
                                ar_ind, x="question_id", y="score", color="score",
                                color_continuous_scale=["#ef4444","#fb923c","#94a3b8","#34d399","#38bdf8"],
                                range_color=[0,4],
                                labels={"question_id":"質問ID","score":"スコア"},
                                title="意識調査 個人スコア（0〜4）",
                                template=PLOTLY_TEMPLATE,
                            )
                            fig_att.update_layout(font_family="Noto Sans JP")
                            st.plotly_chart(fig_att, use_container_width=True)

# ════════════════════════════════════════════════════════
# TAB 10: AI解釈
# ════════════════════════════════════════════════════════
with tabs[10]:
    st.markdown("#### 🤖 Claude AI 解釈・提案")

    if not st.session_state.analysis_results:
        st.info("他のタブで分析を実行すると、AIが結果を解釈できます。")
    else:
        available   = list(st.session_state.analysis_results.keys())
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

# ════════════════════════════════════════════════════════
# フッター
# ════════════════════════════════════════════════════════
st.divider()
st.caption("学力分析ダッシュボード v5 ｜ Streamlit + R (WLE-IRT) + Claude API + Supabase PostgreSQL")
