# QueryGenius

An AI-powered PostgreSQL query optimization platform. Captures slow queries, analyzes them using Claude 3.5 Sonnet via AWS Bedrock, and learns from historical patterns using RAG with pgvector for semantic similarity search.

Built as a backend/database portfolio project demonstrating AI integration, database optimization, and RAG pipeline design.

---

## What it does

You submit a slow SQL query to QueryGenius via HTTP. It:

1. Converts the query into a 384-dimensional vector embedding
2. Searches 10,000+ historical query patterns for semantically similar ones
3. Builds a RAG prompt — query text + schema context + similar historical queries
4. Sends the prompt to Claude 3.5 Sonnet (mocked in MVP, real in Phase 2)
5. Returns specific optimization recommendations with predicted improvement percentages
6. Stores everything so you can retrieve the analysis later by ID

---

## Tech stack

| Layer | Technology |
|---|---|
| API | FastAPI |
| Database | PostgreSQL 15 + pgvector |
| Embeddings | sentence-transformers `all-MiniLM-L6-v2` (384-dim) |
| Vector search | pgvector IVFFlat index, cosine similarity |
| LLM | AWS Bedrock — Claude 3.5 Sonnet (mocked for MVP) |
| ORM | SQLAlchemy |
| Language | Python 3.9+ |

---

## Project structure

```
querygenius/
├── src/
│   ├── api/
│   │   ├── main.py              # FastAPI app entry point
│   │   ├── models.py            # Pydantic request/response models
│   │   └── routes/
│   │       └── analysis.py      # POST /api/analyze, GET /api/analysis/{id}
│   ├── core/
│   │   ├── database.py          # SQLAlchemy engine + session dependency
│   │   └── embeddings.py        # sentence-transformers embedding generation
│   ├── models/
│   │   └── schemas.py           # SQLAlchemy ORM models (queries, optimizations)
│   ├── services/
│   │   ├── analyzer.py          # Orchestrates the full analysis pipeline
│   │   ├── llm.py               # Mock LLM + prompt builder (swap for Bedrock in Phase 2)
│   │   └── similarity.py        # pgvector cosine similarity search
│   └── utils/
│       └── parsers.py           # pg_catalog schema introspection + prompt formatting
├── scripts/
│   ├── setup_db.py              # One-time DB + pgvector + index setup
│   └── seed_data.py             # Insert 10,000 sample slow queries
├── ARCHITECTURE.md              # Target architecture + per-checkpoint progress log
├── requirements.txt
└── .env.example
```

---

## Setup

### Prerequisites

- Python 3.9+
- PostgreSQL 15+ with pgvector extension
- pip

### 1. Clone and install dependencies

```bash
git clone https://github.com/prithishsamanta/QueryGenius.git
cd QueryGenius
pip3 install -r requirements.txt
```

### 2. Configure environment

```bash
cp .env.example .env
```

Edit `.env` and set your database credentials:

```bash
DATABASE_URL=postgresql://querygenius:yourpassword@localhost:5432/querygenius
POSTGRES_USER=querygenius
POSTGRES_PASSWORD=yourpassword
POSTGRES_DB=querygenius
```

### 3. Create the database

```bash
psql -U postgres -c "CREATE USER querygenius WITH PASSWORD 'yourpassword';"
psql -U postgres -c "CREATE DATABASE querygenius OWNER querygenius;"
```

### 4. Set up schema and pgvector

```bash
python3 scripts/setup_db.py
```

This creates the `queries` and `optimizations` tables, the pgvector extension, and the IVFFlat similarity index.

### 5. Seed the database

```bash
python3 scripts/seed_data.py
```

Inserts 10,000 sample slow queries across 15 anti-patterns, batch-encodes their embeddings, and rebuilds the IVFFlat index on real data so similarity search returns meaningful results. Takes about 30–60 seconds.

### 6. Start the API

```bash
python3 -m uvicorn src.api.main:app --reload --port 8000
```

API is now running at `http://localhost:8000`. Interactive docs at `http://localhost:8000/docs`.

---

## Usage

### Analyze a slow query

```bash
curl -X POST http://localhost:8000/api/analyze \
  -H "Content-Type: application/json" \
  -d '{
    "query_text": "SELECT * FROM bookings WHERE status LIKE '\''%confirmed%'\''",
    "execution_time_ms": 2300
  }'
```

Response:

```json
{
  "analysis_id": "7104c90d-7ff5-470b-8775-64c8555f9a5e",
  "status": "completed",
  "recommendations": [
    {
      "type": "add_index",
      "description": "Add GIN trigram index for LIKE pattern matching",
      "sql": "CREATE INDEX idx_col_trgm ON <table> USING gin(<column> gin_trgm_ops);",
      "predicted_improvement": "65%"
    },
    {
      "type": "rewrite",
      "description": "Replace SELECT * with specific column names to reduce I/O",
      "sql": null,
      "predicted_improvement": "25%"
    }
  ],
  "similar_queries": [
    {
      "query_id": 4821,
      "similarity_score": 0.97,
      "optimization_applied": null
    }
  ],
  "created_at": "2026-05-25T22:22:25.484435"
}
```

### Analyze with schema context (precise recommendations)

Pass schema context and recommendations use exact column names, list actual columns for SELECT * rewrites, and skip indexes that already exist.

```bash
curl -X POST http://localhost:8000/api/analyze \
  -H "Content-Type: application/json" \
  -d '{
    "query_text": "SELECT * FROM bookings WHERE status LIKE '\''%confirmed%'\''",
    "execution_time_ms": 2300,
    "schema_context": [
      {
        "table": "bookings",
        "columns": [
          {"name": "id", "type": "integer", "nullable": false},
          {"name": "user_id", "type": "integer", "nullable": false},
          {"name": "seat_id", "type": "integer", "nullable": false},
          {"name": "status", "type": "character varying", "nullable": false},
          {"name": "created_at", "type": "timestamp without time zone", "nullable": false}
        ],
        "indexes": [
          {"name": "bookings_pkey", "columns": ["id"], "unique": true}
        ]
      }
    ]
  }'
```

Response with schema — notice exact column names:

```json
{
  "analysis_id": "a1b2c3d4-...",
  "recommendations": [
    {
      "type": "add_index",
      "description": "Add GIN trigram index for LIKE pattern matching on bookings.status",
      "sql": "CREATE INDEX idx_bookings_status_trgm ON bookings USING gin(status gin_trgm_ops);",
      "predicted_improvement": "65%"
    },
    {
      "type": "rewrite",
      "description": "Replace SELECT * with specific column names to reduce I/O",
      "sql": "SELECT id, user_id, seat_id, status, created_at FROM bookings ...",
      "predicted_improvement": "25%"
    }
  ]
}
```

### Retrieve a previous analysis

```bash
curl http://localhost:8000/api/analysis/7104c90d-7ff5-470b-8775-64c8555f9a5e
```

### Health check

```bash
curl http://localhost:8000/health
```

---

## How the RAG pipeline works

```
Incoming slow query
        ↓
Generate 384-dim embedding (sentence-transformers)
        ↓
Store query + embedding in PostgreSQL
        ↓
pgvector IVFFlat search — find top-3 semantically similar historical queries
        ↓
Build prompt: query + schema context + similar history
        ↓
Claude 3.5 Sonnet (mock in MVP, Bedrock in Phase 2)
        ↓
Store + return recommendations
```

The IVFFlat index groups 10,000 query embeddings into 100 clusters. At search time, only the nearest clusters are scanned — not all 10,000 rows. This makes similarity search fast even as the query history grows.

---

## Schema introspection

The `fetch_schema_from_db()` utility in `src/utils/parsers.py` introspects any PostgreSQL database via `information_schema` and `pg_catalog` to pull table definitions, column types, and existing indexes. In a CI/CD pipeline, this runs against the test database and the schema is passed to QueryGenius as part of the analysis request — the schema never leaves your private network unencrypted.

```python
from src.utils.parsers import fetch_schema_from_db

schema = fetch_schema_from_db(db, table_names=["bookings", "seats"])
# Returns: [{"table": "bookings", "columns": [...], "indexes": [...]}, ...]
```

---

## Migrating from mock to real AWS Bedrock

When AWS credentials are available, swap one import in `src/services/analyzer.py`:

```python
# Phase 1 (MVP) — current
from src.services.llm import mock_analyze_with_claude as analyze_with_claude

# Phase 2 — swap this in
from src.services.llm import real_analyze_with_claude as analyze_with_claude
```

And set credentials in `.env`:

```bash
AWS_REGION=us-east-1
AWS_ACCESS_KEY_ID=your_key
AWS_SECRET_ACCESS_KEY=your_secret
```

---

## Architecture

See [ARCHITECTURE.md](ARCHITECTURE.md) for:
- Full target architecture diagram (FastAPI → Celery → Bedrock → pgvector)
- Deployment and security model (private subnet isolation, AWS PrivateLink)
- Per-checkpoint progress log showing what is real vs mocked at each stage

---

## Interview talking points

**Why pgvector instead of a dedicated vector database?**
Keeping everything in PostgreSQL maintains transactional consistency and reduces operational complexity. For 10,000+ query patterns, pgvector performs well without a separate vector database service.

**Why Claude 3.5 Sonnet?**
Claude excels at code analysis and structured reasoning. Its large context window handles complex execution plans with multiple table schemas in a single prompt.

**How does RAG improve recommendations?**
Instead of asking Claude to optimize every query from scratch, we first search for similar historical queries. If found, those proven solutions are included in the prompt, making recommendations more consistent and grounded in real outcomes.

**How do you prevent hallucinations in index recommendations?**
Schema context grounds the recommendations — Claude sees actual column names, types, and existing indexes. The mock LLM also deduplicates against existing indexes so it never suggests something already in place.

**What is the completion rate?**
Target is 99.5% — achieved in Phase 2 through exponential backoff for Bedrock rate limits and dead letter queues for truly failed tasks.

**How does this integrate with CI/CD?**
A GitHub Actions job runs the test suite against a test database, collects slow queries from `pg_stat_statements`, and POSTs each one to QueryGenius. Recommendations are posted as PR comments, catching query regressions before they hit production.
