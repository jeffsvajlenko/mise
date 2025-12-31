#!/bin/bash
set -e

# Backup configuration
BACKUP_DIR="/backups"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="$BACKUP_DIR/mise_backup_$TIMESTAMP.sql.gz"
DAYS_TO_KEEP=30

# Ensure backup directory exists
mkdir -p "$BACKUP_DIR"

# Create backup
echo "[$(date)] Starting backup..."
PGPASSWORD=$POSTGRES_PASSWORD pg_dump -h postgres -U $POSTGRES_USER $POSTGRES_DB | gzip > "$BACKUP_FILE"

# Check if backup was successful
if [ $? -eq 0 ]; then
    echo "[$(date)] Backup completed: $BACKUP_FILE"

    # Get backup size
    SIZE=$(du -h "$BACKUP_FILE" | cut -f1)
    echo "[$(date)] Backup size: $SIZE"

    # Delete old backups
    OLD_BACKUPS=$(find $BACKUP_DIR -name "mise_backup_*.sql.gz" -mtime +$DAYS_TO_KEEP)
    if [ -n "$OLD_BACKUPS" ]; then
        echo "[$(date)] Cleaning up backups older than $DAYS_TO_KEEP days..."
        find $BACKUP_DIR -name "mise_backup_*.sql.gz" -mtime +$DAYS_TO_KEEP -delete
        echo "[$(date)] Cleanup complete"
    fi

    # Keep only last 10 backups as safety measure
    BACKUP_COUNT=$(ls -1 $BACKUP_DIR/mise_backup_*.sql.gz 2>/dev/null | wc -l)
    if [ $BACKUP_COUNT -gt 10 ]; then
        echo "[$(date)] Keeping only last 10 backups..."
        ls -t $BACKUP_DIR/mise_backup_*.sql.gz | tail -n +11 | xargs rm -f
    fi

    echo "[$(date)] Backup process completed successfully"
else
    echo "[$(date)] ERROR: Backup failed!" >&2
    exit 1
fi
