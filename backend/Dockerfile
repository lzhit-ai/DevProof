FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple \
    PIP_TRUSTED_HOST=pypi.tuna.tsinghua.edu.cn

WORKDIR /app
RUN sed -i 's|deb.debian.org|mirrors.tuna.tsinghua.edu.cn|g; s|security.debian.org|mirrors.tuna.tsinghua.edu.cn|g' /etc/apt/sources.list.d/debian.sources 2>/dev/null || true; \
    sed -i 's|deb.debian.org|mirrors.tuna.tsinghua.edu.cn|g; s|security.debian.org|mirrors.tuna.tsinghua.edu.cn|g' /etc/apt/sources.list 2>/dev/null || true; \
    apt-get update && apt-get install --no-install-recommends -y \
    git \
    && rm -rf /var/lib/apt/lists/*
COPY pyproject.toml ./
COPY alembic.ini ./
COPY app ./app
COPY migrations ./migrations
RUN pip install --upgrade pip && pip install . \
    && python -c "from tree_sitter_language_pack import download; download(['java', 'python', 'javascript', 'typescript', 'tsx'])"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
