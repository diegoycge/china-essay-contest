FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    MEDIA_ROOT=/data/media

RUN apt-get update \
    && apt-get install -y --no-install-recommends gettext \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 1000 portal \
    && mkdir -p /data/media \
    && chown -R portal:portal /data

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY --chown=portal:portal . .
# Build-time only: collectstatic needs settings to import, nothing more.
RUN SECRET_KEY=build-only python manage.py collectstatic --noinput \
    && cd portal && SECRET_KEY=build-only python ../manage.py compilemessages \
    && chmod +x /app/entrypoint.sh

USER portal
EXPOSE 8000
ENTRYPOINT ["/app/entrypoint.sh"]
# No access log on purpose: invitation and password-reset links carry their
# one-time token in the URL path, and it should not be copied into log files.
# The portal keeps its own record of who did what under Logs.
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3", "--timeout", "120"]
