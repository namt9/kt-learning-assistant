# Chất lượng lời giải thích (rubric)

> Sinh tự động bởi `python -m backend.app.evaluation.rubric`. Không sửa tay.

Lời giải thích của LLM thuần và Hybrid sinh bởi claude:claude-sonnet-4-6. Thang 1–5 cho mỗi tiêu chí; giám khảo không biết lời giải thích đến từ cấu hình nào.

- **Đúng**: Giải thích đúng bản chất các lỗi THẬT trong code (so với lỗi đã cài).
- **Cụ thể**: Gắn với chính code này: chỉ ra dòng, biến, giá trị cụ thể; không chung chung.
- **Dễ hiểu**: Sinh viên năm nhất đọc hiểu được; tiếng Việt tự nhiên, không lan man.
- **Hướng dẫn**: Cho biết bước sửa khả thi nhưng KHÔNG đưa sẵn cả đoạn lời giải.
- **Không bịa**: Không nêu lỗi không có trong code, không có thông tin sai.

### LLM-as-judge (claude:claude-sonnet-4-6), 30 bài có đủ 3 cấu hình

| Cấu hình | n | Đúng | Cụ thể | Dễ hiểu | Hướng dẫn | Không bịa | Trung bình |
|---|---|---|---|---|---|---|---|
| Rule-based | 30 | 3.40 | 2.07 | 3.57 | 2.80 | 3.63 | **3.09** |
| LLM thuần | 30 | 4.90 | 4.97 | 4.90 | 4.40 | 4.77 | **4.79** |
| Hybrid | 30 | 4.77 | 4.93 | 4.87 | 4.67 | 4.63 | **4.77** |

| So sánh theo từng bài | Hơn | Hoà | Kém |
|---|---|---|---|
| Hybrid so với Rule-based | 29 | 0 | 1 |
| Hybrid so với LLM thuần | 13 | 10 | 7 |

Trong đó 0 lượt Hybrid phải lùi về giải thích bằng luật (LLM lỗi).

### LLM-as-judge (azure:gpt-5.5), 30 bài có đủ 3 cấu hình

| Cấu hình | n | Đúng | Cụ thể | Dễ hiểu | Hướng dẫn | Không bịa | Trung bình |
|---|---|---|---|---|---|---|---|
| Rule-based | 30 | 3.10 | 1.97 | 3.77 | 2.67 | 3.47 | **2.99** |
| LLM thuần | 30 | 4.87 | 4.97 | 4.93 | 4.93 | 4.60 | **4.86** |
| Hybrid | 30 | 4.90 | 5.00 | 4.90 | 4.90 | 4.53 | **4.85** |

| So sánh theo từng bài | Hơn | Hoà | Kém |
|---|---|---|---|
| Hybrid so với Rule-based | 29 | 0 | 1 |
| Hybrid so với LLM thuần | 5 | 17 | 8 |

Trong đó 0 lượt Hybrid phải lùi về giải thích bằng luật (LLM lỗi).

### Độ khớp giữa hai giám khảo: claude:claude-sonnet-4-6 và azure:gpt-5.5

330 lời giải thích được cả hai giám khảo chấm.

| Tiêu chí | Tương quan Pearson | Lệch tuyệt đối trung bình |
|---|---|---|
| Đúng | 0.64 | 0.68 |
| Cụ thể | 0.92 | 0.26 |
| Dễ hiểu | 0.77 | 0.38 |
| Hướng dẫn | 0.76 | 0.51 |
| Không bịa | 0.47 | 0.85 |

## Lưu ý khi đọc

- Giám khảo LLM có thể ưu ái văn phong LLM (self-preference), nhất là khi cùng model với bên sinh lời giải thích (ở đây: claude:claude-sonnet-4-6). Vì vậy cần đối chiếu giữa các giám khảo và với người chấm (các bảng độ khớp).
- Rule-based dùng câu gợi ý cố định theo mã lỗi, nên điểm "Cụ thể" thấp là đúng thiết kế.
- Lỗi do máy cài vào lời giải mẫu, chưa phải bài làm thật của sinh viên.
