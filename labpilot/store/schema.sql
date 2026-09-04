-- Shape A: one table, one UNDIMENSIONED vector column.
--
-- Measured on the real project 2026-09-03 (PostgreSQL 17.6, pgvector 0.8.2):
--   `v vector` with no width really stores different widths side by side, and
--   `<=>` works on it. It CANNOT be indexed -- "column does not have
--   dimensions". That is accepted on purpose. Slice 8 has not chosen the
--   embedder, and steps 1-2 of slice 4 use EXACT search, which needs no index.
--   Choosing an index shape means choosing a model, so it waits for step 3.

create extension if not exists vector;

-- embedding_model and dim live on the ARTIFACT, never on the chunk. One
-- artifact has one model, so its rows CANNOT disagree and there is nothing
-- left to detect. Put a rule where it cannot be broken, not where it can be
-- checked.
create table if not exists artifacts (
    id              text        primary key,
    name            text        not null,
    side            char(1)     not null check (side in ('A', 'B')),
    embedding_model text        not null,
    dim             int         not null check (dim > 0),
    created_at      timestamptz not null default now()
);

-- No `side` column: one artifact has one side, so artifact_id already decides
-- it, and the side filter IS the artifact filter -- one predicate, not two.
-- No `chunk_count` column: count(*) gives it, and a second copy of the truth
-- drifts.
-- No separate index on artifact_id: it is the primary key's LEADING column,
-- so `where artifact_id = $1` already uses that B-tree. A second index would
-- be a second copy of the same thing.
create table if not exists chunks (
    artifact_id text   not null references artifacts (id) on delete cascade,
    chunk_index int    not null,
    text        text   not null,
    header      text   not null default '',
    source      text   not null,
    start_line  int    not null,
    end_line    int    not null,
    v           vector not null,
    primary key (artifact_id, chunk_index)
);