#!/usr/bin/env Rscript
# =====================================================
# R 統計分析スクリプト v2
# 追加: ability_analysis / cross_analysis
# 入力: JSON（引数ファイル）
# 出力: JSON（stdout）
# =====================================================

suppressPackageStartupMessages({
  library(jsonlite)
  library(dplyr)
  library(tidyr)
})

args <- commandArgs(trailingOnly = TRUE)
if (length(args) > 0) {
  input <- fromJSON(args[1])
} else {
  stop("入力JSONファイルが必要です")
}

analysis_type <- input$analysis_type
data <- as.data.frame(input$data)

# item_paramsが必要な分析では必ず渡す
get_item_params <- function() {
  if (is.null(input$item_params)) stop("item_params が渡されていません")
  ip <- as.data.frame(input$item_params)
  ip$item <- paste0("x", ip$question_id)  # xQ0001 形式
  ip
}

# =====================================================
# 分析関数
# =====================================================

score_distribution <- function(df) {
  score_cols <- grep("^x", names(df), value = TRUE)
  df$total_score <- rowSums(df[, score_cols])
  dist <- df %>% count(total_score) %>% rename(score = total_score, count = n)
  list(distribution = dist, type = "score_distribution")
}

item_difficulty <- function(df) {
  score_cols <- grep("^x", names(df), value = TRUE)
  difficulty <- colMeans(df[, score_cols], na.rm = TRUE)
  result <- data.frame(
    item        = names(difficulty),
    question_id = sub("^x", "", names(difficulty)),  # xQ0001 → Q0001
    correct_rate = round(difficulty, 4)
  )
  list(difficulty = result, type = "item_difficulty")
}

# domain別（動的：domainの種類はitem_paramsから取得）
domain_analysis <- function(df) {
  ip <- get_item_params()
  score_cols <- grep("^x", names(df), value = TRUE)
  domains <- sort(unique(ip$domain))

  results <- lapply(domains, function(d) {
    items <- ip %>% filter(domain == d) %>% pull(item)
    items_in_df <- intersect(items, score_cols)
    if (length(items_in_df) == 0) return(NULL)
    df %>%
      mutate(domain_score = rowMeans(across(all_of(items_in_df)))) %>%
      group_by(class_id) %>%
      summarise(domain = d, n = n(),
                avg_pct = round(mean(domain_score) * 100, 1), .groups = "drop")
  })
  result_df <- bind_rows(Filter(Negate(is.null), results))
  list(domain_scores = result_df, domains = domains, type = "domain_analysis")
}

# ability別（動的：abilityの種類はitem_paramsから取得）
ability_analysis <- function(df) {
  ip <- get_item_params()
  score_cols <- grep("^x", names(df), value = TRUE)
  abilities <- sort(unique(ip$ability))

  results <- lapply(abilities, function(ab) {
    items <- ip %>% filter(ability == ab) %>% pull(item)
    items_in_df <- intersect(items, score_cols)
    if (length(items_in_df) == 0) return(NULL)
    df %>%
      mutate(ab_score = rowMeans(across(all_of(items_in_df)))) %>%
      group_by(class_id) %>%
      summarise(ability = ab, n = n(),
                avg_pct = round(mean(ab_score) * 100, 1), .groups = "drop")
  })
  result_df <- bind_rows(Filter(Negate(is.null), results))
  list(ability_scores = result_df, abilities = abilities, type = "ability_analysis")
}

# domain × ability クロス集計
cross_analysis <- function(df) {
  ip <- get_item_params()
  score_cols <- grep("^x", names(df), value = TRUE)
  domains   <- sort(unique(ip$domain))
  abilities <- sort(unique(ip$ability))

  results <- lapply(domains, function(d) {
    lapply(abilities, function(ab) {
      items <- ip %>% filter(domain == d, ability == ab) %>% pull(item)
      items_in_df <- intersect(items, score_cols)
      if (length(items_in_df) == 0) return(NULL)
      avg <- round(mean(rowMeans(df[, items_in_df, drop = FALSE])) * 100, 1)
      data.frame(domain = d, ability = ab, avg_pct = avg,
                 n_items = length(items_in_df))
    })
  })
  result_df <- bind_rows(Filter(Negate(is.null), unlist(results, recursive = FALSE)))
  list(cross_scores = result_df, domains = domains,
       abilities = abilities, type = "cross_analysis")
}

cronbach_alpha <- function(df) {
  score_cols <- grep("^x", names(df), value = TRUE)
  k <- length(score_cols)
  item_vars <- apply(df[, score_cols], 2, var, na.rm = TRUE)
  total_var  <- var(rowSums(df[, score_cols], na.rm = TRUE))
  alpha <- (k / (k - 1)) * (1 - sum(item_vars) / total_var)
  list(
    alpha = round(alpha, 4), k = k,
    interpretation = ifelse(alpha >= 0.9, "非常に高い",
                    ifelse(alpha >= 0.8, "高い",
                    ifelse(alpha >= 0.7, "許容範囲",
                    ifelse(alpha >= 0.6, "やや低い", "低い")))),
    type = "cronbach_alpha"
  )
}

# =====================================================
# 振り分け
# =====================================================
result <- tryCatch({
  switch(analysis_type,
    "score_distribution" = score_distribution(data),
    "item_difficulty"    = item_difficulty(data),
    "domain_analysis"    = domain_analysis(data),
    "ability_analysis"   = ability_analysis(data),
    "cross_analysis"     = cross_analysis(data),
    "cronbach_alpha"     = cronbach_alpha(data),
    list(error = paste("未対応の分析タイプ:", analysis_type))
  )
}, error = function(e) {
  list(error = conditionMessage(e))
})

cat(toJSON(result, auto_unbox = TRUE, na = "null"))
