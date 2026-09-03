# Daba.Cities : Automated Content Pipeline

Internal automation tool for Daba.Cities that turns approved Notion content rows into ready-to-publish, platform-tailored social posts, with a human approval step before anything goes out.

## What it does

1. A Notion database row is marked **Ready for Review**.
2. n8n picks it up, splits the content into per-platform variants (LinkedIn, Instagram, X, etc.), and uses AI to adapt tone/caption and generate an image per platform.
3. Generated variants are written to Postgres and shown in a Streamlit dashboard for human review.
4. A reviewer can **Approve**, **Reject**, **Edit** text inline, or send it back for **Rewrite** / **Redo Design** (which loops back through generation automatically).
5. Approved content is distributed to the target platform(s).
6. Any pipeline failure is logged and emailed automatically.

## Architecture

```
Notion (source of truth for content ideas)
   │
   ▼
n8n: Daba.Cities - Content Pipeline
   │  - Notion Trigger (filters latest updated rows)
   │  - Filter (status = "Ready for Review")
   │  - Split Platforms
   │  - Image Generation (Replicate — flux-2-klein-4b)
   │  - Toning & Reshaping (AI: per-platform caption/text)
   │  - Write to Postgres (status: pending_approval)
   │  - Wait (pauses for dashboard decision via webhook)
   │
   ▼
Postgres (posts, post_variants, pipeline_errors)
   │
   ▼
Streamlit Dashboard (human approval UI)
   │  - Approve / Reject / Edit / Rewrite / Redo Design
   │
   ▼ (rewrite / redo_design)
n8n: Daba.Cities - Regenerate Content (recursive sub-workflow)

Any node failure → n8n: Daba.Cities - Error Logger → email alert
```

## Components

### n8n workflows
Self-hosted via Docker. Three workflows, exported as JSON (no credentials included — see [Setup](#setup)):
- **Daba.Cities - Content Pipeline** : main end-to-end flow described above.
- **Daba.Cities - Regenerate Content** : sub-workflow n8n calls recursively to handle "rewrite" / "redo_design" decisions from the dashboard (n8n workflows can't loop back to earlier nodes within one run, so this is a self-calling sub-workflow instead).
- **Daba.Cities - Error Logger** : catches failures from the other workflows and emails an alert. Linked as the "Error Workflow" setting on the other two.

### Postgres database
Source of truth for pipeline state (not Notion — Notion is only the content-idea intake). Schema:
- `posts` — one row per content item (status, notion_id, content_type, resume_url, timestamps)
- `post_variants` — one row per platform variant of a post (platform, text, image_url)
- `pipeline_errors` — logged failures

### Dashboard (`dashboard/`)
Streamlit app for human review. Reads pending posts from Postgres, displays each platform's text + generated image, and sends the reviewer's decision back to n8n via the post's stored webhook `resume_url`.

- `app.py` — the dashboard
- `requirements.txt` — Python dependencies

## Setup

### Prerequisites
- Docker + Docker Compose
- A Notion integration token with access to the content database
- A Replicate API token (image generation)
- An AI provider API key for text tone-adaptation (Gemini or OpenAI, depending on the workflow's configured Chat Model)
- An email account for SMTP alerts (e.g. Gmail with an App Password)

### 1. Environment variables
Copy the example file and fill in real values:
```bash
cp .env.example .env
```
Variables needed:
- `N8N_ENCRYPTION_KEY` — generate with `openssl rand -hex 16`
- `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`, `POSTGRES_HOST`, `POSTGRES_PORT`
- `APPROVAL_SECRET` — shared secret between the dashboard and n8n's Wait-node webhook; must match on both sides
- `IMEJIS_API_KEY` — legacy, only needed if the old template-based image node is still present; not required once fully migrated to Replicate

### 2. Start n8n and Postgres
```bash
docker compose up -d
```
n8n will be available at `http://localhost:5678`.

### 3. Create the database schema
```bash
docker compose exec -T postgres psql -U $POSTGRES_USER -d $POSTGRES_DB -f schema.sql
```
This creates the `posts`, `post_variants`, and `pipeline_errors` tables.

### 4. Create the Notion database
Create a new Notion database with these properties (names must match exactly — the workflows reference them directly):

| Property | Type | Notes |
|---|---|---|
| Title | Title | Post headline/subject |
| Content Type | Select | e.g. Investment Opportunity, Project Listing, City Fact, News |
| Status | Select | Must include a `Ready for Review` option — this is what the Filter node checks |
| Description | Text | Main body content used to build captions/image prompts |
| City/Location | Text | |
| Platforms | Multi-select | Target platforms, e.g. LinkedIn, Instagram, X, Facebook |
| ROI % | Number | Optional, used for Investment Opportunity posts |
| Target Publish Date | Date (with time) | |
| Reviewer Feedback | Text | Written back automatically on rejection |

Then share an integration with it:
1. In Notion, go to **Settings → Connections → Develop or manage integrations** and create an integration (or reuse an existing one) to get an integration token.
2. Open the new database → `•••` menu → **Connections** → add that integration.
3. Use the integration token as the credential in n8n's Notion Trigger node (see step 5).

### 5. Import the workflows
In the n8n UI: **Workflows → Import from File**, and import the three JSON files (Content Pipeline, Regenerate Content, Error Logger).

Each imported workflow will show nodes with missing credentials (exports never include secrets). For each:
- **Notion** — your own integration token
- **AI Chat Model node** (Gemini or OpenAI) — your own API key
- **Replicate** (HTTP Request node) — your own API token, sent as an `Authorization: Bearer <token>` header
- **SMTP** — your own email + app password
- **Postgres** — connection details from your `.env`
- **Header Auth (Wait node)** — must match `APPROVAL_SECRET` in `.env`

Activate/publish all three workflows once credentials are set.

### 6. Run the dashboard
```bash
cd dashboard
pip install -r requirements.txt
streamlit run app.py
```
Make sure `.env` points `POSTGRES_HOST` at the same Postgres instance n8n is writing to.

## Notes
- The dashboard reads `resume_url` per post from Postgres , this is what lets a decision made days later reach the correct paused n8n execution.
- Rewrite/redo loops don't have an attempt cap yet a runaway rewrite loop is a known open item.
- Image generation uses Replicate (`black-forest-labs/flux-2-klein-4b`) called via a generic HTTP Request node, not a native n8n Replicate node.
