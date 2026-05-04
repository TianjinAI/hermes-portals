# Hermes Portals — Master Documentation

**A collection of 6 intelligent web portals running on the Hermes VPS**

| Port | Portal | Purpose | Status |
|------|--------|---------|--------|
| 5052 | Email Monitor | Email categorization + learning rules | Production |
| 5053 | Governance Dashboard | Project governance + orchestration | Production |
| 5054 | Readwise Review | Knowledge review + Obsidian sync | Production |
| 5055 | Bloomberg Portal v5 | Newsletter digest + intelligence hub | Production |
| 5056 | Intelligence Hub | Cumulative knowledge dashboard | Production |
| 5057 | VPS Monitor | System stats + token usage tracking | Production |

---

## Architecture Overview

All portals follow a common pattern:
- **Python HTTP server** (BaseHTTPRequestHandler or Flask)
- **SQLite database** for state persistence
- **Static HTML/CSS/JS** for frontend (no build step)
- **REST API endpoints** for data fetching
- **Dark theme** design (consistent across all portals)

### Shared Infrastructure

```
VPS (Alibaba Cloud Alinux 3)
├── /home/admin/.hermes/
│   ├── email-monitor/     → Port 5052
│   ├── governance/        → Port 5053
│   ├── readwise_review/   → Port 5054
│   ├── bloomberg-portal/  → Port 5055
│   ├── bloomberg_digest/  → Data pipeline for 5055
│   ├── bloomberg_portal/  → Port 5056 (Intel Hub)
│   └── vps-monitor/       → Port 5057
│   ├── docs/              → Documentation
│   └── logs/              → Portal logs
│   └── alerts/            → Alert storage
└── systemd services:
    ├── email-portal.service
    ├── bloomberg-portal.service (raw Python process)
    ├── hermes-watchdog.timer (every 2 min)
```

---

## Portal Details

### 5052 — Email Monitor Portal

**Directory**: `~/.hermes/email-monitor/`

**Purpose**: Intelligent email monitoring with learning-based categorization.

**Key Features**:
- Auto-categorization (Urgent, Important, Normal, Newsletter, Spam)
- Learning system: user corrections create persistent rules
- Multi-account support via Himalaya CLI
- Telegram notifications for urgent emails
- Hit count tracking for rule effectiveness

**Architecture**:
```
Himalaya CLI → fetch emails → SQLite (emails.db)
                                    ↓
Web Portal (web_portal_v3.py) ← REST API
                                    ↓
User re-categorizes → rule created → future emails auto-fixed
```

**Skills**: `email/himalaya`, `email/email-monitor-ops`

**Cron Jobs**:
- `email-monitor-hourly` (4x daily: 21:00, 01:00, 05:00, 09:00 CST)
- `misclassify-review` (every 2 hours)

**Files**:
- `web_portal_v3.py` — Portal server (86KB)
- `email_monitor.py` — Email fetching + categorization
- `emails.db` — SQLite database (6.4MB, 1390 emails)
- `review_misclassified.py` — Misclassification review handler

---

### 5053 — Governance Dashboard

**Directory**: `~/.hermes/governance/`

**Purpose**: Project governance, orchestration, and workflow management.

**Key Features**:
- governed-dev 8-stage workflow visualization
- Kanban board integration
- Agent delegation tracking
- Project status overview

**Architecture**:
- Single-file Python portal (`portal.py`)
- Dashboard HTML with dark theme
- Course-tutor and dashboard submodules

**Skills**: `kanban-orchestrator`, `subagent-driven-development`

---

### 5054 — Readwise Review Portal

**Directory**: `~/.hermes/readwise_review/`

**Purpose**: Review Readwise Reader highlights → Obsidian sync pipeline.

**Key Features**:
- Interactive review queue
- LLM-powered summarization
- QC check integration
- Obsidian vault sync
- YouTube transcript handling

**Architecture**:
```
Readwise Reader API → export → state.json
                                    ↓
Review Portal (server.py) ← user reviews
                                    ↓
generate_llmwiki.py → summaries → Obsidian Second_Brain/
```

**Skills**: `readwise-obsidian-pipeline`, `llm-wiki`

**Cron Jobs**:
- `readwise-obsidian-sync` (4x daily: 20:00, 22:00, 00:00, 02:00 CST)

**Files**:
- `server.py` — Portal server (10KB)
- `pipeline.py` — Full pipeline orchestration
- `generate_llmwiki.py` — LLM summarization
- `qc_check.py` — Quality check validation
- `state.json` — Review state (1.1MB)

---

### 5055 — Bloomberg Portal v5

**Directory**: `~/.hermes/bloomberg-portal/`

**Purpose**: Daily Bloomberg newsletter digest with cumulative intelligence.

**Key Features**:
- **Brief view**: Ranked headlines for quick scan
- **Full view**: Per-newsletter cards with attribution
- **Intel view**: Entity/theme extraction, trend analysis
- **DD view**: Deep dive on specific topics
- **KB view**: Cumulative knowledge base
- **MM view**: MacroMicro primer integration

**Architecture**:
```
Gmail (bamboo.ocean) → Himalaya → raw emails
                                    ↓
bloomberg_digest.py → 2-stage LLM → summaries
                                    ↓
                        deduplication → merged stories
                                    ↓
Portal (portal-v5.py) ← JSON files ← knowledge_base.json
```

**Skills**: `email/bloomberg-digest`, `bloomberg-intelligence-hub`

**Cron Jobs**:
- `Bloomberg Daily Digest` (3x daily: 20:00, 02:00, 08:00 CST)
- `Bloomberg Portal Intel Refresh` (5 min after each digest)
- `MM Primer Daily Refresh` (22:00 CST)

**Files**:
- `portal-v5.py` — Portal server (130KB, 6 views)
- `bloomberg_digest.py` — Digest pipeline (41KB)
- `macromicro_primer.md` — MacroMicro context (35KB)

**Data Flow**:
- `raw/` — Cleaned email text
- `summaries/` — Stage 1 LLM outputs
- `briefs/` — Telegram-ready markdown
- `full/` — Full HTML with cards
- `intel/` — Intelligence reports
- `knowledge/knowledge_base.json` — Cumulative entities/themes

---

### 5056 — Intelligence Hub

**Directory**: `~/.hermes/bloomberg_portal/`

**Purpose**: Cumulative intelligence dashboard for Bloomberg analysis.

**Key Features**:
- Cross-day entity tracking
- Theme frequency analysis
- Reporter network visualization
- Sentiment scoring

**Architecture**:
- Shares data with Bloomberg Portal v5
- Standalone portal for intelligence-focused view
- Entity/theme extraction from `knowledge_base.json`

---

### 5057 — VPS Monitor

**Directory**: `~/.hermes/vps-monitor/`

**Purpose**: Real-time system monitoring + LLM token usage tracking.

**Key Features**:
- **System Stats**: Memory, CPU, disk, top processes
- **Token Usage**: Monthly plans vs PAYG costs
- **ChatGPT Plus**: Message quota tracking via OAuth
- **OpenCode Stats**: CLI usage aggregation
- **Theme Toggle**: Dark/light mode

**Architecture**:
```
Hermes LLM calls → usage-tracker plugin → usage.db
                                            ↓
VPS Monitor (server.py) ← REST API (/api/usage)
                                            ↓
index.html renders cards → 15s polling
```

**Skills**: `devops/vps-monitor`

**API Endpoints**:
- `/api/stats` — System stats (3s polling)
- `/api/usage` — Token usage (15s polling)
- `/api/usage/reset` — Clear usage data

**Files**:
- `server.py` — Portal server (13KB)
- `index.html` — Dashboard frontend (21KB)
- `usage.db` — Usage database (143KB)

---

## Cron Jobs Summary

| Job ID | Name | Schedule | Purpose |
|--------|------|----------|---------|
| `087bcbb32507` | Bloomberg Daily Digest | 20:00, 02:00, 08:00 | Newsletter processing |
| `2bc874e8a727` | Intel Refresh | 5 min after digest | Portal intel update |
| `58ccec08e09a` | MM Primer Refresh | 22:00 daily | MacroMicro primer |
| `04c84d28c409` | email-monitor-hourly | 4x daily | Email fetching |
| `63382c79ed2b` | misclassify-review | Every 2h | Rule review |
| `3b39d1480cca` | readwise-obsidian-sync | 4x daily | Knowledge sync |
| `d47536564fa5` | Daily AI Headline News | 07:00 | News aggregation |
| `18cf4d4f7f7d` | Weekly Intel Report | Fri 20:00 | Weekly analysis |

---

## Watchdog System

**Directory**: `~/.hermes/watchdog/`

**Components**:
- `hermes-gateway-watchdog-enhanced` — Enhanced watchdog script
- `hermes-watchdog.service` — systemd service
- `hermes-watchdog.timer` — systemd timer (every 2 min)

**Functions**:
1. DNS health check before platform checks
2. Gateway restart with cooldown (120s)
3. systemd `reset-failed` to clear restart limits
4. Alert logging to multiple destinations
5. Webhook notification support

**Alert Locations**:
- `/home/admin/.hermes/alerts/alerts.log`
- `/home/admin/.hermes/alerts/critical_alerts.log`
- `/home/admin/.hermes/alerts/latest_alert`
- `journalctl -t hermes-alert`

---

## Design Principles

1. **Single-file Python portals** — Easy to deploy, no build step
2. **SQLite for persistence** — Local, fast, no external DB needed
3. **Dark theme consistency** — All portals share CSS variables
4. **REST API pattern** — `/api/...` endpoints for data
5. **Cron-driven pipelines** — Automated data collection
6. **Skill integration** — Each portal has companion Hermes skill

---

## Troubleshooting

**Portal not responding**:
```bash
ss -tlnp | grep 505X
fuser -k 505X/tcp
cd ~/.hermes/<portal-dir> && python3 <server.py> &
```

**Data not updating**:
```bash
cronjob list  # Check job status
cronjob run --job-id <ID>  # Manual trigger
```

**DNS issues**:
```bash
resolvectl status
cat /etc/systemd/resolved.conf
```

---

## Future Enhancements

- [ ] Unified authentication across portals
- [ ] Central logging dashboard
- [ ] Prometheus metrics export
- [ ] Obsidian vault browser portal
- [ ] Cross-portal search

---

**Documented by**: Hermes Agent (翠鸟)
**Date**: May 5, 2026
**Version**: 1.0