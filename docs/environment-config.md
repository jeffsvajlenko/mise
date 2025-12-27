# Environment Configuration

This project uses environment-specific `.env` files to manage configuration for different deployment scenarios.

## Environment Files

### `.env.development` (Development)
- Used for local development
- Connects to local Docker PostgreSQL
- SQL query logging enabled
- **Committed to git** (contains no secrets)

### `.env.production` (Production/Homelab)
- Used for production deployment
- **NOT committed to git** (contains secrets)
- SQL query logging disabled
- You must create this file on your server

### `.env` (Legacy/Override)
- Optional fallback file
- Not committed to git
- Can be used for local overrides

## How It Works

The `src/mise/config.py` module automatically loads the appropriate `.env` file based on the `ENV` environment variable:

```python
# Defaults to development
ENV=development → loads .env.development

# Production
ENV=production → loads .env.production
```

## Usage

### Development (Default)

Just run commands normally - development is the default:

```bash
# Uses .env.development automatically
uv run python scripts/db_status.py
uv run alembic upgrade head
```

Or explicitly set the environment:

```bash
ENV=development uv run python scripts/db_status.py
```

Or use the helper script:

```bash
./scripts/run_dev.sh uv run python scripts/db_status.py
```

### Production

Set `ENV=production` before running commands:

```bash
ENV=production uv run alembic upgrade head
ENV=production uv run python -m uvicorn app:app
```

Or use the helper script:

```bash
./scripts/run_prod.sh uv run alembic upgrade head
```

## Homelab Deployment

### 1. Clone the repository on your server

```bash
git clone <your-repo>
cd mise
```

### 2. Create production environment file

```bash
cp .env.production .env.production.local
nano .env.production.local
```

Update with your actual credentials:

```bash
DATABASE_URL=postgresql+psycopg://mise_user:STRONG_PASSWORD_HERE@localhost:5432/mise_prod
SQLALCHEMY_ECHO=False
ENV=production
```

**Important:** The `.env.production` file in git is just a template. Your actual production file (`.env.production.local`) is gitignored.

### 3. Set up the database

```bash
# Create PostgreSQL database
sudo -u postgres createdb mise_prod
sudo -u postgres createuser mise_user
sudo -u postgres psql -c "ALTER USER mise_user PASSWORD 'STRONG_PASSWORD_HERE';"
sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE mise_prod TO mise_user;"

# Run migrations
ENV=production uv run alembic upgrade head
```

### 4. Run the application

**Option A: Direct execution**
```bash
ENV=production uv run python -m uvicorn app:app --host 0.0.0.0 --port 8000
```

**Option B: Systemd service**

Create `/etc/systemd/system/mise.service`:

```ini
[Unit]
Description=Mise Recipe App
After=postgresql.service

[Service]
Type=simple
User=mise
WorkingDirectory=/opt/mise
Environment="ENV=production"
ExecStart=/opt/mise/.venv/bin/uvicorn app:app --host 0.0.0.0 --port 8000
Restart=always

[Install]
WantedBy=multi-user.target
```

Enable and start:

```bash
sudo systemctl enable mise
sudo systemctl start mise
sudo systemctl status mise
```

**Option C: Docker Compose**

Update `docker-compose.yml` to read from `.env.production`:

```yaml
services:
  app:
    build: .
    env_file:
      - .env.production
    depends_on:
      - db
```

Then:

```bash
docker-compose up -d
```

## Configuration Variables

### `DATABASE_URL`
PostgreSQL connection string.

**Format:** `postgresql+psycopg://user:password@host:port/database`

**Development:** `postgresql+psycopg://mise_user:mise_password@localhost:5432/mise`

**Production:** Update with your actual credentials

### `SQLALCHEMY_ECHO`
Enable/disable SQL query logging.

**Development:** `True` (helpful for debugging)

**Production:** `False` (reduces log noise)

### `ENV`
Environment identifier.

**Values:** `development`, `production`

**Default:** `development`

## Security Best Practices

1. **Never commit `.env.production` with real credentials**
   - The file in git is just a template
   - Use `.env.production.local` on servers (gitignored)

2. **Use strong passwords in production**
   - Generate with: `openssl rand -base64 32`

3. **Restrict file permissions on servers**
   ```bash
   chmod 600 .env.production.local
   chown mise:mise .env.production.local
   ```

4. **Use environment variables in CI/CD**
   - Don't store secrets in `.env` files in CI
   - Use GitHub Secrets, GitLab CI/CD variables, etc.

## Troubleshooting

### "No .env file found" message
This is normal if you haven't created an environment file. The app will use defaults from the code.

### Wrong database being used
Check that `ENV` is set correctly:
```bash
echo $ENV
# Should be "production" on your server
```

### Database connection failed
Verify the `DATABASE_URL` in your `.env.{ENV}` file:
```bash
ENV=production uv run python scripts/db_status.py
```

## Alembic Integration

Alembic automatically uses the same environment configuration. The `alembic/env.py` file imports `DATABASE_URL` from `mise.db.database`, which respects the `ENV` variable.

```bash
# Development migrations
alembic revision --autogenerate -m "description"
alembic upgrade head

# Production migrations
ENV=production alembic upgrade head
```
