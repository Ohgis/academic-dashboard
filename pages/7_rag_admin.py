"""
pages/7_rag_admin.py
RAG管理者画面（PDF取り込み・ドキュメント管理）
"""

import tempfile
from pathlib import Path

import streamlit as st

# ─── ページ設定 ───────────────────────────────────────────────
st.set_page_config(
    page_title="RAG 管理者画面",
    page_icon="🛠️",
    layout="centered",
)

# ─── パスワード認証 ───────────────────────────────────────────
def _check_admin_auth() -> bool:
    if st.session_state.get("rag_admin_authed"):
        return True

    st.title("🛠️ RAG 管理者画面")
    st.caption("このページは管理者専用です")
    pwd = st.text_input("管理者パスワードを入力してください", type="password", key="admin_pwd_input")
    if st.button("ログイン"):
        correct = st.secrets.get("auth", {}).get("admin_password", "")
        if pwd == correct:
            st.session_state["rag_admin_authed"] = True
            st.rerun()
        else:
            st.error("パスワードが違います")
    return False


if not _check_admin_auth():
    st.stop()

# ─── ここから管理者向けUI ─────────────────────────────────────
from rag.ingest import ingest_pdf, ingest_json, ingest_text, delete_document, list_documents

st.title("🛠️ RAG 管理者画面")

# ─── タブ構成 ─────────────────────────────────────────────────
tab_upload, tab_list = st.tabs(["📤 ファイルアップロード", "📋 ドキュメント一覧"])

# =============================================
# Tab 1: PDFアップロード＆取り込み
# =============================================
with tab_upload:
    st.subheader("ファイルをアップロードしてインデックス化")

    uploaded_file = st.file_uploader(
        "PDF または JSON ファイルを選択してください",
        type=["pdf", "json", "txt"],
        help="複数ファイルを取り込む場合は1ファイルずつアップロードしてください",
    )

    if uploaded_file is not None:
        st.info(f"選択中: **{uploaded_file.name}** ({uploaded_file.size:,} bytes)")

        if st.button("📥 インデックス化を開始", use_container_width=True, type="primary"):
            status_text = st.empty()
            progress_bar = st.progress(0.0)

            def progress_callback(message: str, percent: float):
                status_text.write(f"⏳ {message}")
                progress_bar.progress(min(percent, 1.0))

            ext = Path(uploaded_file.name).suffix.lower()
            suffix = ext if ext in [".pdf", ".json", ".txt"] else ".tmp"

            with tempfile.NamedTemporaryFile(
                delete=False, suffix=suffix, prefix="rag_upload_"
            ) as tmp:
                tmp.write(uploaded_file.getbuffer())
                tmp_path = tmp.name

            try:
                if ext == ".json":
                    result = ingest_json(
                        tmp_path,
                        source_name=uploaded_file.name,
                        progress_callback=progress_callback,
                    )
                elif ext == ".txt":
                    result = ingest_text(
                        tmp_path,
                        source_name=uploaded_file.name,
                        progress_callback=progress_callback,
                    )
                else:
                    result = ingest_pdf(
                        tmp_path,
                        source_name=uploaded_file.name,
                        progress_callback=progress_callback,
                    )

                if result["status"] == "success":
                    progress_bar.progress(1.0)
                    status_text.empty()
                    st.success(
                        f"✅ 取り込み完了！　"
                        f"**{uploaded_file.name}** を {result['chunks']} チャンクに分割して登録しました。"
                    )
                else:
                    st.error(f"❌ エラー: {result.get('message', '不明なエラー')}")
            except Exception as e:
                st.error(f"❌ 処理中にエラーが発生しました: {e}")
            finally:
                os.unlink(tmp_path)

# =============================================
# Tab 2: ドキュメント一覧
# =============================================
with tab_list:
    st.subheader("登録済みドキュメント一覧")

    if st.button("🔄 最新情報に更新"):
        st.rerun()

    docs = list_documents()

    if not docs:
        st.info("まだドキュメントが登録されていません。")
    else:
        for doc in docs:
            col1, col2, col3 = st.columns([4, 2, 2])
            with col1:
                st.write(f"📄 **{doc['source']}**")
                ingested = doc["ingested_at"][:10] if doc["ingested_at"] else "不明"
                st.caption(f"登録日: {ingested}")
            with col2:
                st.metric("チャンク数", doc["chunk_count"])
            with col3:
                if st.button("🗑️ 削除", key=f"del_{doc['source']}", type="secondary"):
                    st.session_state[f"confirm_delete_{doc['source']}"] = True

            # 削除確認
            if st.session_state.get(f"confirm_delete_{doc['source']}"):
                st.warning(f"**{doc['source']}** を削除してよろしいですか？")
                c1, c2 = st.columns(2)
                with c1:
                    if st.button("はい、削除する", key=f"yes_{doc['source']}", type="primary"):
                        delete_document(doc["source"])
                        st.session_state.pop(f"confirm_delete_{doc['source']}", None)
                        st.success(f"✅ {doc['source']} を削除しました")
                        st.rerun()
                with c2:
                    if st.button("キャンセル", key=f"no_{doc['source']}"):
                        st.session_state.pop(f"confirm_delete_{doc['source']}", None)
                        st.rerun()

            st.divider()
