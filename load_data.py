"""
データ投入スクリプト: CSVからPostgreSQLへ
実行: python load_data.py
"""
import pandas as pd
import psycopg2
from psycopg2.extras import execute_values
import os
from dotenv import load_dotenv

load_dotenv()

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": os.getenv("DB_PORT", 5432),
    "database": os.getenv("DB_NAME"),
    "user": os.getenv("DB_USER"),
    "password": os.getenv("DB_PASSWORD"),
}


def load_item_params(conn, item_params_path: str):
    """item_params.csv を item_params テーブルへ投入"""
    df = pd.read_csv(item_params_path, index_col=0)
    # df の行: domain, ability  / 列: x1〜x32
    records = []
    for col in df.columns:
        item_no = int(col.replace("x", ""))
        domain = int(df.loc["domain", col])
        ability = str(df.loc["ability", col])
        records.append((item_no, domain, ability))

    with conn.cursor() as cur:
        execute_values(
            cur,
            "INSERT INTO item_params (item_no, domain, ability) VALUES %s ON CONFLICT (item_no) DO UPDATE SET domain=EXCLUDED.domain, ability=EXCLUDED.ability",
            records,
        )
    conn.commit()
    print(f"item_params: {len(records)} 件投入")


def load_test_responses(conn, test_data_path: str, test_date: str = "2024-04-01"):
    """test_dummy_data2.csv を students / test_responses テーブルへ投入"""
    df = pd.read_csv(test_data_path)
    item_cols = [c for c in df.columns if c.startswith("x")]

    student_records = []
    response_records = []

    for _, row in df.iterrows():
        student_id = row["ID"]
        grade = int(row["grade"])
        class_ = str(row["class"])
        subject = str(row["subject"])

        student_records.append((student_id, grade, class_))

        for col in item_cols:
            item_no = int(col.replace("x", ""))
            response = int(row[col])
            response_records.append((student_id, subject, test_date, item_no, response))

    with conn.cursor() as cur:
        # 生徒マスタ
        execute_values(
            cur,
            "INSERT INTO students (student_id, grade, class) VALUES %s ON CONFLICT (student_id) DO NOTHING",
            student_records,
        )
        # 回答データ
        execute_values(
            cur,
            "INSERT INTO test_responses (student_id, subject, test_date, item_no, response) VALUES %s ON CONFLICT DO NOTHING",
            response_records,
        )
    conn.commit()
    print(f"students: {len(student_records)} 件 / test_responses: {len(response_records)} 件投入")


if __name__ == "__main__":
    conn = psycopg2.connect(**DB_CONFIG)
    load_item_params(conn, "item_params.csv")
    load_test_responses(conn, "test_dummy_data2.csv")
    conn.close()
    print("完了")
