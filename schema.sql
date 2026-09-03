-- Daba.Cities Content Pipeline — database schema
-- Run against the postgres service after `docker compose up -d`:
--   docker compose exec -T postgres psql -U $POSTGRES_USER -d $POSTGRES_DB -f schema.sql

CREATE TABLE IF NOT EXISTS posts (
    id                 SERIAL PRIMARY KEY,
    notion_id          TEXT NOT NULL UNIQUE,
    content_type       TEXT NOT NULL,
    status             TEXT NOT NULL DEFAULT 'pending_approval',
    due_at             TIMESTAMPTZ,
    approved_by        TEXT,
    resume_url         TEXT,
    reviewer_feedback  TEXT,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS post_variants (
    id             SERIAL PRIMARY KEY,
    post_id        INTEGER NOT NULL REFERENCES posts(id) ON DELETE CASCADE,
    platform       TEXT NOT NULL,
    text           TEXT,
    image_url      TEXT,
    published_url  TEXT,
    status         TEXT NOT NULL DEFAULT 'pending',
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (post_id, platform)
);

CREATE TABLE IF NOT EXISTS pipeline_errors (
    id             SERIAL PRIMARY KEY,
    workflow_name  TEXT,
    failed_node    TEXT,
    error_message  TEXT,
    occurred_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
