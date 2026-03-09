#!/usr/bin/env Rscript
# analyze_v4.R — 教育データ分析ツール v4 用 R 分析スクリプト
# 入力: JSON ファイルパス (コマンドライン引数)
# 出力: JSON を stdout に出力

suppressPackageStartupMessages({
  library(jsonlite)
  library(dplyr)
  library(tidyr)
})

# ─── 入力読み込み ─────────────────────────────────────────
args <- commandArgs(trailingOnly = TRUE)
if (length(args) == 0) stop("JSON ファイルパスを引数に指定してください")

payload     <- fromJSON(args[1], simplifyDataFrame = TRUE)
analysis    <- payload$analysis_type
data        <- as.data.frame(payload$data)
item_params <- if (!is.null(payload$item_params)) as.data.frame(payload$item_params) else NULL

# ─── IRT WLE θ推定 ──────────────────────────────────────
# question_master の 困難度 (b パラメータ) を固定し、1PLM で WLE 推定
# P(θ) = 1 / (1 + exp(-(θ - b)))
# WLE: Warm (1989) の加重尤度推定

compute_wle <- function(response_vec, b_vec) {
  # response_vec: 0/1 ベクトル (NA 除外済み)
  # b_vec       : 対応する困難度パラメータ
  valid <- !is.na(response_vec) & !is.na(b_vec)
  r <- response_vec[valid]
  b <- b_vec[valid]
  if (length(r) == 0) return(NA_real_)

  # Newton-Raphson (最大 50 回)
  theta <- 0.0
  for (i in seq_len(50)) {
    p   <- 1 / (1 + exp(-(theta - b)))
    q   <- 1 - p
    L1  <- sum(r - p)                    # 1階微分
    L2  <- -sum(p * q)                   # 2階微分
    W   <- sum(p * q * (1 - 2 * p))     # Warm 補正項
    if (abs(L2) < 1e-10) break
    delta <- (L1 - 0.5 * W / L2) / (-L2)
    theta <- theta + delta
    if (abs(delta) < 1e-6) break
  }
  # θ を [-4, 4] にクリップ
  max(-4, min(4, theta))
}

# ─── 共通: item_params からワイド形式を作る ──────────────
# data は student_id / school / class_id / subject / question_id / correct の long 形式
# item_params は question_id / 困難度 / 大領域 / 中領域 / 観点 / 知識理解 / 資質能力 / 解答形式 / 全国値

add_theta <- function(long_df, iparams) {
  # 生徒×教科 ごとに θ を推定
  b_map <- setNames(iparams$困難度, iparams$question_id)

  long_df %>%
    group_by(student_id, school, class_id, subject) %>%
    summarise(
      theta = compute_wle(correct, b_map[question_id]),
      n_items = sum(!is.na(correct)),
      correct_rate = mean(correct, na.rm = TRUE),
      .groups = "drop"
    )
}

# ─── 分析ルーティング ─────────────────────────────────────

result <- tryCatch({

  # ── 1. irt_theta: θ推定 + 分布統計 ──────────────────
  if (analysis == "irt_theta") {
    theta_df <- add_theta(data, item_params)

    # 比較単位ごとの集計
    group_col <- if (!is.null(payload$group_by) && payload$group_by == "class")
      c("school", "class_id") else "school"

    summary_df <- theta_df %>%
      group_by(across(all_of(group_col))) %>%
      summarise(
        n          = n(),
        mean_theta = round(mean(theta, na.rm = TRUE), 3),
        sd_theta   = round(sd(theta,   na.rm = TRUE), 3),
        median_theta = round(median(theta, na.rm = TRUE), 3),
        q25        = round(quantile(theta, 0.25, na.rm = TRUE), 3),
        q75        = round(quantile(theta, 0.75, na.rm = TRUE), 3),
        min_theta  = round(min(theta, na.rm = TRUE), 3),
        max_theta  = round(max(theta, na.rm = TRUE), 3),
        .groups = "drop"
      )

    list(
      summary    = summary_df,
      individual = theta_df
    )

  # ── 2. domain_analysis: 領域別正答率 ─────────────────
  } else if (analysis == "domain_analysis") {
    domain_col <- if (!is.null(payload$domain_level) &&
                      payload$domain_level == "mid") "中領域" else "大領域"
    group_col  <- if (!is.null(payload$group_by) && payload$group_by == "class")
      c("school", "class_id") else "school"

    merged <- data %>%
      left_join(item_params %>% select(question_id, all_of(domain_col)),
                by = "question_id") %>%
      rename(domain = all_of(domain_col))

    result_df <- merged %>%
      group_by(across(all_of(c(group_col, "domain")))) %>%
      summarise(
        avg_correct_rate = round(mean(correct, na.rm = TRUE) * 100, 1),
        n_items          = n_distinct(question_id),
        .groups = "drop"
      )

    list(domain_scores = result_df, domain_level = domain_col, domain_col = domain_col)

  # ── 3. viewpoint_analysis: 観点別正答率 ──────────────
  } else if (analysis == "viewpoint_analysis") {
    group_col <- if (!is.null(payload$group_by) && payload$group_by == "class")
      c("school", "class_id") else "school"

    merged <- data %>%
      left_join(item_params %>% select(question_id, 観点), by = "question_id")

    result_df <- merged %>%
      group_by(across(all_of(c(group_col, "観点")))) %>%
      summarise(
        avg_correct_rate = round(mean(correct, na.rm = TRUE) * 100, 1),
        n_items          = n_distinct(question_id),
        .groups = "drop"
      ) %>%
      mutate(観点名 = case_when(
        観点 == 1 ~ "知識・理解",
        観点 == 2 ~ "思考・判断",
        TRUE      ~ paste0("観点", 観点)
      ))

    list(viewpoint_scores = result_df)

  # ── 4. competency_analysis: 資質能力別 ───────────────
  } else if (analysis == "competency_analysis") {
    group_col <- if (!is.null(payload$group_by) && payload$group_by == "class")
      c("school", "class_id") else "school"

    # 知識理解 と 資質能力 を long 形式に展開
    merged <- data %>%
      left_join(item_params %>% select(question_id, 知識理解, 資質能力),
                by = "question_id")

    # 資質能力列を使う（NAでない行）
    result_df <- merged %>%
      filter(!is.na(資質能力)) %>%
      group_by(across(all_of(c(group_col, "資質能力")))) %>%
      summarise(
        avg_correct_rate = round(mean(correct, na.rm = TRUE) * 100, 1),
        n_items          = n_distinct(question_id),
        .groups = "drop"
      )

    list(competency_scores = result_df)

  # ── 5. format_analysis: 解答形式別 ───────────────────
  } else if (analysis == "format_analysis") {
    group_col <- if (!is.null(payload$group_by) && payload$group_by == "class")
      c("school", "class_id") else "school"

    merged <- data %>%
      left_join(item_params %>% select(question_id, 解答形式), by = "question_id")

    result_df <- merged %>%
      group_by(across(all_of(c(group_col, "解答形式")))) %>%
      summarise(
        avg_correct_rate = round(mean(correct, na.rm = TRUE) * 100, 1),
        n_items          = n_distinct(question_id),
        .groups = "drop"
      ) %>%
      mutate(形式名 = case_when(
        解答形式 == 1 ~ "選択",
        解答形式 == 2 ~ "短答",
        解答形式 == 3 ~ "記述",
        TRUE          ~ paste0("形式", 解答形式)
      ))

    list(format_scores = result_df)

  # ── 6. item_analysis: 小問別正答率・全国値比較 ─────────
  } else if (analysis == "item_analysis") {
    result_df <- data %>%
      group_by(question_id) %>%
      summarise(
        correct_rate = round(mean(correct, na.rm = TRUE) * 100, 1),
        n            = n(),
        .groups = "drop"
      ) %>%
      left_join(item_params %>% select(question_id, 全国値, 困難度, 大領域, 中領域, 観点, 解答形式),
                by = "question_id") %>%
      mutate(
        diff_from_national = round(correct_rate - 全国値, 1)
      ) %>%
      arrange(question_id)

    list(item_scores = result_df)

  # ── 7. attitude_analysis: 意識調査項目別選択割合 ────────
  } else if (analysis == "attitude_analysis") {
    # data は attitude_results (student_id/school/class_id/subject/question_id/score)
    group_col <- if (!is.null(payload$group_by) && payload$group_by == "class")
      c("school", "class_id") else "school"

    result_df <- data %>%
      group_by(across(all_of(c(group_col, "question_id", "score")))) %>%
      summarise(count = n(), .groups = "drop") %>%
      group_by(across(all_of(c(group_col, "question_id")))) %>%
      mutate(pct = round(count / sum(count) * 100, 1)) %>%
      ungroup()

    # 全国値を結合 (attitude_master)
    nat_df <- if (!is.null(payload$attitude_master))
      as.data.frame(payload$attitude_master) else NULL

    list(
      attitude_dist  = result_df,
      attitude_master = nat_df
    )

  # ── 8. attitude_x_theta: 学力層×態度クロス ───────────
  } else if (analysis == "attitude_x_theta") {
    theta_df <- add_theta(
      payload$test_data %>% as.data.frame(),
      item_params
    )

    # 学力層を3分割 (低・中・高)
    theta_df <- theta_df %>%
      mutate(level = ntile(theta, 3),
             level_label = case_when(
               level == 1 ~ "低位",
               level == 2 ~ "中位",
               level == 3 ~ "高位"
             ))

    attitude_df <- data  # attitude_results

    merged <- attitude_df %>%
      left_join(theta_df %>% select(student_id, subject, theta, level_label),
                by = c("student_id", "subject"))

    cross_df <- merged %>%
      filter(!is.na(level_label)) %>%
      group_by(level_label, question_id) %>%
      summarise(avg_score = round(mean(score, na.rm = TRUE), 3),
                .groups = "drop")

    scatter_df <- theta_df %>%
      left_join(
        attitude_df %>%
          group_by(student_id, subject) %>%
          summarise(avg_attitude = mean(score, na.rm = TRUE), .groups = "drop"),
        by = c("student_id", "subject")
      )

    list(
      cross_summary = cross_df,
      scatter       = scatter_df %>% select(student_id, school, class_id, theta, avg_attitude)
    )

  # ── 9. individual_profile: 個人票 ────────────────────
  } else if (analysis == "individual_profile") {
    sid <- payload$student_id

    ind_data <- data %>% filter(student_id == sid)
    if (nrow(ind_data) == 0) stop(paste("student_id not found:", sid))

    b_map <- setNames(item_params$困難度, item_params$question_id)
    theta_val <- compute_wle(ind_data$correct, b_map[ind_data$question_id])

    # 全体θ分布（同教科・全生徒）
    all_theta <- add_theta(data, item_params)
    rank_school <- sum(all_theta$theta <= theta_val, na.rm = TRUE)
    n_school    <- nrow(all_theta)

    # 領域別
    domain_profile <- ind_data %>%
      left_join(item_params %>% select(question_id, 大領域, 中領域, 観点, 資質能力, 解答形式),
                by = "question_id") %>%
      {
        d <- .
        list(
          大領域 = d %>% group_by(大領域) %>%
            summarise(rate = round(mean(correct, na.rm=TRUE)*100,1), n=n(), .groups="drop"),
          中領域 = d %>% group_by(中領域) %>%
            summarise(rate = round(mean(correct, na.rm=TRUE)*100,1), n=n(), .groups="drop"),
          観点   = d %>% group_by(観点) %>%
            summarise(rate = round(mean(correct, na.rm=TRUE)*100,1), n=n(), .groups="drop") %>%
            mutate(観点名 = ifelse(観点==1,"知識・理解","思考・判断")),
          資質能力 = d %>% filter(!is.na(資質能力)) %>% group_by(資質能力) %>%
            summarise(rate = round(mean(correct, na.rm=TRUE)*100,1), n=n(), .groups="drop"),
          解答形式 = d %>% group_by(解答形式) %>%
            summarise(rate = round(mean(correct, na.rm=TRUE)*100,1), n=n(), .groups="drop") %>%
            mutate(形式名 = case_when(解答形式==1~"選択",解答形式==2~"短答",解答形式==3~"記述",TRUE~"その他"))
        )
      }

    list(
      theta         = round(theta_val, 3),
      correct_rate  = round(mean(ind_data$correct, na.rm=TRUE)*100, 1),
      rank_in_group = rank_school,
      n_total       = n_school,
      domain_大領域  = domain_profile$大領域,
      domain_中領域  = domain_profile$中領域,
      domain_観点    = domain_profile$観点,
      domain_資質能力 = domain_profile$資質能力,
      domain_解答形式 = domain_profile$解答形式
    )

  } else {
    list(error = paste("未定義の analysis_type:", analysis))
  }

}, error = function(e) {
  list(error = conditionMessage(e))
})

cat(toJSON(result, auto_unbox = TRUE, na = "null"))
