# PageLift AI Audit (Single-URL Website Audit Tool)

Lightweight AI-powered website audit tool.

It audits one page at a time, extracts factual metrics deterministically, and generates grounded AI insights + prioritized recommendations.

## Deployed Link
After Deployment it will be added here.

## Assignment Requirement Coverage

### Objective

This implementation satisfies the objective:

1. Accepts a single URL
2. Extracts and displays required factual metrics
3. Uses AI to generate structured insights and recommendations

### Scope

- Single-page analysis only
- No multi-page crawling
- Focused, practical implementation (not production-heavy)

### 1) Factual Metrics (Required)

Extracted per page:

- Total word count
- Heading counts (`H1`, `H2`, `H3`)
- CTA count (buttons + primary action links)
- Internal vs external link counts
- Image count
- Percentage of images missing alt text
- Meta title and meta description

These are clearly separated from AI-generated output in CLI JSON, API JSON, and Web UI sections.

### 2) AI Insights (Required)

AI returns structured insights for:

- SEO structure
- Messaging clarity
- CTA usage
- Content depth
- UX / structural concerns

Grounding quality controls:

- Structured metric payload is passed to the model
- Prompt enforces metric-based references
- Output is validated against schema
- Grounding checks reject placeholder/invalid evidence patterns

### 3) Recommendations (Required)

AI output includes:

- 3-5 prioritized recommendations
- Reasoning tied to metrics
- Actionable action lists

### Interface Requirement

This repository provides all of these:

- Local Web App (`eight25-audit-web`)
- CLI (`eight25-audit`)
- API endpoint (`POST /api/audit`) with structured JSON output

### Prompt Logs (Required Deliverable)

Each AI run writes a prompt log to `logs/prompt-logs/` including:

- `system_prompt`
- `user_prompt`
- `structured_input`
- `raw_model_output`
- `parsed_output` (or `error`)

## Project Structure

```text
src/eight25_audit/
  ai.py              # Prompt design, model call, schema + grounding validation
  scrape.py          # Single-URL fetch logic and block detection
  metrics.py         # Deterministic factual extraction from HTML
  prompt_logging.py  # Prompt log persistence
  models.py          # Pydantic models for contracts
  cli.py             # CLI orchestration
  web.py             # Flask web app + API endpoint
```

## Architecture Overview

Flow for both CLI and Web API:

1. Normalize + fetch URL (`scrape.py`)
2. Detect blocked/non-HTML/network failures cleanly
3. Extract factual metrics deterministically (`metrics.py`)
4. If AI enabled:
   - build prompts and structured input (`ai.py`)
   - call model
   - validate schema + grounding
   - persist prompt log (`prompt_logging.py`)
5. Return separated factual + AI output

## AI Design Decisions

- Strict structured output contract using JSON schema + Pydantic
- Two-pass strategy (initial + repair attempt)
- Grounding constraints enforced programmatically
- Low temperature for reduced variance
- Prompt logs persisted for evaluator visibility

## Trade-offs

- HTML fetch only (no browser rendering): some JS-heavy pages may be partial
- CTA detection is heuristic-based by design (assignment-scope practical)
- Anti-bot protected sites may return blocked diagnostics instead of full metrics

## What to Improve With More Time

- Optional Playwright mode for JS-rendered pages
- More robust CTA classifier (DOM context + visual hierarchy signals)
- Unit tests with fixed HTML fixtures for deterministic regression checks
- Better confidence scoring for AI findings


## Run on a Different PC (Step-by-Step)

### 1. Prerequisites

- Python 3.10+
- Git
- Internet access

### 2. Clone repository

```bash
git clone <YOUR_GITHUB_REPO_URL>
cd <YOUR_REPO_FOLDER>
```

### 3. Create and activate virtual environment

Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

macOS/Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 4. Install dependencies

```bash
pip install -r requirements.txt
pip install -e .
```

### 5. Configure environment

```bash
cp .env.example .env
```

Then edit `.env` and set:

- `OPENAI_API_KEY`
- optional: `OPENAI_MODEL`

### 6. Run options

CLI (with AI):

```bash
eight25-audit https://example.com --json
```

CLI (metrics only):

```bash
eight25-audit https://example.com --no-ai --json
```

Web app:

```bash
eight25-audit-web
```

Open:

`http://127.0.0.1:8000`

### 7. Verify prompt logs

After an AI run, check:

`logs/prompt-logs/`

## API Usage

Endpoint:

`POST /api/audit`

Example body:

```json
{
  "url": "https://example.com",
  "no_ai": false
}
```

Returns structured JSON with separated factual metrics and AI output.

