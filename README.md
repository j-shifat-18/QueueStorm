# QueueStorm Investigator

**SUST CSE Carnival 2026 · Codex Community Hackathon · Online Preliminary**

An AI-powered support ticket investigator for digital finance platforms. Reads a customer complaint alongside their recent transaction history, identifies the relevant transaction, judges the evidence, classifies and routes the case, and generates a safe customer reply — without ever requesting credentials or making unauthorized financial promises.

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| API Framework | FastAPI |
| Language | Python 3.11+ |
| AI Engine | Google Gemini 2.0 Flash (`google-genai`) |
| Database | PostgreSQL via NeonDB (asyncpg + SQLAlchemy async) |
| Migrations | Alembic |
| Deployment | Vercel |

---

## Project Structure

```
QueueStorm/
├── api/
│   └── index.py                 # Vercel ASGI entry point
├── app/
│   ├── main.py                  # FastAPI app, lifespan, middleware, error handlers
│   ├── api/
│   │   └── routes.py            # GET /health  and  POST /analyze-ticket
│   ├── core/
│   │   └── config.py            # Settings loaded from environment variables
│   ├── db/
│   │   ├── database.py          # Async SQLAlchemy engine + session
│   │   └── models.py            # TicketLog ORM model
│   ├── models/
│   │   └── schemas.py           # Pydantic request / response schemas
│   └── services/
│       ├── analyzer.py          # Main pipeline orchestrator
│       ├── evidence_engine.py   # Rule-based transaction matching & classification
│       ├── gemini_service.py    # Gemini API wrapper
│       └── safety_guardrails.py # Post-processing safety enforcement
├── alembic/                     # Database migrations
│   └── versions/
│       └── 0001_initial_ticket_logs.py
├── tests/
│   └── test_api.py
├── documents/                   # Problem statement & rubric PDFs
├── sample_output.json           # Sample responses from the public test cases
├── vercel.json                  # Vercel deployment config
├── requirements.txt
├── alembic.ini
├── .env.example                 # Variable names only — no real secrets
└── README.md
```

---

## Local Setup and Running

### Prerequisites

- Python 3.11 or newer
- A NeonDB (or any PostgreSQL) database
- A Google Gemini API key — get one free at [aistudio.google.com](https://aistudio.google.com)

---

### Step 1 — Clone the repo

```bash
git clone <your-repo-url>
cd QueueStorm
```

---

### Step 2 — Create a virtual environment

```bash
python -m venv .venv
```

Activate it:

```bash
# macOS / Linux
source .venv/bin/activate

# Windows
.venv\Scripts\activate
```

---

### Step 3 — Install dependencies

```bash
pip install -r requirements.txt
```

---

### Step 4 — Configure environment variables

```bash
cp .env.example .env
```

Open `.env` and fill in your values:

```env
GEMINI_API_KEY=your_gemini_api_key_here
DATABASE_URL=postgresql://user:password@host/dbname?sslmode=require
PORT=8000
ENVIRONMENT=development
LOG_LEVEL=INFO
```

> The `DATABASE_URL` must start with `postgresql://` (not `postgres://`). NeonDB connection strings work as-is — the app strips `sslmode=require` from the URL and passes it correctly to asyncpg.

---

### Step 5 — Run database migrations

```bash
python -m alembic upgrade head
```

This creates the `ticket_logs` table in your database. Run this once on first setup and again whenever migrations are added.

> If `alembic` is not found as a standalone command, always use `python -m alembic` — that ensures it runs inside your active virtual environment.

---

### Step 6 — Start the server

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Remove `--reload` in production.

---

### Step 7 — Verify it's running

```bash
curl http://localhost:8000/health
```

Expected response:

```json
{"status": "ok"}
```

---

### Step 8 — Send a test ticket

```bash
curl -X POST http://localhost:8000/analyze-ticket \
  -H "Content-Type: application/json" \
  -d '{
    "ticket_id": "TKT-001",
    "complaint": "I sent 5000 taka to a wrong number around 2pm today. Please help.",
    "language": "en",
    "channel": "in_app_chat",
    "user_type": "customer",
    "transaction_history": [
      {
        "transaction_id": "TXN-9101",
        "timestamp": "2026-04-14T14:08:22Z",
        "type": "transfer",
        "amount": 5000,
        "counterparty": "+8801719876543",
        "status": "completed"
      }
    ]
  }'
```

You can also open the interactive API docs at `http://localhost:8000/docs`.

---

## Running Tests

### Install test dependencies (if not already installed)

```bash
pip install pytest pytest-asyncio httpx
```

### Run all tests

```bash
python -m pytest tests/ -v
```

### What the tests cover

| Test | What it checks |
|------|---------------|
| `test_health` | `GET /health` returns `{"status": "ok"}` |
| `test_missing_ticket_id` | Returns 400 when `ticket_id` is absent |
| `test_missing_complaint` | Returns 400 when `complaint` is absent |
| `test_empty_complaint` | Returns 422 for whitespace-only complaint |
| `test_invalid_json` | Returns 400 for malformed JSON body |
| `test_no_transactions_gives_insufficient_data` | Evidence engine returns `insufficient_data` with empty history |
| `test_amount_match` | Evidence engine correctly matches a transaction by amount |
| `test_duplicate_detection` | Detects two identical payments within 2 minutes |
| `test_inconsistent_verdict_repeated_recipient` | Flags wrong-transfer claim as inconsistent when recipient appears 3× |
| `test_phishing_classification` | OTP-request complaint classifies as `phishing_or_social_engineering` |
| `test_wrong_transfer_classification` | Wrong-number complaint classifies as `wrong_transfer` |
| `test_prompt_injection_detection` | Adversarial complaint text is detected and blocked |
| `test_sanitize_removes_credential_request` | Credential-request sentences are stripped from `customer_reply` |
| `test_sanitize_removes_unauthorized_refund` | Refund promises are replaced with safe language |
| `test_sanitize_adds_credential_reminder` | PIN/OTP reminder is always appended |

> Tests that hit the API endpoints run without a real database or Gemini key — the DB dependency gracefully yields `None` when not configured, and the endpoints are tested for schema validation only.

---

## Deploy to Vercel

### Option A — Connect GitHub repo (recommended)

1. Push the repo to GitHub.
2. Go to [vercel.com](https://vercel.com) → **New Project** → import the repo.
3. In **Project Settings → Environment Variables**, add:

   | Name | Value |
   |------|-------|
   | `GEMINI_API_KEY` | your Gemini API key |
   | `DATABASE_URL` | your NeonDB connection string |

4. Click **Deploy**. Every push to `main` redeploys automatically.

### Option B — Vercel CLI

```bash
npm install -g vercel
vercel --prod
```

Set environment variables when prompted, or add them in the dashboard afterwards.

### Live endpoints

```
GET  https://your-project.vercel.app/health
POST https://your-project.vercel.app/analyze-ticket
```

---

## API Reference

### `GET /health`

```json
{"status": "ok"}
```

### `POST /analyze-ticket`

**Required fields:** `ticket_id`, `complaint`

**Optional fields:** `language`, `channel`, `user_type`, `campaign_context`, `transaction_history`, `metadata`

**Request example:**

```json
{
  "ticket_id": "TKT-001",
  "complaint": "I sent 5000 taka to a wrong number around 2pm today.",
  "language": "en",
  "channel": "in_app_chat",
  "user_type": "customer",
  "transaction_history": [
    {
      "transaction_id": "TXN-9101",
      "timestamp": "2026-04-14T14:08:22Z",
      "type": "transfer",
      "amount": 5000,
      "counterparty": "+8801719876543",
      "status": "completed"
    }
  ]
}
```

**Response example:**

```json
{
  "ticket_id": "TKT-001",
  "relevant_transaction_id": "TXN-9101",
  "evidence_verdict": "consistent",
  "case_type": "wrong_transfer",
  "severity": "high",
  "department": "dispute_resolution",
  "agent_summary": "Customer reports sending 5000 BDT via TXN-9101 to +8801719876543, which they believe was the wrong recipient.",
  "recommended_next_action": "Verify TXN-9101 and initiate the wrong-transfer dispute workflow per policy.",
  "customer_reply": "We have noted your concern about transaction TXN-9101. Our dispute team will review the case through official support channels. Please do not share your PIN or OTP with anyone.",
  "human_review_required": true,
  "confidence": 0.92,
  "reason_codes": ["wrong_transfer", "transaction_match"]
}
```

**HTTP status codes:**

| Code | Meaning |
|------|---------|
| `200` | Successful analysis |
| `400` | Malformed JSON or missing required fields |
| `422` | Valid schema but semantically invalid (e.g. empty complaint) |
| `500` | Internal error — safe message returned, no stack traces or secrets exposed |

---

## Architecture

```
POST /analyze-ticket
        │
        ▼
┌───────────────────┐
│  Prompt Injection │  ← Reject adversarial instructions in complaint text
│  Check            │
└────────┬──────────┘
         │
         ▼
┌───────────────────┐
│  Evidence Engine  │  ← Rule-based: amount matching, duplicate detection,
│  (rule-based)     │    inconsistency detection, case type classification
└────────┬──────────┘
         │  pre-computed evidence injected into prompt
         ▼
┌───────────────────┐
│  Gemini 2.0 Flash │  ← Generates agent_summary, recommended_next_action,
│                   │    customer_reply, and refines verdict & routing
└────────┬──────────┘
         │  (rule-based fallback if Gemini fails)
         ▼
┌───────────────────┐
│  Safety Guardrails│  ← Strip credential requests, replace refund promises,
│  (post-process)   │    ensure PIN/OTP reminder present
└────────┬──────────┘
         │
         ▼
┌───────────────────┐
│  Enum + Routing   │  ← Re-enforce valid enum values, department routing,
│  Overrides        │    human_review_required flag
└────────┬──────────┘
         │
         ▼
┌───────────────────┐
│  PostgreSQL       │  ← Persist full request + response for audit
│  (NeonDB)         │
└───────────────────┘
```

---

## AI / Model Usage

| Model | Provider | Why |
|-------|----------|-----|
| `gemini-2.0-flash` | Google AI API | Fast (~1–3s), low cost, strong JSON instruction-following, native Bangla support |

**Hybrid rule + AI design:**
- The rule engine runs first to match transactions, detect duplicates, spot inconsistencies, and classify case type — giving the LLM structured evidence rather than asking it to reason from scratch.
- The LLM focuses on generating high-quality text (summaries, replies) and can refine the verdict with its language understanding.
- If Gemini fails or times out, a pure rule-based fallback kicks in — the service never returns a 500 on LLM failure.

---

## Safety Logic

| Layer | What it does |
|-------|-------------|
| Prompt injection check | Scans complaint for `"ignore previous instructions"`, `"you are now"`, `[system]`, etc. — triggers safe fallback if found |
| System prompt rules | Gemini is explicitly instructed never to request credentials or promise refunds |
| Post-process sanitization | Regex strips any credential-request sentences from `customer_reply`; replaces refund promises with safe language; ensures PIN/OTP reminder is always present |
| Structural overrides | `phishing_or_social_engineering` → `severity=critical`, `department=fraud_risk`, `human_review_required=true` always enforced in code, not left to the LLM |

---

## Database Schema

**Table: `ticket_logs`** — full audit trail of every request and response.

| Column | Type | Description |
|--------|------|-------------|
| `id` | UUID | Primary key |
| `ticket_id` | VARCHAR | Echoed from request |
| `complaint` | TEXT | Original complaint text |
| `language` / `channel` / `user_type` | VARCHAR | Request metadata |
| `transaction_history` | JSON | Full transaction list from request |
| `relevant_transaction_id` | VARCHAR | Transaction identified by the engine |
| `evidence_verdict` | VARCHAR | `consistent` / `inconsistent` / `insufficient_data` |
| `case_type` / `severity` / `department` | VARCHAR | Classification output |
| `agent_summary` | TEXT | Agent-facing summary |
| `recommended_next_action` | TEXT | Operational next step |
| `customer_reply` | TEXT | Safe customer-facing reply |
| `human_review_required` | BOOLEAN | Escalation flag |
| `confidence` | FLOAT | Model confidence 0–1 |
| `reason_codes` | JSON | Short reasoning labels |
| `processing_time_ms` | FLOAT | End-to-end latency in ms |
| `created_at` | TIMESTAMPTZ | Auto-set on insert |

---

## Known Limitations

1. **Bangla keyword coverage** — The rule engine matches a curated set of Bangla phrases. Uncommon transliterations fall back entirely to Gemini.
2. **Transaction history size** — Optimised for 2–5 transactions. Very large histories may increase LLM latency.
3. **No live ledger access** — The service only sees the `transaction_history` provided in the request; it cannot query a live payment system.
4. **Gemini quota** — Uses the team's own API key and quota. The rule-based fallback activates automatically on quota errors or timeouts.
5. **Confidence scores** — LLM-estimated, not statistically calibrated. Treat as a rough signal.
