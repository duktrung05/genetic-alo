import sys
import os
import argparse
from datetime import datetime
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

sys.stdout.reconfigure(encoding="utf-8")

from dataset import ExcelDatasetLoader
from constraints import (
    ConstraintEvaluator,
    DEFAULT_SOFT_WEIGHT_PROFILE,
    SOFT_WEIGHT_PROFILES,
    SoftConstraintConfig,
)
from ga import GeneticAlgorithmEngine
from evaluation import (
    export_schedule_to_excel,
    export_schedule_query_data,
    export_metadata_to_json,
)


def parse_args():
    parser = argparse.ArgumentParser(
        description="Production Timetable Generator (GA + Repair, optional SLS)"
    )

    parser.add_argument(
        "--input",
        type=str,
        default="data/instances/instance_easy.xlsx",
        help="Input Excel dataset path "
        "(default: data/instances/instance_easy.xlsx)",
    )

    parser.add_argument(
        "--output",
        type=str,
        default="outputs/production/best_timetable.xlsx",
        help="Output official Excel timetable path "
        "(default: outputs/production/best_timetable.xlsx)",
    )

    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed for execution reproducibility (default: 42)",
    )

    parser.add_argument(
        "--search-evaluation-budget",
        type=int,
        default=1000,
        help="Search fitness evaluation budget (default: 1000)",
    )

    parser.add_argument(
        "--population-size",
        type=int,
        default=60,
        help="GA Population Size (default: 60)",
    )

    parser.add_argument(
        "--soft-local-search",
        action="store_true",
        default=False,
        help="Enable post-search Soft Local Search (default: False)",
    )

    parser.add_argument(
        "--weight-profile",
        choices=list(SOFT_WEIGHT_PROFILES),
        default=DEFAULT_SOFT_WEIGHT_PROFILE,
        help="S1-S7 stakeholder weight profile (default: balanced)",
    )

    return parser.parse_args()


def get_production_method_identity(use_soft_local_search: bool):
    """Return the canonical method id and display name for this production run."""
    if use_soft_local_search:
        return "ga_repair_sls", "GA + Repair + SLS (Production)"
    return "ga_repair", "GA + Repair"


def main():
    args = parse_args()
    method_id, method_name = get_production_method_identity(
        args.soft_local_search
    )

    print("=" * 80)
    print(
        "PRODUCTION TIMETABLE GENERATOR — "
        "GA + REPAIR + OPTIONAL POST-SEARCH SLS"
    )
    print("=" * 80)

    # ==================================================================
    # 1. NẠP BỘ DỮ LIỆU
    # ==================================================================

    input_path = args.input
    snapshot_path = "outputs/datasets/instance_easy.normalized.json"

    if os.path.exists(input_path):
        print(
            f"\n[Phase 1] Đang tải dữ liệu từ Excel file "
            f"'{input_path}'..."
        )

        dataset = ExcelDatasetLoader.load_and_validate(input_path)

    elif os.path.exists(snapshot_path):
        print(
            f"\n[Phase 1] Đang tải dữ liệu từ Normalized JSON Snapshot "
            f"'{snapshot_path}'..."
        )

        dataset = ExcelDatasetLoader.load_normalized_json(snapshot_path)

    else:
        raise FileNotFoundError(
            f"Neither Excel input '{input_path}' "
            f"nor snapshot '{snapshot_path}' exist!"
        )

    # ==================================================================
    # 2. CHẠY GA + REPAIR
    # ==================================================================

    print(f"\n[Phase 2] Đang chạy thuật toán chính: {method_name}...")

    if args.soft_local_search:
        print(
            "[Phase 2] Post-Search Soft Local Search: ENABLED "
            "(quality optimization)"
        )
    else:
        print("[Phase 2] Post-Search Soft Local Search: DISABLED")

    ga_config = {
        "pop_size": args.population_size,
        "generations": 100,
        "crossover_rate": 0.8,
        "mutation_rate": 0.2,
        "hard_weight": 1000,
        "soft_weight": 1,
    }

    soft_config = SoftConstraintConfig.from_profile(args.weight_profile)
    engine = GeneticAlgorithmEngine(
        dataset,
        pop_size=ga_config["pop_size"],
        hard_weight=ga_config["hard_weight"],
        soft_weight=ga_config["soft_weight"],
        seed=args.seed,
        soft_config=soft_config,
    )

    run_result = engine.run(
        generations=ga_config["generations"],
        crossover_rate=ga_config["crossover_rate"],
        mutation_rate=ga_config["mutation_rate"],
        use_repair=True,
        use_soft_local_search=args.soft_local_search,
        evaluation_budget=args.search_evaluation_budget,
        seed=args.seed,
    )

    # ------------------------------------------------------------------
    # QUAN TRỌNG:
    # best_schedule ở đây phải là lịch cuối cùng do engine trả về.
    # Nếu SLS được bật, đây phải là lịch SAU SLS.
    # ------------------------------------------------------------------

    best_schedule = run_result["best_schedule"]
    metrics = run_result["run_metrics"]

    # ==================================================================
    # 3. ĐÁNH GIÁ LẠI ĐỘC LẬP LẦN CUỐI
    # ==================================================================
    #
    # KHÔNG dùng run_result["soft_penalty"] làm nguồn dữ liệu chuẩn
    # cho đầu ra production.
    #
    # Luôn đánh giá lại chính best_schedule cuối cùng.
    #
    # Đây là bản sửa chính cho lỗi:
    #
    #   GA + Repair = 2063
    #   SLS         = 1671
    #   metadata    = 2063  <-- LỖI CŨ
    #
    # Sau khi sửa:
    #
    #   Lịch cuối cùng
    #       ↓
    #   Bộ đánh giá
    #       ↓
    #   Excel / JSON truy vấn / siêu dữ liệu / UI đều có cùng điểm cuối.
    # ==================================================================

    evaluator = ConstraintEvaluator(dataset, soft_config=soft_config)
    unified = evaluator.evaluate_unified(best_schedule)

    hard_violations = unified.hard_violations
    soft_penalty = unified.soft_penalty

    # Thông tin kiểm tra cho SLS
    soft_before_sls = getattr(metrics, "soft_before_sls", None)

    # Nguồn dữ liệu chuẩn của "sau SLS" luôn là lịch cuối cùng
    # vừa được bộ đánh giá kiểm tra độc lập.
    soft_after_sls = soft_penalty

    # ==================================================================
    # 4. IN KẾT QUẢ PRODUCTION CUỐI CÙNG
    # ==================================================================

    print("\n" + "=" * 80)
    print("KẾT QUẢ TẠO THỜI KHÓA BIỂU — FINAL PRODUCTION RESULT")
    print("=" * 80)

    print(f"  METHOD                   : {method_name}")
    print(f"  Seed                     : {args.seed}")
    print(
        f"  Search Budget            : "
        f"{args.search_evaluation_budget}"
    )
    print(
        f"  Runtime (s)              : "
        f"{metrics.runtime_seconds:.4f}"
    )
    print(
        f"  Time to First Feasible   : "
        f"{metrics.time_to_first_feasible_seconds}"
    )
    print(
        f"  Final Hard Violations    : "
        f"{hard_violations}"
    )
    print(
        f"  Final Soft Penalty       : "
        f"{soft_penalty}"
    )

    if args.soft_local_search:
        print(
            f"  Soft Before SLS          : "
            f"{soft_before_sls}"
        )
        print(
            f"  Soft After SLS           : "
            f"{soft_after_sls}"
        )

    print(
        f"  Hard Feasible            : "
        f"{'CÓ (0 vi phạm)' if hard_violations == 0 else 'KHÔNG'}"
    )

    # ==================================================================
    # 5. PHÂN TÍCH RÀNG BUỘC MỀM
    # ==================================================================

    print("\n  CHI TIẾT RÀNG BUỘC MỀM CHUẨN HÓA (S1–S7):")

    print(
        f"  {'ID':<4} | "
        f"{'Technical Key':<26} | "
        f"{'Raw':<8} | "
        f"{'Norm':<8} | "
        f"{'Weight':<6} | "
        f"{'Weighted Penalty'}"
    )

    print("  " + "-" * 80)

    for item in unified.soft_breakdown:
        print(
            f"  {item.constraint_id:<4} | "
            f"{item.constraint_key:<26} | "
            f"{item.raw_count:<8.4f} | "
            f"{item.normalized_penalty:<8.4f} | "
            f"{item.weight:<6} | "
            f"{item.weighted_penalty:.6f}"
        )

    print(
        f"  TỔNG PHẠM QUY MỀM (SOFT PENALTY): "
        f"{soft_penalty}"
    )

    print("=" * 80)

    # ==================================================================
    # 6. CHUẨN BỊ THƯ MỤC ĐẦU RA
    # ==================================================================

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    metadata_path = (
        output_path.parent / "best_timetable_metadata.json"
    )

    query_json_path = (
        output_path.parent / "schedule_query_data.json"
    )

    # ==================================================================
    # 7. ĐỒNG BỘ CHỈ SỐ LẦN CHẠY ĐỂ XUẤT
    # ==================================================================
    #
    # metrics.to_dict() có thể vẫn chứa final_soft_penalty
    # từ trước khi SLS chạy.
    #
    # Ta tạo một từ điển rồi ghi đè các trường CUỐI CÙNG
    # bằng kết quả từ lần đánh giá lại độc lập.
    # ==================================================================

    metrics_dict = metrics.to_dict()

    metrics_dict["method"] = method_name
    metrics_dict["hard_violations"] = hard_violations
    metrics_dict["soft_penalty"] = soft_penalty

    metrics_dict["final_hard_violations"] = hard_violations
    metrics_dict["final_soft_penalty"] = soft_penalty

    metrics_dict["soft_before_sls"] = soft_before_sls
    metrics_dict["soft_after_sls"] = soft_after_sls

    metrics_dict["feasible"] = hard_violations == 0
    metrics_dict["is_hard_feasible"] = hard_violations == 0

    # Nếu score tồn tại và Hard = 0 thì điểm cuối
    # phải phản ánh điểm phạt mềm cuối cùng.
    if "score" in metrics_dict:
        metrics_dict["score"] = (
            float(soft_penalty)
            if hard_violations == 0
            else metrics_dict["score"]
        )

    # ==================================================================
    # 8. TẠO SIÊU DỮ LIỆU CUỐI CÙNG
    # ==================================================================

    meta_export = {
        "method": method_name,
        "primary_method": method_id,
        "selected_methods": method_id,

        "seed": args.seed,

        "generated_at": datetime.now().isoformat(
            timespec="seconds"
        ),

        "search_evaluation_budget":
            args.search_evaluation_budget,

        "population_size":
            args.population_size,

        "soft_weight_profile":
            args.weight_profile,

        "soft_weights": {
            item.constraint_id: item.weight for item in unified.soft_breakdown
        },

        "soft_enabled": {
            definition.constraint_id: definition.enabled
            for definition in soft_config.definitions.values()
        },

        "effective_soft_constraints": soft_config.to_metadata(),

        "generations":
            ga_config["generations"],

        "crossover_rate":
            ga_config["crossover_rate"],

        "mutation_rate":
            ga_config["mutation_rate"],

        "soft_local_search_enabled":
            args.soft_local_search,

        # --------------------------------------------------------------
        # KẾT QUẢ PRODUCTION CUỐI CÙNG
        # --------------------------------------------------------------

        "hard_violations":
            hard_violations,

        "soft_penalty":
            soft_penalty,

        "final_hard_violations":
            hard_violations,

        "final_soft_penalty":
            soft_penalty,

        "feasible":
            hard_violations == 0,

        # --------------------------------------------------------------
        # KIỂM TRA SLS
        # --------------------------------------------------------------

        "soft_before_sls":
            soft_before_sls,

        "soft_after_sls":
            soft_after_sls,

        # --------------------------------------------------------------
        # THỜI GIAN CHẠY
        # --------------------------------------------------------------

        "runtime_seconds":
            metrics.runtime_seconds,

        "time_to_first_feasible_seconds":
            metrics.time_to_first_feasible_seconds,

        # --------------------------------------------------------------
        # CHỈ SỐ LẦN CHẠY
        # --------------------------------------------------------------

        "all_runs_flat": [
            metrics_dict
        ],
    }

    # ==================================================================
    # 9. XUẤT THỜI KHÓA BIỂU EXCEL CHÍNH THỨC
    # ==================================================================

    exported_file = export_schedule_to_excel(
        schedule=best_schedule,
        dataset=dataset,
        output_path=output_path,
        metadata=meta_export,
        allow_infeasible_export=False,
        soft_config=soft_config,
    )

    print(
        f"\n--> Đã xuất workbook thời khóa biểu chính thức tại: "
        f"{exported_file}"
    )

    # ==================================================================
    # 10. XUẤT JSON TRUY VẤN
    # ==================================================================

    if hard_violations == 0:
        query_file = export_schedule_query_data(
            schedule=best_schedule,
            dataset=dataset,
            output_path=query_json_path,
            hard_violations=hard_violations,
            soft_penalty=soft_penalty,
            metadata=meta_export,
            soft_config=soft_config,
        )

        print(
            f"--> Đã xuất dữ liệu tra cứu JSON tại: "
            f"{query_file}"
        )

    # ==================================================================
    # 11. XUẤT JSON SIÊU DỮ LIỆU CUỐI CÙNG
    # ==================================================================
    #
    # Đây là phần trước đây main.py bị thiếu.
    #
    # Nếu không ghi lại file này thì UI tiếp tục đọc
    # best_timetable_metadata.json cũ.
    # ==================================================================

    export_metadata_to_json(
        meta_export,
        metadata_path,
    )

    print(
        f"--> Đã xuất metadata FINAL tại: "
        f"{metadata_path}"
    )

    # ==================================================================
    # 12. TỔNG KẾT TÍNH NHẤT QUÁN CỦA ĐẦU RA CUỐI
    # ==================================================================

    print("\n" + "=" * 80)
    print("FINAL OUTPUT CONSISTENCY")

    print(
        f"  Excel Final Hard         : "
        f"{hard_violations}"
    )

    print(
        f"  Excel Final Soft         : "
        f"{soft_penalty}"
    )

    print(
        f"  Metadata Final Hard      : "
        f"{hard_violations}"
    )

    print(
        f"  Metadata Final Soft      : "
        f"{soft_penalty}"
    )

    if args.soft_local_search:
        print(
            f"  SLS Improvement          : "
            f"{soft_before_sls} -> {soft_after_sls}"
        )

    print("=" * 80)

    # ==================================================================
    # 13. VẼ BIỂU ĐỒ HỘI TỤ GA
    # ==================================================================
    #
    # Lưu ý:
    # history là quá trình TÌM KIẾM GA TOÀN CỤC.
    # SLS chạy sau tìm kiếm nên điểm SLS cuối có thể thấp hơn
    # điểm cuối trên đường cong hội tụ.
    # ==================================================================

    history = run_result.get("history", [])

    if history:
        chart_dir = output_path.parent
        chart_path = chart_dir / f"convergence_{method_id}.png"

        gens = [
            h["generation"]
            for h in history
        ]

        hards = [
            h["best_hard"]
            for h in history
        ]

        softs = [
            h["best_soft_penalty"]
            for h in history
        ]

        fig, (ax1, ax2) = plt.subplots(
            1,
            2,
            figsize=(12, 4.5),
        )

        ax1.plot(
            gens,
            hards,
            linewidth=2,
            label="Hard Violations",
        )

        ax1.set_title(
            f"{method_name} — Hard Violations Convergence"
        )

        ax1.set_xlabel("Generation")
        ax1.set_ylabel("Hard Violations")

        ax1.grid(
            True,
            linestyle="--",
            alpha=0.6,
        )

        ax2.plot(
            gens,
            softs,
            linewidth=2,
            label="Soft Penalty",
        )

        ax2.set_title(
            f"{method_name} — Soft Penalty Convergence"
        )

        ax2.set_xlabel("Generation")
        ax2.set_ylabel("Soft Penalty")

        ax2.grid(
            True,
            linestyle="--",
            alpha=0.6,
        )

        plt.tight_layout()

        plt.savefig(
            chart_path,
            dpi=300,
        )

        plt.close()

        print(
            f"--> Đã lưu biểu đồ hội tụ tại: "
            f"{chart_path}"
        )


if __name__ == "__main__":
    main()
