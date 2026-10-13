#!/bin/sh
set -eu

echo "Applying database migrations..."
python -m flask --app app db upgrade

echo "Starting application..."
exec "$@"
