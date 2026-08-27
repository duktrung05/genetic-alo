# BÁO CÁO KỸ THUẬT HỆ THỐNG XẾP THỜI KHÓA BIỂU GENETIC ALO

## 1. Giới thiệu

Xếp thời khóa biểu đại học là bài toán tối ưu tổ hợp: mỗi lớp học phần phải được gán vào phòng và thời điểm trong một không gian phương án rất lớn, trong khi nhiều tài nguyên dùng chung và nhiều quy tắc phải được thỏa mãn đồng thời. Các xung đột điển hình gồm một giảng viên, nhóm sinh viên hoặc phòng học bị dùng cho hai hoạt động trùng giờ; phòng không đủ sức chứa hoặc sai loại; giảng viên không sẵn sàng; và một buổi học kéo dài vượt khỏi khối tiết hợp lệ.

Mục tiêu của project là **xây dựng hệ thống tự động tạo thời khóa biểu khả thi bằng Genetic Algorithm (GA) kết hợp Repair và Soft Local Search (SLS), đồng thời cung cấp giao diện demo và truy vấn thời khóa biểu**. Hệ thống phân biệt hai lớp tiêu chí:

- **Hard constraints** là điều kiện bắt buộc. Một lịch chỉ được coi là *feasible* khi tổng vi phạm hard bằng 0.
- **Soft objectives** đo chất lượng vận hành và mức độ thuận tiện. Chúng được tối thiểu hóa sau khi ưu tiên feasibility, nhưng không quyết định tính hợp lệ của lịch.

Project không tuyên bố chứng minh nghiệm tối ưu toàn cục. Kết quả được gọi là *feasible timetable*, *best solution found* hoặc kết quả của *final hybrid method*.

## 2. Phạm vi và mục tiêu hệ thống

Hệ thống cuối cùng hỗ trợ đọc dữ liệu Excel, validation nghiêm ngặt, tối ưu GA, heuristic Repair, hậu xử lý SLS, hiển thị và lọc thời khóa biểu theo nhóm sinh viên/giảng viên/phòng, xuất Excel/JSON/CSV, trợ lý Ask Schedule, và benchmark trên hai instance EASY/MEDIUM.

Ngoài phạm vi hiện tại là: bảo đảm tối ưu chính xác; baseline CP-SAT; triển khai production quy mô lớn, đa người dùng; full LLM chatbot; Retrieval-Augmented Generation (RAG); vector database; và các bộ dữ liệu nghiên cứu Hard/Stress. Hai instance cuối phục vụ demo và đánh giá trong phạm vi môn học, không đại diện cho mọi quy mô trường đại học.

## 3. Kiến trúc hệ thống

Các mô-đun chính và trách nhiệm:

- `domain/`: định nghĩa thực thể, `Gene`, `Schedule` và phép mở rộng lớp học phần thành các hoạt động theo tuần.
- `dataset/`: đọc workbook, ánh xạ dữ liệu vào domain và validation cấu trúc/nghiệp vụ.
- `constraints/`: đánh giá hard constraints, S1–S7 và thực hiện Repair.
- `ga/`: khởi tạo quần thể, selection, crossover, mutation, elitism, quản lý budget và SLS.
- `evaluation/`: run metrics, phương pháp benchmark, thống kê, biểu đồ và exporter.
- `schedule_assistant/`: parser luật, phân giải entity, query service và formatter.
- `main.py`, `main_benchmark.py`: entrypoint production và benchmark tổng quát.
- `ui_app.py`: demo Streamlit tích hợp Scheduler, Timetable, Ask Schedule và artifact benchmark.

Luồng khái niệm là:

```text
Excel → Loader → Validator → Domain Objects
      → GA → Repair → Evaluator → SLS
      → Final Schedule → UI / Export / Ask Schedule
```

Trong engine, Repair được áp dụng cho offspring trong quá trình GA. SLS chỉ xử lý nghiệm tốt nhất sau GA và chỉ khi nghiệm đó đã feasible. Schedule cuối được evaluator kiểm tra lại trước khi trình bày/xuất.

> [Figure placeholder — Figure 1: Overall system architecture]

## 4. Mô hình dữ liệu

**Table 1 — Domain entities**

| Thực thể | Vai trò trong triển khai |
|---|---|
| `Course` | Môn học, gồm ID, tên, số tín chỉ, độ khó và `course_code` chính thức nếu có. |
| `CourseSection` | Lớp học phần thuộc một course, gắn giảng viên, nhóm sinh viên, sĩ số, loại phòng, thời lượng, preference và `meetings_per_week`. |
| `SchedulingActivity` | Một buổi học có thể xếp lịch; giữ `activity_id`, chỉ số buổi và tham chiếu section cha. |
| `Lecturer` | Giảng viên và tập timeslot được phép; `None` biểu diễn không giới hạn bởi availability. |
| `StudentGroup` | Nhóm sinh viên và cơ sở chính (*home campus*) nếu được khai báo. |
| `Campus` | Danh mục cơ sở authoritative để các tài nguyên khác tham chiếu. |
| `Room` | Phòng, sức chứa, loại `NORMAL`/`LAB` và campus. |
| `Timeslot` | Ngày, tiết, thời gian bắt đầu/kết thúc, session và ID ngoài nếu có. |
| `Gene` | Gán đúng một `activity_id` vào `room_id` và `timeslot_id` bắt đầu. |
| `Schedule` | Danh sách gene tạo thành một chromosome hoàn chỉnh. |

Quan hệ cốt lõi:

```text
CourseSection → meetings_per_week → SchedulingActivity → Gene
```

Một `SchedulingActivity` tương ứng một buổi học cần xếp; một `Gene` là phép gán buổi đó vào phòng và start timeslot; một chromosome (`Schedule`) là một thời khóa biểu; một population chứa nhiều chromosome ứng viên. Khi `meetings_per_week = 1`, `activity_id` bằng `section_id` để duy trì backward compatibility. Khi lớn hơn 1, các ID có hậu tố `-M1`, `-M2`, ...; các activity vẫn cùng tham chiếu section cha.

> [Figure placeholder — Figure 2: Section → SchedulingActivity → Gene representation]

## 5. Biểu diễn Genetic Algorithm

Thứ tự activity của chromosome được cố định. Mỗi gene lưu phòng và timeslot bắt đầu; các tiết tiếp theo được suy ra từ `duration_periods`. Population là tập các lịch ứng viên cùng cấu trúc activity.

Đánh giá dùng cặp:

```text
(hard_violations, soft_penalty)
```

Việc so sánh, chọn nghiệm tốt nhất và elitism dùng thứ tự **lexicographic**: giảm hard violations trước, sau đó mới giảm soft penalty. `ConstraintEvaluator` còn cung cấp weighted compatibility score với hệ số hard 1000 và soft 1, nhưng scalar này không thay thế thứ tự ưu tiên lexicographic trong GA cuối. Vì vậy một cải thiện soft không được phép đánh đổi lấy vi phạm hard trong xếp hạng nghiệm.

## 6. Quy trình Genetic Algorithm

1. **Initialization:** sinh 60 chromosome. Với từng activity, engine chọn phòng đủ sức chứa/đúng loại và start timeslot tạo được khối tiết liên tiếp trong cùng session, phù hợp lecturer availability. Với nhiều buổi của cùng section, ngày chưa dùng được ưu tiên khi có thể.
2. **Selection:** tournament selection cỡ 3; cá thể có cặp `(hard, soft)` nhỏ nhất thắng.
3. **Crossover:** one-point crossover với xác suất 0,8. Hai parent phải có cùng thứ tự activity; điểm cắt nằm giữa gene đầu và cuối.
4. **Mutation:** mỗi gene có xác suất mutation 0,2; toán tử chọn thay phòng hoặc thay timeslot. Candidate cục bộ được lọc theo capacity, room type, duration block và lecturer availability; ngày khác cho các buổi cùng section được ưu tiên.
5. **Evaluation và Repair:** offspring được đánh giá; khi bật, Repair tìm cách sửa xung đột trước khi offspring đi vào thế hệ mới.
6. **Elitism:** giữ lại 2 nghiệm tốt nhất theo thứ tự lexicographic.
7. **Next generation:** bổ sung offspring đã xử lý đến đủ kích thước population.
8. **Termination:** cấu hình cuối có giới hạn 100 generations và GA evaluation budget 1.000. Khi budget được cung cấp, budget là giới hạn đo chính và engine chạy đủ budget; khi không dùng budget, lịch hoàn hảo theo cả hard và soft mới có thể kích hoạt dừng sớm.

Mutation làm tăng diversity và khám phá candidate assignment mới; nó không phải cơ chế tự bảo đảm feasibility.

> [Figure placeholder — Figure 3: GA + Repair + SLS pipeline]

## 7. Repair Engine

GA thuần vẫn có thể tạo room, lecturer hoặc student-group overlap, lecturer-unavailable assignment, phòng sai loại, hoặc vi phạm cùng ngày của nhiều buổi. Repair là **heuristic constraint repair**, không phải LLM, machine-learning model hay exact solver.

Repair từ chối chromosome sai cấu trúc thay vì tự tạo gene bị thiếu. Các activity được ưu tiên theo candidate-domain nhỏ, nhu cầu LAB, thời lượng, mức hạn chế của lecturer, sĩ số và ID. Trong tối đa 15 lần thử, engine giữ assignment hiện tại nếu hợp lệ hoặc tìm theo ba tầng: (1) giữ timeslot, đổi room; (2) giữ room, đổi timeslot; (3) đổi cả hai. Mỗi candidate phải thỏa room capacity/type, khối tiết liên tiếp cùng session, lecturer availability, không collision và quy tắc khác ngày cho các meeting cùng section.

Repair đánh giá các phương án, giữ lịch tốt nhất theo `(hard, soft)`, và dừng sớm khi hard bằng 0. Các lần thử sau có thể xáo trộn thứ tự candidate. Trạng thái trả về là `improved`, `unchanged` hoặc `failed`; do đó Repair có bằng chứng thực nghiệm mạnh nhưng không có bảo đảm toán học luôn sửa được mọi instance.

```text
Phát hiện activity xung đột
→ sinh lựa chọn room/time
→ kiểm tra tính hợp lệ và đánh giá
→ giữ move cải thiện hard trước, soft sau
→ lặp đến feasible hoặc chạm giới hạn
```

> [Figure placeholder — Figure 4: Repair Engine flow]

## 8. Soft Local Search (SLS)

SLS là hill-climbing hậu xử lý:

```text
GA + Repair → feasible schedule → SLS → soft quality tốt hơn
```

Nó chỉ chạy khi nghiệm tốt nhất sau GA có `hard_violations = 0`. Ba neighborhood là: A đổi room, B đổi timeslot, C đổi cả hai. Candidate chỉ được nhận khi vẫn có hard bằng 0 và soft penalty giảm nghiêm ngặt. Cấu hình cuối giới hạn 2 passes và 5.000 candidate checks; invariant cuối hoàn nguyên lịch nếu feasibility bị mất hoặc soft xấu hơn. Cách tổ chức này ngăn local search đánh đổi tính hợp lệ để lấy điểm soft.

## 9. Hard Constraints

**Table 2 — Hard constraints**

| Constraint/kiểm tra | Ý nghĩa vi phạm |
|---|---|
| Lecturer overlap | Một giảng viên có các activity chiếm cùng tiết. |
| Room overlap | Một phòng phục vụ nhiều activity cùng tiết. |
| Student-group overlap | Một nhóm sinh viên học nhiều activity cùng tiết. |
| Capacity violation | Sĩ số section lớn hơn sức chứa phòng. |
| Lecturer unavailable | Có tiết bị chiếm ngoài availability của giảng viên. |
| Room-type mismatch | Activity yêu cầu LAB nhưng được gán phòng không phù hợp, hoặc loại không khớp. |
| Same section, same day | Hai meeting của cùng section được xếp cùng ngày. |
| Missing activity | Activity bắt buộc không xuất hiện trong chromosome. |
| Duplicate activity | Một activity xuất hiện nhiều lần. |
| Gene-count mismatch | Số gene khác số activity cần xếp. |
| Invalid activity/section ID | Gene tham chiếu activity không tồn tại. |
| Invalid room ID | Gene tham chiếu phòng không tồn tại. |
| Invalid timeslot/duration block | Start timeslot không tồn tại, thiếu tiết liên tiếp, hoặc khối học vượt/đổi session. |
| Invalid lecturer reference | Section tham chiếu lecturer không tồn tại. |
| Invalid student-group reference | Section tham chiếu group không tồn tại. |

Tất cả hard constraints là bắt buộc; khai báo workbook không thể tắt chúng. Tổng hard violations thống trị mọi soft objective trong xếp hạng.

## 10. Soft Objectives S1–S7

Gọi (S_i\in[0,1]) là penalty chuẩn hóa và (w_i) là trọng số. Mọi objective đều có hướng **0 tốt hơn, 1 là trường hợp xấu nhất sau chuẩn hóa**; mẫu số bằng 0 cho penalty 0. Cấu hình workbook cuối dùng trọng số lần lượt 10, 5, 4, 2, 8, 3, 4.

**Table 3 — S1–S7 soft objectives**

| ID | Objective, trọng số | Công thức chuẩn hóa và diễn giải |
|---|---|---|
| S1 | Compact Student Schedule, 10 | `raw = Σ_group max(0, active_days − 1)`; `den = scheduled_groups × max(0, available_days − 1)`; `S1=raw/den`. Khuyến khích mỗi group đến trường ít ngày hơn. |
| S2 | Evening Periods, 5 | `raw =` tổng số occupied periods thuộc session `evening`; `den =` tổng occupied periods đã xếp. Hạn chế học cuối ngày. |
| S3 | Preferred Shift Mismatch, 4 | `raw =` số assignment có preferred shift nhưng session không khớp; `den =` số assignment có khai báo preference. |
| S4 | Room Seat Waste, 2 | Với assignment đủ capacity: waste ratio `(capacity − students)/capacity`; `S4` là trung bình các ratio hợp lệ. Trường hợp thiếu capacity thuộc hard, không cộng S4. |
| S5 | Consecutive Cross-campus Travel, 8 | Theo từng lecturer/ngày, `den =` số cặp activity kề nhau có campus xác định; `raw =` số cặp diễn ra liên tiếp về tiết (`next.start = previous.end+1`) nhưng khác campus. |
| S6 | Preferred Campus Mismatch, 3 | `raw =` assignment khác preferred campus của section; `den =` số assignment khai báo preferred campus. |
| S7 | Student Home Campus Mismatch, 4 | `raw =` assignment khác home campus của student group; `den =` số assignment có home campus. Mỗi section gắn một group. |

Điểm tổng:

```text
SoftScore = Σ wi Si
```

Các objective được xây dựng dựa trên các tiêu chí phổ biến của university timetabling và yêu cầu nghiệp vụ của project, sau đó được chuẩn hóa về thang `[0,1]`. Các công thức cụ thể không được tuyên bố là tiêu chuẩn quốc tế.

## 11. Input data và validation

Luồng dữ liệu là `Excel → loader → strict validation → domain`. Workbook canonical gồm `CAMPUSES`, `TIMESLOTS`, `ROOMS`, `LECTURER_AVAILABILITY`, `LECTURERS`, `STUDENT_GROUPS`, `COURSES`, `COURSE_SECTIONS` và `CONSTRAINTS`. Campus master là authoritative; các campus reference phải trỏ tới master. Loader giữ nguyên `course_code` và `class_code` chính thức bên cạnh ID nội bộ.

Validation bao phủ duplicate ID, foreign key, enum shift/room type/difficulty, trường số nguyên dương, tính nhất quán thời gian và day-period, campus reference, ma trận availability đầy đủ, room suitability/capacity, LAB supply, total load, `meetings_per_week`, đủ số ngày khác nhau và đủ khối tiết liên tiếp cùng session. Các lỗi cấu trúc bị chặn trước khi GA khởi tạo.

## 12. EASY và MEDIUM datasets

EASY là baseline áp lực thấp và được khuyến nghị cho live demo. MEDIUM giữ xấp xỉ cùng kích thước nhưng tăng LAB demand và hạn chế availability, qua đó giảm scheduling freedom.

**Table 4 — EASY vs MEDIUM dataset comparison**

| Chỉ số | EASY | MEDIUM |
|---|---:|---:|
| Sections / Activities | 62 / 62 | 62 / 62 |
| Courses | 20 | 20 |
| Lecturers | 15 | 15 |
| Student groups | 12 | 12 |
| Rooms / Timeslots / teaching days | 11 / 96 / 6 | 11 / 96 / 6 |
| Activity-period demand | 158 | 158 |
| Room utilization | 14,96% | 14,96% |
| LAB utilization | 7,29% | 22,22% |
| Restricted lecturers | 5/15 | 10/15 |
| Max lecturer load | 26,04% | 34,72% |
| Candidate domain: median / minimum | 468 / 120 | 274 / 62 |
| Activities có domain < 100 | 0 | 5 |

MEDIUM không chủ yếu tăng problem size; nó làm giảm số lựa chọn hợp lệ do áp lực tài nguyên và availability cao hơn. Dữ liệu không cho phép kết luận MEDIUM chậm hơn về thời điểm tìm feasibility, vì các phương pháp Repair đều ghi nhận Gen 1/Eval 63 ở cả hai instance.

## 13. Candidate Domain

Candidate domain của một activity là tập các cặp `(room, start_timeslot)` **hợp lệ riêng lẻ** theo room capacity/type, khối `duration_periods` liên tiếp trong cùng session và lecturer availability. Chỉ số này chưa xét collision toàn cục với activity khác.

Domain nhỏ làm giảm lựa chọn khi tìm và sửa lịch, nên là dấu hiệu của structural constraint pressure cao hơn. Median giảm từ 468 ở EASY xuống 274 ở MEDIUM; minimum giảm từ 120 xuống 62.

## 14. Thiết lập thực nghiệm

Benchmark cuối dùng paired seeds: cùng seed được dùng cho mỗi method trên cùng dataset để tăng tính so sánh, dù các algorithm path có thể tiêu thụ random state khác nhau.

**Table 5 — Benchmark configuration**

| Thành phần | Giá trị |
|---|---|
| Datasets | EASY, MEDIUM |
| Methods | GA; GA + Repair; GA + Repair + SLS |
| Seeds | 0–9 |
| Tổng số run | `2 × 3 × 10 = 60` |
| Population size | 60 |
| Generation limit | 100 |
| GA evaluation budget | 1.000 mỗi run |
| Crossover / mutation rate | 0,8 / 0,2 |
| Hard / soft compatibility weights | 1.000 / 1 |
| SLS limits | 2 passes, 5.000 candidate checks |

Metrics gồm feasible rate, hard violations, soft score chỉ trên feasible solutions, runtime, first feasible generation/evaluation và evaluation accounting. GA evaluation budget không bao gồm candidate checks nội bộ của Repair/SLS.

> [Figure placeholder — Figure 5: Benchmark design]

## 15. Kết quả benchmark

**Table 6 — Final EASY benchmark results**

| Method | Feasible | Hard mean | Soft mean / median (feasible only) | First feasible | Runtime mean |
|---|---:|---:|---:|---:|---:|
| GA | 0/10 | 5,1 | N/A | N/A | 6,532 s |
| GA + Repair | 10/10 | 0 | 9,6450 / 9,6597 | Gen 1 / Eval 63 | 14,179 s |
| GA + Repair + SLS | 10/10 | 0 | 6,3505 / 6,3194 | Gen 1 / Eval 63 | 25,363 s |

**Table 7 — Final MEDIUM benchmark results**

| Method | Feasible | Hard mean | Soft mean / median (feasible only) | First feasible | Runtime mean |
|---|---:|---:|---:|---:|---:|
| GA | 0/10 | 5,7 | N/A | N/A | 7,145 s |
| GA + Repair | 10/10 | 0 | 9,6419 / 9,6210 | Gen 1 / Eval 63 | 15,936 s |
| GA + Repair + SLS | 10/10 | 0 | 5,7109 / 5,5768 | Gen 1 / Eval 63 | 26,935 s |

Các giá trị runtime là trung bình của 10 seed. Soft statistics không được tính cho GA vì cả 20 GA run đều infeasible; so sánh soft giữa lịch infeasible và feasible sẽ không có ý nghĩa theo objective hierarchy.

## 16. Evaluation-cost accounting

**Table 8 — Evaluation-cost comparison (mean candidate checks/run)**

| Dataset | Method | GA evaluations | Repair checks | SLS checks | Total |
|---|---|---:|---:|---:|---:|
| EASY | GA | 1.000 | 0 | 0 | 1.000 |
| EASY | GA + Repair | 1.000 | 30.999,7 | 0 | 31.999,7 |
| EASY | GA + Repair + SLS | 1.000 | 30.999,7 | 5.000 | 36.999,7 |
| MEDIUM | GA | 1.000 | 0 | 0 | 1.000 |
| MEDIUM | GA + Repair | 1.000 | 35.353,6 | 0 | 36.353,6 |
| MEDIUM | GA + Repair + SLS | 1.000 | 35.353,6 | 5.000 | 41.353,6 |

GA evaluations là objective evaluations theo fixed budget. Repair counts là candidate assignments được kiểm tra; SLS counts là candidate moves được kiểm tra theo instrumentation. Tổng cộng ba loại phép kiểm tra giúp diễn giải chi phí tốt hơn việc chỉ nêu GA budget, nhưng chúng không nhất thiết có chi phí CPU giống nhau cho mỗi đơn vị.

## 17. Phân tích kết quả benchmark

### Q1 — Repair có cải thiện feasibility không?

Có tác động quan sát được rất mạnh: GA đạt 0/10 feasible trên cả EASY và MEDIUM, trong khi GA + Repair đạt 10/10 trên cả hai với cùng GA budget. Kết luận hợp lệ là Repair cải thiện mạnh feasibility dưới cấu hình đã thử; đây không phải bảo đảm toán học cho mọi dataset.

### Q2 — SLS có cải thiện soft quality không?

Có, khi chỉ so sánh feasible runs và dùng median nhất quán. EASY giảm từ 9,6597 xuống 6,3194; MEDIUM giảm từ 9,6210 xuống 5,5768. Vì soft score càng thấp càng tốt và SLS bảo toàn hard feasibility, kết quả cho thấy chất lượng soft được cải thiện trong benchmark cuối.

### Q3 — MEDIUM khác EASY thế nào?

MEDIUM có candidate domain nhỏ hơn, LAB utilization cao hơn, nhiều restricted lecturers hơn, max lecturer load lớn hơn và GA hard mean cao hơn nhẹ. Tuy vậy, GA + Repair và GA + Repair + SLS vẫn đạt 10/10 feasible; first feasible vẫn là Gen 1/Eval 63. MEDIUM khó hơn về cấu trúc, còn Repair vẫn robust ở mức khó này.

### Q4 — Trade-off về computational cost là gì?

GA nhanh nhất nhưng không đạt feasibility trong tested budget. Repair tăng runtime và số candidate checks, đổi lại khôi phục feasibility. SLS thêm 5.000 checks và runtime, đổi lại giảm soft penalty đáng kể. Vì vậy method cuối ưu tiên tính hợp lệ trước, rồi chấp nhận thêm chi phí để cải thiện chất lượng.

## 18. Hệ thống demo Streamlit

Ứng dụng có năm trang: **Scheduler**, **Timetable**, **Ask Schedule**, **Benchmark**, **About / Method**. Live-demo flow chính:

```text
Choose dataset → Validate → Generate Timetable → Final Metrics
→ Timetable → Ask Schedule → Export
```

Scheduler mặc định EASY, cho nhập seed và chạy cấu hình frozen GA + Repair + SLS. Kết quả được independent evaluation, hiển thị hard details, S1–S7, runtime và số activity đã xếp. Timetable hỗ trợ view/filter theo student group, lecturer hoặc room. Các download hỗ trợ Excel, JSON và CSV; export lịch infeasible bị chặn. Benchmark page đọc artifact 60-run và ba chart hiện có, không chạy lại/tune benchmark trong UI.

## 19. Ask Schedule assistant

Ask Schedule là **Timetable Q&A Assistant** deterministic. Luồng thực tế:

```text
User Question → RuleBasedParser → Intent + Entity Resolution
→ Active Generated Timetable → ScheduleQueryService → QueryResult
→ ResponseFormatter hoặc UI table projection
```

`ResponseFormatter` là formatter tái sử dụng trong package; trang Streamlit hiện dựng bảng field ngắn bằng `ask_result_table`. Nguồn sự thật duy nhất trong live session là timetable vừa được tạo; UI không fallback sang file cũ trên disk.

Intent hiện được hỗ trợ gồm: lịch theo student group, lecturer, room, course, class code; filter theo ngày/ca; tìm phòng trống; thời gian rảnh của lecturer; và schedule summary. Entity resolver ưu tiên exact normalized match, cho phép partial match và yêu cầu người dùng chọn khi mơ hồ. “Phòng trống” nghĩa là phòng rảnh trong **toàn bộ requested window**. Thời gian rảnh giảng viên là availability trừ các tiết đã được xếp.

Assistant không dùng LLM, RAG, vector database, external API, Internet hay kiến thức lịch ngoài active generated timetable. Do đó nó không phải chatbot ngôn ngữ tự nhiên tổng quát.

> [Figure placeholder — Figure 6: Schedule Assistant architecture]

## 20. Docker và deployment

Demo chạy bằng Streamlit qua `streamlit run ui_app.py`. `Dockerfile` và `docker-compose.yml` cung cấp container local, bind cổng `8501`, truy cập tại `http://localhost:8501`. Repository không cung cấp bằng chứng về cloud deployment hoặc production multi-user service.

## 21. Testing và reliability

Tại baseline được báo cáo, toàn bộ suite chạy bằng `.venv/bin/pytest -q` và **408/408 tests passed, 0 failed**. `git diff --check` hoàn tất không báo lỗi sau khi khôi phục các generated artifacts do UI tests tạo lại. Lần chạy bằng Python hệ thống không có dependency Streamlit đã dừng ở collection; chạy bằng project virtual environment xác nhận suite đầy đủ pass.

Test suite bao phủ domain representation, hard/soft constraints, Repair, SLS, Excel loading/validation, multi-meeting, benchmark/method registry/metrics, exporter, Streamlit UI và Schedule Assistant. Validation trước GA, independent final evaluation, chặn export infeasible và các invariant của SLS tạo thành nhiều lớp kiểm soát nhất quán.

## 22. Hạn chế

- Không có chứng minh global optimality; GA + Repair + SLS đều là heuristic.
- Benchmark cuối chỉ có EASY và MEDIUM; MEDIUM vẫn tương đối manageable đối với Repair.
- Multi-meeting spacing hiện buộc khác ngày, chưa mô hình hóa khoảng cách sư phạm tinh vi hơn.
- Trọng số soft objective là lựa chọn stakeholder/project; thay đổi trọng số có thể đổi best solution found.
- Chưa có CP-SAT/exact baseline để đánh giá optimality gap.
- Schedule Assistant dùng rule-based parsing, không có general natural-language understanding.
- Demo Streamlit chạy local và lưu trạng thái theo session, chưa phải hệ thống production đa người dùng.
- Candidate-domain analysis là legality riêng lẻ, không đo đầy đủ tương tác collision toàn cục.
- Kết quả 10 seed là bằng chứng trong cấu hình cụ thể, không suy rộng thành bảo đảm cho dataset lớn hơn.

Các điểm trên là ranh giới phạm vi hiện tại, không làm thay đổi tính hợp lệ của kết quả benchmark được báo cáo.

## 23. Hướng phát triển

Các hướng phù hợp gồm bổ sung Hard/Stress datasets, baseline CP-SAT, quy tắc spacing nâng cao, sensitivity study cho tham số/trọng số, dữ liệu thực lớn hơn, parser LLM tùy chọn có kiểm soát nguồn sự thật, và triển khai production có quản lý người dùng/tác vụ. Các hạng mục này chưa được triển khai trong baseline hiện tại.

## 24. Kết luận

Project đã tích hợp GA, heuristic Repair và SLS thành hệ thống xếp thời khóa biểu end-to-end. Trong benchmark cuối 60 run, vanilla GA không đạt feasibility trong budget đã thử, còn hai method có Repair đạt 100% feasibility trên EASY và MEDIUM. SLS tiếp tục giảm median soft score từ 9,6597 xuống 6,3194 trên EASY và từ 9,6210 xuống 5,5768 trên MEDIUM, với chi phí runtime và candidate checks cao hơn.

Ứng dụng Streamlit cuối hỗ trợ tạo lịch, kiểm tra constraint, xem/lọc lịch, export, trực quan artifact benchmark và timetable Q&A deterministic. Bằng chứng cho thấy final hybrid method tạo feasible timetable ổn định trong phạm vi hai instance đã kiểm thử; không hàm ý nghiệm tối ưu toàn cục.

## Phụ lục A — Reproducibility

| Metadata | Giá trị |
|---|---|
| Branch khi lập báo cáo | `phase5-final-delivery` |
| Stable tag | `v1.0-final-demo` |
| Baseline commit khi lập báo cáo | `afc46a6500eb03180ca1868c04e52cbc09c11d91` |
| Current commit timestamp | `2026-08-27T11:34:08+07:00` |
| Benchmark source commit | `71bd7ab9a8ff1c12d44dfde8add893106445abf1` |
| Benchmark timestamp | `2026-08-26T17:11:02.759958+00:00` |
| Benchmark Python | `3.11.9` |
| Test environment Python | `3.14.6` trong project `.venv` |
| EASY dataset | `data/instances/instance_easy.xlsx` |
| EASY SHA-256 | `dfbff415600ff0a1a2cba8b55c90ab52dbcd7b3db3b090f16f1b49cee2bc6e6d` |
| MEDIUM dataset | `data/instances/instance_medium.xlsx` |
| MEDIUM SHA-256 | `409c375ed82490cedaeac258b90c6bae7d9e26ad9c50fd01aafc763b324b9d1b` |
| Benchmark artifact | `outputs/final_benchmark/benchmark_results.json` |
| Runs / seeds | 60 runs; seeds 0–9 |
| Production/demo config | population 60; generations 100; GA budget 1.000; crossover 0,8; mutation 0,2; SLS 2/5.000 |

Các commit khác nhau được ghi riêng vì artifact benchmark được tạo tại commit nguồn của thí nghiệm, sau đó baseline demo được hoàn thiện và gắn tag. Để tái lập kiểm tra tài liệu: checkout `v1.0-final-demo`, kiểm tra SHA-256 của hai workbook, dùng dependency project, chạy `pytest -q`, và dùng artifact benchmark đã đóng băng thay vì vô tình tạo một thí nghiệm mới.

## Phụ lục B — Nguồn bằng chứng repository

- Implementation: `domain/`, `constraints/`, `dataset/`, `ga/`, `evaluation/`, `schedule_assistant/`, `ui_app.py`, `main.py`, `main_benchmark.py`.
- Dataset analysis: `outputs/dataset_analysis/` và phần `dataset_metrics` trong `outputs/final_benchmark/benchmark_results.json`.
- Benchmark: `outputs/final_benchmark/benchmark_results.json`, `benchmark_summary.csv`, `benchmark_report.md` và các chart PNG.
- Deployment/demo: `README.md`, `Dockerfile`, `docker-compose.yml` và `ui_app.py`.
- Reliability: `tests/` và kết quả chạy suite tại baseline.
