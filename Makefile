# Makefile — Comandos de desarrollo para Venbot
# Uso: make <comando>

.PHONY: help up down logs shell db-shell redis-shell migrate reset

help:
	@echo ""
	@echo "Comandos disponibles:"
	@echo "  make up          Levanta todos los servicios"
	@echo "  make down        Detiene todos los servicios"
	@echo "  make logs        Ver logs de la app en tiempo real"
	@echo "  make logs-all    Ver logs de todos los servicios"
	@echo "  make shell       Consola Python dentro del contenedor app"
	@echo "  make db-shell    Consola psql de PostgreSQL"
	@echo "  make redis-shell Consola redis-cli"
	@echo "  make migrate     Crea y aplica una migración Alembic"
	@echo "  make reset       Destruye todo (incluye la BD) y vuelve a crear"
	@echo ""

up:
	docker compose up -d
	@echo ""
	@echo "App: http://localhost:8000"
	@echo "Docs: http://localhost:8000/api/docs"
	@echo "Flower: http://localhost:5555"

down:
	docker compose down

logs:
	docker compose logs -f app

logs-all:
	docker compose logs -f

shell:
	docker compose exec app python

db-shell:
	docker compose exec postgres psql -U venbot -d venbot_db

redis-shell:
	docker compose exec redis redis-cli

migrate:
	@read -p "Nombre de la migración: " msg; \
	docker compose exec app alembic revision --autogenerate -m "$$msg"
	docker compose exec app alembic upgrade head

reset:
	@echo "ATENCIÓN: Esto borra la base de datos y todos los datos."
	@read -p "¿Continuar? (escribe 'si'): " confirm; \
	if [ "$$confirm" = "si" ]; then \
		docker compose down -v; \
		docker compose up -d; \
	fi
