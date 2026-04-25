# Bloomberg Intel Engine Tuning Spec

## Goal
Improve the intelligence engine in `portal.py` (functions `build_intelligence()`, `compute_trend()`, `extract_entities_from_text()`, and related helpers).

## Current State
- Only 2 days of data (2026-04-22, 2026-04-23)
- Score: `days_appeared × 3 + article_count`
- Trend: compares first half vs second half
- Entity extraction: matches short names (≥3 chars) which creates noise
- Heat: <3d=Emerging, 3-4d=Medium, 5d+=High
- Insights: template text with topic name, days, coverage %, key stories
- 172 known entities in knowledge_base.json

## Changes to Make

### 1. Score Formula Tuning
Change from `(days_appeared * 3) + article_count` to `(days_appeared * 5) + article_count`.
This prioritizes topics that span multiple days over topics that just have many articles in one day.
Update the threshold in ensure_topic from 2 to also allow emerging 1-day topics so they appear in the portal (but scored lower).

### 2. Entity Noise Reduction
Add a stop-word list and minimum length filter in `extract_entities_from_text()`:

```python
STOP_ENTITIES = frozenset({
    "AI", "US", "UK", "CEO", "IPO", "GDP", "Fed", "SEC", "EU", "NYC",
    "LSE", "NYSE", "SP", "BOE", "ECB", "IMF", "OPEC", "NASDAQ", "USD",
    "Deal", "CEO of", "Board", "Growth", "Risk", "Impact", "Outlook",
    "Strategy", "Demand", "Supply", "Price", "Value", "Rate"
})
MIN_ENTITY_LENGTH = 4
```

Also score entity-based topics lower: multiply entity topic scores by 0.5 to favor category-based topics.

### 3. Cross-Topic Connections
After computing all topics, find connections between them:
- **Entity overlap**: If two topics share ≥ 1 related entity, add a `connections` field to each
- **Date overlap**: If two topics appeared on the same dates, add to connections
- Add `connections: [{"topic": "Geopolitics", "shared_entities": ["Iran"], "shared_dates": ["2026-04-23"]}]` to each topic record's output

Only generate connections for the top 12 topics (by score).

### 4. Topic of the Day
For each brief day, identify the single highest-scoring topic. Add a `topic_of_the_day` list to the intelligence output:

```python
"topic_of_the_day": [
    {"date": "2026-04-23", "topic": "Geopolitics", "score": 42},
    {"date": "2026-04-22", "topic": "Markets", "score": 38}
]
```

This is computed by taking the highest-ranked headline's primary category tag for each day.

### 5. Richer Insights
Update the insight text generation to include:
- Related entity names (up to 3)
- Connection hints ("Also trending: tech, markets, shipping")
- Which newsletters drove the coverage
- A forward-looking sentence when relevant

New format:
```
"{topic} appeared in {days} of {total} brief days ({pct}% coverage) across {count} articles. 
Trend: {direction}. Related: {entities}. {if days >= 2: "This topic has been building across recent briefs."}
Also connected to: {connected_topics}. Key stories: {stories}."
```

### 6. Trend Future-Proofing
Add a helper function `compute_trend_sliding(day_counts, window=7)` that:
- If data has ≥7 days, use sliding window (compare recent 3 days vs previous 4 days)
- If data has <7 days, fall back to current split-in-half logic
- Return direction and counts as before

Keep the existing `compute_trend()` function but rename it to `compute_trend_split()`, and make `compute_trend()` the main entry point that automatically switches between sliding and split modes based on data volume.

## Files to Modify
- `/home/admin/.hermes/bloomberg-portal/portal.py`

## Tests
After changes, verify:
1. `curl -s http://localhost:5053/api/intel` returns valid JSON
2. hot_topics array has items with `connections` field
3. topic_of_the_day array exists
4. insights have richer text
5. No entity names shorter than 4 chars appear in related_entities
6. Portal page loads without JS errors
