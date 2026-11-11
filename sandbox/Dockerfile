# Image chạy code sinh viên: gcc/g++ (kèm ASan/UBSan) và cppcheck.
# DockerRunner (backend/app/judge/runner.py) luôn chạy container với:
#   --network none, --memory, --pids-limit, --cpus 1, no-new-privileges, user không phải root.
FROM debian:bookworm-slim
RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc g++ libc6-dev cppcheck \
    && rm -rf /var/lib/apt/lists/*
RUN useradd -m -u 1000 runner
USER runner
WORKDIR /work
