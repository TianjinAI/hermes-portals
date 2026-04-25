# Bloomberg Portal v4 Rewrite Spec

## Goal
Rewrite `portal.py` to be the single Bloomberg Intelligence Portal on port 5053. The current portal has 4 tabs (Brief, Full, Intel, KB) but Brief is just a flat list and Intel shows useless entity counts. Fix both.

## Files
- `portal.py` — Main portal server (REWRITE THIS)
- `intelligence_portal.html` — Reference for the intelligence UI design (port 5055, will be removed)
- `intelligence_generator.py` — Reference for intelligence logic

## Data Locations
- `~/.hermes/bloomberg_digest/` — Main data directory
  - `briefs/YYYY-MM-DD.md` — Daily brief markdown (RANKED by market impact)
  - `full/YYYY-MM-DD.html` — Full HTML digest
  - `YYYY-MM-DD.json` — Metadata
  - `YYYY-MM-DD_index.json` — Newsletter index
  - `knowledge/knowledge_base.json` — Cumulative KB (entities, themes, facts)
  - `summaries/` — Individual newsletter summaries (text files)

## Brief Markdown Format (CRITICAL — parse this for Brief tab)
```markdown
## Bloomberg Daily Brief — 2026-04-23

### 🔥 Top Headlines (by market impact)

1. **US-Iran Strait of Hormuz standoff escalates** — Context paragraph here. [Geopolitics/Energy]
2. **Tesla plunges 2.3% premarket** — Context paragraph. [Equities]
...

### 📊 Key Market Data

**Equities:**
- S&P 500 futures: **7,134** (-0.5%)
- Nasdaq 100 futures: **26,989** (-0.3%)

**Commodities:**
- Brent crude: **$104.02** (+2.1%)

### 💡 What to Watch Today

1. **Hormuz escalation updates** — Description of what to watch
2. **Tesla earnings** — Description
...

### 🗞️ Quick Scan
| Time | Subject | Takeaway |
|------|---------|----------|
...
```

## Tab Requirements

### Brief Tab (FIX — currently broken)
- Parse the brief markdown (NOT the HTML), which already has stories ranked by market impact
- Show market data strip at top (compact cards with label/value/change)
- Show ranked stories as cards with: rank number, title, context, category tag
- Show "What to Watch" section at bottom
- Server-side parsing: parse brief markdown in Python, send structured JSON to client

### Intel Tab (REDESIGN — currently useless)
- Build a cross-day intelligence engine that analyzes ALL available briefs
- Identify hot topics by tracking which categories/entities appear across multiple days
- Show topic cards with: topic name, heat level (days appeared), related articles
- Generate written insights connecting dots across days (template-based, no LLM needed)
- Show trend indicators (rising/falling/stable)
- Include a "Refresh" button
- Read knowledge_base.json for known entities to enhance topic extraction

### Full Tab (KEEP — minor improvements)
- Show raw HTML digest, same as current
- Better CSS styling

### KB Tab (KEEP — same as current)
- Stats and history

## API Endpoints
- `GET /` — Serve HTML
- `GET /api/dates` — List available dates
- `GET /api/date/<date>` — Data for a date (add `brief_parsed` field with parsed markdown)
- `GET /api/intel` — Cross-day intelligence data (NEW)
- `GET /api/kb` — Knowledge base stats

## Intelligence Engine Logic
1. Load all brief markdown files from `~/.hermes/bloomberg_digest/briefs/`
2. Parse each into structured data (headlines with title/context/category, market data, watch items)
3. Track topic frequency: for each category tag (split on `/` and `,`), track which dates it appears in
4. Load known entities from knowledge_base.json, find entity mentions in headlines
5. Rank topics by: (days_appeared * 3) + article_count
6. For top 3 topics, generate insight text: "Topic X appeared in N of M days (X% of coverage). Key stories: ..."
7. Build trends: compare recent vs earlier frequency for each topic
8. Return JSON with: hot_topics, trends, insights, stats

## Design
- Keep the existing light theme (warm cream background, dark header)
- Same CSS variables
- Keep the date navigation and tab switching
- Remove the sidebar (archive list) — dates are in the header

## Constraints
- Single file: portal.py (everything in one file, HTML embedded as string)
- Port 5053
- No external dependencies beyond Python stdlib
- No LLM calls — intelligence is statistical/template-based
- Must handle gracefully: missing brief files, missing KB, only 1-2 days of data
