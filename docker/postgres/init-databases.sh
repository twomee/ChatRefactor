#!/bin/bash
# init-databases.sh — Creates separate databases for each microservice.
# Mounted into PostgreSQL container via docker-compose volumes.
# Runs only on first container startup (when data directory is empty).

set -e

echo "Creating microservice databases..."

for db in chatbox_auth chatbox_chat chatbox_messages chatbox_files; do
  echo "  Creating database: $db"
  psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" <<-EOSQL
    SELECT 'CREATE DATABASE $db OWNER $POSTGRES_USER'
    WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = '$db')\gexec
EOSQL
done

echo "All microservice databases created successfully."
