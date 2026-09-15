# Single image build. The frontend is compiled, then served by the API process.
# One container, one port, and no reverse proxy to configure.

# Stage 1: build the app and the widget
FROM node:20-alpine AS frontend

WORKDIR /build
COPY package.json package-lock.json ./
RUN npm ci

COPY tsconfig.json vite.config.ts vite.widget.config.ts index.html ./
COPY src ./src
COPY public ./public
COPY fixtures ./fixtures
RUN npm run build

# Stage 2: the runtime image
FROM python:3.11-slim

# Never write bytecode, never buffer stdout, so logs appear immediately.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY backend/requirements.txt ./backend/requirements.txt
# asyncpg is not in requirements.txt because a source install only needs it if
# it chooses PostgreSQL. It is baked in here so that pointing DATABASE_URL at a
# PostgreSQL server is the only thing you have to do to this image.
RUN pip install --no-cache-dir -r backend/requirements.txt asyncpg==0.31.0

COPY backend/app ./backend/app
COPY fixtures ./fixtures
COPY --from=frontend /build/dist ./dist

# The SQLite file lives here. Mount a volume over it to keep the data.
RUN mkdir -p backend/data \
    && addgroup --system app \
    && adduser --system --ingroup app app \
    && chown -R app:app /app
USER app

WORKDIR /app/backend
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
