# Chương: Phương pháp (bản nháp)

> Bản nháp cho việc Tuần 3 #11, viết từ code và tài liệu trong repo để nhóm có khung chung. Mỗi mục ghi người phụ trách theo kế hoạch. Người đó đọc lại, sửa văn phong, bổ sung lý do chọn phương án và tài liệu tham khảo, rồi xoá dòng ghi chú này.

## 1. Tổng quan kiến trúc *(A)*

Hệ thống gồm hai phiên bản trên cùng một mã nguồn:

- **v0** (tag git `v0`): hệ hỗ trợ giải bài tập lập trình dựa trên luật, do nhóm tự xây vì không có sẵn hệ cũ. Sinh viên chọn bài, nộp code C/C++. Hệ biên dịch, chạy test trong sandbox, báo lỗi bằng công cụ phân tích và luật, rồi lưu log.
- **v1**: trợ lý học tập Multi-Agent + Knowledge Graph, giữ nguyên các khối của v0 và bổ sung KG, các agent, suy luận lai và mô hình sinh viên.

```
          Giao diện web: nộp bài · chẩn đoán · lộ trình · chat · hồ sơ · KG viewer
                                          │
                                   Orchestrator ─────────────── Chat Agent
          ┌──────────────┬────────────────┼──────────────────┬───────────────────┐
   Grading Agent   Luật khai phá     Cập nhật KG       Diagnosis Agent    Learning-Path Agent
   (judge v0)      (khử nhiễu)       (log → Neo4j)     (luật + KG + LLM)  (suy luận trên KG)
                                          │
              Neo4j KG + ontology OWL · SQLite (log, chẩn đoán) · lớp trung gian LLM
```

Các khối trao đổi dữ liệu qua schema pydantic chung (`backend/app/schemas.py`). Mọi bước của v1 đều có đường dự phòng: Neo4j không chạy thì dùng tri thức đọc từ YAML; LLM lỗi hoặc không có khoá thì lùi về giải thích bằng luật. Nhờ vậy, sinh viên luôn nhận được ít nhất kết quả chấm.

## 2. Hệ nền v0: chấm bài và phát hiện lỗi bằng luật *(B)*

**Sandbox.** Mỗi lệnh biên dịch hoặc chạy là một lần `docker run --rm` trên image `kt-sandbox` (gcc, g++, cppcheck), tắt mạng, giới hạn bộ nhớ, số tiến trình, 1 CPU, `no-new-privileges`, chạy bằng user không phải root. Thư mục bài nộp được mount vào `/work`. Có thêm chế độ chạy trực tiếp trên máy dev (chỉ giới hạn bằng rlimit, không an toàn) để phát triển và chạy test.

**Chấm bài.** Biên dịch, chạy từng test với giới hạn thời gian và bộ nhớ của bài, so khớp đầu ra, rồi trả về AC/WA/CE/RE/TLE/MLE và điểm theo tỉ lệ test đạt.

**Phát hiện lỗi.** Bốn nguồn, mỗi nguồn được ánh xạ về một danh mục chung 23 Bug Pattern (`knowledge/bug_patterns.yaml`):

- cảnh báo và lỗi của gcc (`-Wall -Wextra`), ánh xạ theo cờ cảnh báo và nội dung thông báo;
- cppcheck;
- AddressSanitizer, UndefinedBehaviorSanitizer, LeakSanitizer khi chạy lại bài với bản biên dịch có sanitizer;
- 10 luật tự viết, dạng heuristic trên mã nguồn đã bỏ comment và chuỗi (6 luật lúc gắn tag v0, thêm 4 luật sau). Các luật nhắm vào lỗi công cụ chuẩn hay bỏ sót: thiếu `&` trong scanf, `=` trong điều kiện, `;` thừa sau if/for/while, lệch biên vòng lặp, chia nguyên gán cho số thực, malloc không free, chia cho hằng 0, điều kiện luôn đúng hoặc luôn sai, vòng lặp vô hạn không có lối thoát, trả địa chỉ biến cục bộ.

Mỗi lỗi có nguồn, dòng và độ tin cậy; luật tự viết có độ tin cậy dưới 1 để phân biệt với kết quả chắc chắn của công cụ. v0 trả kèm một câu gợi ý cố định cho mỗi mã lỗi.

## 3. Knowledge Graph và ontology *(A)*

**Nguồn tri thức.** Các file YAML trong `knowledge/`, được kiểm tra tính nhất quán (không tham chiếu treo, quan hệ tiên quyết không có chu trình, mỗi mẫu lỗi có ít nhất một hành động sư phạm) rồi nạp vào Neo4j. Ontology OWL 2 được sinh từ cùng các file đó, nên hai bên luôn khớp nhau.

| Thành phần | Số lượng |
|---|---|
| Nhóm khái niệm (Nền tảng, Biến, Con trỏ, Cấu trúc dữ liệu, Quản lý bộ nhớ) | 5 |
| Khái niệm C/C++, mỗi khái niệm có level 1–3 | 40 |
| Quan hệ tiên quyết trực tiếp | 67 |
| Mẫu lỗi (Bug Pattern) | 23 |
| Hành động sư phạm (giải thích, ví dụ, trực quan, gỡ lỗi, bài tập, câu hỏi), gắn phong cách học phù hợp | 37 |
| Bài tập | 10 |

**Lược đồ.** `Student -SUBMITTED-> StudentCode -EXHIBITS{line, source, confidence}-> BugPattern -REMEDIATED_BY-> PedagogicalAction -TEACHES-> Concept`, cùng với `BugPattern -RELATED_TO-> Concept`, `Concept -PREREQUISITE_OF-> Concept`, `Problem -PRACTICES-> Concept`. Mỗi lần nộp bài được ghi vào KG ngay sau khi chấm, nên đồ thị phản ánh lỗi thật của từng sinh viên.

**Ontology.** `prerequisiteOf` khai báo bắc cầu; các quan hệ có thuộc tính nghịch đảo. Các lớp định nghĩa để reasoner tự phân loại cá thể: `MemoryBug`, `PointerBug`, `RemediableBug`, `BeginnerConcept`, và các lớp hành động theo phong cách học. Luật khai phá cũng được biểu diễn thành cá thể (`SuppressRule`, `AddRule`). Kiểm tra bằng OWL RL không thấy mâu thuẫn; suy ra 23/23 mẫu lỗi đều có cách khắc phục.

## 4. Dữ liệu và khai phá luật chẩn đoán *(C)*

**Sinh log có nhãn.** Không có log thật, nên nhóm cài lỗi có chủ đích vào lời giải mẫu của 10 bài tập bằng 19 toán tử, rồi chấm các bài lỗi bằng v0. Kết quả là 270 bài có nhãn đúng (`docs/error_stats.md`).

**Giao dịch.** Mỗi bài nộp thành một giao dịch gồm các mục:
- quan sát được: `verdict=…`, `found=…` (lỗi tầng luật báo), `feat=…` (đặc trưng code như có malloc, có phép chia), `concept=…`;
- nhãn: `bug=…` (lỗi thật), `fp=…` (công cụ báo nhưng không phải lỗi thật).

**Khai phá.** Apriori tự cài, min_support 0.03, min_confidence 0.7, tập mục tối đa 4. Vế trái của luật chỉ gồm các mục quan sát được. Thu được hai loại luật:
- **luật bổ sung** `{…} → bug=X`: đoán lỗi công cụ bỏ sót (39 luật);
- **luật khử nhiễu** `{found=A, …} → fp=A`: cảnh báo A chỉ là hệ quả của lỗi gốc khác (29 luật).

**Chọn luật đưa vào hệ.** Đánh giá leave-one-problem-out cho thấy luật khử nhiễu tăng F1 trên bài chưa thấy (0.70 → 0.84), còn luật bổ sung làm giảm (0.67). v1 chỉ áp luật khử nhiễu có confidence ≥ 0.8 (24 luật). Cảnh báo bị khử không bị xoá mà được gắn luật đã khử nó, để giao diện và báo cáo truy vết được.

## 5. Hệ đa agent và suy luận lai *(D)*

**Orchestrator.** Luồng cho một lần nộp cố định: chấm bài → khử nhiễu → lưu log và cập nhật KG → chẩn đoán → lộ trình học. Vì vậy Orchestrator viết bằng Python thuần thay cho LangGraph, dễ đọc và dễ test hơn. Mỗi bước ghi vào trace (agent, trạng thái, thời gian, ghi chú dự phòng); giao diện hiển thị trace này. Bước nào lỗi thì ghi lại và chạy tiếp.

**Diagnosis Agent: ba chế độ.**

| Chế độ | Xác định lỗi | Giải thích |
|---|---|---|
| Rule-based | Luật (v0 + khử nhiễu) | Gợi ý cố định và tri thức KG |
| LLM thuần | LLM, chỉ thấy đề, code, kết quả chấm | LLM |
| Hybrid | Luật, cộng lỗi LLM đề xuất đã qua kiểm tra | LLM, dựa trên dữ kiện truy xuất từ KG |

**Hybrid, cụ thể:**

1. **Lỗi đã kiểm chứng:** lỗi công cụ tìm thấy, sau khi khử nhiễu.
2. **Truy xuất KG:** với mỗi lỗi, lấy tên, gợi ý chuẩn, khái niệm liên quan và hành động sư phạm hợp phong cách học của sinh viên.
3. **Gọi LLM với JSON schema:** trường `items` chỉ được chứa đúng các mã đã kiểm chứng (ràng buộc enum), nên LLM phải giải thích đúng các lỗi đó.
4. **Đề xuất thêm khi bài chưa đạt test:** LLM được ghi lỗi công cụ bỏ sót vào trường `extra`. Một lỗi đề xuất chỉ được giữ khi mã nằm trong danh mục của KG, chỉ một dòng có thật trong bài, và không phải mã mà luật khử nhiễu vừa xác định là hệ quả. Lỗi được giữ mang nguồn `llm`, độ tin cậy 0.5 và ghi chú "công cụ chưa kiểm chứng". Lỗi bị loại được ghi vào danh sách `rejected`.
5. **Ràng buộc sư phạm:** prompt yêu cầu chỉ gợi ý hướng sửa, không viết hộ lời giải. Phong cách học được đưa vào prompt.
6. **Dự phòng:** LLM lỗi thì trả kết quả Rule-based và ghi lý do. Kết quả chẩn đoán được lưu theo bài nộp, chế độ và phong cách học, nên xem lại không tốn phí LLM.

**Lớp trung gian LLM.** Agent chỉ gọi một giao diện `generate(system, user, schema)`. Thứ tự provider cấu hình được: Claude (API của Anthropic hoặc qua Microsoft Foundry), GPT trên Azure, Ollama chạy local. Provider đầu lỗi thì thử provider sau.

**Learning-Path Agent.** Suy luận trên KG (truy vấn Cypher; Neo4j không chạy thì dùng cùng thuật toán trên YAML):
1. khái niệm mục tiêu là các khái niệm gắn với lỗi hiện tại;
2. thêm các khái niệm tiên quyết (mọi cấp) mà sinh viên từng mắc lỗi liên quan;
3. sắp theo độ sâu tiên quyết, khái niệm nền trước;
4. mỗi khái niệm chọn một hành động sư phạm chưa dùng, ưu tiên: sửa lỗi hiện tại, rồi sửa lỗi từng mắc ở khái niệm đó, rồi khớp phong cách học, rồi dễ hơn.

**Chat Agent.** Định tuyến câu hỏi bằng luật từ khoá tiếng Việt (có hoặc không dấu) và nhận diện tên khái niệm hoặc mã lỗi trong câu. Có 6 ý định: giải thích lỗi bài vừa nộp (gọi Diagnosis Agent), nên học gì tiếp (Learning-Path Agent), hỏi khái niệm (truy xuất KG, LLM diễn đạt lại), hỏi năng lực (hồ sơ), gợi ý hướng làm bài, và trợ giúp. Định tuyến không cần LLM, nên chat vẫn chạy khi không có LLM.

## 6. Mô hình sinh viên và giao diện *(E)*

**Mức thành thạo theo khái niệm.** Tính từ log nộp bài:
- bài AC là một lần thành công cho các khái niệm bài tập đó luyện, trừ khái niệm vẫn còn lỗi;
- mỗi lỗi gốc (không tính cảnh báo đã khử nhiễu) là một lần thất bại cho các khái niệm gắn với lỗi;
- lần nộp thứ k tính từ lần gần nhất có trọng số 0.85^k, để hồ sơ phản ánh tiến bộ gần đây;
- mastery = (thành công + 1) / (thành công + thất bại + 2) (làm trơn Laplace; chưa có dữ liệu thì bằng 0.5).

**Phong cách học (Felder–Silverman rút gọn 2 chiều: hình ảnh/lời, thực hành/suy ngẫm).**
- **Bảng hỏi:** 6 câu, 3 câu mỗi chiều, cho điểm q trong [-1, 1].
- **Hành vi:** mỗi sự kiện là một phiếu bầu. Mở một hành động sư phạm bầu cho các phong cách gắn với hành động đó; mở KG viewer bầu cho hình ảnh; hỏi khái niệm bầu cho lời; nộp sai rồi nộp lại ngay trong 2 phút bầu cho thực hành; xem chẩn đoán trước khi nộp lại bầu cho suy ngẫm. Từ đó tính điểm hành vi b, với trọng số min(2, số sự kiện / 10).
- **Điểm kết hợp** là trung bình có trọng số của q và b. Hành vi nặng tới gấp đôi bảng hỏi: vài cú nhấp không đảo được kết quả bảng hỏi, nhưng hơn 10 sự kiện nhất quán thì đảo được.
- **Phong cách hiệu lực** được dùng để chọn hành động sư phạm trong lộ trình, đưa vào prompt chẩn đoán và chat. Tab Hồ sơ năng lực hiển thị điểm từng chiều kèm bằng chứng.

**Giao diện.** Ba trang web tĩnh gọi API FastAPI: v0, v1 (tab Kết quả, Hỏi trợ lý, Hồ sơ năng lực) và KG viewer (Cytoscape.js). Khung màn hình và ảnh chụp ở `docs/ui.md`. Văn bản do LLM viết được hiển thị markdown tối giản, sau khi đã escape HTML.

**Đóng gói.** `docker compose up -d --build` chạy backend, Neo4j và build image sandbox. Backend gọi Docker của máy chủ để chạy từng bài nộp trong sandbox.
