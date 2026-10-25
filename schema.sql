CREATE SEQUENCE IF NOT EXISTS seq_commit_id START 1;

CREATE TABLE IF NOT EXISTS package_skeletons (
    package_name VARCHAR PRIMARY KEY,
    source_url VARCHAR,
    original_size_bytes BIGINT,
    skeleton_size_bytes BIGINT,
    token_reduction_pct DOUBLE,
    skeleton_code VARCHAR,
    content_hash VARCHAR,
    last_updated_utc VARCHAR
);

CREATE TABLE IF NOT EXISTS ledger (
    commit_id BIGINT PRIMARY KEY,
    timestamp_utc VARCHAR,
    operation VARCHAR,
    package_name VARCHAR,
    reduction_pct DOUBLE,
    detail VARCHAR
);
