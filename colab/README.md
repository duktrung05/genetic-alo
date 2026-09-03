# Genetic ALO trên Google Colab

Chỉ cần một file: `Genetic_ALO_Colab.ipynb`.

Notebook gồm các phần:

- Clone nhánh `main` từ GitHub và cài `requirements.txt`.
- Hiển thị, kiểm tra dataset EASY/MEDIUM và chạy pytest tùy chọn.
- Chạy production GA + Repair + SLS và xuất lịch.
- Chạy sensitivity và benchmark tùy chọn.
- Mở đúng giao diện Streamlit qua link tạm thời.

Repository hiện có khoảng **128 file source, dataset và output**.
Sau khi clone, dataset Excel thật nằm trong `data/instances`.

- Mở notebook từ GitHub bằng Google Colab.
- Chọn `Runtime → Run all`.
- Dùng runtime CPU; không cần GPU.
- Pytest, sensitivity và benchmark mặc định tắt để chạy demo nhanh.
- Quick Tunnel chỉ dùng cho buổi demo; giữ tab Colab hoạt động.
