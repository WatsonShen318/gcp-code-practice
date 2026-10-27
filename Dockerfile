ARG builderImage=cvsh.jfrog.io/cvsdigital-docker/python:3.14-slim
ARG fromImage=cvsh.jfrog.io/cvsdigital-docker/devsecops/distroless/python-3.14-distroless:latest

FROM ${builderImage} AS builder

WORKDIR /build
COPY requirements.txt ./

RUN --mount=type=secret,id=artifactory_user,env=ARTIFACTORY_USERNAME \
    --mount=type=secret,id=artifactory_token,env=ARTIFACTORY_TOKEN \
    printf 'machine cvsh.jfrog.io\nlogin %s\npassword %s\n' \
        "$ARTIFACTORY_USERNAME" "$ARTIFACTORY_TOKEN" > "$HOME/.netrc" \
    && chmod 600 "$HOME/.netrc" \
    && pip install --no-cache-dir \
        --index-url "https://cvsh.jfrog.io/artifactory/api/pypi/cvsdigital-pypi/simple" \
        --target=/app/packages \
        --python-version 3.14 \
        --implementation cp \
        --only-binary=:all: \
        -r requirements.txt \
    && rm -f "$HOME/.netrc"

COPY app.py .
COPY ping_auth.py .
COPY secret_loader.py .
COPY static ./static
COPY data ./data

# Fail the build if the application or its required assets cannot be loaded.
RUN PYTHONPATH=/app/packages python -c "import app; assert app.DATA_FILE.is_file(); assert (app.BASE_DIR / 'static' / 'index.html').is_file()"

FROM ${fromImage}

COPY --from=builder /app/packages /app/packages
COPY --from=builder /build/app.py /app/app.py
COPY --from=builder /build/ping_auth.py /app/ping_auth.py
COPY --from=builder /build/secret_loader.py /app/secret_loader.py
COPY --from=builder /build/static /app/static
COPY --from=builder /build/data /app/data

WORKDIR /app

ENV PYTHONPATH=/app:/app/packages \
    AUTH_ENABLED=false \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "app:app", "--app-dir", "/app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
