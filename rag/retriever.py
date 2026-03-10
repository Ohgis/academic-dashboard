"""
rag/retriever.py
Supabase pgvector による類似度検索（psycopg2直接接続）
"""

import psycopg2
from openai import OpenAI
import streamlit as st

EMBEDDING_MODEL = "text-embedding-3-small"
TOP_K = 5


def _get_conn():
    return psycopg2.connect(
        host=st.secrets["V4_DB_HOST"],
        port=st.secrets["V4_DB_PORT"],
        dbname=st.secrets["V4_DB_NAME"],
        user=st.secrets["V4_DB_USER"],
        password=st.secrets["V4_DB_PASSWORD"],
    )


def retrieve(query: str) -> list[dict]:
    """
    クエリに対してコサイン類似度でtop-k件のチャンクを返す。

    Returns:
        [{"id": str, "source": str, "page": int, "content": str, "similarity": float}]
    """
    openai_client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])

    # クエリをEmbedding
    response = openai_client.embeddings.create(
        model=EMBEDDING_MODEL,
        input=query,
    )
    query_embedding = response.data[0].embedding

    conn = _get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, source, page, content,
                       1 - (embedding <=> %s::vector) AS similarity
                FROM rag_documents
                ORDER BY embedding <=> %s::vector
                LIMIT %s
                """,
                (str(query_embedding), str(query_embedding), TOP_K),
            )
            rows = cur.fetchall()
    finally:
        conn.close()

    return [
        {
            "id": str(row[0]),
            "source": row[1],
            "page": row[2],
            "content": row[3],
            "similarity": float(row[4]),
        }
        for row in rows
    ]
