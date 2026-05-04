# Hermes Portals

A unified collection of 6 intelligent web portals for the Hermes Agent ecosystem.

## Portals

| Portal | Port | Description |
|--------|------|-------------|
| **email-monitor** | 5052 | Email categorization with learning rules |
| **bloomberg-portal** | 5055 | Bloomberg newsletter digest + intelligence hub |
| **bloomberg-digest** | - | Backend pipeline for Bloomberg portal |
| **readwise-review** | 5054 | Readwise → Obsidian knowledge sync |
| **vps-monitor** | 5057 | System stats + LLM token usage dashboard |
| **governance** | 5053 | Project orchestration dashboard |

## Quick Start

Each portal is a standalone Python HTTP server:

```bash
# Run any portal
cd hermes-portals/<portal-name>
python3 server.py  # or portal.py
```

## Architecture

- **Single-file Python portals** — No build step, easy deployment
- **SQLite persistence** — Local, fast, no external DB
- **Dark theme** — Consistent CSS across all portals
- **REST API** —  endpoints for data fetching
- **Cron-driven pipelines** — Automated data collection

## Documentation

See [docs/PORTALS_MASTER.md](docs/PORTALS_MASTER.md) for full architecture, cron jobs, and troubleshooting.

## License

MIT

## Author

Hermes Agent (翠鸟) — Shaobin Sun
