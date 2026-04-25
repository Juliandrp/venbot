# Tests de Venbot

Suite de tests usando pytest + pytest-asyncio + SQLite en memoria por test.

## Ejecutar

Dentro del contenedor `app`:

```bash
docker compose exec app pytest
```

Con cobertura:

```bash
docker compose exec app pytest --cov=app --cov-report=term-missing
```

Solo un archivo:

```bash
docker compose exec app pytest tests/test_auth.py -v
```

Solo un test:

```bash
docker compose exec app pytest tests/test_auth.py::test_login_credenciales_validas -v
```

Excluir tests lentos:

```bash
docker compose exec app pytest -m "not slow"
```

## Cobertura actual

- `test_auth.py` — registro, login, refresh, endpoints protegidos
- `test_products.py` — CRUD, multi-tenant isolation, 404
- `test_customers.py` — CRUD, búsqueda, validación de email
- `test_plan_limits.py` — límites de productos/campañas, super-admin sin límites, defaults trial
- `test_billing_admin.py` — endpoints super-admin, planes, upgrade, checkout sin provider
- `test_storage.py` — LocalStorage, lectura de URL, eliminación
- `test_security.py` — bcrypt, Fernet, JWT access/refresh

## Notas

- Los tests usan **SQLite en memoria** para máxima velocidad y aislamiento.
- Los workers Celery NO se ejecutan en tests (las llamadas a `.delay()` no encolan).
- Servicios externos (Gemini, OpenAI, Pollinations, Stripe, etc.) NO se llaman — están aislados por la separación de capas.
- Cada test recibe una BD virgen con todas las tablas creadas vía `Base.metadata.create_all`.
