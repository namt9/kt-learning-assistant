"""Biểu đồ cho chương thực nghiệm (docs/bao_cao/thuc_nghiem.md). Cần matplotlib.

    python docs/img/eval/make_charts.py docs/img/eval

Số liệu chép từ các báo cáo sinh tự động: docs/eval_report.md, docs/rubric_report.md,
docs/eval_report_so_bo_3bai.md, docs/mining_report.md. Chạy lại đánh giá thì sửa số ở đây.
"""

import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402  (phải chọn backend Agg trước khi import pyplot)
import numpy as np  # noqa: E402

S = ["#2a78d6", "#eb6834", "#1baf7a"]  # bảng màu phân loại, thứ tự cố định
SURF, INK, INK2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df"
CONFIGS = ["v0: công cụ thô", "Rule-based", "LLM thuần", "Hybrid"]


def two(v):
    return f"{v:.2f}"


def one(v):
    return f"{v:.1f}"


def grouped(ax, cats, series, names, ymax, fmt):
    """Cột nhóm: mỗi chuỗi một màu, in giá trị trên đầu cột (màu xanh ngọc tương phản thấp)."""
    n = len(series)
    w = 0.8 / n
    x = np.arange(len(cats))
    for k, (vals, name) in enumerate(zip(series, names, strict=True)):
        xs = x - 0.4 + w * (k + 0.5)
        bars = ax.bar(xs, vals, w - 0.03, color=S[k], label=name, edgecolor=SURF, linewidth=1.5)
        for b, v in zip(bars, vals, strict=True):
            cx = b.get_x() + b.get_width() / 2
            ax.text(
                cx, v + ymax * 0.012, fmt(v), ha="center", va="bottom", fontsize=8.5, color=INK2
            )
    ax.set_xticks(x, cats)
    ax.set_ylim(0, ymax)
    ax.yaxis.grid(True, color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.tick_params(axis="y", length=0)
    if n > 1:  # một chuỗi thì tiêu đề đã nói tên, không cần chú giải
        ax.legend(frameon=False, ncol=n, loc="upper left", bbox_to_anchor=(0, 1.13))


def chart(out, name, size, title, cats, series, names, ymax, yticks, fmt, pad=26):
    fig, ax = plt.subplots(figsize=size)
    grouped(ax, cats, series, names, ymax, fmt)
    ax.set_yticks(yticks)
    ax.set_title(title, loc="left", fontsize=11.5 if pad > 10 else 11, pad=pad)
    fig.tight_layout()
    fig.savefig(f"{out}/{name}", dpi=160)
    plt.close(fig)


def main(out):
    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "font.size": 10.5,
            "text.color": INK,
            "axes.labelcolor": INK2,
            "xtick.color": INK2,
            "ytick.color": INK2,
            "axes.edgecolor": GRID,
            "figure.facecolor": SURF,
            "axes.facecolor": SURF,
        }
    )
    unit = [0, 0.25, 0.5, 0.75, 1]
    five = [0, 1, 2, 3, 4, 5]

    # Xác định lỗi, Sonnet 4.6, 30 bài
    chart(
        out,
        "detection_sonnet.png",
        (7.2, 3.6),
        "Xác định lỗi trên 30 bài (LLM: Claude Sonnet 4.6)",
        CONFIGS,
        [[0.60, 0.97, 0.96, 0.92], [0.81, 0.79, 0.96, 0.98], [0.69, 0.87, 0.96, 0.95]],
        ["Precision", "Recall", "F1"],
        1.12,
        unit,
        two,
    )
    # F1 theo LLM: Sonnet (30 bài, 10 bài tập) và Ollama (30 bài, 3 bài tập, Hybrid bản 1)
    chart(
        out,
        "f1_by_llm.png",
        (7.2, 3.4),
        "F1 xác định lỗi theo LLM",
        CONFIGS,
        [[0.69, 0.87, 0.96, 0.95], [0.69, 0.88, 0.41, 0.88]],
        ["Claude Sonnet 4.6", "Ollama qwen2.5 7B (bản sơ bộ)"],
        1.12,
        unit,
        two,
    )
    # Rubric trung bình theo giám khảo
    chart(
        out,
        "rubric_avg.png",
        (6.4, 3.4),
        "Điểm rubric trung bình (thang 1–5, chấm mù)",
        ["Rule-based", "LLM thuần", "Hybrid"],
        [[3.09, 4.79, 4.77], [2.99, 4.86, 4.85]],
        ["Giám khảo Sonnet 4.6", "Giám khảo GPT-5.5"],
        5.6,
        five,
        two,
    )
    # Rubric theo tiêu chí, giám khảo GPT-5.5 (khác model với bên sinh lời giải thích)
    chart(
        out,
        "rubric_criteria_gpt.png",
        (7.2, 3.4),
        "Rubric theo tiêu chí (giám khảo GPT-5.5)",
        ["Đúng", "Cụ thể", "Dễ hiểu", "Hướng dẫn", "Không bịa"],
        [
            [3.10, 1.97, 3.77, 2.67, 3.47],
            [4.87, 4.97, 4.93, 4.93, 4.60],
            [4.90, 5.00, 4.90, 4.90, 4.53],
        ],
        ["Rule-based", "LLM thuần", "Hybrid"],
        5.6,
        five,
        one,
    )
    # Luật khai phá, leave-one-problem-out
    chart(
        out,
        "mining_lopo.png",
        (6.4, 3.2),
        "F1 trung bình trên bài chưa thấy khi khai phá luật (leave-one-problem-out)",
        ["Tầng luật v0", "+ luật bổ sung", "+ luật khử nhiễu", "+ cả hai"],
        [[0.70, 0.67, 0.84, 0.80]],
        ["F1"],
        1.0,
        [0, 0.25, 0.5, 0.75],
        two,
        pad=10,
    )


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "docs/img/eval")
