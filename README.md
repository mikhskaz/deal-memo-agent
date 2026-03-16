# Deal Memo Agent

An AI-powered investment memo drafting system. Analysts upload a CIM (Confidential Information Memorandum) or financial documents; the agent extracts structured deal data, enriches it with live web intelligence, and produces a first-pass investment memo in Sagard's standard format.

---

## Table of Contents

1. [Project Structure](#project-structure)
2. [Tech Stack](#tech-stack)
3. [Environment Variables](#environment-variables)
4. [Installation & Setup](#installation--setup)
5. [Architecture Overview](#architecture-overview)
6. [Pipeline — Step by Step](#pipeline--step-by-step)
7. [Prompt Design](#prompt-design)
8. [API Reference](#api-reference)
9. [Frontend](#frontend)
10. [Data Models](#data-models)
11. [File Handling](#file-handling)
12. [Web Search Integration](#web-search-integration)
13. [Output Generation](#output-generation)
14. [Error Handling & Retries](#error-handling--retries)
15. [Logging & Observability](#logging--observability)
16. [Security](#security)
17. [Testing](#testing)
18. [Known Limitations](#known-limitations)
19. [Extending the System](#extending-the-system)

---

## Project Structure
```
deal-memo-agent/
├── app.py                  # FastAPI entrypoint
├── requirements.txt
├── .env.example
├── README.md
│
├── api/
│   ├── routes/
│   │   ├── upload.py       # POST /upload — accepts PDF, returns job_id
│   │   ├── status.py       # GET /status/{job_id} — SSE stream of pipeline progress
│   │   └── memo.py         # GET /memo/{job_id} — returns final memo JSON + markdown
│   └── middleware.py       # CORS, request logging, error formatting
│
├── pipeline/
│   ├── orchestrator.py     # Runs stages in order, manages state
│   ├── ingest.py           # PDF parsing, chunking
│   ├── extract.py          # LLM extraction — structured fields from document
│   ├── enrich.py           # Web search — comps, news, sector data
│   ├── draft.py            # LLM synthesis — writes the memo sections
│   └── export.py           # Renders memo to markdown + DOCX
│
├── models/
│   ├── deal.py             # Pydantic: DealExtraction, DealEnrichment, Memo
│   └── job.py              # Pydantic: Job, JobStatus, PipelineStage
│
├── prompts/
│   ├── extraction.py       # Prompt templates for field extraction
│   ├── enrichment.py       # Prompt templates for search query generation
│   └── drafting.py         # Prompt templates for memo section writing
│
├── utils/
│   ├── pdf.py              # PDF-to-text with table detection
│   ├── chunker.py          # Token-aware chunking
│   ├── search.py           # Tavily/Brave search client wrapper
│   └── docx_renderer.py    # python-docx memo template filler
│
├── storage/
│   └── job_store.py        # In-memory job store (dict); swap for Redis in prod
│
└── frontend/
    ├── index.html
    ├── app.js              # Vanilla JS — upload, SSE progress, memo display
    └── styles.css
```

---

## Tech Stack

| Layer | Choice | Reason |
|---|---|---|
| Backend | Python 3.11, FastAPI | Async, easy SSE, fast iteration |
| LLM | Anthropic Claude (`claude-sonnet-4-5`) | Best instruction-following for structured extraction |
| PDF parsing | `pdfplumber` + `PyMuPDF` | pdfplumber for tables, PyMuPDF for text layout |
| Chunking | `tiktoken` (cl100k_base) | Token-accurate splits for context window management |
| Web search | Tavily API | Returns clean, structured results; built for LLM use |
| Output | `python-docx` + markdown | DOCX for analysts, markdown for display |
| Frontend | Vanilla JS + HTML/CSS | No build step; ships in one folder |
| Job state | In-memory dict (dev) | Simple; documented swap path to Redis |

---

## Environment Variables
```bash
# .env.example

ANTHROPIC_API_KEY=sk-ant-...
TAVILY_API_KEY=tvly-...

# Model config
EXTRACTION_MODEL=claude-sonnet-4-5
DRAFTING_MODEL=claude-sonnet-4-5
MAX_TOKENS_EXTRACTION=4096
MAX_TOKENS_DRAFT=8192

# Pipeline config
CHUNK_SIZE_TOKENS=6000
CHUNK_OVERLAP_TOKENS=500
MAX_SEARCH_QUERIES=6
MAX_SEARCH_RESULTS_PER_QUERY=3

# App
PORT=8000
CORS_ORIGINS=http://localhost:3000
LOG_LEVEL=INFO
```

---

## Installation & Setup
```bash
git clone https://github.com/yourname/deal-memo-agent
cd deal-memo-agent

python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

pip install -r requirements.txt

cp .env.example .env
# Fill in ANTHROPIC_API_KEY and TAVILY_API_KEY

uvicorn app:app --reload --port 8000
# Frontend: open frontend/index.html in browser
```

### requirements.txt
```
fastapi==0.111.0
uvicorn[standard]==0.29.0
python-multipart==0.0.9
anthropic==0.28.0
pdfplumber==0.11.0
PyMuPDF==1.24.3
tiktoken==0.7.0
tavily-python==0.3.3
python-docx==1.1.2
pydantic==2.7.1
pydantic-settings==2.3.0
python-dotenv==1.0.1
httpx==0.27.0
sse-starlette==2.1.0
```

---

## Architecture Overview
```
User (browser)
    │
    ▼
FastAPI (app.py)
    │
    ├── POST /upload ──────────────► ingest.py
    │                                   │ pdfplumber + PyMuPDF
    │                                   │ chunker.py (tiktoken)
    │                                   ▼
    ├── SSE /status/{id} ◄──── orchestrator.py
    │                               │
    │                         ┌─────┴──────┐
    │                         ▼            ▼
    │                    extract.py    enrich.py
    │                    (Claude)      (Tavily → Claude)
    │                         │            │
    │                         └─────┬──────┘
    │                               ▼
    │                          draft.py
    │                          (Claude)
    │                               │
    └── GET /memo/{id} ◄────── export.py
                               (markdown + DOCX)
```

The pipeline runs as a background asyncio task. Progress is streamed to the frontend via Server-Sent Events (SSE). The frontend polls `/status/{job_id}` and updates the UI at each stage completion.

---

## Pipeline — Step by Step

### Stage 1: Ingest (`pipeline/ingest.py`)

**Goal**: Convert PDF bytes → list of text chunks with metadata.
```python
def ingest(pdf_bytes: bytes) -> list[Chunk]:
    # 1. Try pdfplumber first for table-rich pages
    # 2. Fall back to PyMuPDF for layout-heavy pages
    # 3. Concatenate all page text into one string
    # 4. Split into chunks using tiktoken
    #    - CHUNK_SIZE_TOKENS = 6000
    #    - CHUNK_OVERLAP_TOKENS = 500
    #    - Preserve paragraph boundaries where possible
    # 5. Tag each chunk: {index, page_range, token_count, text}
    return chunks
```

**Chunk model:**
```python
class Chunk(BaseModel):
    index: int
    page_range: tuple[int, int]
    token_count: int
    text: str
```

Table detection: if `pdfplumber` finds a table on a page, extract it as a markdown-formatted string and prepend it to that page's text before chunking.

---

### Stage 2: Extract (`pipeline/extract.py`)

**Goal**: Run the extraction prompt across all chunks and merge results into a single `DealExtraction` object.

Strategy: **map-reduce**
- Map: send each chunk to Claude with the extraction prompt; get partial JSON back
- Reduce: send all partial JSONs to Claude with the merge prompt; get one unified JSON

This handles CIMs that are 60–200 pages without blowing the context window.
```python
async def extract(chunks: list[Chunk]) -> DealExtraction:
    partials = await asyncio.gather(*[
        extract_chunk(chunk) for chunk in chunks
    ])
    merged = await merge_extractions(partials)
    return merged
```

Each `extract_chunk` call uses `MAX_TOKENS_EXTRACTION=4096`. The merge call uses up to 8192 tokens.

Claude is called with `response_format` via a tool call that forces structured JSON output — do not parse free-text. See [Prompt Design](#prompt-design).

---

### Stage 3: Enrich (`pipeline/enrich.py`)

**Goal**: Use the extracted deal data to generate targeted web searches, then summarize the results into an `DealEnrichment` object.
```python
async def enrich(extraction: DealExtraction) -> DealEnrichment:
    # 1. Generate search queries from extraction
    queries = await generate_search_queries(extraction)
    # Returns up to MAX_SEARCH_QUERIES queries

    # 2. Execute all queries in parallel via Tavily
    results = await asyncio.gather(*[
        search(q) for q in queries
    ])

    # 3. Summarize results per category
    enrichment = await summarize_search_results(extraction, results)
    return enrichment
```

**Search categories generated:**
- Comparable company multiples (revenue, EBITDA) for the sector
- Recent M&A transactions in the sector (last 24 months)
- News on the target company (last 12 months)
- Key competitors and market share data
- Regulatory or macro tailwinds/headwinds for the sector
- Management team background (founder, CEO)

Tavily is called with `search_depth="advanced"` and `max_results=MAX_SEARCH_RESULTS_PER_QUERY`. Each result includes URL, title, content snippet.

---

### Stage 4: Draft (`pipeline/draft.py`)

**Goal**: Synthesize extraction + enrichment into a full memo, section by section.

Each memo section is drafted in a separate Claude call. This produces higher quality than drafting the whole memo in one call, and allows per-section retries.
```python
SECTIONS = [
    "executive_summary",
    "business_description",
    "market_opportunity",
    "financial_overview",
    "key_risks",
    "management_team",
    "diligence_questions",
    "recommended_next_step",
]

async def draft(extraction: DealExtraction, enrichment: DealEnrichment) -> Memo:
    sections = await asyncio.gather(*[
        draft_section(section, extraction, enrichment)
        for section in SECTIONS
    ])
    return Memo(sections=dict(zip(SECTIONS, sections)))
```

Each section prompt includes: the full extraction JSON, the relevant enrichment data for that section, explicit length and tone instructions, and a grounding instruction ("only use information present in the documents or search results — do not fabricate figures").

---

### Stage 5: Export (`pipeline/export.py`)

**Goal**: Render the memo to markdown (for UI display) and DOCX (for download).

Markdown: concatenate section headers and bodies with standard formatting.

DOCX: use `python-docx` with a pre-built template (`memo_template.docx` in `/assets`). Fill in each section using named bookmarks in the template. Include a header with "AI-ASSISTED DRAFT — NOT FOR DISTRIBUTION" and the generation timestamp.

---

## Prompt Design

All prompts live in `prompts/`. They are Python functions that return a string, taking structured data as arguments. No f-string spaghetti in the pipeline code.

### Extraction prompt (per chunk)
```python
# prompts/extraction.py

EXTRACTION_SYSTEM = """
You are a senior investment analyst assistant. You will be given a section of a
Confidential Information Memorandum (CIM). Extract all available information
into the JSON schema provided via the tool. 

Rules:
- Only extract information explicitly stated in the text.
- If a field is not present in this section, return null — do not infer or estimate.
- For financial figures, always include the unit (e.g. "$12.4M", "£3.2B").
- For dates, use ISO 8601 format (YYYY or YYYY-MM).
- Be exhaustive — capture every number, name, and metric you find.
"""

def extraction_user_prompt(chunk: Chunk) -> str:
    return f"""
Extract deal information from the following section of a CIM.
This is chunk {chunk.index} covering pages {chunk.page_range[0]}–{chunk.page_range[1]}.

<document_section>
{chunk.text}
</document_section>

Use the extract_deal_data tool to return your findings.
"""
```

Extraction is done via a **tool call** (function calling), not free-text parsing:
```python
EXTRACTION_TOOL = {
    "name": "extract_deal_data",
    "description": "Extract structured deal information from a CIM section.",
    "input_schema": {
        "type": "object",
        "properties": {
            "company_name": {"type": ["string", "null"]},
            "company_description": {"type": ["string", "null"]},
            "founded_year": {"type": ["integer", "null"]},
            "headquarters": {"type": ["string", "null"]},
            "sector": {"type": ["string", "null"]},
            "sub_sector": {"type": ["string", "null"]},
            "business_model": {"type": ["string", "null"]},
            "revenue_current": {"type": ["string", "null"]},
            "revenue_prior_year": {"type": ["string", "null"]},
            "revenue_growth_rate": {"type": ["string", "null"]},
            "ebitda_current": {"type": ["string", "null"]},
            "ebitda_margin": {"type": ["string", "null"]},
            "arr": {"type": ["string", "null"]},
            "gross_margin": {"type": ["string", "null"]},
            "customer_count": {"type": ["integer", "null"]},
            "nrr": {"type": ["string", "null"]},
            "asking_price_or_valuation": {"type": ["string", "null"]},
            "deal_type": {
                "type": ["string", "null"],
                "enum": ["buyout", "growth_equity", "venture", "credit", "real_estate", null]
            },
            "management_team": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "title": {"type": "string"},
                        "background": {"type": ["string", "null"]}
                    }
                }
            },
            "key_customers": {"type": "array", "items": {"type": "string"}},
            "key_risks_mentioned": {"type": "array", "items": {"type": "string"}},
            "competitive_advantages": {"type": "array", "items": {"type": "string"}},
            "total_addressable_market": {"type": ["string", "null"]},
            "geographic_markets": {"type": "array", "items": {"type": "string"}},
            "employee_count": {"type": ["integer", "null"]},
            "other_notable_facts": {"type": "array", "items": {"type": "string"}}
        }
    }
}
```

### Search query generation prompt
```python
# prompts/enrichment.py

def query_generation_prompt(extraction: DealExtraction) -> str:
    return f"""
You are a buy-side investment analyst preparing to research a deal.
Based on the following deal summary, generate up to {MAX_SEARCH_QUERIES} targeted
web search queries to gather the intelligence needed for an investment memo.

Deal summary:
{extraction.model_dump_json(indent=2)}

Generate queries for:
1. Comparable public company EV/Revenue and EV/EBITDA multiples in this sector
2. Recent private M&A transactions in this sector (last 24 months)
3. Recent news about this specific company
4. Key competitors and market share
5. Sector macro trends, tailwinds, and regulatory context
6. Background on the CEO / founder if named

Return a JSON array of query strings. No explanation, just the array.
"""
```

### Memo section drafting prompt
```python
# prompts/drafting.py

DRAFTING_SYSTEM = """
You are a senior investment analyst at Sagard, a multi-strategy alternative
asset management firm. You write clear, rigorous, concise investment memos.

Style:
- Institutional tone: direct, analytical, no marketing language
- Numbers always cited with source (CIM or web search result)
- Flag uncertainty explicitly: "per management", "CIM states", "based on public comps"
- Do not fabricate figures, names, or transactions
- Bullet points for risks and diligence questions; prose for summaries
"""

def section_prompt(section: str, extraction: DealExtraction,
                   enrichment: DealEnrichment) -> str:
    # Each section has its own focused sub-prompt defined below
    ...
```

Define a focused sub-prompt for each of the 8 sections. For example, `financial_overview` receives: extraction financials, comp multiples from enrichment, and instructions to compute an implied valuation range if asking price and comps are both available.

---

## API Reference

### `POST /upload`

Upload a CIM PDF. Returns a job ID.

**Request:** `multipart/form-data`
- `file`: PDF file (max 50MB)

**Response:**
```json
{
  "job_id": "uuid4",
  "status": "queued"
}
```

**Errors:**
- `400` — not a PDF, or file too large
- `422` — missing file field

---

### `GET /status/{job_id}`

Server-Sent Events stream. Each event is a JSON object:
```
event: pipeline_update
data: {"stage": "extract", "status": "running", "progress": 0.4, "message": "Extracting fields from chunk 3/8..."}

event: pipeline_update
data: {"stage": "extract", "status": "complete", "progress": 1.0}

event: pipeline_update
data: {"stage": "enrich", "status": "running", ...}

event: complete
data: {"job_id": "uuid4", "memo_ready": true}

event: error
data: {"stage": "draft", "message": "Claude API timeout — retrying..."}
```

Stages in order: `ingest → extract → enrich → draft → export`

---

### `GET /memo/{job_id}`

Returns the completed memo.

**Response:**
```json
{
  "job_id": "uuid4",
  "company_name": "Acme Corp",
  "generated_at": "2025-10-01T14:32:00Z",
  "memo": {
    "executive_summary": "## Executive Summary\n\n...",
    "business_description": "...",
    "market_opportunity": "...",
    "financial_overview": "...",
    "key_risks": "...",
    "management_team": "...",
    "diligence_questions": "...",
    "recommended_next_step": "..."
  },
  "extraction": { ...DealExtraction JSON... },
  "sources": [
    {"query": "SaaS comps EV/Revenue 2025", "url": "...", "title": "..."}
  ],
  "docx_download_url": "/download/uuid4.docx"
}
```

---

### `GET /download/{job_id}.docx`

Returns the DOCX file as `application/vnd.openxmlformats-officedocument.wordprocessingml.document`.

---

## Data Models
```python
# models/deal.py

class DealExtraction(BaseModel):
    company_name: str | None
    company_description: str | None
    founded_year: int | None
    headquarters: str | None
    sector: str | None
    sub_sector: str | None
    business_model: str | None
    revenue_current: str | None
    revenue_prior_year: str | None
    revenue_growth_rate: str | None
    ebitda_current: str | None
    ebitda_margin: str | None
    arr: str | None
    gross_margin: str | None
    customer_count: int | None
    nrr: str | None
    asking_price_or_valuation: str | None
    deal_type: Literal["buyout","growth_equity","venture","credit","real_estate"] | None
    management_team: list[ManagementMember]
    key_customers: list[str]
    key_risks_mentioned: list[str]
    competitive_advantages: list[str]
    total_addressable_market: str | None
    geographic_markets: list[str]
    employee_count: int | None
    other_notable_facts: list[str]

class ManagementMember(BaseModel):
    name: str
    title: str
    background: str | None

class SearchResult(BaseModel):
    query: str
    url: str
    title: str
    content: str

class DealEnrichment(BaseModel):
    comparable_multiples: str | None       # Summarized prose from search
    recent_transactions: str | None
    company_news: str | None
    competitive_landscape: str | None
    sector_macro: str | None
    management_backgrounds: str | None
    sources: list[SearchResult]

class MemoSection(BaseModel):
    section_id: str
    content: str                           # Markdown string
    word_count: int

class Memo(BaseModel):
    sections: dict[str, MemoSection]
    generated_at: datetime
    model_used: str
    total_tokens_used: int

class Job(BaseModel):
    job_id: str
    status: Literal["queued","running","complete","failed"]
    current_stage: str | None
    extraction: DealExtraction | None
    enrichment: DealEnrichment | None
    memo: Memo | None
    error: str | None
    created_at: datetime
    completed_at: datetime | None
```

---

## File Handling

- Files are written to a temp directory (`/tmp/deal-memo-agent/{job_id}/`) on upload
- `input.pdf` — original upload
- `extracted.json` — DealExtraction output
- `enriched.json` — DealEnrichment output
- `memo.json` — full Memo object
- `memo.md` — rendered markdown
- `memo.docx` — rendered DOCX
- Temp files are deleted 1 hour after job completion via a background cleanup task
- **No files are persisted beyond the session.** No S3, no database. This is intentional for security — CIM documents are confidential deal materials.

---

## Web Search Integration

Tavily client wrapper lives in `utils/search.py`:
```python
from tavily import TavilyClient

client = TavilyClient(api_key=settings.TAVILY_API_KEY)

async def search(query: str) -> list[SearchResult]:
    response = client.search(
        query=query,
        search_depth="advanced",
        max_results=settings.MAX_SEARCH_RESULTS_PER_QUERY,
        include_answer=False,
        include_raw_content=False,
    )
    return [
        SearchResult(
            query=query,
            url=r["url"],
            title=r["title"],
            content=r["content"],
        )
        for r in response["results"]
    ]
```

All search results are included in the memo's `sources` array so analysts can verify every cited figure.

---

## Output Generation

### Markdown

Each section is already markdown from the drafting step. The export step:
1. Prepends a header block: company name, generation timestamp, AI-draft disclaimer
2. Concatenates sections in standard order
3. Appends a sources appendix with all URLs used

### DOCX

Use `python-docx`. The template (`assets/memo_template.docx`) contains named bookmarks for each section. The renderer:
1. Opens the template
2. Finds each bookmark by name
3. Inserts the section content as formatted paragraphs
4. Sets document properties: author = "Deal Memo Agent (AI Draft)", subject = company name
5. Saves to `/tmp/deal-memo-agent/{job_id}/memo.docx`

Include a red header on page 1: **"AI-ASSISTED DRAFT — FOR INTERNAL REVIEW ONLY — NOT FOR DISTRIBUTION"**

---

## Error Handling & Retries

All Claude API calls are wrapped with exponential backoff:
```python
import asyncio

async def call_claude_with_retry(client, **kwargs) -> Message:
    for attempt in range(3):
        try:
            return await client.messages.create(**kwargs)
        except anthropic.RateLimitError:
            await asyncio.sleep(2 ** attempt)
        except anthropic.APITimeoutError:
            await asyncio.sleep(2 ** attempt)
    raise RuntimeError("Claude API failed after 3 attempts")
```

If a single chunk extraction fails, log the error and continue — the merge step handles missing chunks gracefully (null fields are expected).

If an entire stage fails, set `job.status = "failed"` and stream an error SSE event to the frontend with the stage name and error message.

---

## Logging & Observability

Use Python `logging` at `INFO` by default, `DEBUG` in dev.

Log at every stage transition:
```
INFO  [job:uuid4] Stage ingest started
INFO  [job:uuid4] Parsed 84 pages, created 12 chunks (72,340 tokens total)
INFO  [job:uuid4] Stage extract started — 12 chunks
INFO  [job:uuid4] Chunk 3/12 extracted — 14 fields found
INFO  [job:uuid4] Stage extract complete — tokens used: 18,420
INFO  [job:uuid4] Stage enrich started — generating search queries
INFO  [job:uuid4] Generated 6 queries, executing in parallel
INFO  [job:uuid4] Search complete — 17 results across 6 queries
INFO  [job:uuid4] Stage draft started — 8 sections
INFO  [job:uuid4] Section executive_summary drafted — 312 words
...
INFO  [job:uuid4] Pipeline complete — total tokens: 42,180, elapsed: 67s
```

Track and log total token usage per job. Include this in the `/memo` response as `total_tokens_used`.

---

## Security

- No API keys in frontend code — all Anthropic and Tavily calls happen server-side only
- PDF upload: validate MIME type server-side (not just extension), max 50MB
- No user auth required for MVP — but add an `API_KEY` header check if deploying externally (simple `secrets.compare_digest`)
- CORS: set `CORS_ORIGINS` explicitly — do not use `*` in production
- Temp files scoped to job ID — no path traversal possible if job IDs are UUID4
- The memo DOCX includes a header warning that the content is AI-generated — never remove this

---

## Testing
```
tests/
├── test_ingest.py       # PDF parsing with sample CIMs of varying formats
├── test_extract.py      # Extraction prompt with known-answer fixtures
├── test_enrich.py       # Search query generation (mock Tavily)
├── test_draft.py        # Section drafting with fixture extraction + enrichment
├── test_api.py          # FastAPI integration tests (upload → status → memo)
└── fixtures/
    ├── sample_cim.pdf   # Synthetic, redacted CIM for testing
    ├── extraction_expected.json
    └── enrichment_mock.json
```

Run:
```bash
pytest tests/ -v
```

Test the extraction prompt against `fixtures/extraction_expected.json` — spot-check that key financial fields (revenue, EBITDA, ARR) are correctly extracted. This is the most important test; failures here propagate through the whole pipeline.

---

## Known Limitations

- **Scanned PDFs**: if the CIM is a scanned image PDF (no text layer), extraction will fail. OCR support (via `pytesseract` or AWS Textract) is not included in v1.
- **Non-standard CIM formats**: some CIMs are pitch decks (PPTX). Only PDF is supported in v1.
- **Private company data gaps**: web search for private companies often returns limited financial data. The enrichment step will have null fields — this is expected and handled.
- **Table extraction**: complex merged-cell tables in PDFs sometimes parse incorrectly. The analyst should verify any extracted financial tables.
- **Token limits**: CIMs over ~300 pages may produce more chunks than the merge prompt can handle in one call. Add a secondary aggregation step if handling very large documents.
- **Hallucination**: the grounding instruction reduces but does not eliminate fabrication. Every figure in the output memo must be verified by the analyst before use.

---

## Extending the System

### Add Google Drive as a source
- Add a `GET /gdrive/files` route that lists Drive files using the Google Drive API
- Analyst selects a file instead of uploading — the pipeline receives the file bytes identically
- Requires OAuth2 flow; use `google-auth-oauthlib`

### Add CRM logging (Affinity / Salesforce)
- After memo generation, offer a "Log to CRM" button
- POST the deal name, sector, stage, and memo URL to the CRM API
- This keeps the human in the loop — logging is triggered manually, not automatically

### Portfolio monitoring extension
- Same extraction pipeline, applied to quarterly board packs instead of CIMs
- Add a `comparison` stage: compare extracted financials against a prior-period baseline stored in a JSON file per portfolio company
- Flag deviations beyond a configurable threshold (e.g. revenue miss > 10%)

### Memory layer
- Store `DealExtraction` objects in a vector database (e.g. ChromaDB) after each job
- Add a `/similar-deals` endpoint: given a new extraction, return the 3 most similar past deals
- Surfaces precedents directly in the memo: "Similar to [Deal X] closed in 2023"