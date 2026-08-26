#!/bin/bash
set -e

# Create the mem0_app database for mem0's auth/config data.
# The default 'postgres' database is used by both Honcho and mem0 for pgvector.
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    SELECT 'CREATE DATABASE mem0_app'
    WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'mem0_app')\gexec
EOSQL

# Enable pgvector extension (needed by both Honcho and mem0)
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    CREATE EXTENSION IF NOT EXISTS vector;
EOSQL
