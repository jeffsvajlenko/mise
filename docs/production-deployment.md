# Production Deployment Guide - Home Lab Edition

## Overview

This guide covers deploying Mise for private family use on a home lab server with:
- Simple API key authentication
- Docker Compose orchestration
- Port forwarding for external access
- Automated backups
- Basic monitoring

## Architecture

```
Internet → Port Forward (443/80) → nginx (reverse proxy + HTTPS)
                                      ↓
                              mise-api (FastAPI)
                                      ↓
                              mise-worker (background jobs)
                                      ↓
                              postgres (database)
```

## Security Model (Family Use)

**Authentication:**
- API key authentication (X-API-Key header)
- CORS disabled by default (API client mode - most secure)
- IP address restriction (optional)
- HTTPS only (Let's Encrypt)

**CORS Configuration:**
- **Disabled by default** - For API clients (curl, Python, mobile apps)
- Browser-based requests blocked (prevents malicious websites)
- Enable only if you add a web frontend (set `API_CORS_ORIGINS`)

**Good for:**
- Trusted family members (5-20 users)
- API clients (not browser-based apps)
- Private network access
- Low traffic (< 1000 requests/day)

**Not suitable for:**
- Public internet exposure
- Untrusted users
- High traffic
- Browser-based web apps (unless CORS enabled)

## Prerequisites

**Server Requirements:**
- Linux server (Ubuntu 22.04+ recommended)
- 2GB+ RAM
- 20GB+ disk space
- Docker + Docker Compose installed
- Domain name (for HTTPS) or IP address

**Ports to forward:**
- 443 (HTTPS) - Required
- 80 (HTTP) - For Let's Encrypt verification

## File Structure

```
/opt/mise/
├── docker-compose.yml       # Main orchestration
├── .env.production         # Production secrets (not in git)
├── nginx/
│   ├── nginx.conf          # nginx configuration
│   └── ssl/                # SSL certificates (auto-generated)
├── data/
│   ├── postgres/           # Database files
│   ├── files/              # Recipe images
│   └── backups/            # Automated backups
└── logs/
    ├── nginx/
    ├── api/
    └── worker/
```

## Setup Steps

### 1. Server Preparation

```bash
# Create deployment directory
sudo mkdir -p /opt/mise
cd /opt/mise

# Clone repository (or copy files)
git clone https://github.com/yourusername/mise.git .

# Create required directories
sudo mkdir -p data/postgres data/files data/backups logs/{nginx,api,worker}
sudo chown -R $USER:$USER /opt/mise

# Install Docker and Docker Compose (if not already)
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
sudo usermod -aG docker $USER
newgrp docker
```

### 2. Configuration

Create `/opt/mise/.env.production`:

```bash
# Database Configuration
POSTGRES_USER=mise_user
POSTGRES_PASSWORD=CHANGE_THIS_SECURE_PASSWORD
POSTGRES_DB=mise
DATABASE_URL=postgresql+psycopg://mise_user:CHANGE_THIS_SECURE_PASSWORD@postgres:5432/mise

# API Configuration
API_HOST=0.0.0.0
API_PORT=8000
API_SECRET_KEY=CHANGE_THIS_TO_RANDOM_STRING_32_CHARS_MIN

# Allowed API Keys (comma-separated for multiple family members)
API_KEYS=family-secret-key-abc123,backup-key-xyz789

# File Storage
FILE_STORAGE_PATH=/data/files

# Anthropic AI Configuration
ANTHROPIC_API_KEY=sk-ant-your-api-key-here
AI_MODEL=claude-haiku-4-5-20251001
AI_MAX_TOKENS=4096

# Logging
LOG_LEVEL=INFO
SQLALCHEMY_ECHO=False

# Domain Configuration (for HTTPS)
DOMAIN=recipes.yourdomain.com
# Or use IP if no domain: DOMAIN=192.168.1.100

# Email for Let's Encrypt notifications
LETSENCRYPT_EMAIL=you@example.com
```

**Generate secure values:**
```bash
# Generate API secret key
python3 -c "import secrets; print(secrets.token_urlsafe(32))"

# Generate API key for family
python3 -c "import secrets; print('family-' + secrets.token_urlsafe(16))"

# Generate database password
python3 -c "import secrets; print(secrets.token_urlsafe(24))"
```

### 3. Docker Compose Setup

Create `/opt/mise/docker-compose.yml`:

```yaml
version: '3.8'

services:
  postgres:
    image: postgres:16-alpine
    container_name: mise-postgres
    restart: unless-stopped
    environment:
      POSTGRES_USER: ${POSTGRES_USER}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
      POSTGRES_DB: ${POSTGRES_DB}
    volumes:
      - ./data/postgres:/var/lib/postgresql/data
      - ./data/backups:/backups
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER}"]
      interval: 10s
      timeout: 5s
      retries: 5
    networks:
      - mise-network

  api:
    build:
      context: .
      dockerfile: Dockerfile
    container_name: mise-api
    restart: unless-stopped
    depends_on:
      postgres:
        condition: service_healthy
    environment:
      - DATABASE_URL=${DATABASE_URL}
      - API_SECRET_KEY=${API_SECRET_KEY}
      - API_KEYS=${API_KEYS}
      - FILE_STORAGE_PATH=/data/files
      - ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}
      - AI_MODEL=${AI_MODEL}
      - AI_MAX_TOKENS=${AI_MAX_TOKENS}
      - LOG_LEVEL=${LOG_LEVEL}
      - SQLALCHEMY_ECHO=${SQLALCHEMY_ECHO}
    volumes:
      - ./data/files:/data/files
      - ./logs/api:/var/log/mise
    command: uvicorn mise.api.main:app --host 0.0.0.0 --port 8000
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/api/health"]
      interval: 30s
      timeout: 10s
      retries: 3
    networks:
      - mise-network

  worker:
    build:
      context: .
      dockerfile: Dockerfile
    container_name: mise-worker
    restart: unless-stopped
    depends_on:
      postgres:
        condition: service_healthy
    environment:
      - DATABASE_URL=${DATABASE_URL}
      - FILE_STORAGE_PATH=/data/files
      - ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}
      - AI_MODEL=${AI_MODEL}
      - AI_MAX_TOKENS=${AI_MAX_TOKENS}
      - LOG_LEVEL=${LOG_LEVEL}
      - SQLALCHEMY_ECHO=${SQLALCHEMY_ECHO}
      - WORKER_ID=worker-1
      - WORKER_POLL_INTERVAL=5
    volumes:
      - ./data/files:/data/files
      - ./logs/worker:/var/log/mise
    command: python -m mise.worker.processor --mode continuous
    networks:
      - mise-network

  nginx:
    image: nginx:alpine
    container_name: mise-nginx
    restart: unless-stopped
    depends_on:
      - api
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx/nginx.conf:/etc/nginx/nginx.conf:ro
      - ./nginx/ssl:/etc/nginx/ssl
      - ./logs/nginx:/var/log/nginx
    networks:
      - mise-network

  # Automated backup service
  backup:
    image: postgres:16-alpine
    container_name: mise-backup
    restart: unless-stopped
    depends_on:
      - postgres
    environment:
      - POSTGRES_USER=${POSTGRES_USER}
      - POSTGRES_PASSWORD=${POSTGRES_PASSWORD}
      - POSTGRES_DB=${POSTGRES_DB}
    volumes:
      - ./data/backups:/backups
      - ./scripts/backup.sh:/backup.sh:ro
    command: sh -c "while true; do sleep 86400; /backup.sh; done"
    networks:
      - mise-network

networks:
  mise-network:
    driver: bridge
```

### 4. Dockerfile

Create `/opt/mise/Dockerfile`:

```dockerfile
FROM python:3.13-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    gcc \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Install uv for dependency management
RUN pip install uv

# Copy project files
COPY pyproject.toml uv.lock ./
COPY src/ ./src/
COPY alembic/ ./alembic/
COPY alembic.ini ./

# Install dependencies
RUN uv sync --frozen

# Create log directory
RUN mkdir -p /var/log/mise

# Run migrations on startup (handled by entrypoint)
COPY scripts/docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh

ENTRYPOINT ["/docker-entrypoint.sh"]
```

### 5. nginx Configuration

Create `/opt/mise/nginx/nginx.conf`:

```nginx
events {
    worker_connections 1024;
}

http {
    # Rate limiting for API
    limit_req_zone $binary_remote_addr zone=api_limit:10m rate=10r/s;

    # SSL Configuration
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;
    ssl_prefer_server_ciphers on;

    # Logging
    access_log /var/log/nginx/access.log;
    error_log /var/log/nginx/error.log;

    # HTTP to HTTPS redirect
    server {
        listen 80;
        server_name ${DOMAIN};

        # Allow Let's Encrypt verification
        location /.well-known/acme-challenge/ {
            root /var/www/certbot;
        }

        # Redirect everything else to HTTPS
        location / {
            return 301 https://$server_name$request_uri;
        }
    }

    # HTTPS server
    server {
        listen 443 ssl http2;
        server_name ${DOMAIN};

        # SSL Certificates (generated by certbot)
        ssl_certificate /etc/nginx/ssl/fullchain.pem;
        ssl_certificate_key /etc/nginx/ssl/privkey.pem;

        # Security headers
        add_header X-Frame-Options "SAMEORIGIN" always;
        add_header X-Content-Type-Options "nosniff" always;
        add_header X-XSS-Protection "1; mode=block" always;
        add_header Referrer-Policy "no-referrer-when-downgrade" always;

        # Max upload size (for recipe images)
        client_max_body_size 10M;

        # API endpoints
        location /api/ {
            # Rate limiting
            limit_req zone=api_limit burst=20 nodelay;

            proxy_pass http://api:8000;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;

            # Timeouts
            proxy_connect_timeout 60s;
            proxy_send_timeout 60s;
            proxy_read_timeout 60s;
        }

        # API docs (optional: remove for extra security)
        location /docs {
            proxy_pass http://api:8000;
            proxy_set_header Host $host;
        }

        location /redoc {
            proxy_pass http://api:8000;
            proxy_set_header Host $host;
        }

        # Health check (no auth required)
        location /api/health {
            proxy_pass http://api:8000;
        }

        # Root redirect to docs
        location = / {
            return 301 /docs;
        }
    }
}
```

### 6. Docker Entrypoint Script

Create `/opt/mise/scripts/docker-entrypoint.sh`:

```bash
#!/bin/bash
set -e

# Wait for postgres to be ready
echo "Waiting for PostgreSQL..."
until PGPASSWORD=$POSTGRES_PASSWORD psql -h postgres -U $POSTGRES_USER -d $POSTGRES_DB -c '\q' 2>/dev/null; do
  sleep 2
done
echo "PostgreSQL is ready"

# Run database migrations
echo "Running database migrations..."
uv run alembic upgrade head

# Execute the main command
exec "$@"
```

### 7. Backup Script

Create `/opt/mise/scripts/backup.sh`:

```bash
#!/bin/bash

# Backup configuration
BACKUP_DIR="/backups"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="$BACKUP_DIR/mise_backup_$TIMESTAMP.sql.gz"
DAYS_TO_KEEP=30

# Create backup
echo "Starting backup at $(date)"
pg_dump -h postgres -U $POSTGRES_USER $POSTGRES_DB | gzip > "$BACKUP_FILE"

# Check if backup was successful
if [ $? -eq 0 ]; then
    echo "Backup completed: $BACKUP_FILE"

    # Delete old backups
    find $BACKUP_DIR -name "mise_backup_*.sql.gz" -mtime +$DAYS_TO_KEEP -delete
    echo "Cleaned up backups older than $DAYS_TO_KEEP days"
else
    echo "Backup failed!"
    exit 1
fi
```

### 8. API Authentication Middleware

Create `/opt/mise/src/mise/api/auth.py`:

```python
"""Simple API key authentication for family use."""

import os
from fastapi import HTTPException, Security
from fastapi.security import APIKeyHeader

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def get_api_keys() -> list[str]:
    """Get allowed API keys from environment."""
    keys_str = os.getenv("API_KEYS", "")
    if not keys_str:
        # Development mode: allow without key
        return []
    return [k.strip() for k in keys_str.split(",") if k.strip()]


async def verify_api_key(api_key: str = Security(api_key_header)):
    """Verify API key from request header."""
    allowed_keys = get_api_keys()

    # If no keys configured, allow (development mode)
    if not allowed_keys:
        return True

    # Require key in production
    if not api_key:
        raise HTTPException(
            status_code=401,
            detail="Missing API key. Include X-API-Key header."
        )

    if api_key not in allowed_keys:
        raise HTTPException(
            status_code=403,
            detail="Invalid API key"
        )

    return True
```

Update `/opt/mise/src/mise/api/main.py`:

```python
# Add after imports
from mise.api.auth import verify_api_key
from fastapi import Depends

# Update router includes to add auth dependency
app.include_router(
    ingestions.router,
    prefix="/api/ingestions",
    tags=["ingestions"],
    dependencies=[Depends(verify_api_key)]  # Add this
)
app.include_router(
    recipes.router,
    prefix="/api/recipes",
    tags=["recipes"],
    dependencies=[Depends(verify_api_key)]  # Add this
)
app.include_router(
    files.router,
    prefix="/api/files",
    tags=["files"],
    dependencies=[Depends(verify_api_key)]  # Add this
)
# Health check has no auth (for monitoring)
app.include_router(health.router, tags=["health"])
```

## Deployment

### Initial Deployment

```bash
cd /opt/mise

# 1. Configure environment
cp .env.production.example .env.production
nano .env.production  # Edit with your values

# 2. Build containers
docker-compose build

# 3. Start services
docker-compose up -d

# 4. Check logs
docker-compose logs -f

# 5. Verify health
curl http://localhost/api/health

# 6. Setup SSL (if using domain)
# Follow certbot instructions for nginx
```

### SSL Certificate Setup (with domain)

```bash
# Using certbot
docker run -it --rm \
  -v /opt/mise/nginx/ssl:/etc/letsencrypt \
  -v /opt/mise/nginx/www:/var/www/certbot \
  certbot/certbot certonly \
  --webroot \
  --webroot-path=/var/www/certbot \
  --email your@email.com \
  --agree-tos \
  --no-eff-email \
  -d recipes.yourdomain.com

# Copy certificates
cp /opt/mise/nginx/ssl/live/recipes.yourdomain.com/fullchain.pem /opt/mise/nginx/ssl/
cp /opt/mise/nginx/ssl/live/recipes.yourdomain.com/privkey.pem /opt/mise/nginx/ssl/

# Reload nginx
docker-compose restart nginx
```

### Without Domain (IP only)

Generate self-signed certificate:

```bash
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout /opt/mise/nginx/ssl/privkey.pem \
  -out /opt/mise/nginx/ssl/fullchain.pem \
  -subj "/CN=192.168.1.100"
```

## Usage

### Client Setup (Family Members)

Share these instructions with family:

**Mobile/Desktop App:**
```
Server: https://recipes.yourdomain.com
API Key: family-secret-key-abc123
```

**Using curl:**
```bash
# Create ingestion
curl -X POST https://recipes.yourdomain.com/api/ingestions \
  -H "X-API-Key: family-secret-key-abc123" \
  -H "Content-Type: application/json" \
  -d '{
    "source_type": "text",
    "text": "Pasta Recipe: Boil pasta, add sauce..."
  }'

# List recipes
curl https://recipes.yourdomain.com/api/recipes \
  -H "X-API-Key: family-secret-key-abc123"
```

## Maintenance

### Checking Status

```bash
cd /opt/mise

# Check all services
docker-compose ps

# View logs
docker-compose logs -f api
docker-compose logs -f worker
docker-compose logs -f postgres

# Check disk usage
du -sh data/
```

### Updating

```bash
cd /opt/mise

# Pull latest changes
git pull

# Rebuild and restart
docker-compose build
docker-compose up -d

# Run new migrations
docker-compose exec api uv run alembic upgrade head
```

### Backups

**Manual backup:**
```bash
docker-compose exec postgres pg_dump -U mise_user mise | gzip > backup_$(date +%Y%m%d).sql.gz
```

**Restore from backup:**
```bash
gunzip < backup_20250101.sql.gz | docker-compose exec -T postgres psql -U mise_user mise
```

**Backup files:**
```bash
tar -czf files_backup_$(date +%Y%m%d).tar.gz data/files/
```

### Troubleshooting

**Worker not processing jobs:**
```bash
# Check worker logs
docker-compose logs -f worker

# Restart worker
docker-compose restart worker
```

**Database connection issues:**
```bash
# Check postgres health
docker-compose exec postgres pg_isready -U mise_user

# Check database size
docker-compose exec postgres psql -U mise_user -d mise -c "SELECT pg_size_pretty(pg_database_size('mise'));"
```

**API errors:**
```bash
# Check API logs
docker-compose logs -f api

# Test health endpoint
curl http://localhost/api/health

# Restart API
docker-compose restart api
```

## Monitoring

### Basic Monitoring

Create `/opt/mise/scripts/monitor.sh`:

```bash
#!/bin/bash

echo "=== Mise System Status ==="
echo ""

# Container status
echo "Containers:"
docker-compose ps

# Disk usage
echo ""
echo "Disk Usage:"
du -sh /opt/mise/data/*

# Database size
echo ""
echo "Database:"
docker-compose exec -T postgres psql -U mise_user -d mise -c "SELECT pg_size_pretty(pg_database_size('mise')) as size;"

# Recent ingestions
echo ""
echo "Recent Ingestions (last 24h):"
docker-compose exec -T postgres psql -U mise_user -d mise -c "
SELECT status, COUNT(*)
FROM ingestion_requests
WHERE created_at > NOW() - INTERVAL '24 hours'
GROUP BY status;"

# API health
echo ""
echo "API Health:"
curl -s http://localhost/api/health | python3 -m json.tool
```

Run daily via cron:
```bash
0 8 * * * /opt/mise/scripts/monitor.sh >> /opt/mise/logs/monitor.log
```

## Security Checklist

- [ ] Changed all default passwords in `.env.production`
- [ ] Generated strong API keys
- [ ] HTTPS enabled (SSL certificate installed)
- [ ] API key authentication configured
- [ ] Port forwarding limited to 80/443 only
- [ ] Regular backups configured
- [ ] Firewall configured (UFW or iptables)
- [ ] API keys shared securely with family (not via email)
- [ ] `.env.production` not committed to git
- [ ] Logs monitored regularly

## Next Steps

1. **Optional: IP Whitelist** - Restrict to known IPs in nginx
2. **Optional: VPN** - Access via WireGuard/Tailscale instead of port forwarding
3. **Optional: Uptime Monitoring** - UptimeRobot or similar
4. **Optional: Log Aggregation** - Loki or ELK stack

## Support

For issues or questions:
1. Check logs: `docker-compose logs`
2. Review documentation: `/docs`
3. Check GitHub issues
