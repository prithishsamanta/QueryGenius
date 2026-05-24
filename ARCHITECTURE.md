# QueryGenius — Architecture & Progress Log

This document tracks two things:
1. **Target Architecture** — the full intended system, unchanged across checkpoints
2. **Checkpoint Log** — dated snapshots of what is actually wired up, updated after every checkpoint commit

> Rule: Before every `git commit -m "checkpoint: ..."`, append a new entry to the Checkpoint Log below.

---

## Target Architecture

The complete system once all phases are done.

```mermaid
flowchart TD
    Client([HTTP Client / curl]) -->|POST /api/analyze| API

    subgraph API Layer
        API[FastAPI\nsrc/api/main.py]
        Routes[Routes\nsrc/api/routes/analysis.py]
        API --> Routes
    end

    subgraph Task Queue - Phase 2
        Celery[Celery Worker]
        Redis[(Redis Broker)]
        Routes -->|enqueue task| Redis
        Redis --> Celery
    end

    subgraph Core Pipeline
        Embeddings[Embedding Generation\nsentence-transformers\nall-MiniLM-L6-v2]
        Similarity[pgvector Similarity Search\ntop-3 historical matches]
        LLM[AWS Bedrock\nClaude 3.5 Sonnet]
        Celery --> Embeddings
        Embeddings --> Similarity
        Similarity -->|RAG context| LLM
    end

    subgraph PostgreSQL Database
        QueriesTable[(queries table\n+ VECTOR 384 column)]
        OptTable[(optimizations table)]
        VecIndex[(IVFFlat Index\nvector_cosine_ops)]
        Embeddings -->|store query + embedding| QueriesTable
        QueriesTable --- VecIndex
        VecIndex --> Similarity
        LLM -->|store recommendations| OptTable
    end

    LLM -->|recommendations + similar queries| Routes
    Routes -->|AnalyzeResponse JSON| Client

    Client -->|GET /api/analysis/id| Routes
    Routes -->|lookup by analysis_id| OptTable
```

### Component Summary

| Component | Technology | Purpose |
|---|---|---|
| HTTP API | FastAPI | Receive queries, return analysis |
| Task Queue | Celery + Redis | Async processing (Phase 2) |
| Embeddings | sentence-transformers `all-MiniLM-L6-v2` | Convert SQL text to 384-dim vectors |
| Vector Search | pgvector (`<->` cosine distance) | Find historically similar queries |
| LLM Analysis | AWS Bedrock — Claude 3.5 Sonnet | Generate optimization recommendations |
| Database | PostgreSQL 15 + pgvector | Store everything in one place |

### Full Data Flow (Target)

```
POST /api/analyze
  → validate request (Pydantic)
  → enqueue Celery task
    → generate embedding (sentence-transformers)
    → store query + embedding in queries table
    → pgvector search: find top-3 similar historical queries
    → build RAG prompt (query + execution plan + similar history)
    → call Claude 3.5 Sonnet via AWS Bedrock
    → parse recommendations
    → store recommendations in optimizations table
  → return AnalyzeResponse (analysis_id, recommendations, similar_queries)

GET /api/analysis/{id}
  → lookup analysis_id in database
  → return stored AnalyzeResponse
```

---

## Checkpoint Log

Entries are newest-first. Each entry shows what is real, what is mocked, and the actual data flow at that point in time.

---

### Checkpoint: Day 1 MVP — 2026-05-24

**Commit:** `feat: Complete Day 1 MVP - Core QueryGenius functionality`

#### What is real vs mocked

| Component | Status | Notes |
|---|---|---|
| FastAPI app + CORS | Real | Running, auto-docs at `/docs` |
| `POST /api/analyze` route | Real | Fully wired end-to-end |
| `GET /api/analysis/{id}` route | Stub | Returns 404 — retrieval not implemented |
| Pydantic request/response models | Real | Validation, destructive query blocking |
| PostgreSQL connection | Real | SQLAlchemy engine + session DI |
| `queries` table + `optimizations` table | Real | Created via `scripts/setup_db.py` |
| pgvector extension + IVFFlat index | Real | Created at DB setup time |
| Embedding generation | Real | `all-MiniLM-L6-v2`, 384-dim, lazy-loaded |
| pgvector similarity search | Real | Cosine distance, threshold 0.7, top-3 |
| LLM / AI recommendations | **Mocked** | Pattern-matching rules, no Bedrock call |
| Celery async task queue | **Not started** | All processing is synchronous |
| Redis | **Not started** | No broker configured |
| AWS Bedrock integration | **Not started** | No credentials wired |
| Seed data | **Not started** | Database starts empty |
| `GET /api/analysis/{id}` retrieval | **Not started** | Returns 404 always |

#### Current Data Flow

```mermaid
flowchart TD
    Client([HTTP Client]) -->|POST /api/analyze\nquery_text + execution_time_ms| Route

    subgraph API Layer
        Route[analysis.py\nPOST /api/analyze]
        Pydantic[AnalyzeRequest\nValidation]
        Route --> Pydantic
    end

    subgraph AnalyzerService
        Embed[generate_embedding\nall-MiniLM-L6-v2\n384 floats]
        Store[Store Query\nqueries table]
        Search[find_similar_queries\npgvector cosine distance]
        Mock[mock_analyze_with_claude\npattern matching rules]
        StoreRec[Store Recommendations\noptimizations table]

        Pydantic --> Embed
        Embed --> Store
        Store --> Search
        Search -->|top-3 similar or empty list| Mock
        Mock --> StoreRec
    end

    subgraph PostgreSQL
        QueriesTable[(queries\n+ embedding VECTOR 384)]
        OptTable[(optimizations)]
        VecIndex[(IVFFlat Index)]
        Store --> QueriesTable
        QueriesTable --- VecIndex
        VecIndex --> Search
        StoreRec --> OptTable
    end

    StoreRec -->|AnalyzeResponse JSON\nanalysis_id + recommendations + similar_queries| Client

    style Mock fill:#f5a623,color:#000
    style Search fill:#7ed321,color:#000
    style Embed fill:#7ed321,color:#000
```

**Orange** = mocked component. **Green** = real and working.

#### What the mock LLM does

Since Bedrock is not connected, `src/services/llm.py` inspects the query text for patterns:

- `LIKE '%...` → recommends GIN trigram index
- No `WHERE` clause → recommends adding a filter
- `SELECT *` → recommends selecting specific columns
- `JOIN` present → recommends index on join columns
- Similar history found → references the historical match
- No pattern matched → suggests running `EXPLAIN ANALYZE`

#### How to run at this checkpoint

```bash
# Start the API
uvicorn src.api.main:app --reload --port 8000

# Submit a query for analysis
curl -X POST http://localhost:8000/api/analyze \
  -H "Content-Type: application/json" \
  -d '{"query_text": "SELECT * FROM users WHERE email LIKE '"'"'%@gmail.com'"'"'", "execution_time_ms": 1850}'

# View auto-generated API docs
open http://localhost:8000/docs
```

#### What comes next (Day 2 targets)

- Seed database with sample queries so similarity search returns real results
- Implement `GET /api/analysis/{id}` retrieval from the database
- Wire AWS Bedrock (or keep mock until credentials available)
