"""
rag/ingest.py
PDF・JSON取り込み → チャンク分割 → Embedding → Supabase(psycopg2)格納
"""

import base64
import json
from pathlib import Path

import fitz  # PyMuPDF
import psycopg2
from openai import OpenAI
from langchain_text_splitters import RecursiveCharacterTextSplitter
import streamlit as st

CHUNK_SIZE = 512
CHUNK_OVERLAP = 64
EMBEDDING_MODEL = "text-embedding-3-small"


def _get_conn():
    """psycopg2接続を返す（secrets.tomlから読み込み）"""
    return psycopg2.connect(
        host=st.secrets["V4_DB_HOST"],
        port=st.secrets["V4_DB_PORT"],
        dbname=st.secrets["V4_DB_NAME"],
        user=st.secrets["V4_DB_USER"],
        password=st.secrets["V4_DB_PASSWORD"],
    )


def _get_openai_client() -> OpenAI:
    return OpenAI(api_key=st.secrets["OPENAI_API_KEY"])


def _extract_images_text(page: fitz.Page, openai_client: OpenAI) -> str:
    """ページ内の画像をGPT-4o Visionでテキスト化して返す"""
    image_texts = []
    for img in page.get_images(full=True):
        xref = img[0]
        base_image = page.parent.extract_image(xref)
        image_bytes = base_image["image"]
        ext = base_image["ext"]
        mime = "image/jpeg" if ext == "jpg" else f"image/{ext}"
        b64 = base64.b64encode(image_bytes).decode("utf-8")
        try:
            response = openai_client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image_url",
                                "image_url": {"url": f"data:{mime};base64,{b64}"},
                            },
                            {
                                "type": "text",
                                "text": (
                                    "この画像に含まれるテキストや図表の内容を、"
                                    "日本語で詳しく説明してください。"
                                    "テキストがある場合はそのまま書き起こしてください。"
                                ),
                            },
                        ],
                    }
                ],
                max_tokens=1000,
            )
            image_texts.append(response.choices[0].message.content)
        except Exception as e:
            image_texts.append(f"[画像テキスト化エラー: {e}]")
    return "\n".join(image_texts)


def _embed_texts(texts: list[str], openai_client: OpenAI) -> list[list[float]]:
    """テキストリストをまとめてEmbedding"""
    response = openai_client.embeddings.create(
        model=EMBEDDING_MODEL,
        input=texts,
    )
    return [item.embedding for item in response.data]


def _insert_chunks(all_chunks: list[dict], embeddings: list[list[float]]) -> None:
    """チャンクとEmbeddingをSupabaseに格納する共通処理"""
    conn = _get_conn()
    try:
        with conn.cursor() as cur:
            for chunk, emb in zip(all_chunks, embeddings):
                cur.execute(
                    """
                    INSERT INTO rag_documents
                        (source, page, chunk_index, content, embedding)
                    VALUES (%s, %s, %s, %s, %s::vector)
                    """,
                    (
                        chunk["source"],
                        chunk["page"],
                        chunk["chunk_index"],
                        chunk["content"],
                        str(emb),
                    ),
                )
        conn.commit()
    finally:
        conn.close()


def ingest_pdf(pdf_path: str | Path, source_name: str, progress_callback=None) -> dict:
    """
    PDFを取り込んでSupabaseに格納する。

    Args:
        pdf_path: PDFファイルのパス
        source_name: 保存するファイル名（元のアップロード名）
        progress_callback: 進捗コールバック (message: str, percent: float)

    Returns:
        {"status": "success", "source": str, "chunks": int}
    """
    pdf_path = Path(pdf_path)
    openai_client = _get_openai_client()
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
    )

    def _progress(msg: str, pct: float = 0.0):
        if progress_callback:
            progress_callback(msg, pct)

    _progress("PDFを開いています...", 0.0)
    doc = fitz.open(str(pdf_path))
    total_pages = len(doc)
    all_chunks = []

    for page_num in range(total_pages):
        pct = 0.1 + (page_num / total_pages) * 0.5
        _progress(f"ページ {page_num + 1}/{total_pages} を処理中...", pct)

        page = doc[page_num]
        text = page.get_text("text")
        image_text = _extract_images_text(page, openai_client)
        full_text = text
        if image_text.strip():
            full_text += f"\n[画像内容]\n{image_text}"

        if not full_text.strip():
            continue

        chunks = splitter.split_text(full_text)
        for idx, chunk in enumerate(chunks):
            all_chunks.append(
                {
                    "source": source_name,
                    "page": page_num + 1,
                    "chunk_index": idx,
                    "content": chunk,
                }
            )

    doc.close()

    if not all_chunks:
        return {"status": "error", "message": "テキストを抽出できませんでした"}

    _progress("Embeddingを生成中...", 0.65)

    BATCH = 100
    texts = [c["content"] for c in all_chunks]
    embeddings = []
    for i in range(0, len(texts), BATCH):
        batch_embeddings = _embed_texts(texts[i : i + BATCH], openai_client)
        embeddings.extend(batch_embeddings)
        pct = 0.65 + (min(i + BATCH, len(texts)) / len(texts)) * 0.25
        _progress(f"Embedding生成中... ({min(i+BATCH, len(texts))}/{len(texts)})", pct)

    _progress("Supabaseに保存中...", 0.92)
    _insert_chunks(all_chunks, embeddings)

    _progress("完了！", 1.0)
    return {"status": "success", "source": source_name, "chunks": len(all_chunks)}


def ingest_json(json_path: str | Path, source_name: str, progress_callback=None) -> dict:
    """
    FAQ形式のJSONを取り込んでSupabaseに格納する。
    1つのquestion+answerセットを1チャンクとして扱う。

    Args:
        json_path: JSONファイルのパス
        source_name: 保存するファイル名（元のアップロード名）
        progress_callback: 進捗コールバック (message: str, percent: float)

    Returns:
        {"status": "success", "source": str, "chunks": int}
    """
    def _progress(msg: str, pct: float = 0.0):
        if progress_callback:
            progress_callback(msg, pct)

    _progress("JSONを読み込んでいます...", 0.0)

    with open(json_path, encoding="utf-8") as f:
        data = json.load(f)

    # JSONの構造を自動判定してチャンク化
    # 対応形式1: [{"category": ..., "items": [{"question": ..., "answer": ..., "url": ...}]}]
    # 対応形式2: [{"QUESTION": ..., "ANSWER": ..., "CATEGORY_ID": ...}]（フラット形式）
    all_chunks = []
    chunk_index = 0

    # 形式1の判定：最初の要素に "items" キーがあるかどうか
    is_nested = isinstance(data, list) and len(data) > 0 and "items" in data[0]

    if is_nested:
        for category in data:
            category_name = category.get("category", "")
            for item in category.get("items", []):
                question = item.get("question", "")
                answer = item.get("answer", "")
                url = item.get("url", "")
                content = f"【カテゴリ】{category_name}\n【質問】{question}\n【回答】{answer}"
                if url:
                    content += f"\n【URL】{url}"
                all_chunks.append({
                    "source": source_name,
                    "page": 1,
                    "chunk_index": chunk_index,
                    "content": content,
                })
                chunk_index += 1
    else:
        # フラット形式（大文字キー対応）
        for item in data:
            question = item.get("QUESTION") or item.get("question", "")
            answer = item.get("ANSWER") or item.get("answer", "")
            category_id = item.get("CATEGORY_ID", "")
            content = f"【質問】{question}\n【回答】{answer}"
            if category_id:
                content = f"【カテゴリID】{category_id}\n" + content
            all_chunks.append({
                "source": source_name,
                "page": 1,
                "chunk_index": chunk_index,
                "content": content,
            })
            chunk_index += 1

    if not all_chunks:
        return {"status": "error", "message": "チャンクを生成できませんでした"}

    _progress("Embeddingを生成中...", 0.4)

    openai_client = _get_openai_client()
    BATCH = 100
    texts = [c["content"] for c in all_chunks]
    embeddings = []
    for i in range(0, len(texts), BATCH):
        batch_embeddings = _embed_texts(texts[i : i + BATCH], openai_client)
        embeddings.extend(batch_embeddings)
        pct = 0.4 + (min(i + BATCH, len(texts)) / len(texts)) * 0.5
        _progress(f"Embedding生成中... ({min(i+BATCH, len(texts))}/{len(texts)})", pct)

    _progress("Supabaseに保存中...", 0.92)
    _insert_chunks(all_chunks, embeddings)

    _progress("完了！", 1.0)
    return {"status": "success", "source": source_name, "chunks": len(all_chunks)}



def ingest_text(text_path: str | Path, source_name: str, progress_callback=None) -> dict:
    """
    テキストファイルを取り込んでSupabaseに格納する。
    RecursiveCharacterTextSplitterでチャンク分割する。

    Args:
        text_path: テキストファイルのパス
        source_name: 保存するファイル名（元のアップロード名）
        progress_callback: 進捗コールバック (message: str, percent: float)

    Returns:
        {"status": "success", "source": str, "chunks": int}
    """
    def _progress(msg: str, pct: float = 0.0):
        if progress_callback:
            progress_callback(msg, pct)

    _progress("テキストファイルを読み込んでいます...", 0.0)

    with open(text_path, encoding="utf-8") as f:
        full_text = f.read()

    if not full_text.strip():
        return {"status": "error", "message": "テキストを抽出できませんでした"}

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
    )
    chunks = splitter.split_text(full_text)

    all_chunks = [
        {
            "source": source_name,
            "page": 1,
            "chunk_index": idx,
            "content": chunk,
        }
        for idx, chunk in enumerate(chunks)
    ]

    _progress("Embeddingを生成中...", 0.4)

    openai_client = _get_openai_client()
    BATCH = 100
    texts = [c["content"] for c in all_chunks]
    embeddings = []
    for i in range(0, len(texts), BATCH):
        batch_embeddings = _embed_texts(texts[i : i + BATCH], openai_client)
        embeddings.extend(batch_embeddings)
        pct = 0.4 + (min(i + BATCH, len(texts)) / len(texts)) * 0.5
        _progress(f"Embedding生成中... ({min(i+BATCH, len(texts))}/{len(texts)})", pct)

    _progress("Supabaseに保存中...", 0.92)
    _insert_chunks(all_chunks, embeddings)

    _progress("完了！", 1.0)
    return {"status": "success", "source": source_name, "chunks": len(all_chunks)}


def delete_document(source_name: str) -> None:
    """指定ファイル名のチャンクをSupabaseから削除"""
    conn = _get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM rag_documents WHERE source = %s",
                (source_name,),
            )
        conn.commit()
    finally:
        conn.close()


def list_documents() -> list[dict]:
    """
    登録済みドキュメントの一覧を返す。
    Returns: [{"source": str, "chunk_count": int, "ingested_at": str}]
    """
    conn = _get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT source, COUNT(*) as chunk_count, MAX(ingested_at) as ingested_at
                FROM rag_documents
                GROUP BY source
                ORDER BY MAX(ingested_at) DESC
                """
            )
            rows = cur.fetchall()
    finally:
        conn.close()

    return [
        {
            "source": row[0],
            "chunk_count": row[1],
            "ingested_at": str(row[2])[:10] if row[2] else "不明",
        }
        for row in rows
    ]
