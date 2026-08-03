# Backend image for the Liguan tourism opinion API.
FROM python:3.11-slim-bookworm AS builder
WORKDIR /sanic-web

ENV PIP_INDEX_URL="https://mirrors.aliyun.com/pypi/simple" \
    PIP_EXTRA_INDEX_URL="https://pypi.doubanio.com/simple" \
    UV_INDEX_URL="https://mirrors.aliyun.com/pypi/simple" \
    PATH="/root/.local/bin:${PATH}"

COPY . .

RUN set -eux; \
    apt-get update && \
    apt-get install -y --no-install-recommends gcc python3-dev && \
    pip install --no-cache-dir pipx && \
    pipx install "uv==0.8.0" && \
    uv venv --clear && \
    . .venv/bin/activate && \
    uv sync --no-cache --index-url https://mirrors.aliyun.com/pypi/simple --extra-index-url "" --verbose && \
    apt-get purge -y gcc python3-dev && \
    apt-get autoremove -y && \
    rm -rf /var/lib/apt/lists/*

FROM python:3.11-slim-bookworm
WORKDIR /sanic-web

COPY --from=builder /sanic-web /sanic-web

ENV PATH="/sanic-web/.venv/bin:${PATH}"

EXPOSE 8088

CMD [".venv/bin/python", "serv.py"]
