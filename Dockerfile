FROM node:22-alpine AS web
WORKDIR /web
COPY apps/web/package*.json apps/web/tsconfig.json apps/web/index.html ./
COPY apps/web/src ./src
RUN npm ci && npm run build

FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PORT=8080 AGENTFLIGHT_DB=/data/agentflight.db AGENTFLIGHT_DEMO_MODE=true
WORKDIR /app
COPY pyproject.toml README.md requirements.lock ./
COPY src ./src
COPY main.py ./
COPY artifacts ./artifacts
COPY --from=web /web/dist ./apps/web/dist
RUN pip install --no-cache-dir -r requirements.lock && mkdir -p /data && chown -R 65532:65532 /app /data
USER 65532
EXPOSE 8080
CMD ["python", "main.py"]
