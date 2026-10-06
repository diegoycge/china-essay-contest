#!/bin/sh
set -e

# Only the web container prepares the database; the scheduler just waits for it.
if [ "$1" = "gunicorn" ]; then
    python manage.py migrate --noinput
    python manage.py load_contest --if-empty
    python manage.py bootstrap_admin
fi

exec "$@"
