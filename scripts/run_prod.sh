#!/usr/bin/env bash
# Run commands in production environment

# Set environment to production
export ENV=production

# Execute the command passed as arguments
exec "$@"
