"""Stage 5：固定时间切分下的一次 RandomForest 与 lag_1 基准比较。"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error

from src.config import PROJECT_ROOT, REPORT_DIR


DATA_PATH = PROJECT_ROOT / "data" / "processed" / "product_month_features.csv"
REPORT_PATH = REPORT_DIR / "stage5_random_forest.md"
FEATURES = [
    "lag_1", "lag_2", "lag_3", "rolling_mean_3", "rolling_mean_6",
    "rolling_std_3", "historical_interaction_mean", "historical_interaction_max",
    "active_months_history", "historical_rating_mean", "historical_rating_count",
]
TARGET = "future_interaction_count"
COLUMNS = ["parent_asin", "month", "split", TARGET, *FEATURES]
PARAMETERS = {
    "n_estimators": 150,
    "max_depth": 12,
    "min_samples_leaf": 5,
    "random_state": 42,
    "n_jobs": -1,
}
STAGE4_BASELINE_MAE = 0.995866666667


def load_and_validate(path: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    # usecols 白名单确保当前月审计列、商品 ID、metadata 不进入模型输入。
    data = pd.read_csv(path, usecols=COLUMNS)
    train = data.loc[data["split"].eq("train")].copy()
    test = data.loc[data["split"].eq("test")].copy()
    if len(data) != 180_000 or len(train) != 120_000 or len(test) != 60_000:
        raise ValueError(f"数据行数不符合固定口径：all={len(data)}, train={len(train)}, test={len(test)}")
    for label, frame, start_year, end_year in (
        ("train", train, 2020, 2021), ("test", test, 2022, 2022)
    ):
        expected_months = {
            f"{year}-{month:02d}-01"
            for year in range(start_year, end_year + 1)
            for month in range(1, 13)
        }
        if set(frame["month"].astype(str)) != expected_months:
            raise ValueError(f"{label} 月份与既定时间切分不符")
        if frame["parent_asin"].nunique() != 5_000:
            raise ValueError(f"{label} 不是固定的 5,000 个商品")
        if frame.duplicated(["parent_asin", "month"]).any():
            raise ValueError(f"{label} 存在重复商品月份")
        for column in [*FEATURES, TARGET]:
            frame[column] = pd.to_numeric(frame[column], errors="raise")
        values = frame[[*FEATURES, TARGET]].to_numpy(dtype=float)
        if not np.isfinite(values).all():
            raise ValueError(f"{label} 特征或目标存在 NaN/无穷值")
        if (frame[TARGET] < 0).any():
            raise ValueError(f"{label} 目标存在负值")
    if set(train["parent_asin"]) != set(test["parent_asin"]):
        raise ValueError("Train/Test 商品 cohort 不一致")
    baseline_mae = mean_absolute_error(test[TARGET], test["lag_1"])
    if not np.isclose(baseline_mae, STAGE4_BASELINE_MAE, rtol=0, atol=1e-6):
        raise ValueError(f"Baseline MAE={baseline_mae:.12f} 与 Stage 4 不符；停止训练")
    return train, test.sort_values(["month", "parent_asin"]).reset_index(drop=True)


def evaluate(train: pd.DataFrame, test: pd.DataFrame) -> dict:
    # 只拟合一次固定参数模型；2022 target 仅用于拟合完成后的评估。
    model = RandomForestRegressor(**PARAMETERS)
    model.fit(train[FEATURES], train[TARGET])
    raw_prediction = model.predict(test[FEATURES])
    if len(raw_prediction) != 60_000 or not np.isfinite(raw_prediction).all():
        raise ValueError("RF prediction 数量不符或存在 NaN/无穷值")
    negative_count = int(np.count_nonzero(raw_prediction < 0))
    prediction = np.maximum(raw_prediction, 0) if negative_count else raw_prediction
    actual = test[TARGET].to_numpy(dtype=float)
    baseline_prediction = test["lag_1"].to_numpy(dtype=float)
    baseline_error = np.abs(actual - baseline_prediction)
    rf_error = np.abs(actual - prediction)
    baseline_mae = float(baseline_error.mean())
    rf_mae = float(rf_error.mean())
    improvement = baseline_mae - rf_mae
    if not np.isclose(baseline_mae, STAGE4_BASELINE_MAE, rtol=0, atol=1e-6):
        raise AssertionError("评估后的 Baseline MAE 与 Stage 4 不符")
    segments = []
    for label, mask in (
        ("target = 0", actual == 0),
        ("target = 1–3", (actual >= 1) & (actual <= 3)),
        ("target >= 4", actual >= 4),
    ):
        base_segment_mae = float(baseline_error[mask].mean())
        rf_segment_mae = float(rf_error[mask].mean())
        segments.append((label, int(mask.sum()), base_segment_mae, rf_segment_mae,
                         base_segment_mae - rf_segment_mae))
    if sum(item[1] for item in segments) != len(test):
        raise AssertionError("target 分段未覆盖所有测试行")
    # 原始行按 month、ASIN 排序；idxmax 在并列时取首行，选择可复现。
    advantage = baseline_error - rf_error
    better_index = int(np.argmax(advantage))
    worse_index = int(np.argmin(advantage))
    high_candidates = np.flatnonzero(actual >= 4)
    high_candidates = high_candidates[(high_candidates != better_index) & (high_candidates != worse_index)]
    high_index = int(high_candidates[np.argmax(actual[high_candidates])])
    return {
        "model": model, "test": test, "actual": actual,
        "baseline_prediction": baseline_prediction, "rf_prediction": prediction,
        "baseline_error": baseline_error, "rf_error": rf_error,
        "baseline_mae": baseline_mae, "rf_mae": rf_mae,
        "improvement": improvement, "relative_improvement": improvement / baseline_mae,
        "negative_count": negative_count, "segments": segments,
        "cases": {"RF 明显更好": better_index, "RF 明显更差": worse_index,
                  "高热度": high_index},
        "importance": sorted(zip(FEATURES, model.feature_importances_),
                             key=lambda pair: pair[1], reverse=True),
    }


def error_summary(errors: np.ndarray) -> tuple[float, float, float, float]:
    return tuple(float(value) for value in (
        np.median(errors), np.percentile(errors, 90),
        np.percentile(errors, 95), np.max(errors)
    ))


def write_report(result: dict, path: Path) -> None:
    segment_rows = [
        f"| {label} | {count:,} | {base:.6f} | {rf:.6f} | {delta:+.6f} |"
        for label, count, base, rf, delta in result["segments"]
    ]
    error_rows = []
    for name, key in (("lag_1 Baseline", "baseline_error"), ("RandomForest", "rf_error")):
        values = error_summary(result[key])
        error_rows.append(f"| {name} | " + " | ".join(f"{value:.6f}" for value in values) + " |")
    importance_rows = [
        f"| {rank} | {feature} | {importance:.6f} |"
        for rank, (feature, importance) in enumerate(result["importance"], start=1)
    ]
    case_rows = []
    for label, index in result["cases"].items():
        row = result["test"].iloc[index]
        case_rows.append(
            f"| {label} | {row['parent_asin']} | {row['month']} | "
            f"{result['actual'][index]:.0f} | {result['baseline_prediction'][index]:.6f} | "
            f"{result['rf_prediction'][index]:.6f} | {result['baseline_error'][index]:.6f} | "
            f"{result['rf_error'][index]:.6f} |"
        )
    lines = [
        "# Stage 5 RandomForest 与 Baseline", "",
        "Train：2020-01～2021-12，120,000 行；Test：2022-01～2022-12，60,000 行。"
        "沿用原始 `split`，没有随机切分。目标：`future_interaction_count`。",
        "", "## 模型", "",
        "仅使用 11 个 Stage 3 历史特征：" + ", ".join(f"`{feature}`" for feature in FEATURES) + "。",
        "`interaction_count`、`parent_asin`、2023 metadata 不进入 X；target 仅作 y。",
        "固定参数：" + ", ".join(f"`{key}={value}`" for key, value in PARAMETERS.items()) + "。仅训练一次。",
        "", "## 总体比较", "",
        f"lag_1 Baseline MAE：{result['baseline_mae']:.6f}；RandomForest MAE：{result['rf_mae']:.6f}。",
        f"绝对改善（Baseline − RF）：{result['improvement']:+.6f}；"
        f"相对改善：{result['relative_improvement']:+.2%}。",
        "", "## 真实 target 分段", "",
        "| 区间 | 样本数 | Baseline MAE | RF MAE | 改善 |",
        "|---|---:|---:|---:|---:|", *segment_rows,
        "", "## 绝对误差分布", "",
        "| 方法 | median | P90 | P95 | max |", "|---|---:|---:|---:|---:|", *error_rows,
        "", "## Feature importance", "",
        "| 排名 | 特征 | importance |", "|---:|---|---:|", *importance_rows,
        "", "重要性仅表示该模型对历史特征的依赖，不代表因果关系。",
        "", "## 2022 真实案例", "",
        "案例依固定行序选择：改善差值最大、恶化差值最大、其余高热度中 target 最大。"
        "仅比较预测误差，不推断商品变化原因。",
        "", "| 案例 | parent_asin | month | target | lag_1 prediction | RF prediction | Baseline abs error | RF abs error |",
        "|---|---|---|---:|---:|---:|---:|---:|", *case_rows,
        "", "## 验证与限制", "",
        "运行前核对固定行数、月份、cohort、11 特征无 NaN/无穷值及 Stage 4 Baseline MAE；"
        "运行后核对 60,000 个连续预测及负值数量。",
        f"负预测数：{result['negative_count']}；出现时业务输出 clip 到 0，未取整。",
        "数据为 5-core interaction，目标是热度代理指标，不是真实销量；"
        "模型仅在该固定 cohort 和 2022 测试期得到本报告结果。", "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    train, test = load_and_validate(DATA_PATH)
    print(f"validated_train_rows={len(train)} test_rows={len(test)} baseline_mae={mean_absolute_error(test[TARGET], test['lag_1']):.12f}", flush=True)
    result = evaluate(train, test)
    write_report(result, REPORT_PATH)
    print(f"rf_mae={result['rf_mae']:.12f}")
    print(f"absolute_improvement={result['improvement']:+.12f}")
    print(f"relative_improvement={result['relative_improvement']:+.6%}")
    print(f"negative_predictions={result['negative_count']} rf_prediction_count={len(result['rf_prediction'])}")
    print(f"report={REPORT_PATH}")


if __name__ == "__main__":
    main()
