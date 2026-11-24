.PHONY: up down test build

up:
	docker compose up --build -d

down:
	docker compose down

test:
	cd backend && pytest tests -v

build:
	docker compose build
