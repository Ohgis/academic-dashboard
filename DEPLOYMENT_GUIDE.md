# Streamlit Community Cloud デプロイ完全ガイド

## 📦 準備するファイル

以下の3つのファイルをGitHubにアップロードします：

1. **dashboard_app_v2.py** - メインアプリケーション
2. **requirements.txt** - 必要なPythonライブラリ
3. **README.md** - プロジェクト説明（任意）

---

## 🔧 ステップ1: GitHubリポジトリの作成

### 1-1. GitHubにログイン
https://github.com にアクセスしてログイン

### 1-2. 新しいリポジトリを作成
1. 右上の「+」→「New repository」をクリック
2. リポジトリ名を入力（例: `academic-data-dashboard`）
3. Public または Private を選択
   - **Public**: 誰でもコードを見られる（無料で使える）
   - **Private**: 自分だけがコードを見られる（Streamlit Community Cloudで使う場合も無料）
4. 「Create repository」をクリック

### 1-3. ファイルをアップロード
方法A: Webブラウザから直接アップロード
1. 「uploading an existing file」をクリック
2. 以下のファイルをドラッグ&ドロップ：
   - dashboard_app_v2.py
   - requirements.txt
   - README.md（任意）
3. 「Commit changes」をクリック

方法B: Gitコマンドを使う（Git経験者向け）
```bash
git init
git add dashboard_app_v2.py requirements.txt README.md
git commit -m "Initial commit"
git remote add origin https://github.com/あなたのユーザー名/リポジトリ名.git
git push -u origin main
```

---

## 🚀 ステップ2: Streamlit Community Cloudでデプロイ

### 2-1. Streamlit Community Cloudにサインアップ
1. https://streamlit.io/cloud にアクセス
2. 「Sign up」→「Continue with GitHub」をクリック
3. GitHubアカウントで認証

### 2-2. 新しいアプリをデプロイ
1. ダッシュボードで「New app」をクリック
2. 以下を入力：
   - **Repository**: 先ほど作成したリポジトリを選択（例: `yourname/academic-data-dashboard`）
   - **Branch**: `main` （または `master`）
   - **Main file path**: `dashboard_app_v2.py`
3. 「Advanced settings」（任意）
   - Python version: 3.9 または 3.10 を推奨
4. 「Deploy!」をクリック

### 2-3. デプロイ完了を待つ
- 初回デプロイは5-10分かかります
- ログが表示されるので、エラーがないか確認
- 完了すると自動的にアプリが開きます

---

## 🌐 ステップ3: アプリのURLを取得

デプロイが完了すると、以下のようなURLが発行されます：
```
https://yourapp-xxxxx.streamlit.app
```

このURLを関係者に共有すれば、誰でもアクセスできます！

---

## 🔒 オプション: アクセス制限を設定

### 方法1: 簡易パスワード認証
dashboard_app_v2.pyの冒頭に以下を追加：

```python
import streamlit as st

# パスワード認証
def check_password():
    def password_entered():
        if st.session_state["password"] == "your_password_here":
            st.session_state["password_correct"] = True
            del st.session_state["password"]
        else:
            st.session_state["password_correct"] = False

    if "password_correct" not in st.session_state:
        st.text_input("パスワードを入力してください", type="password", 
                     on_change=password_entered, key="password")
        return False
    elif not st.session_state["password_correct"]:
        st.text_input("パスワードを入力してください", type="password", 
                     on_change=password_entered, key="password")
        st.error("パスワードが間違っています")
        return False
    else:
        return True

if not check_password():
    st.stop()

# ここから通常のアプリケーションコード
```

### 方法2: Streamlit Community Cloudの認証機能
1. Streamlit Community Cloudのダッシュボードでアプリを選択
2. 「Settings」→「Sharing」
3. 招待したい人のメールアドレスを追加

---

## 📝 ステップ4: アプリの更新方法

コードを変更したい場合：

1. GitHubのリポジトリでファイルを編集
   - ブラウザ上で直接編集、または
   - ローカルで編集してpush
2. Streamlit Community Cloudが**自動的に**再デプロイ
3. 1-2分で変更が反映されます

---

## ⚙️ トラブルシューティング

### エラー: ModuleNotFoundError
→ `requirements.txt`にライブラリが正しく記載されているか確認

### エラー: ファイルが見つからない
→ GitHubのリポジトリ構造を確認（ファイルがルートディレクトリにあるか）

### デプロイが遅い/止まる
→ Streamlit Community Cloudのステータスページを確認
→ 一度アプリを削除して再デプロイ

### アプリが重い/遅い
→ 無料版はリソース制限あり
→ 有料版（Streamlit Cloud Teams）を検討

---

## 💡 便利な機能

### Secrets管理
API keyなどの機密情報を安全に管理：

1. Streamlit Community Cloudのダッシュボード
2. アプリの「Settings」→「Secrets」
3. TOML形式で入力：
```toml
password = "your_secret_password"
api_key = "your_api_key"
```

4. コード内で使用：
```python
import streamlit as st
password = st.secrets["password"]
```

### カスタムドメイン
有料版では独自ドメインの設定が可能

---

## 📊 料金について

### 無料版（Community）
- 1アプリまで
- Public/Privateリポジトリ対応
- 月間実行時間の制限あり（通常は十分）
- リソース: 1GB RAM

### 有料版（Teams - $20/月〜）
- 無制限のアプリ
- より多くのリソース
- カスタムドメイン
- 優先サポート

---

## 🎯 次のステップ

1. ✅ アプリをデプロイ
2. ✅ URLを関係者と共有
3. ✅ フィードバックを収集
4. 🔄 必要に応じてコードを改善・更新
5. 📈 利用状況を見てスケールアップを検討

---

## 参考リンク

- Streamlit Community Cloud公式ドキュメント: https://docs.streamlit.io/streamlit-community-cloud
- Streamlitフォーラム: https://discuss.streamlit.io/
- GitHubヘルプ: https://docs.github.com/

---

何か問題があれば、Streamlitのフォーラムやドキュメントが非常に充実しているので、そちらも参考にしてください！
