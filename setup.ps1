# setup.ps1 — Configura el entorno local de Venbot en Windows
# Uso: .\setup.ps1

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "   Venbot — Setup entorno local" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# 1. Verificar Docker
Write-Host "[1/4] Verificando Docker..." -ForegroundColor Yellow
try {
    $dockerVersion = docker --version 2>&1
    Write-Host "      OK: $dockerVersion" -ForegroundColor Green
} catch {
    Write-Host "      ERROR: Docker no encontrado. Instala Docker Desktop primero." -ForegroundColor Red
    Write-Host "      https://www.docker.com/products/docker-desktop" -ForegroundColor Gray
    exit 1
}

# 2. Verificar que Docker esté corriendo
$dockerInfo = docker info 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "      ERROR: Docker no está corriendo. Abre Docker Desktop." -ForegroundColor Red
    exit 1
}

# 3. Generar claves con Python (incluido en Docker) o con .NET
Write-Host ""
Write-Host "[2/4] Generando claves de seguridad..." -ForegroundColor Yellow

# SECRET_KEY — 32 bytes hex
$secretKeyBytes = New-Object byte[] 32
[System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($secretKeyBytes)
$secretKey = [BitConverter]::ToString($secretKeyBytes) -replace '-', ''
$secretKey = $secretKey.ToLower()

# ENCRYPTION_KEY — Fernet key (URL-safe base64, 32 bytes)
$fernetBytes = New-Object byte[] 32
[System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($fernetBytes)
$encryptionKey = [Convert]::ToBase64String($fernetBytes)
# Hacerlo URL-safe (Fernet usa base64 URL-safe con padding)
$encryptionKey = $encryptionKey.Replace('+', '-').Replace('/', '_')

Write-Host "      SECRET_KEY generado" -ForegroundColor Green
Write-Host "      ENCRYPTION_KEY generado" -ForegroundColor Green

# 4. Crear .env si no existe
Write-Host ""
Write-Host "[3/4] Creando archivo .env..." -ForegroundColor Yellow

if (Test-Path ".env") {
    Write-Host "      Ya existe un .env — no se sobreescribe." -ForegroundColor Yellow
    Write-Host "      Si quieres regenerarlo, borra el .env actual y corre el script de nuevo." -ForegroundColor Gray
} else {
    $envContent = @"
# ============================================================
# App
# ============================================================
SECRET_KEY=$secretKey
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=60
REFRESH_TOKEN_EXPIRE_DAYS=30
ENVIRONMENT=development
APP_BASE_URL=http://localhost:8000

# ============================================================
# Database (Docker Compose la crea automáticamente)
# ============================================================
DATABASE_URL=postgresql+asyncpg://venbot:venbot_pass@postgres:5432/venbot_db
SYNC_DATABASE_URL=postgresql://venbot:venbot_pass@postgres:5432/venbot_db

# ============================================================
# Redis / Celery
# ============================================================
REDIS_URL=redis://redis:6379/0
CELERY_BROKER_URL=redis://redis:6379/1
CELERY_RESULT_BACKEND=redis://redis:6379/2

# ============================================================
# Cifrado de secretos de tenants
# ============================================================
ENCRYPTION_KEY=$encryptionKey

# ============================================================
# IA — Mínimo: ANTHROPIC_API_KEY para que el bot funcione
# ============================================================
ANTHROPIC_API_KEY=sk-ant-REEMPLAZA-CON-TU-CLAVE
OPENAI_API_KEY=sk-REEMPLAZA-CON-TU-CLAVE

# ============================================================
# Super-admin (se crea solo al iniciar la app)
# ============================================================
SUPERADMIN_EMAIL=admin@venbot.io
SUPERADMIN_PASSWORD=cambia-esta-clave-ahora

# ============================================================
# Flower (monitoreo Celery)
# ============================================================
FLOWER_USER=admin
FLOWER_PASSWORD=flower123
"@
    $envContent | Out-File -FilePath ".env" -Encoding utf8 -NoNewline
    Write-Host "      .env creado correctamente" -ForegroundColor Green
}

# 5. Instrucciones finales
Write-Host ""
Write-Host "[4/4] Listo para arrancar" -ForegroundColor Yellow
Write-Host ""
Write-Host "  IMPORTANTE: Edita el .env y completa:" -ForegroundColor Magenta
Write-Host "    ANTHROPIC_API_KEY=sk-ant-..."  -ForegroundColor White
Write-Host "    SUPERADMIN_PASSWORD=tu-clave-segura" -ForegroundColor White
Write-Host ""
Write-Host "  Luego ejecuta:" -ForegroundColor Cyan
Write-Host "    docker compose up -d" -ForegroundColor White
Write-Host ""
Write-Host "  URLs disponibles:" -ForegroundColor Cyan
Write-Host "    App:      http://localhost:8000" -ForegroundColor White
Write-Host "    API docs: http://localhost:8000/api/docs" -ForegroundColor White
Write-Host "    Flower:   http://localhost:5555" -ForegroundColor White
Write-Host ""
Write-Host "  Para ver los logs:" -ForegroundColor Cyan
Write-Host "    docker compose logs -f app" -ForegroundColor White
Write-Host "    docker compose logs -f celery-worker" -ForegroundColor White
Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
