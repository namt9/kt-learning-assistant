# Thống kê lỗi phổ biến: dữ liệu tự sinh và đối chiếu tài liệu

Tài liệu cho việc Tuần 1 #13 (thống kê sơ bộ các loại lỗi phổ biến). Kế hoạch ban đầu là thống kê trên dataset ngoài (ITSP, DeepFix, CodeNet), nhưng việc tải dataset (#12) đã cắt vì thuyết trình dời lên 2/12. Tài liệu này gồm hai phần: phân bố lỗi trong dữ liệu tự sinh của nhóm, kèm hạn chế của nó, và các lỗi phổ biến theo những nghiên cứu đã công bố, đối chiếu với danh mục 23 Bug Pattern của hệ thống.

## 1. Dữ liệu tự sinh của nhóm

270 bài nộp có nhãn, sinh bằng cách cài lỗi có chủ đích vào lời giải mẫu của 10 bài tập (`backend/app/mining/mutate.py`, dữ liệu ở `data/mined/mutants.jsonl`). 191 bài mang 2 lỗi, tổng cộng 461 nhãn lỗi.

| Lỗi | Số nhãn | Toán tử cài lỗi |
|---|---|---|
| SCANF_MISSING_AMP | 104 | bỏ `&` trong scanf |
| INFINITE_LOOP | 90 | bỏ bước tăng của vòng lặp |
| OFF_BY_ONE | 83 | `<` thành `<=`, `>=` thành `>`, bắt đầu từ n |
| UNINIT_VAR | 27 | bỏ giá trị khởi tạo |
| FORMAT_MISMATCH | 26 | sai đặc tả định dạng printf/scanf |
| STRAY_SEMICOLON | 22 | thêm `;` sau if/for/while |
| DOUBLE_FREE | 15 | free hai lần |
| DANGLING_PTR | 15 | free sớm rồi dùng tiếp |
| MEM_LEAK | 13 | bỏ free |
| ASSIGN_IN_COND | 13 | `==` thành `=` |
| NULL_DEREF | 12 | bỏ malloc |
| INT_DIVISION | 9 | bỏ ép kiểu số thực |
| INT_OVERFLOW | 8 | thu hẹp kiểu (long long thành int) |
| UNDECLARED_ID | 8 | đổi tên biến ở chỗ dùng |
| MISSING_BRACES | 8 | bỏ ngoặc nhọn của khối nhiều lệnh |
| ARRAY_OOB | 5 | cấp phát thiếu |
| SYNTAX_ERROR | 3 | bỏ `;` |

Phân bố kết quả chấm của 270 bài: RE 135, TLE 59, WA 53, AC 12, CE 11. Độ phủ của từng công cụ trên từng loại lỗi nằm trong `docs/mining_report.md`, mục "Tầng luật v0 so với nhãn đúng".

**Hạn chế: phân bố trên không phản ánh lỗi phổ biến thật của sinh viên.** Số nhãn của một loại lỗi phụ thuộc vào số chỗ trong lời giải mẫu mà toán tử cài được. Ví dụ, bài nào cũng có scanf và vòng lặp nên SCANF_MISSING_AMP, INFINITE_LOOP và OFF_BY_ONE chiếm 60% số nhãn. Ngược lại, lỗi cú pháp chỉ có 3 nhãn, vì chỉ một toán tử (bỏ `;`) sinh ra loại lỗi này. Vì vậy, nhóm chỉ dùng dữ liệu này để đo hệ thống bắt được bao nhiêu lỗi đã biết trước, không dùng để kết luận lỗi nào sinh viên hay mắc nhất.

## 2. Lỗi phổ biến theo các nghiên cứu đã công bố

### Lỗi biên dịch của sinh viên năm nhất viết C

- **TRACER** (Ahmed và cộng sự, ICSE-SEET 2018) dùng dữ liệu thu bằng Prutor trong môn nhập môn lập trình C ở IIT Kanpur, hơn 400 sinh viên năm nhất. Dữ liệu gồm 23.275 cặp chương trình lỗi/đã sửa chỉ khác một dòng và 17.451 cặp khác nhiều dòng. Các loại lỗi biên dịch xuất hiện trong ít nhất 50 bài gồm: expected identifier, undeclared identifier, expected expression, extraneous identifier, incorrect assignment, re-definition, invalid operands, incorrect pointer/struct, sai số đối số khi gọi hàm, expected declaration or statement, gọi một thứ không phải hàm, chữ số không hợp lệ trong hằng, return trong hàm void, và câu lệnh không nằm trong vòng lặp/switch. Bài báo nêu "missing identifier" là nhóm lỗi thường gặp. Ví dụ minh hoạ đầu tiên của bài báo chính là `scanf("%d", a)` thiếu `&`. Khoảng một nửa số sinh viên mắc cùng một loại lỗi khó hiểu thông báo và cần trợ giảng giải thích.
- **DeepFix** (Gupta và cộng sự, AAAI 2017) dùng cùng nguồn dữ liệu IIT Kanpur: 6.971 chương trình C lỗi biên dịch thuộc 93 bài tập. DeepFix sửa trọn được 27% số bài. Bài báo xếp các lỗi này vào nhóm lỗi phổ biến, không phụ thuộc bài tập, do sinh viên chưa quen ngôn ngữ hoặc thiếu cẩn thận.

### Lỗi logic (biên dịch được nhưng chạy sai)

- **ITSP** (Yi và cộng sự, ESEC/FSE 2017) gồm 661 chương trình C sai kết quả của sinh viên môn CS-101 ở IIT Kanpur. Các công cụ sửa lỗi tự động chạy nguyên trạng chỉ sửa được khoảng 30% số bài.
- **Khảo sát 30 năm** (Alzahrani và Vahid, ASEE 2021) tổng hợp 47 công trình từ 1985 đến 2018, thu được 166 lỗi logic thuộc 11 nhóm: vòng lặp (27 lỗi), hàm (24), tính toán (21), điều kiện (18), rẽ nhánh (14), biến (7), mảng (5), và các nhóm khác. 43 lỗi được nhiều công trình cùng nêu; 11 trong số đó được đánh dấu là tốn nhiều thời gian để sửa.
- Khảo sát trên trích nghiên cứu của **Ettles, Luxton-Reilly và Denny** (ACE 2018): 51.000 bài nộp C của 809 sinh viên cho 10 bài tập. Các lỗi tốn thời gian nhất là truy cập phần tử mảng không hợp lệ, lệch một phần tử và sai biên, với thời gian sửa trung vị từ 8 đến 20 phút. Các lỗi khác được khảo sát nêu nhiều lần: biến chưa khởi tạo, chia nguyên khi cần chia thực, ép kiểu, vòng lặp vô hạn, `;` thừa tạo khối lệnh rỗng, nhầm `=` với `==`, và bỏ qua hoặc trả sai giá trị trả về của hàm.
- Cũng theo khảo sát, các lỗi cú pháp hàng đầu theo Denny là: không nhận ra định danh, sai kiểu, thiếu dấu chấm phẩy.

## 3. Đối chiếu với danh mục Bug Pattern của hệ thống

| Lỗi phổ biến theo tài liệu | Bug Pattern | Có trong dữ liệu tự sinh |
|---|---|---|
| Thiếu `;`, expected identifier/expression, thiếu ngoặc | SYNTAX_ERROR | Có (ít) |
| Undeclared identifier | UNDECLARED_ID | Có |
| Sai kiểu, invalid operands, incorrect assignment | TYPE_MISMATCH | Không |
| scanf thiếu `&` | SCANF_MISSING_AMP | Có |
| Biến chưa khởi tạo | UNINIT_VAR | Có |
| Lệch một phần tử, vòng for không bao gồm biên | OFF_BY_ONE | Có |
| Truy cập mảng ngoài phạm vi | ARRAY_OOB | Có (ít) |
| Chia nguyên khi cần chia thực, ép kiểu | INT_DIVISION | Có |
| Vòng lặp vô hạn | INFINITE_LOOP | Có |
| `;` thừa sau if/for/while | STRAY_SEMICOLON | Có |
| Nhầm `=` với `==` | ASSIGN_IN_COND | Có |
| Chia cho 0 | DIV_BY_ZERO | Không |
| Thiếu return trong hàm có giá trị trả về | MISSING_RETURN | Không |
| Sai số đối số khi gọi hàm, gọi thứ không phải hàm | Chưa có mã riêng (gcc báo, xếp vào UNCLASSIFIED) | Không |
| Trả sai giá trị (ví dụ 0 thay vì -1), hiểu sai đề, sai thuật toán | Chưa có mã riêng: phụ thuộc từng bài, chỉ thấy qua WA | Không |

Nhận xét:

- Danh mục 23 Bug Pattern phủ phần lớn các lỗi mà tài liệu nêu là phổ biến hoặc tốn thời gian ở mức nhập môn C. Nhóm lỗi tốn thời gian nhất theo Ettles (mảng, lệch biên) chính là OFF_BY_ONE và ARRAY_OOB. Đây cũng là chỗ công cụ chuẩn yếu nhất trên dữ liệu của nhóm: recall OFF_BY_ONE của tầng luật v0 chỉ 45%.
- Nhóm lỗi danh mục chưa có mã riêng là lỗi logic phụ thuộc đề bài: trả sai giá trị, hiểu sai yêu cầu, sai thuật toán. Luật và công cụ không phát hiện được các lỗi này. Hybrid chỉ bắt được khi LLM đề xuất thêm lỗi lúc bài chưa đạt test, và hiện vẫn phải gắn vào một mã sẵn có.
- Dữ liệu tự sinh thiếu hẳn lỗi sai kiểu, chia cho 0 và thiếu return, và có rất ít lỗi cú pháp. Trong khi đó, tài liệu cho thấy lỗi biên dịch chiếm phần lớn số lần sinh viên bị kẹt ở giai đoạn đầu. Các con số trong `docs/eval_report.md` vì vậy chủ yếu phản ánh lỗi khi chạy và lỗi logic.

## Nguồn

- Alzahrani N., Vahid F. (2021). Common Logic Errors for Programming Learners: A Three-decade Literature Survey. ASEE Annual Conference. https://peer.asee.org/36814
- Ettles A., Luxton-Reilly A., Denny P. (2018). Common logic errors made by novice programmers. ACE 2018, tr. 83–89. https://doi.org/10.1145/3160489.3160493. Số liệu ở trên lấy lại từ khảo sát của Alzahrani và Vahid.
- Ahmed U. Z., Kumar P., Karkare A., Kar P., Gulwani S. (2018). Compilation Error Repair: For the Student Programs, From the Student Programs. ICSE-SEET 2018, tr. 78–87. https://doi.org/10.1145/3183377.3183383
- Gupta R., Pal S., Kanade A., Shevade S. (2017). DeepFix: Fixing Common C Language Errors by Deep Learning. AAAI 2017, tr. 1345–1351. https://ojs.aaai.org/index.php/AAAI/article/view/10742
- Yi J., Ahmed U. Z., Karkare A., Tan S. H., Roychoudhury A. (2017). A Feasibility Study of Using Automated Program Repair for Introductory Programming Assignments. ESEC/FSE 2017, tr. 740–751. Dữ liệu: https://github.com/jyi/ITSP
