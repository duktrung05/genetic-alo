import sys
from pathlib import Path
sys.stdout.reconfigure(encoding='utf-8')

root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

from dataset import DatasetFactory
from ga import GeneticAlgorithmEngine
from constraints import ConstraintEvaluator

def print_schedule_matrix(result_schedule, dataset):
    evaluator = ConstraintEvaluator(dataset)
    section_map = evaluator.section_map
    room_map = evaluator.room_map
    ts_map = evaluator.timeslot_map

    print("\n" + "="*80)
    print("MẪU THỜI KHÓA BIỂU TỐI ƯU THU ĐƯỢC TỪ GA")
    print("="*80)
    print(f"{'Mã LHP':<8} | {'Tên Môn Học':<28} | {'Giảng Viên':<18} | {'Lớp SV':<12} | {'Phòng':<10} | {'Thời Gian'}")
    print("-" * 105)

    sorted_genes = sorted(result_schedule.genes, key=lambda g: (ts_map[g.timeslot_id].day, ts_map[g.timeslot_id].period))
    for gene in sorted_genes:
        c = section_map[gene.section_id]
        r = room_map[gene.room_id]
        ts = ts_map[gene.timeslot_id]
        print(f"{c.section_id:<8} | {c.course_name:<28} | {c.lecturer_id:<18} | {c.group_id:<12} | {r.name:<10} | {ts.day} (Tiết {ts.period})")

def main():
    print("Khởi tạo bộ dữ liệu bài toán...")
    dataset = DatasetFactory.create_medium_dataset()

    print("\nKhởi tạo GA Engine...")
    ga = GeneticAlgorithmEngine(dataset=dataset, pop_size=60, hard_weight=1000, soft_weight=1)

    print("Đang tiến hành tối ưu hóa xếp lịch bằng Thuật giải Di truyền (GA)...")
    result = ga.run(generations=100, crossover_rate=0.8, mutation_rate=0.2, use_repair=True)

    print("\n" + "="*50)
    print("KẾT QUẢ TỐI ƯU HÓA THỜI KHÓA BIỂU")
    print("="*50)
    print(f"Tổng điểm Fitness tốt nhất: {result['best_score']}")
    print(f"Số vi phạm RÀNG BUỘC CỨNG (Hard): {result['hard_violations']} (Mục tiêu: 0)")
    print(f"Chi tiết vi phạm cứng: {result['hard_details']}")
    print(f"Số vi phạm RÀNG BUỘC MỀM (Raw Soft): {result.get('raw_soft_violations', sum(result['soft_details'].values()))}")
    print(f"Điểm phạt RÀNG BUỘC MỀM (Soft Penalty): {result.get('soft_penalty', result['soft_violations'])}")
    print(f"Chi tiết vi phạm mềm: {result['soft_details']}")

    # In tiến trình 5 thế hệ đầu & 5 thế hệ cuối
    history = result['history']
    print("\n--- Tiến trình hội tụ Fitness qua các thế hệ ---")
    for h in history[:5]:
        print(f"Gen {h['generation']:>3d} | Eval: {h['fitness_evaluations']:>4d} | Hard: {h['best_hard']:>2d} | Soft: {h['best_soft_penalty']:>4d} | Score: {h['best_score']:.2f}")
    if len(history) > 10:
        print("...")
    for h in history[-5:]:
        print(f"Gen {h['generation']:>3d} | Eval: {h['fitness_evaluations']:>4d} | Hard: {h['best_hard']:>2d} | Soft: {h['best_soft_penalty']:>4d} | Score: {h['best_score']:.2f}")

    print_schedule_matrix(result['best_schedule'], dataset)

    if result['hard_violations'] == 0:
        from evaluation import export_schedule_to_csv, export_schedule_to_excel, export_metadata_to_json
        csv_path = "outputs/timetables/best_timetable.csv"
        excel_path = "outputs/timetables/best_timetable.xlsx"
        meta_path = "outputs/timetables/best_timetable_metadata.json"
        export_schedule_to_csv(result['best_schedule'], dataset, csv_path)
        export_schedule_to_excel(result['best_schedule'], dataset, excel_path)
        export_metadata_to_json(result, meta_path)
        print(f"\n--> Đã xuất thời khóa biểu thành công ra file:\n  CSV: {csv_path}\n  Excel: {excel_path}")

if __name__ == "__main__":
    main()
