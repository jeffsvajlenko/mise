#!/usr/bin/env bash
# Run commands in development environment

# Set environment to development
export ENV=development

# Execute the command passed as arguments
exec "$@"
