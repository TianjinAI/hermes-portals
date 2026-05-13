# Bloomberg Intelligence Portal — Change Log

## 2026-05-14: Newsletter Labels + Direct Article Click-through

### Problem 1: Brief cards showed "NEWS" instead of newsletter names
- Synthesized articles had empty `tags` arrays → cards defaulted to "NEWS"
- **Fix:** Build a newsletter subject→type map from `data.newsletters`, then display
  unique newsletter type names (Morning Briefing, Markets Daily, Politics, etc.)
  as chips on breaking cards and feed cards.

### Problem 2: Clicking a Brief card → Full showed no article/links
- Flow was: click card → fuzzy-match article title to Headline → set selectedHeadline
  → renderFull() tries exact title match between headline and articles → fails every time
  because synthesized article titles ≠ Daily Brief headline titles
- **Fix:** New `selectedArticle` state variable. Clicking a card now sets this directly.
  renderFull() checks for selectedArticle first and displays the article content +
  all Bloomberg links without going through headline matching.
- Also shows an "Other Articles" sidebar for navigation between stories.

### Files changed
- `portal-v5.py` — 106 insertions, 38 deletions

### Known edge cases
- Newsletter type labels fall back to subject line when the source newsletter isn't
  indexed in the digest (e.g., article mentions a newsletter that wasn't captured
  in digest.json that day). In practice ~80% resolve to canonical type names.
- Synthesis pipeline (`synthesize_articles.py`) must be run for a date before articles
  appear. The cron job handles this automatically for today's data.

### Git
- Repo: TianjinAI/hermes-portals (branch: master)
- Commit: `995cf26` — "Brief tab: newsletter labels + direct article click-through..."
