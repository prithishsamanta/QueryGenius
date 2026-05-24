# QueryGenius: AI-Powered Database Query Optimization Platform

## Project Context
<context>
An intelligent database performance monitoring system that uses AI to analyze slow PostgreSQL queries and provide optimization recommendations. Captures slow query logs, analyzes execution plans using Claude 3.5 Sonnet via AWS Bedrock, and learns from historical patterns using RAG with pgvector for semantic similarity search.

Current phase: MVP Development - Building core functionality for resume demonstration
Timeline: May 2026 (3-5 day build target)
Purpose: Backend/database portfolio project showcasing AI integration + database expertise
</context>

## Tech Stack
<stack>
<language>Python 3.9.6</language>
<backend>FastAPI</backend>
<database>PostgreSQL 15+ with pgvector extension</database>
<ai>AWS Bedrock (Claude 3.5 Sonnet), LangChain, sentence-transformers</ai>
<async>Celery (Phase 2), Redis</async>
<testing>pytest (Phase 2)</testing>
<orm>SQLAlchemy</orm>
<formatter>black</formatter>
<linter>ruff</linter>
</stack>

## Project Structure
<structure>
querygenius/
├── .claude/              # Claude Code configuration
│   ├── CLAUDE.md        # This file
│   ├── settings.json    # Project settings & boundaries
│   └── rules/
│       ├── backend.md   # FastAPI & API design standards
│       ├── database.md  # PostgreSQL & pgvector patterns
│       └── ai.md        # LLM integration best practices
├── src/
│   ├── api/
│   │   ├── __init__.py
│   │   ├── main.py      # FastAPI app entry point
│   │   └── routes/      # API endpoint handlers
│   ├── core/
│   │   ├── config.py    # Configuration management
│   │   ├── database.py  # DB connection & session
│   │   └── embeddings.py # Vector embedding generation
│   ├── models/
│   │   └── schemas.py   # SQLAlchemy models
│   ├── services/
│   │   ├── analyzer.py  # Claude/Bedrock integration
│   │   ├── query_store.py # Query storage & retrieval
│   │   └── similarity.py  # pgvector similarity search
│   └── utils/
│       └── parsers.py   # EXPLAIN plan parsing
├── tests/               # Unit tests (Phase 2)
├── scripts/
│   ├── setup_db.py      # PostgreSQL + pgvector setup
│   └── seed_data.py     # Sample queries for testing
├── requirements.txt
├── .env.example         # Environment variables template
└── README.md
</structure>

## Development Phases

### Phase 1: MVP (Days 1-3) - CURRENT FOCUS
<phase_1_mvp>
Goal: Working demo that proves the concept

Must Have:
- FastAPI with 2 core endpoints:
   - POST /api/analyze - Submit slow query for analysis
   - GET /api/analysis/{id} - Retrieve analysis results
- PostgreSQL database with pgvector extension
- Store queries with vector embeddings (384-dim)
- Basic similarity search (find top 3 similar queries)
- Mock AWS Bedrock responses (until credentials available)
- Simple CLI or curl commands for testing

Can Skip for Now:
- Celery async processing (use synchronous for MVP)
- Advanced error handling
- Web dashboard
- Comprehensive test suite
- Production deployment concerns
</phase_1_mvp>

### Phase 2: Production Features (Days 4-5)
<phase_2_production>
Add When MVP Works:
- Celery + Redis for async processing
- Real AWS Bedrock integration
- Exponential backoff + retry logic
- Comprehensive pytest suite
- Dead letter queue for failed tasks
- Performance metrics tracking
</phase_2_production>

## Coding Standards

### Core Principles
<principles>
1. **Type Safety First**: Use type hints for all function signatures
2. **Zero Placeholders**: No TODOs, no `pass # implement later`
3. **Separation of Concerns**: Keep FastAPI routes thin, business logic in services
4. **Database Best Practices**: Always use SQLAlchemy ORM, never raw SQL strings
5. **AI Integration Safety**: Mock LLM calls until Bedrock credentials available
6. **How To Write Comments**: None of the Comments should have useless Emojis in them
</principles>

### Code Style
<style>
- Format: Black (line length 100)
- Linting: Ruff with strict mode
- Docstrings: Google style for all public functions
- Imports: Absolute imports, grouped (stdlib → third-party → local)
- Naming: 
  - Functions/variables: snake_case
  - Classes: PascalCase
  - Constants: UPPER_SNAKE_CASE
  - Private methods: _leading_underscore
</style>

### Function Template
<template>
```python
from typing import Optional

def analyze_query(
    query_text: str,
    execution_plan: Optional[dict] = None
) -> dict:
    """
    Analyze a slow PostgreSQL query and generate optimization recommendations.
    
    Args:
        query_text: The SQL query to analyze
        execution_plan: Optional EXPLAIN ANALYZE output as JSON
        
    Returns:
        Dictionary containing:
        - analysis_id: Unique identifier
        - recommendations: List of optimization suggestions
        - similarity_score: Match score with historical queries
        
    Raises:
        ValueError: If query_text is empty or invalid
        DatabaseError: If storage operation fails
        
    Examples:
        >>> result = analyze_query("SELECT * FROM users WHERE email LIKE '%@gmail.com'")
        >>> result['recommendations'][0]['type']
        'add_index'
    """
    if not query_text or not query_text.strip():
        raise ValueError("Query text cannot be empty")
    
    # Implementation here
    return {
        "analysis_id": "abc123",
        "recommendations": [],
        "similarity_score": 0.85
    }
```
</template>

## Anti-Patterns - NEVER DO THESE
<anti_patterns>
- NEVER use placeholder comments:
   - `# TODO: implement AWS Bedrock call`
   - `# rest of code goes here`
   - `pass  # will add later`

- NEVER hardcode credentials:
   - No AWS keys in code
   - Use environment variables for all secrets
   - Check .env into .gitignore

- NEVER skip input validation:
   - Always validate API request bodies
   - Check for SQL injection patterns in query_text
   - Validate vector dimensions before storage

- NEVER mix database sessions:
   - One request = one session
   - Always close sessions in finally blocks
   - Use FastAPI dependency injection for sessions

- NEVER ignore errors silently:
   - Don't use bare `except:` clauses
   - Log all errors with context
   - Return meaningful error responses

- NEVER assume pgvector is installed:
   - Check for extension before vector operations
   - Provide clear setup instructions
   - Gracefully degrade if missing

- NEVER add unecessary emojis or expressions:
   - Emojis should never be used in code or comments
   - All comments written should explain what is done in the area well
</anti_patterns>

## Current Features & Status
<features>
- Completed
- [x] Project structure planned
- [x] Tech stack decided
- [x] CLAUDE.md created

- In Progress (Phase 1 MVP)
- [ ] PostgreSQL + pgvector setup script
- [ ] SQLAlchemy models for queries table
- [ ] FastAPI basic routes (POST /analyze, GET /analysis)
- [ ] Embedding generation with sentence-transformers
- [ ] Mock LLM analyzer (returns fake recommendations)
- [ ] Basic similarity search with pgvector

- Planned (Phase 2)
- [ ] Real AWS Bedrock integration
- [ ] Celery async processing
- [ ] Comprehensive test suite
- [ ] Error handling & retry logic
- [ ] Performance metrics dashboard
- [ ] GitHub Actions CI/CD
</features>

## Development Workflow
<workflow>
1. **Before coding**: Create git checkpoint
   ```bash
   git add -A && git commit -m "checkpoint: before [feature]"
   ```

2. **While coding**: 
   - Write function signature with complete type hints
   - Write docstring with examples
   - Implement function fully (no placeholders)
   - Test manually with curl or Python REPL
   - Verify database changes with psql

3. **After feature works**:
   ```bash
   git add -A && git commit -m "feat: [feature description]"
   ```

4. **Daily shutdown**:
   ```bash
   git add -A && git commit -m "checkpoint: end of day [date]"
   ```
</workflow>

## Database Schema
<database_schema>
```sql
-- Main queries table
CREATE TABLE queries (
    id SERIAL PRIMARY KEY,
    query_text TEXT NOT NULL,
    execution_time_ms FLOAT,
    execution_plan JSONB,
    database_name VARCHAR(100),
    created_at TIMESTAMP DEFAULT NOW(),
    embedding VECTOR(384)  -- pgvector type for embeddings
);

-- Index for vector similarity search
CREATE INDEX ON queries USING ivfflat (embedding vector_cosine_ops);

-- Optimizations table (Phase 2)
CREATE TABLE optimizations (
    id SERIAL PRIMARY KEY,
    query_id INTEGER REFERENCES queries(id),
    recommendation_type VARCHAR(50),
    recommendation_text TEXT,
    predicted_improvement_percent FLOAT,
    created_at TIMESTAMP DEFAULT NOW()
);
```
</database_schema>

## API Endpoints
<api_endpoints>
### POST /api/analyze
Submit a slow query for analysis

**Request:**
```json
{
  "query_text": "SELECT * FROM users WHERE email LIKE '%@gmail.com'",
  "execution_time_ms": 1850,
  "execution_plan": { /* optional EXPLAIN output */ }
}
```

**Response:**
```json
{
  "analysis_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "completed",
  "recommendations": [
    {
      "type": "add_index",
      "description": "Add index on users.email with text_pattern_ops",
      "sql": "CREATE INDEX idx_users_email_pattern ON users(email text_pattern_ops);",
      "predicted_improvement": "60%"
    }
  ],
  "similar_queries": [
    {
      "query_id": 42,
      "similarity_score": 0.87,
      "optimization_applied": "Added email index"
    }
  ]
}
```

### GET /api/analysis/{analysis_id}
Retrieve analysis results

**Response:** Same as POST response above
</api_endpoints>

## Environment Variables
<environment>
Required (create .env file):
```bash
# Database
DATABASE_URL=postgresql://user:pass@localhost:5432/querygenius
POSTGRES_USER=querygenius
POSTGRES_PASSWORD=your_secure_password
POSTGRES_DB=querygenius

# AWS Bedrock (Phase 2 - leave empty for now)
AWS_REGION=us-east-1
AWS_ACCESS_KEY_ID=
AWS_SECRET_ACCESS_KEY=

# Application
ENVIRONMENT=development
LOG_LEVEL=INFO
API_HOST=0.0.0.0
API_PORT=8000

# Vector Embeddings
EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2
EMBEDDING_DIMENSION=384
```
</environment>

## Testing Requirements (Phase 2)
<testing_requirements>
For EVERY service function, write tests for:
1. **Happy path**: Normal expected usage
2. **Edge cases**: Empty queries, huge execution plans, missing fields
3. **Error cases**: Invalid inputs, database failures, LLM timeouts

Example test structure:
```python
def test_analyze_query_with_valid_input():
    result = analyze_query("SELECT * FROM users")
    assert "analysis_id" in result
    assert len(result["recommendations"]) > 0

def test_analyze_query_with_empty_text_raises_error():
    with pytest.raises(ValueError, match="Query text cannot be empty"):
        analyze_query("")
```
</testing_requirements>

## Commands Reference
<commands>
# Setup database (first time)
python scripts/setup_db.py

# Run FastAPI server
uvicorn src.api.main:app --reload --port 8000

# Test API endpoints
curl -X POST http://localhost:8000/api/analyze \
  -H "Content-Type: application/json" \
  -d '{"query_text": "SELECT * FROM users", "execution_time_ms": 1200}'

# Check PostgreSQL
psql -U querygenius -d querygenius -c "SELECT COUNT(*) FROM queries;"

# Format code
black src/ --line-length 100

# Lint code
ruff check src/

# Generate embeddings test
python -c "from src.core.embeddings import generate_embedding; print(generate_embedding('test query')[:5])"
</commands>

## Context for AI
<ai_instructions>
When generating code for QueryGenius:

1. **Start with <thinking> tags** to plan approach
2. **Include complete type hints** for all parameters and returns
3. **Write full implementations** - no placeholders or TODOs
4. **Mock external dependencies** (AWS Bedrock) until credentials available
5. **Follow the exact FastAPI patterns** shown in rules/backend.md
6. **Use SQLAlchemy ORM** exclusively for database operations
7. **Generate realistic sample data** for testing

Response format:
<thinking>
User wants [feature]. Plan:
- Step 1: [what to do]
- Step 2: [what to do]
- Dependencies: [what's needed]
- Edge cases to handle: [list]
</thinking>

<code>
[complete, production-ready implementation]
</code>

<usage>
[how to test/run the code]
</usage>
</ai_instructions>

## Important Metrics to Achieve
<metrics>
For resume demonstration, the project must show:
- 10,000+ query patterns stored (use seed script)
- 40% median query improvement (mock analysis results)
- 99.5% completion rate (track in Phase 2)
- pgvector similarity search working
- RAG pipeline retrieving historical patterns
- AWS Bedrock integration (mock for MVP, real in Phase 2)

These don't need to be "real production" numbers - but the system must be structured to DEMONSTRATE these capabilities.
</metrics>

## Notes for Resume/Interview
<interview_prep>
Key talking points about this project:

**Why pgvector?**
"Keeping everything in PostgreSQL maintains transactional consistency and reduces operational complexity. For 10,000 query patterns, pgvector performs well without needing a separate vector database."

**Why Claude 3.5 Sonnet?**
"Claude excels at code analysis and structured reasoning. Its large context window can handle complex execution plans with multiple table schemas."

**How does RAG help?**
"Instead of asking Claude to optimize every query from scratch, we first search for similar historical queries. If found, we include those proven solutions in the prompt, making recommendations more consistent."

**How do you prevent hallucinations?**
"The RAG pipeline grounds recommendations in historical data. We also validate that suggested indexes reference actual columns in the schema before returning them."

**What's the completion rate?**
"99.5% means that out of 1000 analysis requests, 995 complete successfully. We achieve this through exponential backoff for API rate limits and dead letter queues for truly failed tasks."
</interview_prep>

## Important Notes
<notes>
- This is a PORTFOLIO project - prioritize demonstrable features over production perfection
- Every feature must be complete and manually testable before moving on
- Mock AWS Bedrock until credentials available - don't block progress
- Document architectural decisions for interview discussions
- Focus on backend/database depth, not UI polish
- The goal is proving you understand: AI integration, database optimization, RAG patterns, async processing
</notes>

## Project Timeline (Realistic)
<timeline>
**Day 1 (Setup & Foundation)**
- PostgreSQL + pgvector installation
- Database schema creation
- SQLAlchemy models
- Basic FastAPI skeleton

**Day 2 (Core Features)**
- Embedding generation with sentence-transformers
- Mock LLM analyzer
- POST /analyze endpoint
- pgvector similarity search

**Day 3 (Integration & Testing)**
- Seed database with sample queries
- GET /analysis endpoint
- Manual testing with curl
- README with demo instructions

**Day 4-5 (Polish - If Time)**
- Replace mock LLM with real Bedrock
- Add Celery for async
- Write pytest suite
</timeline>
