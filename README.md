# 🧬 Code AST Skeleton Wire

An autonomous, zero-maintenance token-reduction infrastructure running entirely on GitHub Actions. It pulls Python source code from upstream repositories, parses their Abstract Syntax Tree (AST), strips out inner function logic, and emits structural signature files that reduce LLM token overhead by 80% to 90%.

## Token Reduction Metrics
- **Average Token Savings**: 80% – 90%
- **AST Pruning**: Replaces execution bodies with `...` while preserving type annotations, classes, and decorators.

## Machine Feeds
- [`v1/index.json`](public/v1/index.json) (Catalog & reduction stats)
- [`llms.txt`](public/llms.txt) (Token-efficient LLM digest)
- `skeletons.parquet` (Columnar database snapshot)

## Architecture
- **Parser**: Standard Python `ast` NodeTransformer
- **Database**: DuckDB + Parquet
- **Ledger**: Append-only Git-committed JSONL in `/data/history`
- **Edge CDN**: GitHub Pages (Fastly CDN)
