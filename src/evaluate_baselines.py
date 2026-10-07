"""在固定的 2022 test 集上评估两个无需训练的历史基线。"""

from __future__ import annotations

import math
from pathlib import Path

import pandas as pd

from src.config import PROJECT_ROOT, REPORT_DIR


INPUT_PATH = PROJECT_ROOT / "data" / "processed" / "product_month_features.csv"
REPORT_PATH = REPORT_DIR / "stage4_baseline.md"
EXPECTED_TEST_ROWS = 60_000
INPUT_COLUMNS = [
    "parent_asin", "month", "split", "future_interaction_count",
    "lag_1", "rolling_mean_3",
]


def load_test_data(path: Path) -> pd.DataFrame:
    # 仅载入预测所需的历史列和目标列；审计列 interaction_count 不进入本脚本。
    data = pd.read_csv(path, usecols=INPUT_COLUMNS)
    test = data.loc[data["split"].eq("test"), INPUT_COLUMNS].copy()
    if len(test) != EXPECTED_TEST_ROWS:
        raise ValueError(f"test 行数应为 {EXPECTED_TEST_ROWS}，实际为 {len(test)}")
    months = set(test["month"].astype(str))
    expected_months = {f"2022-{month:02d}-01" for month in range(1, 13)}
    if months != expected_months:
        raise ValueError(f"test 月份不符合 2022 自然月：{sorted(months)}")
    if test["parent_asin"].nunique() != 5_000:
        raise ValueError("test 商品数不等于 Stage 3 固定 cohort 的 5,000")
    if test.duplicated(["parent_asin", "month"]).any():
        raise ValueError("test 存在重复的商品-月份")
    numeric_columns = ["future_interaction_count", "lag_1", "rolling_mean_3"]
    for column in numeric_columns:
        test[column] = pd.to_numeric(test[column], errors="raise")
        if test[column].isna().any() or not test[column].map(math.isfinite).all():
            raise ValueError(f"{column} 存在 NaN 或无穷值")
        if (test[column] < 0).any():
            raise ValueError(f"{column} 存在负值")
    target = test["future_interaction_count"]
    if not target.eq(target.round()).all():
        raise ValueError("target 必须是非负整数计数")
    return test.sort_values(["month", "parent_asin"]).reset_index(drop=True)


def evaluate(test: pd.DataFrame) -> dict:
    target = test["future_interaction_count"]
    # 两个预测只复制 Stage 3 已验证为 T 之前历史的特征，不使用当前月计数或目标。
    test["prediction_lag1"] = test["lag_1"]
    test["prediction_rolling3"] = test["rolling_mean_3"]
    names = {"lag_1": "prediction_lag1", "rolling_mean_3": "prediction_rolling3"}
    results = {}
    for name, prediction_column in names.items():
        prediction = test[prediction_column]
        error = (target - prediction).abs()
        test[f"absolute_error_{name}"] = error
        program_mae = float(error.mean())
        # 独立逐行累加复核，避免只重复调用同一个向量化结果。
        manual_mae = math.fsum(
            abs(float(actual) - float(predicted))
            for actual, predicted in zip(target, prediction)
        ) / len(test)
        if not math.isclose(program_mae, manual_mae, rel_tol=0, abs_tol=1e-10):
            raise AssertionError(f"{name} MAE 手工复核不一致")
        results[name] = {
            "prediction_mean": float(prediction.mean()),
            "mae": program_mae,
            "manual_mae": manual_mae,
        }
    if test[["prediction_lag1", "prediction_rolling3"]].isna().any().any():
        raise AssertionError("baseline prediction 存在 NaN")
    segments = {
        "target = 0": target.eq(0),
        "target = 1~3": target.between(1, 3),
        "target >= 4": target.ge(4),
    }
    if sum(int(mask.sum()) for mask in segments.values()) != len(test):
        raise AssertionError("target 分段未覆盖所有 test 行")
    segment_results = []
    for label, mask in segments.items():
        segment_results.append({
            "segment": label,
            "rows": int(mask.sum()),
            "mae_lag1": float(test.loc[mask, "absolute_error_lag_1"].mean()),
            "mae_rolling3": float(test.loc[mask, "absolute_error_rolling_mean_3"].mean()),
        })
    best_name = min(names, key=lambda name: results[name]["mae"])
    # 准确案例只从真实有交互的月份选择，避免全零案例掩盖评估难度。
    combined_error = test["absolute_error_lag_1"] + test["absolute_error_rolling_mean_3"]
    accurate_candidates = test.loc[target.gt(0)]
    accurate_index = combined_error.loc[accurate_candidates.index].idxmin()
    bad_index = combined_error.idxmax()
    return {
        "test": test,
        "results": results,
        "segments": segment_results,
        "best_name": best_name,
        "accurate": test.loc[accurate_index],
        "bad": test.loc[bad_index],
    }


def format_case(row: pd.Series) -> str:
    values = [
        str(row["parent_asin"]), str(row["month"]),
        f'{row["lag_1"]:.6f}', f'{row["rolling_mean_3"]:.6f}',
        f'{row["future_interaction_count"]:.0f}',
        f'{row["prediction_lag1"]:.6f}', f'{row["prediction_rolling3"]:.6f}',
        f'{row["absolute_error_lag_1"]:.6f}',
        f'{row["absolute_error_rolling_mean_3"]:.6f}',
    ]
    return "| " + " | ".join(values) + " |"


def write_report(evaluation: dict, path: Path) -> None:
    test = evaluation["test"]
    target = test["future_interaction_count"]
    results = evaluation["results"]
    segments = evaluation["segments"]
    best = evaluation["best_name"]
    segment_lines = [
        f'| {item["segment"]} | {item["rows"]:,} | {item["mae_lag1"]:.6f} | {item["mae_rolling3"]:.6f} |'
        for item in segments
    ]
    report = "\n".join([
        "# Stage 4 Baseline 评估", "",
        "仅评估 Stage 3 固定 cohort 的 2022-01 至 2022-12 `split=test`；"
        f"{len(test):,} 行、{test['parent_asin'].nunique():,} 个 parent_asin。无随机切分。",
        "目标为当前月 `future_interaction_count`。当前月 `interaction_count` 仅为审计列，本脚本未读取。",
        "", "## Baseline 与总体指标", "",
        "`lag_1` 为上个月计数；`rolling_mean_3` 为预测月之前三个完整月的均值。"
        "二者由 Stage 3 历史特征表提供；本阶段只复制特征作预测，不使用 test target 构造特征。",
        "", f"Target mean: {target.mean():.6f}；median: {target.median():.6f}；zero rate: {target.eq(0).mean():.6%}。",
        "", "| Baseline | Prediction mean | MAE | 手工 MAE |", "|---|---:|---:|---:|",
        f'| lag_1 | {results["lag_1"]["prediction_mean"]:.6f} | {results["lag_1"]["mae"]:.6f} | {results["lag_1"]["manual_mae"]:.6f} |',
        f'| rolling_mean_3 | {results["rolling_mean_3"]["prediction_mean"]:.6f} | {results["rolling_mean_3"]["mae"]:.6f} | {results["rolling_mean_3"]["manual_mae"]:.6f} |',
        "", "## 按真实 target 分段", "",
        "| 区间 | 样本数 | lag_1 MAE | rolling_mean_3 MAE |", "|---|---:|---:|---:|",
        *segment_lines,
        "", "## 最佳 Baseline", "",
        f'`best_baseline_name = {best}`；`best_baseline_MAE = {results[best]["mae"]:.6f}`。'
        "下一阶段复杂模型至少应与该 2022 test 基准比较。",
        "", "## 真实案例", "",
        "准确案例取非零 target 中两个 Baseline 绝对误差之和最小的一行；明显错误案例取该和最大的一行。",
        "", "| 案例 | parent_asin | month | lag_1 | rolling_mean_3 | actual target | prediction_lag1 | prediction_rolling3 | abs error lag1 | abs error rolling3 |",
        "|---|---|---|---:|---:|---:|---:|---:|---:|---:|",
        format_case(evaluation["accurate"]).replace("| ", "| 准确 | ", 1),
        format_case(evaluation["bad"]).replace("| ", "| 明显错误 | ", 1),
        "", "## 验证", "",
        "60,000 行、12 个 2022 月份、5,000 个商品、商品-月份唯一；目标与预测无 NaN/无穷值；"
        "两种 MAE 与独立逐行绝对误差求和一致。预测仅来自预先构造的历史特征。", "",
    ])
    path.write_text(report, encoding="utf-8")


def main() -> None:
    test = load_test_data(INPUT_PATH)
    evaluation = evaluate(test)
    write_report(evaluation, REPORT_PATH)
    print(f"test_rows={len(test)}")
    print(f"target_mean={test['future_interaction_count'].mean():.6f}")
    print(f"target_median={test['future_interaction_count'].median():.6f}")
    print(f"target_zero_rate={test['future_interaction_count'].eq(0).mean():.6%}")
    for name, result in evaluation["results"].items():
        print(f"{name}_MAE={result['mae']:.12f}; manual_MAE={result['manual_mae']:.12f}")
    print(f"best_baseline={evaluation['best_name']}")
    print(f"report={REPORT_PATH}")


if __name__ == "__main__":
    main()
