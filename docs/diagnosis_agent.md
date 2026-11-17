# Diagnosis Agent và lớp trung gian LLM

Code: `backend/app/agents/diagnosis.py`, `backend/app/llm/`.

## Luồng hybrid

```mermaid
flowchart LR
    S[Bài nộp] --> R[Luật v0<br/>gcc, cppcheck, sanitizer, luật tự viết]
    R -->|mã Bug Pattern + dòng| K[KG<br/>khái niệm, hành động sư phạm]
    R --> P[Prompt]
    K --> P
    P --> L[LLM<br/>Claude → Ollama]
    L -->|JSON đúng schema| V[Kiểm tra<br/>loại mã lỗi ngoài danh sách]
    V --> D[Diagnosis]
```

- **Luật là nguồn sự thật**: LLM chỉ được giải thích các mã lỗi luật đã phát hiện. JSON schema giới
  hạn `bug_pattern` trong đúng danh sách đó, và code lọc lại một lần nữa phòng khi model local không
  tuân thủ schema. Mã bị loại được ghi vào `rejected`, dùng để đo tỉ lệ bịa ở tuần 4.
- **KG cung cấp tri thức**: tên khái niệm, gợi ý chuẩn và hành động sư phạm (ưu tiên theo phong cách
  học) được đưa vào prompt, rồi trả về cho sinh viên dưới dạng `actions` để học thêm.
- **Không viết hộ lời giải**: prompt yêu cầu chỉ gợi ý hướng sửa.
- **Không bao giờ lỗi trắng**: LLM lỗi hoặc chưa cấu hình thì tự lùi về giải thích bằng luật; KG tắt thì
  dùng danh mục `bug_patterns.yaml`. Lý do ghi trong `notes`.

## Ba chế độ (cũng là ba cấu hình so sánh ở tuần 4)

| `mode` | Ai tìm lỗi | Ai giải thích | Gọi LLM |
|---|---|---|---|
| `rule` | Luật | Gợi ý cố định + KG | Không |
| `llm_only` | LLM (chỉ thấy đề, code, kết quả chấm) | LLM | Có |
| `hybrid` | Luật | LLM, có KG làm ngữ cảnh | Có |

## Lớp trung gian LLM

Agent chỉ gọi `FallbackLLM.generate(system, user, schema)`. Thứ tự provider đặt bằng
`LLM_PROVIDERS` (mặc định `claude,ollama`):

- `claude`: Anthropic SDK, model `CLAUDE_MODEL` (mặc định `claude-opus-5-5`), structured outputs.
  Bật fallback phía server: nếu model từ chối vì bộ lọc an toàn, API tự chạy lại trên model dự phòng.
- `ollama`: model local `OLLAMA_MODEL` (mặc định `qwen2.5:7b-instruct`), dùng khi demo không có
  mạng: `docker compose --profile ollama up -d` rồi
  `docker compose exec ollama ollama pull qwen2.5:7b-instruct`.

Thêm provider mới: viết class có `name` và `generate_json(system, user, schema) -> dict`, ném
`LLMError` khi thất bại, rồi đăng ký trong `backend/app/llm/__init__.py`.

## API

```
POST /submissions/{id}/diagnosis?mode=hybrid&styles=visual[&refresh=true]
```

Kết quả được lưu trong bảng `diagnoses` (SQLite) theo (bài nộp, chế độ, phong cách học), nên gọi lại
không tốn phí LLM. Kết quả đã phải lùi về luật thì không lưu, để lần sau thử LLM lại.
