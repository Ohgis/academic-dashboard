"""
rag/generator.py
プロンプト構築 + gpt-4o-mini 呼び出し
"""

from openai import OpenAI
import streamlit as st

LLM_MODEL = "gpt-4o-mini"

SYSTEM_PROMPT = """あなたは社内マニュアルに関する質問に答えるアシスタントです。
以下のルールを厳守してください。

1. 回答は必ず提供された【参考情報】のみを根拠にしてください。
2. 【参考情報】に回答の根拠がない場合は「マニュアルに記載がありません」と明示してください。
3. 回答は日本語で行ってください。
4. 情報の出典（ファイル名・ページ番号）は回答末尾に「出典: ファイル名 p.X」の形式で記載してください。
5. 推測や一般論で補完することは避けてください。"""


def build_context(chunks: list[dict]) -> str:
    """検索チャンクをプロンプト用テキストに変換"""
    parts = []
    for i, chunk in enumerate(chunks, 1):
        parts.append(
            f"[{i}] 出典: {chunk['source']} p.{chunk['page']}\n{chunk['content']}"
        )
    return "\n\n".join(parts)


def generate(
    query: str,
    chunks: list[dict],
    history: list[dict] | None = None,
) -> str:
    """
    RAG回答を生成する。

    Args:
        query: ユーザーの質問
        chunks: retriever.retrieve() の返り値
        history: OpenAI messages形式の会話履歴（systemメッセージを除く）

    Returns:
        回答テキスト
    """
    openai_client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])

    context = build_context(chunks)

    user_message = f"""【参考情報】
{context}

【質問】
{query}"""

    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    if history:
        messages.extend(history)
    messages.append({"role": "user", "content": user_message})

    response = openai_client.chat.completions.create(
        model=LLM_MODEL,
        messages=messages,
        max_tokens=1000,
        temperature=0.0,
    )

    return response.choices[0].message.content
