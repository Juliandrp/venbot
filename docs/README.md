# Manual técnico — Venbot

Documentación para desarrolladores que mantienen o extienden Venbot.

## Índice

| # | Capítulo | Para qué |
|---|----------|----------|
| 01 | [Arquitectura](01-arquitectura.md) | Visión general del sistema, componentes, diagrama de flujo |
| 02 | [Stack y dependencias](02-stack-y-dependencias.md) | Tecnologías usadas, versiones, por qué se eligieron |
| 03 | [Modelo de datos](03-modelo-de-datos.md) | Tablas, relaciones, campos críticos |
| 04 | [API endpoints](04-api-endpoints.md) | Referencia completa de todos los endpoints |
| 05 | [Workers y tareas](05-workers-y-tareas.md) | Celery, beat, colas, tareas programadas |
| 06 | [Pipeline IA](06-pipeline-ia.md) | Cómo funciona la generación de contenido |
| 07 | [Storage y archivos](07-storage-y-archivos.md) | Local vs S3, cómo extender a otros backends |
| 08 | [Multi-tenant y seguridad](08-multi-tenant-y-seguridad.md) | Isolation, JWT, cifrado de secretos |
| 09 | [Deploy en Coolify](09-deploy-coolify.md) | Cómo está montado en producción |
| 10 | [Migraciones Alembic](10-migraciones-alembic.md) | Cómo agregar columnas/tablas sin perder datos |
| 11 | [Troubleshooting](11-troubleshooting.md) | Problemas comunes y cómo diagnosticarlos |
| 12 | [Decisiones de diseño](12-decisiones-de-diseno.md) | Por qué se hizo así y no de otra forma |

## Convenciones

- **Idioma**: el código y comentarios están en español. Identificadores de modelos también (`Cliente`, `Pedido`, `Campana`).
- **Single-file**: cada feature vive en un solo archivo cuando es posible (`app/api/customers.py`, `app/services/payments.py`).
- **Async-first**: todo el código de la app es `async`. Workers Celery son síncronos pero corren `asyncio.run()` por dentro.

## Cómo contribuir

1. Branch desde `develop`, no desde `main`
2. Cambios pequeños = un commit. Cambios grandes = un PR
3. Si modificas un modelo SQLAlchemy: genera migración Alembic en el mismo commit
4. Tests para lógica nueva — `pytest tests/test_<modulo>.py`
5. Push a develop → revisión → merge a main → deploy automático en Coolify

## Stack en una línea

> FastAPI + PostgreSQL + Redis + Celery + Jinja2/Alpine.js/Tailwind, deployado en Coolify como Docker container único con uvicorn + worker + beat dentro.
