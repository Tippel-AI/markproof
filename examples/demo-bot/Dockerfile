# SPDX-FileCopyrightText: 2026 Lukas Friedrich / Tippel
# SPDX-License-Identifier: Apache-2.0
#
# Optional convenience image for the demo target. Not a production pattern and
# not what CI uses by default — CI runs `uvicorn app:app` straight from the
# checkout. Build context is this directory:
#
#   docker build -t markproof-demo-bot examples/demo-bot
#   docker run --rm -p 8000:8000 -e DEMO_MODE=fail markproof-demo-bot

FROM python:3.13-slim

# Deterministic, quiet, no stray .pyc in the layer.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    DEMO_MODE=pass

WORKDIR /app

# Requirements first so the dependency layer survives edits to app.py.
COPY requirements.txt ./
RUN pip install -r requirements.txt

COPY app.py ./

# Unprivileged: the demo bot needs to write nothing.
RUN useradd --create-home --uid 10001 demo
USER demo

EXPOSE 8000

# urllib rather than curl — nothing extra to install into the image.
HEALTHCHECK --interval=10s --timeout=3s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2).status == 200 else 1)"

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000", "--log-level", "warning"]
