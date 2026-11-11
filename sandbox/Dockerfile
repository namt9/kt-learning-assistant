# Image chạy code sinh viên: chỉ có trình biên dịch và công cụ phân tích.
# Khi chạy cần: --network none, --memory, --pids-limit, user không phải root.
FROM gcc:13
RUN apt-get update \
    && apt-get install -y --no-install-recommends cppcheck \
    && rm -rf /var/lib/apt/lists/*
RUN useradd -m runner
USER runner
WORKDIR /work
