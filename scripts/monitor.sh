#!/bin/bash
# Monitoring script for Mise production deployment
# Checks service health, disk space, and logs errors

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.prod.yml}"
LOG_DIR="${LOG_DIR:-./logs}"
DATA_DIR="${DATA_DIR:-./data}"
DISK_WARNING_THRESHOLD=80  # Warn if disk usage exceeds this percentage

echo "==================================="
echo "Mise Production Health Check"
echo "$(date)"
echo "==================================="
echo ""

# Check Docker services
echo "📦 Docker Services:"
echo "-----------------------------------"
docker-compose -f "$COMPOSE_FILE" ps

SERVICE_STATUS=0

# Check each service health
for service in postgres api worker nginx; do
    if docker-compose -f "$COMPOSE_FILE" ps "$service" | grep -q "Up"; then
        echo -e "${GREEN}✓${NC} $service is running"
    else
        echo -e "${RED}✗${NC} $service is NOT running"
        SERVICE_STATUS=1
    fi
done

echo ""

# Check API health endpoint
echo "🏥 API Health Check:"
echo "-----------------------------------"
if curl -f -s http://localhost/api/health > /dev/null 2>&1; then
    echo -e "${GREEN}✓${NC} API is responding"
    # Get detailed health info
    curl -s http://localhost/api/health | python3 -m json.tool
else
    echo -e "${RED}✗${NC} API is NOT responding"
    SERVICE_STATUS=1
fi

echo ""

# Check disk space
echo "💾 Disk Space:"
echo "-----------------------------------"
DISK_USAGE=$(df -h "$DATA_DIR" | awk 'NR==2 {print $5}' | sed 's/%//')
DISK_SIZE=$(df -h "$DATA_DIR" | awk 'NR==2 {print $2}')
DISK_USED=$(df -h "$DATA_DIR" | awk 'NR==2 {print $3}')
DISK_AVAIL=$(df -h "$DATA_DIR" | awk 'NR==2 {print $4}')

echo "Data directory: $DATA_DIR"
echo "Total: $DISK_SIZE | Used: $DISK_USED | Available: $DISK_AVAIL"

if [ "$DISK_USAGE" -gt "$DISK_WARNING_THRESHOLD" ]; then
    echo -e "${RED}⚠${NC}  Disk usage is at ${DISK_USAGE}% (threshold: ${DISK_WARNING_THRESHOLD}%)"
    SERVICE_STATUS=1
else
    echo -e "${GREEN}✓${NC} Disk usage is at ${DISK_USAGE}%"
fi

echo ""

# Check database size
echo "🗄️  Database:"
echo "-----------------------------------"
DB_SIZE=$(docker-compose -f "$COMPOSE_FILE" exec -T postgres \
    psql -U "${POSTGRES_USER:-mise_user}" -d "${POSTGRES_DB:-mise}" \
    -t -c "SELECT pg_size_pretty(pg_database_size('${POSTGRES_DB:-mise}'));" 2>/dev/null | xargs)

if [ -n "$DB_SIZE" ]; then
    echo -e "${GREEN}✓${NC} Database size: $DB_SIZE"
else
    echo -e "${YELLOW}⚠${NC}  Could not determine database size"
fi

# Check number of recipes
RECIPE_COUNT=$(docker-compose -f "$COMPOSE_FILE" exec -T postgres \
    psql -U "${POSTGRES_USER:-mise_user}" -d "${POSTGRES_DB:-mise}" \
    -t -c "SELECT COUNT(*) FROM recipe_db_model WHERE deleted_at IS NULL;" 2>/dev/null | xargs)

if [ -n "$RECIPE_COUNT" ]; then
    echo "   Recipes in database: $RECIPE_COUNT"
fi

# Check pending ingestions
PENDING_COUNT=$(docker-compose -f "$COMPOSE_FILE" exec -T postgres \
    psql -U "${POSTGRES_USER:-mise_user}" -d "${POSTGRES_DB:-mise}" \
    -t -c "SELECT COUNT(*) FROM ingestion_request WHERE status = 'pending';" 2>/dev/null | xargs)

if [ -n "$PENDING_COUNT" ]; then
    if [ "$PENDING_COUNT" -gt 0 ]; then
        echo -e "${YELLOW}⚠${NC}  Pending ingestions: $PENDING_COUNT"
    else
        echo "   Pending ingestions: $PENDING_COUNT"
    fi
fi

echo ""

# Check recent errors in logs
echo "📋 Recent Errors (last 24h):"
echo "-----------------------------------"
ERROR_COUNT=0

if [ -d "$LOG_DIR" ]; then
    # Check API logs
    if [ -f "$LOG_DIR/api/mise.log" ]; then
        API_ERRORS=$(find "$LOG_DIR/api" -name "*.log" -mtime -1 -exec grep -i "error\|exception\|critical" {} \; 2>/dev/null | wc -l)
        if [ "$API_ERRORS" -gt 0 ]; then
            echo -e "${YELLOW}⚠${NC}  API: $API_ERRORS errors found"
            ERROR_COUNT=$((ERROR_COUNT + API_ERRORS))
        else
            echo -e "${GREEN}✓${NC} API: No errors"
        fi
    fi

    # Check worker logs
    if [ -f "$LOG_DIR/worker/mise.log" ]; then
        WORKER_ERRORS=$(find "$LOG_DIR/worker" -name "*.log" -mtime -1 -exec grep -i "error\|exception\|critical" {} \; 2>/dev/null | wc -l)
        if [ "$WORKER_ERRORS" -gt 0 ]; then
            echo -e "${YELLOW}⚠${NC}  Worker: $WORKER_ERRORS errors found"
            ERROR_COUNT=$((ERROR_COUNT + WORKER_ERRORS))
        else
            echo -e "${GREEN}✓${NC} Worker: No errors"
        fi
    fi
else
    echo -e "${YELLOW}⚠${NC}  Log directory not found: $LOG_DIR"
fi

echo ""

# Check backups
echo "💾 Backups:"
echo "-----------------------------------"
if [ -d "$DATA_DIR/backups" ]; then
    BACKUP_COUNT=$(ls -1 "$DATA_DIR/backups"/mise_backup_*.sql.gz 2>/dev/null | wc -l)
    if [ "$BACKUP_COUNT" -gt 0 ]; then
        LATEST_BACKUP=$(ls -t "$DATA_DIR/backups"/mise_backup_*.sql.gz 2>/dev/null | head -n 1)
        BACKUP_AGE=$(find "$LATEST_BACKUP" -mtime +1 2>/dev/null)

        if [ -n "$BACKUP_AGE" ]; then
            echo -e "${YELLOW}⚠${NC}  Latest backup is older than 24 hours"
        else
            echo -e "${GREEN}✓${NC} Latest backup: $(basename "$LATEST_BACKUP")"
        fi
        echo "   Total backups: $BACKUP_COUNT"
    else
        echo -e "${YELLOW}⚠${NC}  No backups found"
    fi
else
    echo -e "${YELLOW}⚠${NC}  Backup directory not found"
fi

echo ""
echo "==================================="

# Exit with appropriate status
if [ $SERVICE_STATUS -eq 0 ] && [ $ERROR_COUNT -eq 0 ]; then
    echo -e "${GREEN}✓ All systems operational${NC}"
    exit 0
else
    echo -e "${RED}⚠ Issues detected - review above${NC}"
    exit 1
fi
