.PHONY: middleware-up middleware-down backend frontend build seed

middleware-up:
	docker compose -f docker/docker-compose.yaml up -d

middleware-down:
	docker compose -f docker/docker-compose.yaml down

backend:
	.venv/bin/python serv.py

frontend:
	cd web && pnpm dev

build:
	cd web && pnpm build

seed:
	.venv/bin/python scripts/seed_tourism_data.py
