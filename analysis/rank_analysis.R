#!/usr/bin/env Rscript
# =============================================================================
# rank_analysis.R
# 学力層別分類: GMM（混合正規分布）vs 正答率カッティングポイント 5段階比較
#
# 前提: preprocess.py で生成した *_eng.csv を入力とする
# 依存: base R のみ（mclust があれば自動的に使用）
#
# 使い方:
#   Rscript rank_analysis.R sampledata_eng.csv [subject_meta.json]
# =============================================================================

HAS_MCLUST <- requireNamespace("mclust", quietly = TRUE)
if (HAS_MCLUST) {
  library(mclust)
  cat("mclust 使用\n\n")
} else {
  cat("mclust なし: EM-GMM 自前実装で代替\n\n")
}

# =============================================================================
# 0. 設定
# =============================================================================
N_RANKS <- 5   # 全国学調 IRT バンドに合わせた 5 段階

# 正答率カッティングポイント（全国学調の目安に準拠）
CUT_POINTS  <- c(0, 0.40, 0.55, 0.70, 0.85, 1.0)
RANK_LABELS <- c("1_低位", "2_中低位", "3_中位", "4_中高位", "5_高位")

# 教科定義（preprocess.py の出力列名に対応）
SUBJECTS <- list(
  list(eng = "kokugo", ja = "国語"),
  list(eng = "shakai", ja = "社会"),
  list(eng = "sugaku", ja = "数学"),
  list(eng = "rika",   ja = "理科"),
  list(eng = "eigo",   ja = "英語")
)

# =============================================================================
# 1. EM-GMM 実装（mclust 非存在時のフォールバック）
# =============================================================================
em_gmm <- function(x, G, max_iter = 300, tol = 1e-8) {
  n  <- length(x)
  x  <- as.numeric(x)
  km <- kmeans(x, centers = G, nstart = 30, iter.max = 200)
  mu <- as.vector(km$centers[order(km$centers)])
  sg <- rep(sd(x) / G + 1e-6, G)
  pi <- rep(1 / G, G)
  ll_prev <- -Inf

  for (i in seq_len(max_iter)) {
    # E-step
    D <- sapply(1:G, function(k) pi[k] * dnorm(x, mu[k], sg[k]))
    rs <- rowSums(D) + 1e-300
    r  <- D / rs
    # M-step
    nk <- colSums(r);  pi <- nk / n
    mu <- colSums(r * x) / nk
    sg <- pmax(sqrt(colSums(r * outer(x, mu, "-")^2) / nk), 1e-8)
    ll <- sum(log(rs))
    if (abs(ll - ll_prev) < tol) break
    ll_prev <- ll
  }
  cl_raw <- max.col(r)
  reorder <- rank(tapply(x, cl_raw, mean), ties.method = "first")
  list(classification = as.integer(reorder[cl_raw]),
       mean = mu[order(mu)], loglik = ll)
}

# =============================================================================
# 2. 分類ユーティリティ
# =============================================================================
classify_gmm <- function(scores, n_ranks = N_RANKS) {
  nu <- length(unique(scores))
  if (nu < n_ranks) {
    message(sprintf("    ユニーク値(%d) < ランク数(%d) → 調整", nu, n_ranks))
    n_ranks <- max(2, nu)
  }
  fit <- tryCatch({
    if (HAS_MCLUST) Mclust(scores, G = n_ranks, verbose = FALSE)
    else             em_gmm(scores, G = n_ranks)
  }, error = function(e) { message("    GMM失敗: ", e$message); NULL })

  if (is.null(fit)) {   # フォールバック: パーセンタイル
    br <- quantile(scores, seq(0, 1, length.out = n_ranks + 1))
    br[1] <- br[1] - 1e-9
    return(as.integer(cut(scores, br, labels = 1:n_ranks)))
  }
  if (HAS_MCLUST) {
    ro <- rank(fit$parameters$mean, ties.method = "first")
    return(as.integer(ro[fit$classification]))
  }
  fit$classification
}

classify_cut <- function(rates, cut_points = CUT_POINTS) {
  as.integer(cut(rates, cut_points,
                 labels = seq_along(cut_points[-1]),
                 include.lowest = TRUE))
}

# =============================================================================
# 3. データ読み込み
# =============================================================================
args     <- commandArgs(trailingOnly = TRUE)
csv_path <- if (length(args) >= 1) args[1] else "sampledata_eng.csv"

cat("============================================================\n")
cat("学力層別分類分析  GMM vs カッティングポイント\n")
cat("============================================================\n\n")

df <- read.csv(csv_path, check.names = FALSE, stringsAsFactors = FALSE)
cat(sprintf("データ: %s  (%d名 / %d列)\n\n", csv_path, nrow(df), ncol(df)))

# =============================================================================
# 4. 教科別得点集計
# =============================================================================
score_df <- df[, c("school", "class_id", "student_no"), drop = FALSE]

cat("--- 教科別問題数 ---\n")
valid_subjects <- list()

for (subj in SUBJECTS) {
  pat  <- paste0("^", subj$eng, "_[0-9]+$")
  cols <- grep(pat, names(df), value = TRUE)
  if (length(cols) == 0) { cat(sprintf("  %-8s: 列なし\n", subj$ja)); next }

  score_df[[paste0(subj$eng, "_score")]]  <- rowSums(df[, cols, drop = FALSE], na.rm = TRUE)
  score_df[[paste0(subj$eng, "_n")]]      <- length(cols)
  score_df[[paste0(subj$eng, "_rate")]]   <-
    score_df[[paste0(subj$eng, "_score")]] / length(cols)

  cat(sprintf("  %-8s: %d問\n", subj$ja, length(cols)))
  valid_subjects[[length(valid_subjects) + 1]] <- subj
}

cat("\n--- 得点サマリ ---\n")
for (subj in valid_subjects) {
  v <- score_df[[paste0(subj$eng, "_score")]]
  cat(sprintf("  %-8s 平均=%.1f  SD=%.1f  min=%d  max=%d  正答率=%.1f%%\n",
              subj$ja, mean(v), sd(v), min(v), max(v),
              mean(score_df[[paste0(subj$eng, "_rate")]]) * 100))
}

# =============================================================================
# 5. 学力層分類
# =============================================================================
cat("\n\n--- 学力層分類（5段階）---\n")

for (subj in valid_subjects) {
  sc  <- score_df[[paste0(subj$eng, "_score")]]
  rt  <- score_df[[paste0(subj$eng, "_rate")]]
  gcol <- paste0(subj$eng, "_gmm")
  ccol <- paste0(subj$eng, "_cut")

  cat(sprintf("\n【%s】\n", subj$ja))
  score_df[[gcol]] <- classify_gmm(sc)
  score_df[[ccol]] <- classify_cut(rt)

  for (m in c("GMM", "CUT")) {
    col <- if (m == "GMM") gcol else ccol
    tbl <- table(score_df[[col]])
    mn  <- tapply(rt, score_df[[col]], mean, na.rm = TRUE)
    cat(sprintf("  [%s] 人数  : %s\n", m,
                paste(sprintf("R%s=%d名", names(tbl), as.integer(tbl)), collapse=" | ")))
    cat(sprintf("       正答率: %s\n",
                paste(sprintf("R%s=%.1f%%", names(mn), mn*100), collapse=" | ")))
  }
}

# =============================================================================
# 6. GMM vs CUT 一致率
# =============================================================================
cat("\n\n============================================================\n")
cat("GMM vs カッティングポイント 一致率\n")
cat("============================================================\n")

agree_tbl <- data.frame(
  subject   = character(),
  exact_pct = numeric(),
  within1_pct = numeric(),
  stringsAsFactors = FALSE
)

for (subj in valid_subjects) {
  g <- score_df[[paste0(subj$eng, "_gmm")]]
  c <- score_df[[paste0(subj$eng, "_cut")]]
  cross <- table(GMM = g, CUT = c)

  exact   <- sum(diag(cross)) / sum(cross) * 100
  within1 <- mean(abs(g - c) <= 1, na.rm = TRUE) * 100
  agree_tbl <- rbind(agree_tbl, data.frame(
    subject = subj$ja, exact_pct = exact, within1_pct = within1
  ))

  cat(sprintf("\n【%s】\n", subj$ja))
  tmp <- capture.output(print(addmargins(cross)))
  cat(paste0("  ", tmp, "\n"))
  cat(sprintf("  完全一致率   : %.1f%%\n", exact))
  cat(sprintf("  ±1以内一致率: %.1f%%\n", within1))

  diff2 <- which(abs(g - c) >= 2)
  if (length(diff2) > 0)
    cat(sprintf("  2ランク以上乖離: %d名 (student_no: %s)\n",
                length(diff2),
                paste(score_df$student_no[diff2], collapse = ",")))
  else cat("  2ランク以上乖離: なし\n")
}

# =============================================================================
# 7. 教科間ランク相関（Spearman / GMM）
# =============================================================================
cat("\n\n============================================================\n")
cat("教科間ランク相関（Spearman / GMM）\n")
cat("============================================================\n")

gcols <- paste0(sapply(valid_subjects, `[[`, "eng"), "_gmm")
gcols <- gcols[gcols %in% names(score_df)]
if (length(gcols) >= 2) {
  cm <- cor(score_df[, gcols], use = "pairwise.complete.obs", method = "spearman")
  rownames(cm) <- colnames(cm) <- sapply(valid_subjects, `[[`, "ja")[
    sapply(valid_subjects, function(s) paste0(s$eng, "_gmm")) %in% gcols]
  tmp <- capture.output(print(round(cm, 3)))
  cat(paste0("  ", tmp, "\n"))
}

# =============================================================================
# 8. 可視化
# =============================================================================
cat("\n可視化を生成中...\n")
n_sub <- length(valid_subjects)
nc    <- ceiling(n_sub / 2)

pdf("rank_comparison.pdf", width = 14, height = 10, family = "Japan1GothicBBB" )

# --- 正答率ヒストグラム + 境界線 ---
par(mfrow = c(2, nc), mar = c(4.5, 4, 3.5, 1.5))

for (subj in valid_subjects) {
  rt   <- score_df[[paste0(subj$eng, "_rate")]]
  grnk <- score_df[[paste0(subj$eng, "_gmm")]]

  hist(rt, breaks = seq(0, 1, 0.05),
       col = adjustcolor("steelblue", 0.3), border = "white",
       main = subj$ja, xlab = "正答率", ylab = "人数",
       xlim = c(0, 1), las = 1)

  # GMM境界（青実線）= 各ランク最大値
  for (r in 1:(N_RANKS - 1)) {
    b <- suppressWarnings(max(rt[grnk == r], na.rm = TRUE))
    if (is.finite(b)) abline(v = b, col = "#2563eb", lty = 1, lwd = 2)
  }
  # カッティングポイント（赤破線）
  abline(v = CUT_POINTS[-c(1, length(CUT_POINTS))],
         col = "#dc2626", lty = 2, lwd = 1.8)

  legend("topright", cex = 0.72, bty = "n",
         legend = c("CUT(赤破線)", "GMM(青実線)"),
         col = c("#dc2626", "#2563eb"), lty = c(2, 1), lwd = 1.8)
}

# --- 一致率棒グラフ ---
par(mfrow = c(1, 1), mar = c(5, 5, 4, 2))
bp <- barplot(agree_tbl$exact_pct,
              names.arg = agree_tbl$subject,
              col = "#2563eb", ylim = c(0, 110),
              main = "GMM vs CUT  完全一致率 (%)",
              ylab = "完全一致率 (%)", xlab = "教科", las = 1)
barplot(agree_tbl$within1_pct,
        names.arg = agree_tbl$subject,
        col = adjustcolor("#93c5fd", 0.6),
        ylim = c(0, 110), add = TRUE, axes = FALSE)
abline(h = 80, col = "#dc2626", lty = 2, lwd = 1.5)
text(bp, agree_tbl$exact_pct + 3,
     sprintf("%.0f%%", agree_tbl$exact_pct), cex = 0.85, font = 2)
legend("topright", bty = "n",
       legend = c("完全一致", "±1以内", "80%ライン"),
       fill   = c("#2563eb", "#93c5fd", NA),
       lty    = c(NA, NA, 2),
       col    = c(NA, NA, "#dc2626"), border = NA)

# --- GMM ランク分布（教科横断） ---
par(mfrow = c(1, 1), mar = c(5, 4, 4, 2))
rank_dist <- sapply(valid_subjects, function(subj) {
  tbl <- table(factor(score_df[[paste0(subj$eng, "_gmm")]], levels = 1:N_RANKS))
  as.integer(tbl)
})
colnames(rank_dist) <- sapply(valid_subjects, `[[`, "ja")
rownames(rank_dist) <- RANK_LABELS

pal <- c("#bfdbfe","#60a5fa","#2563eb","#1d4ed8","#1e3a8a")
barplot(rank_dist, beside = TRUE,
        col = pal, ylim = c(0, max(rank_dist) * 1.3),
        main = "教科別 GMM ランク分布",
        xlab = "教科", ylab = "人数", las = 1)
legend("topright", legend = RANK_LABELS, fill = pal, bty = "n", cex = 0.8)

dev.off()

# =============================================================================
# 9. CSV 出力
# =============================================================================
write.csv(score_df, "rank_results.csv", row.names = FALSE)

cat("\n============================================================\n")
cat("完了！\n\n")
cat("出力ファイル:\n")
cat("  rank_results.csv       生徒別ランク付きデータ\n")
cat("  rank_comparison.pdf    分布グラフ + 一致率比較\n")
cat("\n次のステップ:\n")
cat("  1. rank_results.csv + attitude_data.csv を結合してクロス集計\n")
cat("  2. 十分な人数（目安: 各層30名以上）でGMM安定性を再確認\n")
cat("  3. 本番データで確認後、analyze_v3.R に組み込む\n")
cat("============================================================\n")
