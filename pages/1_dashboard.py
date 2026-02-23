import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go

# ページ設定
st.set_page_config(
    page_title="学力データ分析ダッシュボード（拡張版）",
    page_icon="📊",
    layout="wide"
)

# 問題パラメータの定義
DOMAIN_PARAMS = {
    'domain_1': ['x1', 'x2', 'x3', 'x4', 'x5', 'x6', 'x7', 'x8'],
    'domain_2': ['x9', 'x10', 'x11', 'x12', 'x13', 'x14', 'x15', 'x16'],
    'domain_3': ['x17', 'x18', 'x19', 'x20', 'x21', 'x22', 'x23', 'x24'],
    'domain_4': ['x25', 'x26', 'x27', 'x28', 'x29', 'x30', 'x31', 'x32']
}

ABILITY_PARAMS = {
    'ability_a': ['x1', 'x2', 'x9', 'x10', 'x17', 'x18', 'x25', 'x26'],
    'ability_b': ['x3', 'x4', 'x11', 'x12', 'x19', 'x20', 'x27', 'x28'],
    'ability_c': ['x5', 'x6', 'x13', 'x14', 'x21', 'x22', 'x29', 'x30'],
    'ability_d': ['x7', 'x8', 'x15', 'x16', 'x23', 'x24', 'x31', 'x32']
}

# 日本語表示用のマッピング
DOMAIN_LABELS = {
    'domain_1': '領域1',
    'domain_2': '領域2',
    'domain_3': '領域3',
    'domain_4': '領域4'
}

ABILITY_LABELS = {
    'ability_a': '能力A',
    'ability_b': '能力B',
    'ability_c': '能力C',
    'ability_d': '能力D'
}

def calculate_scores(df):
    """能力別・領域別の得点を計算"""
    question_cols = [f'x{i}' for i in range(1, 33)]
    
    # 能力別得点の計算
    for ability, questions in ABILITY_PARAMS.items():
        available_questions = [q for q in questions if q in df.columns]
        if available_questions:
            df[f'{ability}_score'] = df[available_questions].sum(axis=1)
            df[f'{ability}_rate'] = (df[f'{ability}_score'] / len(available_questions) * 100).round(1)
    
    # 領域別得点の計算
    for domain, questions in DOMAIN_PARAMS.items():
        available_questions = [q for q in questions if q in df.columns]
        if available_questions:
            df[f'{domain}_score'] = df[available_questions].sum(axis=1)
            df[f'{domain}_rate'] = (df[f'{domain}_score'] / len(available_questions) * 100).round(1)
    
    # 総合得点
    available_all = [q for q in question_cols if q in df.columns]
    if available_all:
        df['total_score'] = df[available_all].sum(axis=1)
        df['total_rate'] = (df['total_score'] / len(available_all) * 100).round(1)
    
    return df

def get_ability_stats(df):
    """能力別の統計量を取得"""
    stats = []
    for ability, label in ABILITY_LABELS.items():
        score_col = f'{ability}_score'
        rate_col = f'{ability}_rate'
        if score_col in df.columns and rate_col in df.columns:
            stats.append({
                '能力': label,
                '平均素点': df[score_col].mean(),
                '平均得点率(%)': df[rate_col].mean(),
                '標準偏差': df[rate_col].std(),
                '最高得点率(%)': df[rate_col].max(),
                '最低得点率(%)': df[rate_col].min()
            })
    return pd.DataFrame(stats)

def get_domain_stats(df):
    """領域別の統計量を取得"""
    stats = []
    for domain, label in DOMAIN_LABELS.items():
        score_col = f'{domain}_score'
        rate_col = f'{domain}_rate'
        if score_col in df.columns and rate_col in df.columns:
            stats.append({
                '領域': label,
                '平均素点': df[score_col].mean(),
                '平均得点率(%)': df[rate_col].mean(),
                '標準偏差': df[rate_col].std(),
                '最高得点率(%)': df[rate_col].max(),
                '最低得点率(%)': df[rate_col].min()
            })
    return pd.DataFrame(stats)

def get_subject_stats(df):
    """教科別の統計量を取得"""
    if 'subject' not in df.columns:
        return pd.DataFrame()
    
    stats = []
    for subject in df['subject'].unique():
        subject_df = df[df['subject'] == subject]
        if 'total_score' in subject_df.columns and 'total_rate' in subject_df.columns:
            stats.append({
                '教科': subject,
                '受験者数': len(subject_df),
                '平均素点': subject_df['total_score'].mean(),
                '平均得点率(%)': subject_df['total_rate'].mean(),
                '標準偏差': subject_df['total_rate'].std(),
                '最高得点率(%)': subject_df['total_rate'].max(),
                '最低得点率(%)': subject_df['total_rate'].min(),
                '中央値(%)': subject_df['total_rate'].median()
            })
    return pd.DataFrame(stats)

def get_subject_ability_stats(df):
    """教科×能力のクロス集計"""
    if 'subject' not in df.columns:
        return pd.DataFrame()
    
    stats = []
    for subject in df['subject'].unique():
        subject_df = df[df['subject'] == subject]
        for ability, label in ABILITY_LABELS.items():
            rate_col = f'{ability}_rate'
            if rate_col in subject_df.columns:
                stats.append({
                    '教科': subject,
                    '能力': label,
                    '平均得点率(%)': subject_df[rate_col].mean()
                })
    return pd.DataFrame(stats)

def get_subject_domain_stats(df):
    """教科×領域のクロス集計"""
    if 'subject' not in df.columns:
        return pd.DataFrame()
    
    stats = []
    for subject in df['subject'].unique():
        subject_df = df[df['subject'] == subject]
        for domain, label in DOMAIN_LABELS.items():
            rate_col = f'{domain}_rate'
            if rate_col in subject_df.columns:
                stats.append({
                    '教科': subject,
                    '領域': label,
                    '平均得点率(%)': subject_df[rate_col].mean()
                })
    return pd.DataFrame(stats)

def get_question_correct_rate(df, param_dict):
    """小問別正答率を取得"""
    rates = []
    for category, questions in param_dict.items():
        for q in questions:
            if q in df.columns:
                rates.append({
                    '問題': q,
                    'カテゴリ': category,
                    '正答率(%)': df[q].mean() * 100,
                    '正答者数': df[q].sum(),
                    '受験者数': len(df)
                })
    return pd.DataFrame(rates)

# タイトル
st.title("📊 学力データ分析ダッシュボード（拡張版）")
st.markdown("**能力・領域パラメータに基づく多角的分析**")
st.markdown("---")

# サイドバー
with st.sidebar:
    st.header("📁 データアップロード")
    uploaded_file = st.file_uploader(
        "CSVファイルを選択してください",
        type=['csv'],
        help="ID, grade, class, subject, x1-x32の列を含むCSVファイル"
    )
    
    st.markdown("---")
    st.markdown("### 📋 パラメータ設定")
    st.markdown("**領域パラメータ**")
    for domain, label in DOMAIN_LABELS.items():
        questions = DOMAIN_PARAMS[domain]
        st.text(f"{label}: {questions[0]}-{questions[-1]}")
    
    st.markdown("**能力パラメータ**")
    for ability, label in ABILITY_LABELS.items():
        st.text(f"{label}: 各領域から2問ずつ")

# メイン画面
if uploaded_file is None:
    st.info("👈 左のサイドバーからCSVファイルをアップロードしてください")
    st.markdown("""
    ### このダッシュボードでできること
    - ✅ **能力別分析**: 4つの能力（A, B, C, D）ごとの素点・得点率を算出
    - ✅ **領域別分析**: 4つの領域（1, 2, 3, 4）ごとの素点・得点率を算出
    - ✅ **多次元可視化**: 能力・領域のレーダーチャート、ヒートマップ
    - ✅ **個別診断**: 生徒ごとの強み・弱みの可視化
    - ✅ **小問分析**: パラメータごとの正答率分析
    """)
else:
    try:
        # データ読み込み
        df = pd.read_csv(uploaded_file)
        
        # BOM除去（UTF-8 with BOM対策）
        df.columns = df.columns.str.replace('\ufeff', '')
        
        # 得点計算
        df = calculate_scores(df)
        
        # タブで機能を分割
        tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs([
            "📄 データ確認", 
            "🎯 能力別分析",
            "📦 領域別分析",
            "📚 教科別分析",
            "✓ 小問分析", 
            "👤 個別診断",
            "📊 総合ダッシュボード"
        ])
        
        # タブ1: データ確認
        with tab1:
            st.subheader("アップロードされたデータ（計算済み）")
            
            # 基本情報
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("生徒数", df['ID'].nunique())
            with col2:
                st.metric("学年数", df['grade'].nunique())
            with col3:
                st.metric("クラス数", df['class'].nunique())
            with col4:
                st.metric("教科数", df['subject'].nunique())
            
            # データ表示オプション
            show_columns = st.multiselect(
                "表示する列を選択",
                options=df.columns.tolist(),
                default=['ID', 'grade', 'class', 'subject', 'total_score', 'total_rate']
            )
            
            if show_columns:
                st.dataframe(df[show_columns], use_container_width=True)
            else:
                st.dataframe(df, use_container_width=True)
        
        # タブ2: 能力別分析
        with tab2:
            st.subheader("能力別統計量")
            
            ability_stats = get_ability_stats(df)
            st.dataframe(ability_stats.round(2), use_container_width=True)
            
            # 能力別得点率の分布
            st.markdown("### 能力別得点率の分布")
            
            ability_rate_cols = [f'{ability}_rate' for ability in ABILITY_PARAMS.keys() if f'{ability}_rate' in df.columns]
            
            if ability_rate_cols:
                # データを縦持ちに変換
                plot_data = []
                for col in ability_rate_cols:
                    ability_name = col.replace('_rate', '')
                    label = ABILITY_LABELS.get(ability_name, ability_name)
                    for value in df[col]:
                        plot_data.append({'能力': label, '得点率(%)': value})
                
                plot_df = pd.DataFrame(plot_data)
                
                # 箱ひげ図
                fig = px.box(
                    plot_df,
                    x='能力',
                    y='得点率(%)',
                    title='能力別得点率の分布',
                    color='能力'
                )
                st.plotly_chart(fig, use_container_width=True)
                
                # ヒストグラム（能力ごとに独立表示）
                fig2 = px.histogram(
                    plot_df,
                    x='得点率(%)',
                    color='能力',
                    nbins=20,
                    title='能力別得点率のヒストグラム',
                    opacity=0.7,
                    barmode='group',  # overlayからgroupに変更
                    labels={'count': '生徒数'}
                )
                # 軸ラベルを明確化
                fig2.update_xaxis(title_text='得点率(%)')
                fig2.update_yaxis(title_text='生徒数')
                st.plotly_chart(fig2, use_container_width=True)
                          
            # 能力間の相関分析
            st.markdown("### 能力間の相関")
            
            if len(ability_rate_cols) >= 2:
                col1, col2 = st.columns(2)
                with col1:
                    ability_x = st.selectbox("X軸の能力", ability_rate_cols, format_func=lambda x: ABILITY_LABELS.get(x.replace('_rate', ''), x))
                with col2:
                    ability_y = st.selectbox("Y軸の能力", 
                                           [c for c in ability_rate_cols if c != ability_x],
                                           format_func=lambda x: ABILITY_LABELS.get(x.replace('_rate', ''), x))
                
                # 平均値の計算
                mean_x = df[ability_x].mean()
                mean_y = df[ability_y].mean()
                
                # 散布図作成（IDをホバー表示に追加）
                fig = px.scatter(
                    df,
                    x=ability_x,
                    y=ability_y,
                    title=f'{ABILITY_LABELS.get(ability_x.replace("_rate", ""), ability_x)} vs {ABILITY_LABELS.get(ability_y.replace("_rate", ""), ability_y)}',
                    trendline="ols",
                    hover_data={'ID': True, ability_x: ':.1f', ability_y: ':.1f'}
                )
                
                # 平均線を追加（赤い破線）
                fig.add_hline(y=mean_y, line_dash="dash", line_color="red", line_width=2, 
                             annotation_text=f"Y軸平均: {mean_y:.1f}%", 
                             annotation_position="right")
                fig.add_vline(x=mean_x, line_dash="dash", line_color="red", line_width=2,
                             annotation_text=f"X軸平均: {mean_x:.1f}%",
                             annotation_position="top")
                
                st.plotly_chart(fig, use_container_width=True)
                
                corr = df[[ability_x, ability_y]].corr().iloc[0, 1]
                
                # 相関係数と平均値の情報を表示
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("相関係数", f"{corr:.3f}")
                with col2:
                    st.metric(f"X軸平均 ({ABILITY_LABELS.get(ability_x.replace('_rate', ''), ability_x)})", f"{mean_x:.1f}%")
                with col3:
                    st.metric(f"Y軸平均 ({ABILITY_LABELS.get(ability_y.replace('_rate', ''), ability_y)})", f"{mean_y:.1f}%")
        
        # タブ3: 領域別分析
        with tab3:
            st.subheader("領域別統計量")
            
            domain_stats = get_domain_stats(df)
            st.dataframe(domain_stats.round(2), use_container_width=True)
            
            # 領域別得点率の分布
            st.markdown("### 領域別得点率の分布")
            
            domain_rate_cols = [f'{domain}_rate' for domain in DOMAIN_PARAMS.keys() if f'{domain}_rate' in df.columns]
            
            if domain_rate_cols:
                # データを縦持ちに変換
                plot_data = []
                for col in domain_rate_cols:
                    domain_name = col.replace('_rate', '')
                    label = DOMAIN_LABELS.get(domain_name, domain_name)
                    for value in df[col]:
                        plot_data.append({'領域': label, '得点率(%)': value})
                
                plot_df = pd.DataFrame(plot_data)
                
                # 箱ひげ図
                fig = px.box(
                    plot_df,
                    x='領域',
                    y='得点率(%)',
                    title='領域別得点率の分布',
                    color='領域'
                )
                st.plotly_chart(fig, use_container_width=True)
                
                # ヒストグラム（重ね合わせ）
                fig2 = px.histogram(
                    plot_df,
                    x='得点率(%)',
                    color='領域',
                    nbins=20,
                    title='領域別得点率のヒストグラム',
                    opacity=0.7,
                    barmode='overlay'
                )
                st.plotly_chart(fig2, use_container_width=True)
        
        # タブ4: 教科別分析
        with tab4:
            st.subheader("教科別統計量")
            
            # 教科の数を確認
            if 'subject' in df.columns:
                subjects = df['subject'].unique()
                
                if len(subjects) > 1:
                    # 複数教科がある場合
                    subject_stats = get_subject_stats(df)
                    st.dataframe(subject_stats.round(2), use_container_width=True)
                    
                    # 教科別総合得点率の比較
                    st.markdown("### 教科別総合得点率の比較")
                    
                    fig = px.box(
                        df,
                        x='subject',
                        y='total_rate',
                        title='教科別総合得点率の分布',
                        labels={'subject': '教科', 'total_rate': '総合得点率(%)'},
                        color='subject'
                    )
                    st.plotly_chart(fig, use_container_width=True)
                    
                    # 教科×能力のヒートマップ
                    st.markdown("### 教科×能力の平均得点率ヒートマップ")
                    
                    subject_ability_stats = get_subject_ability_stats(df)
                    if not subject_ability_stats.empty:
                        pivot_table = subject_ability_stats.pivot(index='能力', columns='教科', values='平均得点率(%)')
                        
                        fig2 = px.imshow(
                            pivot_table,
                            labels=dict(x="教科", y="能力", color="平均得点率(%)"),
                            x=pivot_table.columns,
                            y=pivot_table.index,
                            color_continuous_scale='RdYlGn',
                            aspect='auto',
                            title='教科×能力の平均得点率',
                            text_auto='.1f'
                        )
                        st.plotly_chart(fig2, use_container_width=True)
                    
                    # 教科×領域のヒートマップ
                    st.markdown("### 教科×領域の平均得点率ヒートマップ")
                    
                    subject_domain_stats = get_subject_domain_stats(df)
                    if not subject_domain_stats.empty:
                        pivot_table2 = subject_domain_stats.pivot(index='領域', columns='教科', values='平均得点率(%)')
                        
                        fig3 = px.imshow(
                            pivot_table2,
                            labels=dict(x="教科", y="領域", color="平均得点率(%)"),
                            x=pivot_table2.columns,
                            y=pivot_table2.index,
                            color_continuous_scale='RdYlGn',
                            aspect='auto',
                            title='教科×領域の平均得点率',
                            text_auto='.1f'
                        )
                        st.plotly_chart(fig3, use_container_width=True)
                    
                    # 教科選択による詳細分析
                    st.markdown("### 教科別詳細分析")
                    
                    selected_subject = st.selectbox("詳細分析する教科を選択", subjects)
                    subject_df = df[df['subject'] == selected_subject]
                    
                    col1, col2 = st.columns(2)
                    
                    with col1:
                        # 能力別の統計
                        st.markdown(f"**{selected_subject} - 能力別統計**")
                        ability_stats_subject = get_ability_stats(subject_df)
                        st.dataframe(ability_stats_subject.round(2), use_container_width=True)
                    
                    with col2:
                        # 領域別の統計
                        st.markdown(f"**{selected_subject} - 領域別統計**")
                        domain_stats_subject = get_domain_stats(subject_df)
                        st.dataframe(domain_stats_subject.round(2), use_container_width=True)
                    
                    # 教科間の相関分析
                    if len(subjects) >= 2:
                        st.markdown("### 教科間の相関分析")
                        
                        # データをピボット（生徒×教科）
                        pivot_df = df.pivot_table(
                            index='ID',
                            columns='subject',
                            values='total_rate'
                        ).reset_index()
                        
                        col1, col2 = st.columns(2)
                        with col1:
                            subject_x = st.selectbox("X軸の教科", subjects, key="subject_corr_x")
                        with col2:
                            subject_y = st.selectbox("Y軸の教科", 
                                                   [s for s in subjects if s != subject_x],
                                                   key="subject_corr_y")
                        
                        if subject_x in pivot_df.columns and subject_y in pivot_df.columns:
                            # 平均値の計算
                            mean_subject_x = pivot_df[subject_x].mean()
                            mean_subject_y = pivot_df[subject_y].mean()
                            
                            # 散布図作成（IDをホバー表示に追加）
                            fig4 = px.scatter(
                                pivot_df,
                                x=subject_x,
                                y=subject_y,
                                title=f'{subject_x} vs {subject_y}の総合得点率相関',
                                labels={subject_x: f'{subject_x} 総合得点率(%)', 
                                       subject_y: f'{subject_y} 総合得点率(%)'},
                                trendline="ols",
                                hover_data={'ID': True, subject_x: ':.1f', subject_y: ':.1f'}
                            )
                            
                            # 平均線を追加（赤い破線）
                            fig4.add_hline(y=mean_subject_y, line_dash="dash", line_color="red", line_width=2,
                                          annotation_text=f"{subject_y}平均: {mean_subject_y:.1f}%",
                                          annotation_position="right")
                            fig4.add_vline(x=mean_subject_x, line_dash="dash", line_color="red", line_width=2,
                                          annotation_text=f"{subject_x}平均: {mean_subject_x:.1f}%",
                                          annotation_position="top")
                            
                            st.plotly_chart(fig4, use_container_width=True)
                            
                            corr = pivot_df[[subject_x, subject_y]].corr().iloc[0, 1]
                            
                            # 相関係数と平均値の情報を表示
                            col1, col2, col3 = st.columns(3)
                            with col1:
                                st.metric("相関係数", f"{corr:.3f}")
                            with col2:
                                st.metric(f"{subject_x}平均", f"{mean_subject_x:.1f}%")
                            with col3:
                                st.metric(f"{subject_y}平均", f"{mean_subject_y:.1f}%")
                
                else:
                    # 単一教科の場合
                    st.info(f"データには1つの教科（{subjects[0]}）のみが含まれています。")
                    st.markdown("複数教科のデータをアップロードすると、教科間の比較分析が可能になります。")
                    
                    # 単一教科でも基本統計は表示
                    subject_stats = get_subject_stats(df)
                    st.dataframe(subject_stats.round(2), use_container_width=True)
            else:
                st.warning("データにsubject列が見つかりません。")
        
        # タブ5: 小問分析
        with tab5:
            st.subheader("小問別正答率分析")
            
            analysis_type = st.radio("分析タイプ", ["能力別", "領域別"])
            
            if analysis_type == "能力別":
                param_dict = ABILITY_PARAMS
                label_dict = ABILITY_LABELS
            else:
                param_dict = DOMAIN_PARAMS
                label_dict = DOMAIN_LABELS
            
            # 正答率データ取得
            correct_rate_df = get_question_correct_rate(df, param_dict)
            correct_rate_df['カテゴリ名'] = correct_rate_df['カテゴリ'].map(label_dict)
            
            # 棒グラフ
            fig = px.bar(
                correct_rate_df,
                x='問題',
                y='正答率(%)',
                color='カテゴリ名',
                title=f'{analysis_type}の小問別正答率',
                hover_data=['正答者数', '受験者数']
            )
            st.plotly_chart(fig, use_container_width=True)
            
            # カテゴリ別の平均正答率
            st.markdown(f"### {analysis_type}の平均正答率")
            category_avg = correct_rate_df.groupby('カテゴリ名')['正答率(%)'].mean().reset_index()
            category_avg.columns = ['カテゴリ', '平均正答率(%)']
            category_avg['平均正答率(%)'] = category_avg['平均正答率(%)'].round(2)
            
            fig2 = px.bar(
                category_avg,
                x='カテゴリ',
                y='平均正答率(%)',
                title=f'{analysis_type}の平均正答率',
                text='平均正答率(%)'
            )
            fig2.update_traces(texttemplate='%{text:.1f}%', textposition='outside')
            st.plotly_chart(fig2, use_container_width=True)
            
            # 詳細データ
            st.markdown("### 詳細データ")
            st.dataframe(correct_rate_df.round(2), use_container_width=True)
        
        # タブ6: 個別診断
        with tab6:
            st.subheader("生徒別診断")
            
            # 生徒と教科の選択
            col1, col2 = st.columns(2)
            
            with col1:
                students = sorted(df['ID'].unique())
                selected_student = st.selectbox("生徒を選択", students)
            
            with col2:
                # 教科選択（複数教科がある場合）
                if 'subject' in df.columns:
                    subjects_available = sorted(df['subject'].unique())
                    if len(subjects_available) > 1:
                        selected_subject = st.selectbox("教科を選択", ['全教科'] + list(subjects_available))
                    else:
                        selected_subject = subjects_available[0]
                        st.info(f"教科: {selected_subject}")
                else:
                    selected_subject = '全教科'
            
            # データをフィルタリング
            if selected_subject == '全教科':
                student_df_filtered = df[df['ID'] == selected_student]
                comparison_df = df  # クラス平均用
            else:
                student_df_filtered = df[(df['ID'] == selected_student) & (df['subject'] == selected_subject)]
                comparison_df = df[df['subject'] == selected_subject]  # クラス平均用
            
            if len(student_df_filtered) == 0:
                st.warning("選択された条件に該当するデータがありません。")
            else:
                # 全教科の場合は平均を取る
                if selected_subject == '全教科' and len(student_df_filtered) > 1:
                    student_data = student_df_filtered.mean(numeric_only=True)
                else:
                    student_data = student_df_filtered.iloc[0]
                
                # 基本情報
                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    st.metric("ID", selected_student)
                with col2:
                    st.metric("学年", int(student_data['grade']))
                with col3:
                    st.metric("クラス", student_df_filtered['class'].iloc[0])
                with col4:
                    if selected_subject == '全教科':
                        st.metric("総合得点率（全教科平均）", f"{student_data['total_rate']:.1f}%")
                    else:
                        st.metric(f"総合得点率（{selected_subject}）", f"{student_data['total_rate']:.1f}%")
                
                # 教科別の得点表示（全教科選択時）
                if selected_subject == '全教科' and len(student_df_filtered) > 1:
                    st.markdown("### 教科別総合得点率")
                    subject_scores = student_df_filtered[['subject', 'total_rate']].copy()
                    subject_scores.columns = ['教科', '総合得点率(%)']
                    st.dataframe(subject_scores, use_container_width=True)
                
                # レーダーチャート（能力）
                col1, col2 = st.columns(2)
                
                with col1:
                    st.markdown("### 能力別プロファイル")
                    
                    abilities = []
                    student_scores = []
                    class_avg_scores = []
                    
                    for ability, label in ABILITY_LABELS.items():
                        rate_col = f'{ability}_rate'
                        if rate_col in df.columns:
                            abilities.append(label)
                            student_scores.append(student_data[rate_col])
                            class_avg_scores.append(comparison_df[rate_col].mean())
                    
                    fig = go.Figure()
                    
                    fig.add_trace(go.Scatterpolar(
                        r=student_scores,
                        theta=abilities,
                        fill='toself',
                        name=f'{selected_student} ({selected_subject})',
                        line=dict(color='blue')
                    ))
                    
                    fig.add_trace(go.Scatterpolar(
                        r=class_avg_scores,
                        theta=abilities,
                        fill='toself',
                        name=f'クラス平均 ({selected_subject})',
                        line=dict(color='red', dash='dash')
                    ))
                    
                    fig.update_layout(
                        polar=dict(radialaxis=dict(visible=True, range=[0, 100])),
                        showlegend=True
                    )
                    
                    st.plotly_chart(fig, use_container_width=True)
                
                with col2:
                    st.markdown("### 領域別プロファイル")
                    
                    domains = []
                    student_scores_d = []
                    class_avg_scores_d = []
                    
                    for domain, label in DOMAIN_LABELS.items():
                        rate_col = f'{domain}_rate'
                        if rate_col in df.columns:
                            domains.append(label)
                            student_scores_d.append(student_data[rate_col])
                            class_avg_scores_d.append(comparison_df[rate_col].mean())
                    
                    fig2 = go.Figure()
                    
                    fig2.add_trace(go.Scatterpolar(
                        r=student_scores_d,
                        theta=domains,
                        fill='toself',
                        name=f'{selected_student} ({selected_subject})',
                        line=dict(color='green')
                    ))
                    
                    fig2.add_trace(go.Scatterpolar(
                        r=class_avg_scores_d,
                        theta=domains,
                        fill='toself',
                        name=f'クラス平均 ({selected_subject})',
                        line=dict(color='red', dash='dash')
                    ))
                    
                    fig2.update_layout(
                        polar=dict(radialaxis=dict(visible=True, range=[0, 100])),
                        showlegend=True
                    )
                    
                    st.plotly_chart(fig2, use_container_width=True)
                
                # 強み・弱みの分析
                st.markdown("### 強み・弱みの分析")
                
                # 能力別
                ability_data = []
                for ability, label in ABILITY_LABELS.items():
                    rate_col = f'{ability}_rate'
                    if rate_col in df.columns:
                        student_rate = student_data[rate_col]
                        class_avg = comparison_df[rate_col].mean()
                        diff = student_rate - class_avg
                        ability_data.append({
                            'カテゴリ': label,
                            '生徒得点率(%)': student_rate,
                            'クラス平均(%)': class_avg,
                            '差分': diff
                        })
                
                ability_analysis_df = pd.DataFrame(ability_data)
                ability_analysis_df = ability_analysis_df.sort_values('差分', ascending=False)
                
                st.markdown(f"**能力別比較（{selected_subject}）**")
                st.dataframe(ability_analysis_df.round(2), use_container_width=True)
                
                # 領域別
                domain_data = []
                for domain, label in DOMAIN_LABELS.items():
                    rate_col = f'{domain}_rate'
                    if rate_col in df.columns:
                        student_rate = student_data[rate_col]
                        class_avg = comparison_df[rate_col].mean()
                        diff = student_rate - class_avg
                        domain_data.append({
                            'カテゴリ': label,
                            '生徒得点率(%)': student_rate,
                            'クラス平均(%)': class_avg,
                            '差分': diff
                        })
                
                domain_analysis_df = pd.DataFrame(domain_data)
                domain_analysis_df = domain_analysis_df.sort_values('差分', ascending=False)
                
                st.markdown(f"**領域別比較（{selected_subject}）**")
                st.dataframe(domain_analysis_df.round(2), use_container_width=True)
                
                # 教科別の強み・弱み（全教科選択時）
                if selected_subject == '全教科' and len(subjects_available) > 1:
                    st.markdown("### 教科別パフォーマンス")
                    
                    subject_performance = []
                    for subj in subjects_available:
                        subj_student_df = df[(df['ID'] == selected_student) & (df['subject'] == subj)]
                        subj_class_df = df[df['subject'] == subj]
                        
                        if len(subj_student_df) > 0:
                            student_rate = subj_student_df['total_rate'].iloc[0]
                            class_avg = subj_class_df['total_rate'].mean()
                            diff = student_rate - class_avg
                            
                            subject_performance.append({
                                '教科': subj,
                                '生徒得点率(%)': student_rate,
                                'クラス平均(%)': class_avg,
                                '差分': diff
                            })
                    
                    subject_performance_df = pd.DataFrame(subject_performance)
                    subject_performance_df = subject_performance_df.sort_values('差分', ascending=False)
                    
                    st.dataframe(subject_performance_df.round(2), use_container_width=True)
                    
                    # 教科別レーダーチャート
                    fig3 = go.Figure()
                    
                    fig3.add_trace(go.Scatterpolar(
                        r=subject_performance_df['生徒得点率(%)'].tolist(),
                        theta=subject_performance_df['教科'].tolist(),
                        fill='toself',
                        name=selected_student,
                        line=dict(color='purple')
                    ))
                    
                    fig3.add_trace(go.Scatterpolar(
                        r=subject_performance_df['クラス平均(%)'].tolist(),
                        theta=subject_performance_df['教科'].tolist(),
                        fill='toself',
                        name='クラス平均',
                        line=dict(color='red', dash='dash')
                    ))
                    
                    fig3.update_layout(
                        polar=dict(radialaxis=dict(visible=True, range=[0, 100])),
                        showlegend=True,
                        title='教科別総合得点率'
                    )
                    
                    st.plotly_chart(fig3, use_container_width=True)
        
        # タブ7: 総合ダッシュボード
        with tab7:
            st.subheader("総合ダッシュボード")
            
            # ヒートマップ（生徒×能力）
            st.markdown("### 生徒別・能力別得点率ヒートマップ")
            
            ability_rate_cols = [f'{ability}_rate' for ability in ABILITY_PARAMS.keys() if f'{ability}_rate' in df.columns]
            
            if ability_rate_cols:
                heatmap_df = df[['ID'] + ability_rate_cols].copy()
                # 重複IDの処理：各生徒のデータを集約（平均）
                heatmap_df = heatmap_df.groupby('ID', as_index=False).mean()
                heatmap_df.columns = ['ID'] + [ABILITY_LABELS.get(col.replace('_rate', ''), col) for col in ability_rate_cols]
                heatmap_df = heatmap_df.set_index('ID')
                
                fig = px.imshow(
                    heatmap_df.T,
                    labels=dict(x="生徒ID", y="能力", color="得点率(%)"),
                    x=heatmap_df.index,
                    y=heatmap_df.columns,
                    color_continuous_scale='RdYlGn',
                    aspect='auto',
                    title='生徒別・能力別得点率ヒートマップ'
                )
                st.plotly_chart(fig, use_container_width=True)
            
            # ヒートマップ（生徒×領域）
            st.markdown("### 生徒別・領域別得点率ヒートマップ")
            
            domain_rate_cols = [f'{domain}_rate' for domain in DOMAIN_PARAMS.keys() if f'{domain}_rate' in df.columns]
            
            if domain_rate_cols:
                heatmap_df2 = df[['ID'] + domain_rate_cols].copy()
                # 重複IDの処理：各生徒のデータを集約（平均）
                heatmap_df2 = heatmap_df2.groupby('ID', as_index=False).mean()
                heatmap_df2.columns = ['ID'] + [DOMAIN_LABELS.get(col.replace('_rate', ''), col) for col in domain_rate_cols]
                heatmap_df2 = heatmap_df2.set_index('ID')
                
                fig2 = px.imshow(
                    heatmap_df2.T,
                    labels=dict(x="生徒ID", y="領域", color="得点率(%)"),
                    x=heatmap_df2.index,
                    y=heatmap_df2.columns,
                    color_continuous_scale='RdYlGn',
                    aspect='auto',
                    title='生徒別・領域別得点率ヒートマップ'
                )
                st.plotly_chart(fig2, use_container_width=True)
            
            # 能力×領域のクロス分析
            st.markdown("### 能力×領域のクロス分析")
            
            col1, col2 = st.columns(2)
            with col1:
                selected_ability = st.selectbox("能力を選択", list(ABILITY_LABELS.keys()), format_func=lambda x: ABILITY_LABELS[x])
            with col2:
                selected_domain = st.selectbox("領域を選択", list(DOMAIN_LABELS.keys()), format_func=lambda x: DOMAIN_LABELS[x])
            
            ability_col = f'{selected_ability}_rate'
            domain_col = f'{selected_domain}_rate'
            
            if ability_col in df.columns and domain_col in df.columns:
                # 平均値の計算
                mean_ability = df[ability_col].mean()
                mean_domain = df[domain_col].mean()
                
                # 散布図作成（IDをホバー表示に追加）
                fig3 = px.scatter(
                    df,
                    x=ability_col,
                    y=domain_col,
                    title=f'{ABILITY_LABELS[selected_ability]} vs {DOMAIN_LABELS[selected_domain]}',
                    labels={ability_col: f'{ABILITY_LABELS[selected_ability]}得点率(%)', 
                           domain_col: f'{DOMAIN_LABELS[selected_domain]}得点率(%)'},
                    trendline="ols",
                    hover_data={'ID': True, ability_col: ':.1f', domain_col: ':.1f'}
                )
                
                # 平均線を追加（赤い破線）
                fig3.add_hline(y=mean_domain, line_dash="dash", line_color="red", line_width=2,
                              annotation_text=f"領域平均: {mean_domain:.1f}%",
                              annotation_position="right")
                fig3.add_vline(x=mean_ability, line_dash="dash", line_color="red", line_width=2,
                              annotation_text=f"能力平均: {mean_ability:.1f}%",
                              annotation_position="top")
                
                st.plotly_chart(fig3, use_container_width=True)
                
                corr = df[[ability_col, domain_col]].corr().iloc[0, 1]
                
                # 相関係数と平均値の情報を表示
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("相関係数", f"{corr:.3f}")
                with col2:
                    st.metric(f"能力平均 ({ABILITY_LABELS[selected_ability]})", f"{mean_ability:.1f}%")
                with col3:
                    st.metric(f"領域平均 ({DOMAIN_LABELS[selected_domain]})", f"{mean_domain:.1f}%")
    
    except Exception as e:
        st.error(f"エラーが発生しました: {str(e)}")
        st.info("CSVファイルの形式を確認してください")
        import traceback
        st.code(traceback.format_exc())

# フッター
st.markdown("---")
st.markdown("*拡張版 - 学力データ分析ダッシュボード with 能力・領域パラメータ*")
