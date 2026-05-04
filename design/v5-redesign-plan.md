# Bloomberg Portal v5 Redesign — Implementation Plan

## Goal
Apply WorkBuddy's design brief to portal-v5.py, skipping animations (Section 5).

## Approach
Direct code modifications to the single-file Python server. CSS is embedded in template string, JS render functions are inline. No build tools.

## Phases

### Phase 1 — CSS Variable Overhaul
**File:** portal-v5.py (CSS vars in HTML template)
- Replace the `:root` block with WB's vibrant tokens:
  - `--accent-primary: #FFA028` (Bloomberg orange)
  - `--accent-live: #00F0FF` (cyan)
  - `--up: #0ECB81` (mint) — replaces old `--green`
  - `--down: #F6465D` (crimson) — replaces old `--red`
  - `--amber: #FFB300` (kept)
  - `--gradient-up / --gradient-down / --gradient-heat` (new)
- Add typography scale: `--text-hero`, `--text-title`, `--text-ticker`
- Add badge system CSS (heat-low/med/high, live, new)

### Phase 2 — Intel Tab Hero Redesign
**File:** portal-v5.py `renderIntel()` function
- **Ticker strip**: sticky, 32px height, horizontal auto-scroll of top 3 signals, color-coded pills
- **Narrative stats**: replace flat stat grid with 4 cards showing: number + sparkline (SVG) + delta sentence
- **Promote charts**: keep current Chart.js but make them wider, gradient fills, floating heat badge on timeline chart

### Phase 3 — Compact Topic Cards
**File:** portal-v5.py `renderIntel()` + CSS
- Redesign `.topic-card` from ~200px padded block to 80px compact row
- Elements: left heat bar (4px gradient), topic name (14px bold), mini sparkline (80x20px), article count, heat badge, expand chevron
- Hover: lighter bg, heat bar widens 4→6px, slight lift
- Expanded: reveals top 3 headlines, chevron rotates

### Phase 4 — Filter & Sort Bar
- Add compact filter bar above topic card list
- Filter pills: All | Markets | Policy | Tech | Energy
- Sort: Heat ↓ | Volume ↓ | Recency ↓
- Active pill: bg #FFA028, text #0B0E11

### Phase 5 — Sticky Headers & Spacing
- Make `Market Intelligence` and `Topic Intelligence` section headers sticky
- Reduce padding/gaps: card padding 18→12px, gap 16→8px
- Collapsible charts on mobile

## Files Changed
- `~/.hermes/bloomberg-portal/portal-v5.py` (single file, CSS + JS + HTML)

## Verification
1. Reload Intel tab at http://100.98.169.12:5055
2. Check ticker strip appears at top
3. Check stat cards show sparklines + delta text
4. Check topic cards are compact with heat bars
5. Check filter/sort bar works
6. Check sticky headers stay put on scroll
7. Restart server after changes

## Excluded (per user)
- Animation/micro-interactions (Section 5 of WB brief)
- Load choreography, hover transitions, sparkline draw animation
