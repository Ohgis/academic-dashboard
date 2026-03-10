"""
pages/6_rag_chat.py
RAGチャット画面（一般ユーザー向け）
"""

import streamlit as st

# ─── ページ設定 ───────────────────────────────────────────────
st.set_page_config(
    page_title="社内マニュアル Q&A",
    page_icon="💬",
    layout="centered",
)

# ─── パスワード認証 ───────────────────────────────────────────
def _check_auth() -> bool:
    if st.session_state.get("rag_user_authed"):
        return True

    st.title("💬 社内マニュアル Q&A")
    st.caption("このページはパスワードが必要です")
    pwd = st.text_input("パスワードを入力してください", type="password", key="user_pwd_input")
    if st.button("ログイン"):
        correct = st.secrets.get("auth", {}).get("user_password", "")
        if pwd == correct:
            st.session_state["rag_user_authed"] = True
            st.rerun()
        else:
            st.error("パスワードが違います")
    return False


if not _check_auth():
    st.stop()

# ─── ここから認証済みユーザー向けUI ──────────────────────────
from rag.retriever import retrieve
from rag.generator import generate

st.title("💬 社内マニュアル Q&A")
st.caption("社内マニュアルに関する質問にお答えします。")

# セッション初期化
if "rag_messages" not in st.session_state:
    st.session_state["rag_messages"] = []  # {"role", "content", "sources"}

# 会話履歴を表示
for msg in st.session_state["rag_messages"]:
    with st.chat_message(msg["role"]):
        st.write(msg["content"])
        if msg.get("sources"):
            with st.expander("📄 出典"):
                for s in msg["sources"]:
                    st.caption(f"• {s['source']}  p.{s['page']}  （類似度: {s['similarity']:.2f}）")

# 入力フォーム
if query := st.chat_input("質問を入力してください"):
    # ユーザーメッセージを表示 & 保存
    with st.chat_message("user"):
        st.write(query)
    st.session_state["rag_messages"].append({"role": "user", "content": query})

    # 検索 & 生成
    with st.chat_message("assistant"):
        with st.spinner("検索中..."):
            chunks = retrieve(query)

        if not chunks:
            answer = "関連するマニュアル情報が見つかりませんでした。"
            sources = []
        else:
            with st.spinner("回答を生成中..."):
                # 会話履歴（system以外）を渡す
                history = [
                    {"role": m["role"], "content": m["content"]}
                    for m in st.session_state["rag_messages"][:-1]  # 最後のuser発言は既にqueryに含まれる
                ]
                answer = generate(query, chunks, history=history)
            sources = [
                {"source": c["source"], "page": c["page"], "similarity": c["similarity"]}
                for c in chunks
            ]

        st.write(answer)
        if sources:
            with st.expander("📄 出典"):
                for s in sources:
                    st.caption(f"• {s['source']}  p.{s['page']}  （類似度: {s['similarity']:.2f}）")

    # アシスタントメッセージを保存
    st.session_state["rag_messages"].append(
        {"role": "assistant", "content": answer, "sources": sources}
    )

# 会話クリアボタン
if st.session_state["rag_messages"]:
    st.divider()
    if st.button("🗑️ 会話をクリア", use_container_width=False):
        st.session_state["rag_messages"] = []
        st.rerun()
