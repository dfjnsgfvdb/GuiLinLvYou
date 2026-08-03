#!/usr/bin/env sh
set -eu

if [ ! -f .env ]; then
  cp .env.template .env
fi

docker compose --env-file .env up -d
docker compose --env-file .env ps
printf '\nLiguan middleware is ready. Configure ../.env.local before starting the API.\n'
