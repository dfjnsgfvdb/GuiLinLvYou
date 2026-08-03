.PHONY: dev build preview docker-build

dev:
	pnpm dev

build:
	pnpm build

preview:
	pnpm preview

docker-build: build
	docker build -t liguan-tourism-console:latest -f docker/Dockerfile .
