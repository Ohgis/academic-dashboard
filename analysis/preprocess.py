"""
preprocess.py
-------------
sampledata.csv（日本語列名・BOM付UTF-8）を
R で読めるシンプルなCSVに変換する前処理スクリプト。

出力:
  sampledata_eng.csv   --- R分析用（英語列名、正誤のみ）
  attitude_data.csv    --- 態度点（アンケート）
"""

import pandas as pd
import re
import sys
from pathlib import Path

# ── 設定 ─────────────────────────────────────────────────────────────────────
SUBJECTS = [
    ("国",  "kokugo"),
    ("社",  "shakai"),
    ("数",  "sugaku"),
    ("B理", "rika"),
    ("英",  "eigo"),
]

def get_correct_cols(df, prefix):
    """正誤列（0/1）のみ: 態度・Unnamedを除く"""
    pat = re.compile(rf"^{re.escape(prefix)}\d+$")
    return [c for c in df.columns if pat.match(c)]

def get_attitude_cols(df, prefix):
    """態度点列（〇態〇）"""
    pat = re.compile(rf"^{re.escape(prefix)}態\d+$")
    return [c for c in df.columns if pat.match(c)]

# ── 読み込み ──────────────────────────────────────────────────────────────────
csv_path = sys.argv[1] if len(sys.argv) > 1 else "sampledata.csv"
df = pd.read_csv(csv_path, encoding="utf-8-sig")
print(f"読み込み: {csv_path}  ({len(df)}名, {len(df.columns)}列)")

# ── 正誤データ変換 ────────────────────────────────────────────────────────────
parts = [df[["学校名", "組", "出席番号"]].rename(
    columns={"学校名": "school", "組": "class_id", "出席番号": "student_no"}
)]
subject_info = {}   # subject_eng -> list of item column names

for prefix, eng in SUBJECTS:
    cols = get_correct_cols(df, prefix)
    if not cols:
        print(f"  警告: {prefix} の正誤列が見つかりません")
        continue

    sub = df[cols].copy()
    # 列名を kokugo_1, kokugo_2 ... に変換（元の問番号を保持）
    rename = {}
    for c in cols:
        num = re.sub(rf"^{re.escape(prefix)}", "", c)
        rename[c] = f"{eng}_{num}"
    sub = sub.rename(columns=rename)
    parts.append(sub)
    subject_info[eng] = list(rename.values())
    print(f"  {eng:8s}: {len(cols)}問")

test_df = pd.concat(parts, axis=1)
out_test = Path(csv_path).stem + "_eng.csv"
test_df.to_csv(out_test, index=False)
print(f"\n正誤データ保存: {out_test}  ({len(test_df)}行, {len(test_df.columns)}列)")

# ── 態度点データ変換 ──────────────────────────────────────────────────────────
att_parts = [df[["学校名", "組", "出席番号"]].rename(
    columns={"学校名": "school", "組": "class_id", "出席番号": "student_no"}
)]

for prefix, eng in SUBJECTS:
    cols = get_attitude_cols(df, prefix)
    if not cols:
        continue

    sub = df[cols].copy()
    rename = {}
    for c in cols:
        num = re.sub(rf"^{re.escape(prefix)}態", "", c)
        rename[c] = f"{eng}_att_{num}"
    sub = sub.rename(columns=rename)
    att_parts.append(sub)
    print(f"  {eng:8s} 態度点: {len(cols)}問")

att_df = pd.concat(att_parts, axis=1)
att_df.to_csv("attitude_data.csv", index=False)
print(f"態度点データ保存: attitude_data.csv  ({len(att_df)}行, {len(att_df.columns)}列)")

# ── メタ情報を出力（Rスクリプトが参照） ───────────────────────────────────────
import json
meta = {s: {"cols": cols, "n_items": len(cols)} for s, cols in subject_info.items()}
with open("subject_meta.json", "w") as f:
    json.dump(meta, f, indent=2)
print("メタ情報保存: subject_meta.json")
