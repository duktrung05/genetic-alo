import sys
sys.stdout.reconfigure(encoding='utf-8')

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
    dataset = DatasetFactory.create_dataset()

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
    print(f"{'Thế hệ':<10} | {'Fitness Tốt Nhất':<20} | {'Fitness Trung Bình':<20} | {'Best Hard Violations'}")
    for h in history[:5]:
        print(f"{h['generation']:<10} | {h['best_score']:<20.2f} | {h['avg_score']:<20.2f} | {h['best_hard']}")
    print("...")
    for h in history[-5:]:
        print(f"{h['generation']:<10} | {h['best_score']:<20.2f} | {h['avg_score']:<20.2f} | {h['best_hard']}")


    if result['hard_violations'] == 0:
        print("\nSUCCESS: GA đã tìm thành công Thời khóa biểu thỏa mãn HỢP LỆ VỚI 0 VI PHẠM CỨNG!")
    else:
        print("\nWARNING: Vẫn còn vi phạm ràng buộc cứng. Cần tăng số thế hệ hoặc chỉnh tham số GA.")

    print_schedule_matrix(result['best_schedule'], dataset)

if __name__ == "__main__":
    main()
