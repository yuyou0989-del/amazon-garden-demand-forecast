"""Stage 6B：复现 Stage 5 固定模型预测，并进行 2022 测试误差分析。"""

from __future__ import annotations

import numpy as np
import pandas as pd

from src.config import PROJECT_ROOT, REPORT_DIR
from src.train_random_forest import DATA_PATH, evaluate, load_and_validate


REPORT_PATH = REPORT_DIR / "stage6_error_analysis.md"
CANDIDATES_PATH = PROJECT_ROOT / "data" / "processed" / "stage6_error_candidates.csv"
STAGE5_RF_MAE = 0.935867471409
STAGE5_P95 = 3.216521
OUTPUT_COLUMNS = [
    "parent_asin", "month", "actual", "prediction",
    "signed_error", "absolute_error", "direction",
]


def make_error_rows() -> tuple[pd.DataFrame, float, dict]:
    train, test = load_and_validate(DATA_PATH)
    # Stage 5 未持久化模型/逐行预测；按完全相同代码与固定参数仅重现一次。
    stage5 = evaluate(train, test)
    if not np.isclose(stage5["rf_mae"], STAGE5_RF_MAE, rtol=0, atol=1e-6):
        raise ValueError(f"RF MAE={stage5['rf_mae']:.12f} 与 Stage 5 不符；停止分析")
    actual = stage5["actual"]
    prediction = stage5["rf_prediction"]
    signed = actual - prediction
    absolute = np.abs(signed)
    rows = pd.DataFrame({
        "parent_asin": test["parent_asin"].to_numpy(),
        "month": test["month"].to_numpy(),
        "actual": actual,
        "prediction": prediction,
        "signed_error": signed,
        "absolute_error": absolute,
        "direction": np.where(signed > 0, "underprediction",
                              np.where(signed < 0, "overprediction", "exact")),
    })
    if len(rows) != 60_000 or rows[OUTPUT_COLUMNS].isna().any().any():
        raise AssertionError("测试行数或误差字段不完整")
    p90, p95, p99 = (float(value) for value in np.percentile(absolute, [90, 95, 99]))
    if not np.isclose(p95, STAGE5_P95, rtol=0, atol=1e-6):
        raise ValueError(f"P95={p95:.12f} 与 Stage 5 不符；停止分析")
    thresholds = {"P90": p90, "P95": p95, "P99": p99}
    return rows, p95, {"stage5": stage5, "thresholds": thresholds}


def select_top(rows: pd.DataFrame, count: int, direction: str | None = None) -> pd.DataFrame:
    selected = rows if direction is None else rows.loc[rows["direction"].eq(direction)]
    return selected.sort_values(
        ["absolute_error", "parent_asin", "month"],
        ascending=[False, True, True], kind="stable"
    ).head(count)


def format_rows(rows: pd.DataFrame) -> list[str]:
    return [
        f"| {row.parent_asin} | {row.month} | {row.actual:.0f} | "
        f"{row.prediction:.6f} | {row.signed_error:+.6f} | "
        f"{row.absolute_error:.6f} | {row.direction} |"
        for row in rows.itertuples(index=False)
    ]



def direction_magnitudes(rows: pd.DataFrame, direction: str) -> dict:
    # 低估为正残差，高估为负残差；幅度统一转成正数，便于比较。
    signed = rows.loc[rows["direction"].eq(direction), "signed_error"]
    magnitudes = signed if direction == "underprediction" else -signed
    if magnitudes.empty:
        raise ValueError(f"{direction} 没有样本，无法计算幅度分布")
    return {
        "count": len(magnitudes), "mean": float(magnitudes.mean()),
        "median": float(magnitudes.median()),
        "p90": float(magnitudes.quantile(0.90)),
        "p95": float(magnitudes.quantile(0.95)),
        "total": float(magnitudes.sum()),
    }


def bias_analysis(rows: pd.DataFrame) -> dict:
    signed = rows["signed_error"]
    under = direction_magnitudes(rows, "underprediction")
    over = direction_magnitudes(rows, "overprediction")
    if not np.isclose(under["total"] - over["total"], signed.sum(), rtol=0, atol=1e-8):
        raise AssertionError("误差方向幅度之和与整体 signed_error 不一致")
    segments = []
    for label, mask in (
        ("target = 0", rows["actual"].eq(0)),
        ("target = 1–3", rows["actual"].between(1, 3)),
        ("target >= 4", rows["actual"].ge(4)),
    ):
        part = rows.loc[mask]
        segments.append({
            "label": label, "rows": len(part),
            "mean_signed_error": float(part["signed_error"].mean()),
            "under_count": int(part["direction"].eq("underprediction").sum()),
            "over_count": int(part["direction"].eq("overprediction").sum()),
            "mean_absolute_error": float(part["absolute_error"].mean()),
        })
    if sum(item["rows"] for item in segments) != len(rows):
        raise AssertionError("target 分段没有覆盖完整 Test")
    return {
        "mean": float(signed.mean()), "median": float(signed.median()),
        "sum": float(signed.sum()), "under": under, "over": over,
        "segments": segments,
    }


def write_report(rows: pd.DataFrame, candidates: pd.DataFrame, analysis: dict) -> None:
    thresholds = analysis["thresholds"]
    all_directions = rows["direction"].value_counts()
    candidate_directions = candidates["direction"].value_counts()
    repeated = (candidates.groupby("parent_asin").size()
                .reset_index(name="anomaly_month_count")
                .sort_values(["anomaly_month_count", "parent_asin"],
                             ascending=[False, True]).head(10))
    top10 = select_top(rows, 10)
    under5 = select_top(candidates, 5, "underprediction")
    over5 = select_top(candidates, 5, "overprediction")
    header = "| parent_asin | month | actual | prediction | signed_error | absolute_error | direction |"
    divider = "|---|---|---:|---:|---:|---:|---|"
    lines = [
        "# Stage 6B：RandomForest 预测误差与异常候选", "",
        "Stage 5 未保存逐行预测或模型文件；本次仅以同一 Stage 3 数据、同一 11 个特征、"
        "同一固定参数和时间切分重现一次预测，没有调参或训练其他模型。",
        f"2022 Test：{len(rows):,} 行；复核 RF MAE：{analysis['stage5']['rf_mae']:.6f}。",
        "`signed_error = actual − prediction`；正值为 underprediction（低估），"
        "负值为 overprediction（高估），零为 exact。",
        "", "## 阈值与数量", "",
        f"绝对误差 P90 = {thresholds['P90']:.6f}；P95 = {thresholds['P95']:.6f}；"
        f"P99 = {thresholds['P99']:.6f}。",
        f"规则：`absolute_error > P95`。候选 {len(candidates):,} 行，"
        f"占 Test {len(candidates) / len(rows):.4%}。严格大于，不包含等于阈值的行。",
        f"全部 Test：underprediction {all_directions.get('underprediction', 0):,}；"
        f"overprediction {all_directions.get('overprediction', 0):,}；"
        f"exact {all_directions.get('exact', 0):,}。",
        f"P95 候选：underprediction {candidate_directions.get('underprediction', 0):,}；"
        f"overprediction {candidate_directions.get('overprediction', 0):,}；"
        f"exact {candidate_directions.get('exact', 0):,}。",
        "", "## 最大绝对误差 Top 10", "", header, divider, *format_rows(top10),
        "", "## 候选中最大低估 Top 5", "", header, divider, *format_rows(under5),
        "", "## 候选中最大高估 Top 5", "", header, divider, *format_rows(over5),
        "", "## 重复进入候选的商品 Top 10", "",
        "| parent_asin | anomaly month count |", "|---|---:|",
        *(f"| {row.parent_asin} | {row.anomaly_month_count} |"
          for row in repeated.itertuples(index=False)),
        "", "## 证据边界", "",
        "P95 来自 2022 Test，只用于事后模型误差分析，不是已部署的生产报警阈值；"
        "不得用该 Test 阈值继续调整 RandomForest，再在同一 Test 宣称性能提升。"
        "生产环境应先从 Train/Validation 的历史误差确定阈值，再应用于未来未见数据。",
        "候选表示预测误差大，不证明商品热度变化的原因；interaction 也不等于销量。", "",
    ]
    bias = bias_analysis(rows)
    under, over = bias["under"], bias["over"]
    direction_rows = [
        f"| {label} | {stats['count']:,} | {stats['mean']:.6f} | "
        f"{stats['median']:.6f} | {stats['p90']:.6f} | "
        f"{stats['p95']:.6f} | {stats['total']:.6f} |"
        for label, stats in (("underprediction", under), ("overprediction", over))
    ]
    segment_rows = [
        f"| {item['label']} | {item['rows']:,} | {item['mean_signed_error']:+.6f} | "
        f"{item['under_count']:,} | {item['over_count']:,} | "
        f"{item['mean_absolute_error']:.6f} |"
        for item in bias["segments"]
    ]
    net_direction = "总体平均低估" if bias["mean"] > 0 else "总体平均高估" if bias["mean"] < 0 else "总体平均无方向偏差"
    lines.extend([
        "", "## Prediction Bias / Direction Analysis", "",
        f"全部 Test：mean signed_error = {bias['mean']:+.6f}；"
        f"median = {bias['median']:+.6f}；sum = {bias['sum']:+.6f}。",
        "| 方向 | count | mean magnitude | median | P90 | P95 | total magnitude |",
        "|---|---:|---:|---:|---:|---:|---:|", *direction_rows,
        "", "| 真实 target 区间 | rows | mean signed_error | under count | over count | MAE |",
        "|---|---:|---:|---:|---:|---:|", *segment_rows,
        "", f"在这 60,000 行中，高估 {over['count']:,} 次、低估 {under['count']:,} 次；"
        f"平均残差显示{net_direction}。低估平均幅度 {under['mean']:.6f}，"
        f"高估平均幅度 {over['mean']:.6f}；应结合分段表判断方向和大小，"
        "不能只凭高估次数较多就下结论。",
        "这些是 2022 Test 的事后残差描述；不能证明未来数据也有相同偏差，"
        "不能推断误差原因或真实销量，也不能据此回头调参后在同一 Test 宣称改进。", "",
    ])
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    rows, p95, analysis = make_error_rows()
    candidates = rows.loc[rows["absolute_error"].gt(p95), OUTPUT_COLUMNS].copy()
    if not candidates["absolute_error"].gt(p95).all():
        raise AssertionError("候选包含未超过 P95 的行")
    candidates = select_top(candidates, len(candidates))
    candidates.to_csv(CANDIDATES_PATH, index=False)
    write_report(rows, candidates, analysis)
    print(f"test_rows={len(rows)} rf_mae={analysis['stage5']['rf_mae']:.12f}")
    print("thresholds=" + ", ".join(f"{key}:{value:.12f}" for key, value in analysis["thresholds"].items()))
    print(f"candidates={len(candidates)} share={len(candidates)/len(rows):.6%}")
    print("all_directions=" + str(rows["direction"].value_counts().to_dict()))
    print("candidate_directions=" + str(candidates["direction"].value_counts().to_dict()))
    bias = bias_analysis(rows)
    print(f"signed_error_mean={bias['mean']:+.12f} median={bias['median']:+.12f} sum={bias['sum']:+.12f}")
    print("under_magnitude=" + str(bias["under"]))
    print("over_magnitude=" + str(bias["over"]))
    print("target_segments=" + str(bias["segments"]))
    print(f"report={REPORT_PATH} candidates_csv={CANDIDATES_PATH}")


if __name__ == "__main__":
    main()
