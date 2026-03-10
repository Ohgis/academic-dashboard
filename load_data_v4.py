"""
load_data_v4.py
CSVファイルを Supabase PostgreSQL にアップロードするスクリプト。
ローカルで1回だけ実行してください。

使い方:
    python load_data_v4.py

事前に .env ファイルか環境変数に以下を設定してください:
    V4_DB_HOST / V4_DB_PORT / V4_DB_NAME / V4_DB_USER / V4_DB_PASSWORD

または、スクリプト下部の CONNECTION 変数を直接書き換えてもOKです。
"""

import os
import sys
import pandas as pd
import psycopg2
from psycopg2.extras import execute_values

# ─── 接続設定 ─────────────────────────────────────────
# .env から読む場合は python-dotenv をインストール:
#   pip install python-dotenv
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

CONNECTION = dict(
    host     = os.getenv("V4_DB_HOST",     "aws-1-ap-northeast-1.pooler.supabase.com"),
    port     = int(os.getenv("V4_DB_PORT", "5432")),
    dbname   = os.getenv("V4_DB_NAME",     "postgres"),
    user     = os.getenv("V4_DB_USER",     "postgres.ditvtgclnxpmqhjkqmim"),
    password = os.getenv("V4_DB_PASSWORD", "m7@&jdeD/C7+T$x"),
)

# ─── CSVファイルパス ───────────────────────────────────
# スクリプトと同じフォルダにCSVを置くか、絶対パスで指定
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

CSV_FILES = {
    "test_results":     os.path.join(BASE_DIR, "test_results.csv"),
    "question_master":  os.path.join(BASE_DIR, "question_master.csv"),
    "attitude_results": os.path.join(BASE_DIR, "attitude_results.csv"),
    "attitude_master":  os.path.join(BASE_DIR, "attitude_master.csv"),
}

# ─── テーブル定義（列順・型）──────────────────────────
TABLE_CONFIGS = {
    "test_results": {
        "columns": ["student_id", "school", "class_id", "student_no",
                    "subject", "question_id", "correct"],
        "dtypes": {
            "student_id": str, "school": str,
            "class_id": int,   "student_no": int,
            "subject": str,    "question_id": str,
            "correct": int,
        },
        "has_serial_id": True,   # id列はDBが自動採番
    },
    "question_master": {
        "columns": ["question_id", "subject", "大領域", "中領域", "観点",
                    "知識理解", "資質能力", "全国値", "困難度", "解答形式"],
        "dtypes": {
            "question_id": str, "subject": str,
            "大領域": "Int64",  "中領域": "Int64",
            "観点": "Int64",    "知識理解": float,
            "資質能力": float,  "全国値": "Int64",
            "困難度": float,    "解答形式": "Int64",
        },
        "has_serial_id": False,
    },
    "attitude_results": {
        "columns": ["student_id", "school", "class_id", "student_no",
                    "subject", "question_id", "score"],
        "dtypes": {
            "student_id": str, "school": str,
            "class_id": int,   "student_no": int,
            "subject": str,    "question_id": str,
            "score": int,
        },
        "has_serial_id": True,
    },
    "attitude_master": {
        "columns": ["question_id", "subject", "全国値"],
        "dtypes": {
            "question_id": str, "subject": str, "全国値": "Int64",
        },
        "has_serial_id": False,
    },
}

# ─── アップロード関数 ────────────────────────────────
def upload_table(conn, table_name: str, csv_path: str, config: dict):
    print(f"\n{'='*50}")
    print(f"📤 {table_name} をアップロード中...")

    # CSV読み込み
    df = pd.read_csv(csv_path, dtype=str)  # まず全部strで読む
    df.columns = df.columns.str.strip()    # BOMや空白除去

    # 必要列だけ選択
    cols = config["columns"]
    missing = [c for c in cols if c not in df.columns]
    if missing:
        print(f"  ❌ 列が見つかりません: {missing}")
        print(f"     CSVの列: {list(df.columns)}")
        return False

    df = df[cols].copy()

    # 型変換
    for col, dtype in config["dtypes"].items():
        if col not in df.columns:
            continue
        try:
            if dtype == float:
                df[col] = pd.to_numeric(df[col], errors="coerce")
            elif dtype in (int, "Int64"):
                df[col] = pd.to_numeric(df[col], errors="coerce").astype("Int64")
            else:
                df[col] = df[col].fillna("").astype(str)
        except Exception as e:
            print(f"  ⚠️  {col} の型変換エラー: {e}")

    # NaN → None（PostgreSQL の NULL）
    df = df.where(pd.notnull(df), None)

    print(f"  行数: {len(df):,}  列数: {len(df.columns)}")

    # INSERT
    with conn.cursor() as cur:
        # 既存データを削除（TRUNCATE で高速）
        cur.execute(f'DELETE FROM "{table_name}"')
        conn.commit()
        print(f"  🗑️  既存データを削除しました ({cur.rowcount} 件)")

        # numpy型 → Python ネイティブ型に変換（psycopg2対応）
        def to_native(v):
            if v is None:
                return None
            import numpy as np
            if isinstance(v, (np.integer,)):  return int(v)
            if isinstance(v, (np.floating,)): return float(v)
            if isinstance(v, float) and __import__('math').isnan(v): return None
            return v

        records = [
            tuple(to_native(v) for v in row)
            for row in df.itertuples(index=False, name=None)
        ]
        quoted_cols = ", ".join(f'"{c}"' for c in cols)
        sql = f'INSERT INTO "{table_name}" ({quoted_cols}) VALUES %s'

        batch_size = 1000
        total = len(records)
        inserted = 0
        for i in range(0, total, batch_size):
            batch = records[i:i + batch_size]
            execute_values(cur, sql, batch)
            inserted += len(batch)
            pct = inserted / total * 100
            print(f"  📥 {inserted:,}/{total:,} 件 ({pct:.0f}%)", end="\r")

        conn.commit()
        print(f"\n  ✅ {inserted:,} 件をINSERTしました")

    return True


# ─── 件数確認 ────────────────────────────────────────
def verify_counts(conn):
    print(f"\n{'='*50}")
    print("📊 アップロード結果確認")
    with conn.cursor() as cur:
        for table in TABLE_CONFIGS:
            cur.execute(f'SELECT COUNT(*) FROM "{table}"')
            count = cur.fetchone()[0]
            print(f"  {table:25s}: {count:>8,} 件")


# ─── メイン ─────────────────────────────────────────
def main():
    # CSV存在チェック
    print("📁 CSVファイル確認中...")
    all_ok = True
    for table, path in CSV_FILES.items():
        exists = os.path.exists(path)
        print(f"  {'✅' if exists else '❌'} {table}: {path}")
        if not exists:
            all_ok = False

    if not all_ok:
        print("\n❌ 見つからないCSVがあります。パスを確認してください。")
        sys.exit(1)

    # DB接続
    print(f"\n🔌 Supabase に接続中... ({CONNECTION['host']})")
    try:
        conn = psycopg2.connect(**CONNECTION)
        print("  ✅ 接続成功")
    except Exception as e:
        print(f"  ❌ 接続失敗: {e}")
        sys.exit(1)

    # アップロード順序（外部キー依存に注意: masterを先に）
    upload_order = [
        "question_master",
        "attitude_master",
        "test_results",
        "attitude_results",
    ]

    success_all = True
    for table in upload_order:
        ok = upload_table(conn, table, CSV_FILES[table], TABLE_CONFIGS[table])
        if not ok:
            success_all = False

    # 件数確認
    verify_counts(conn)
    conn.close()

    print(f"\n{'='*50}")
    if success_all:
        print("🎉 全テーブルのアップロードが完了しました！")
    else:
        print("⚠️  一部テーブルでエラーが発生しました。ログを確認してください。")


if __name__ == "__main__":
    main()
