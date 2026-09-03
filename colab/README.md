# Bộ Google Colab Genetic ALO

## Thứ tự chạy

1. `00_Thiet_Lap_Du_An_Colab.ipynb` — clone source/data từ GitHub và kiểm tra môi trường.
2. `01_Kiem_Thu_Va_Du_Lieu.ipynb` — hiển thị Excel, kiểm tra dataset và chạy pytest.
3. `02_Chay_GA_Va_Xuat_Lich.ipynb` — chạy GA + Repair + SLS, xuất lịch.
4. `03_Phan_Tich_Do_Nhay.ipynb` — thí nghiệm độ nhạy trọng số.
5. `04_Benchmark_So_Sanh.ipynb` — benchmark nhanh hoặc benchmark 60 lượt.
6. `05_Streamlit_Demo.ipynb` — mở đúng giao diện `ui_app.py` qua link tạm thời.

Repository hiện có khoảng **128 file source, dataset Excel và output**.
Mỗi notebook tự clone nhánh `main` vào `/content/genetic-alo`, sau đó khôi phục
output mới nhất từ Google Drive nếu có. Dataset thật nằm trong `data/instances`.

## Cách nộp/chạy

- Giải nén bộ bàn giao và upload sáu file `.ipynb` lên Google Drive hoặc Colab.
- Mở và chạy theo thứ tự 00 → 05.
- Dùng runtime CPU; không cần GPU.
- Chạy notebook 02 trước notebook 05 để giao diện dùng output mới nhất.
- Quick Tunnel của notebook 05 chỉ dùng cho buổi demo; giữ tab Colab hoạt động.
