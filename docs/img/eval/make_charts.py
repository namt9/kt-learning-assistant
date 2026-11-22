"""Biểu đồ cho chương thực nghiệm (docs/bao_cao/thuc_nghiem.md). Cần matplotlib.

    python docs/img/eval/make_charts.py docs/img/eval

Số liệu chép từ các báo cáo sinh tự động: docs/eval_report.md, docs/rubric_report.md,
docs/eval_report_so_bo_3bai.md, docs/mining_report.md. Chạy lại đánh giá thì sửa số ở đây."""
import sys
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

OUT = sys.argv[1]
S = ["#2a78d6", "#eb6834", "#1baf7a"]  # bảng màu phân loại, thứ tự cố định
SURF, INK, INK2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df"
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10.5, "text.color": INK,
                     "axes.labelcolor": INK2, "xtick.color": INK2, "ytick.color": INK2,
                     "axes.edgecolor": GRID, "figure.facecolor": SURF, "axes.facecolor": SURF})

def grouped(ax, cats, series, names, ymax, fmt, colors):
    n = len(series); w = 0.8 / n
    x = np.arange(len(cats))
    for k, (vals, name) in enumerate(zip(series, names)):
        xs = x - 0.4 + w * (k + 0.5)
        bars = ax.bar(xs, vals, w - 0.03, color=colors[k], label=name, edgecolor=SURF, linewidth=1.5)
        for b, v in zip(bars, vals):
            ax.text(b.get_x() + b.get_width() / 2, v + ymax * 0.012, fmt(v), ha="center",
                    va="bottom", fontsize=8.5, color=INK2)
    ax.set_xticks(x, cats)
    ax.set_ylim(0, ymax)
    ax.yaxis.grid(True, color=GRID, linewidth=0.8); ax.set_axisbelow(True)
    for s in ("top", "right", "left"): ax.spines[s].set_visible(False)
    ax.tick_params(axis="y", length=0)
    if n > 1:
        ax.legend(frameon=False, ncol=n, loc="upper left", bbox_to_anchor=(0, 1.13))

def save(fig, name):
    fig.tight_layout(); fig.savefig(f"{OUT}/{name}", dpi=160); plt.close(fig)

cfg = ["v0: công cụ thô", "Rule-based", "LLM thuần", "Hybrid"]
# 1. Xác định lỗi, Sonnet 4.6, 30 bài
fig, ax = plt.subplots(figsize=(7.2, 3.6))
grouped(ax, cfg, [[0.60, 0.97, 0.96, 0.92], [0.81, 0.79, 0.96, 0.98], [0.69, 0.87, 0.96, 0.95]],
        ["Precision", "Recall", "F1"], 1.12, lambda v: f"{v:.2f}", S)
ax.set_yticks([0, .25, .5, .75, 1])
ax.set_title("Xác định lỗi trên 30 bài (LLM: Claude Sonnet 4.6)", loc="left", fontsize=11.5, pad=26)
save(fig, "detection_sonnet.png")

# 2. F1 theo LLM: Sonnet (30 bài, 10 bài tập) và Ollama qwen2.5 7B (30 bài, 3 bài tập, Hybrid bản 1)
fig, ax = plt.subplots(figsize=(7.2, 3.4))
grouped(ax, cfg, [[0.69, 0.87, 0.96, 0.95], [0.69, 0.88, 0.41, 0.88]],
        ["Claude Sonnet 4.6", "Ollama qwen2.5 7B (bản sơ bộ)"], 1.12, lambda v: f"{v:.2f}", S)
ax.set_yticks([0, .25, .5, .75, 1])
ax.set_title("F1 xác định lỗi theo LLM", loc="left", fontsize=11.5, pad=26)
save(fig, "f1_by_llm.png")

# 3. Rubric trung bình theo giám khảo
fig, ax = plt.subplots(figsize=(6.4, 3.4))
grouped(ax, ["Rule-based", "LLM thuần", "Hybrid"], [[3.09, 4.79, 4.77], [2.99, 4.86, 4.85]],
        ["Giám khảo Sonnet 4.6", "Giám khảo GPT-5.5"], 5.6, lambda v: f"{v:.2f}", S)
ax.set_yticks([0, 1, 2, 3, 4, 5])
ax.set_title("Điểm rubric trung bình (thang 1–5, chấm mù)", loc="left", fontsize=11.5, pad=26)
save(fig, "rubric_avg.png")

# 4. Rubric theo tiêu chí, giám khảo GPT-5.5 (khác model với bên sinh)
crit = ["Đúng", "Cụ thể", "Dễ hiểu", "Hướng dẫn", "Không bịa"]
fig, ax = plt.subplots(figsize=(7.2, 3.4))
grouped(ax, crit, [[3.10, 1.97, 3.77, 2.67, 3.47], [4.87, 4.97, 4.93, 4.93, 4.60],
                   [4.90, 5.00, 4.90, 4.90, 4.53]],
        ["Rule-based", "LLM thuần", "Hybrid"], 5.6, lambda v: f"{v:.1f}", S)
ax.set_yticks([0, 1, 2, 3, 4, 5])
ax.set_title("Rubric theo tiêu chí (giám khảo GPT-5.5)", loc="left", fontsize=11.5, pad=26)
save(fig, "rubric_criteria_gpt.png")

# 5. Luật khai phá, leave-one-problem-out, F1 trung bình
fig, ax = plt.subplots(figsize=(6.4, 3.2))
grouped(ax, ["Tầng luật v0", "+ luật bổ sung", "+ luật khử nhiễu", "+ cả hai"],
        [[0.70, 0.67, 0.84, 0.80]], ["F1 trung bình trên bài chưa thấy"], 1.0,
        lambda v: f"{v:.2f}", S)
ax.set_yticks([0, .25, .5, .75])
ax.set_title("F1 trung bình trên bài chưa thấy khi khai phá luật (leave-one-problem-out)", loc="left", fontsize=11, pad=10)
save(fig, "mining_lopo.png")
print("ok")
