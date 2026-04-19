-- Enable required PostgreSQL extensions on database creation
CREATE EXTENSION IF NOT EXISTS vector;       -- for pgvector ANN search
CREATE EXTENSION IF NOT EXISTS pg_trgm;      -- for BM25-like full-text search
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";  -- for gen_random_uuid()
