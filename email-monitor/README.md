# Email Portal

An intelligent email monitoring dashboard that learns from your corrections. Fetches emails via IMAP, auto-categorizes them, and improves over time based on your re-categorization rules.

![Features](https://img.shields.io/badge/features-auto--categorization%20%7C%20learning%20rules%20%7C%20telegram%20alerts-blue)
![Stack](https://img.shields.io/badge/stack-python%20%7C%20flask%20%7C%20sqlite-green)

## Features

- **Auto-Categorization**: Automatically sorts emails into Urgent, Important, Normal, Newsletter, or Spam
- **Learning System**: When you re-categorize an email, create persistent rules that apply to future emails from the same sender/domain/subject
- **Multi-Account Support**: Monitor multiple email accounts via Himalaya CLI
- **Web Dashboard**: Clean, responsive UI for browsing and managing emails
- **Telegram Notifications**: Get alerts for urgent emails delivered to your phone
- **Hit Count Tracking**: Rules are sorted by usage so effective rules bubble up
- **Full Privacy**: All data stays local (SQLite), no cloud services

## How the Learning Works

1. **Initial Classification**: New emails are auto-categorized based on keywords, sender domains, and heuristics
2. **User Correction**: You click an email and re-categorize it (e.g., move from "Urgent" to "Newsletter")
3. **Rule Creation**: The UI offers to "Create a rule for future emails" - choose sender, domain, or subject pattern
4. **Future Emails**: Matching emails are automatically categorized correctly before any auto-classification runs

### Rule Types

| Type | Example | Matches |
|------|---------|---------|
| `sender` | `news@bloomberg.com` | Exact email address |
| `domain` | `bloomberg.com` | All emails from that domain |
| `subject_contains` | `Daily Brief` | Subjects containing the text |
| `subject_regex` | `^\[PR\]` | Subjects matching regex pattern |

## Installation

### Prerequisites

- Python 3.11+
- [Himalaya](https://github.com/soywod/himalaya) CLI configured with your email accounts
- Telegram (optional, for notifications)

### Setup

```bash
# Clone the repo
git clone https://github.com/TianjinAI/email_portal.git
cd email_portal

# Install dependencies (Flask only, stdlib for rest)
pip install flask

# Configure your Himalaya accounts in email_monitor.py
# Edit line 18: accounts = ["your-account-1", "your-account-2"]

# Initialize the database
python3 -c "from email_monitor import init_database; init_database()"

# Start the web portal
python3 web_portal_v3.py
```

The portal runs on http://localhost:5052

## Configuration

### Email Accounts

Edit `email_monitor.py` line 18:
```python
"accounts": ["gmail-work", "yahoo-personal"],  # Your Himalaya account names
```

### Auto-Categorization Keywords

Customize in `email_monitor.py`:
```python
"urgency_keywords": ["bill", "invoice", "deadline", ...],
"urgency_senders": ["stripe", "amazon", "bank", ...],
"newsletter_domains": ["substack.com", "medium.com", ...],
```

### Telegram Notifications

Set your target in `telegram_notify.py` or via environment:
```bash
export TELEGRAM_TARGET="telegram:Your Name (dm)"
```

## Usage

### Web Dashboard

1. Open http://localhost:5052
2. Browse emails by category (All, Urgent, Important, Normal, Newsletter, Spam)
3. Click any email to expand and see full body
4. Use re-categorize buttons to fix mis-categorized emails
5. Click "Create Rule" to make the correction permanent

### API Endpoints

```bash
# List all user-created rules
GET /api/rules

# Create a new rule
POST /api/rules
Body: {"rule_type": "domain", "rule_value": "bloomberg.com", "category": "newsletter"}

# Test which rules match an email
GET /api/rules/test?sender_email=test@example.com&subject=Hello

# Delete a rule
DELETE /api/rules/<id>

# Re-categorize an email
POST /api/email/<id>/category
Body: {"category": "urgent"}
```

### Running the Monitor

```bash
# Fetch new emails and notify for urgent ones
python3 email_monitor.py

# Or use the convenience script
./run_monitor.sh
```

Set up a cron job to run every hour:
```bash
0 * * * * cd /path/to/email_portal && python3 email_monitor.py >> cron.log 2>&1
```

## Architecture

```
┌─────────────────┐     ┌──────────────┐     ┌─────────────┐
│   Himalaya CLI  │────▶│  email_monitor│────▶│  SQLite DB  │
│   (IMAP fetch)  │     │  (classify)   │     │ (emails.db) │
└─────────────────┘     └──────────────┘     └──────┬──────┘
                                                    │
                           ┌────────────────────────┘
                           ▼
                    ┌──────────────┐
                    │  web_portal  │◀── Browser UI
                    │   (Flask)    │◀── API calls
                    └──────────────┘
                           │
                           ▼
                    ┌──────────────┐
                    │ Telegram API │──▶ Mobile notifications
                    └──────────────┘
```

## Database Schema

```sql
-- Emails table
CREATE TABLE emails (
    id INTEGER PRIMARY KEY,
    account TEXT,
    message_id TEXT UNIQUE,
    sender_email TEXT,
    sender_name TEXT,
    subject TEXT,
    body TEXT,
    category TEXT,  -- urgent|important|normal|newsletter|spam
    received_at TEXT,
    is_read BOOLEAN
);

-- User-defined categorization rules
CREATE TABLE user_rules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    rule_type TEXT NOT NULL,     -- 'sender'|'domain'|'subject_contains'|'subject_regex'
    rule_value TEXT NOT NULL,
    category TEXT NOT NULL,
    created_at TEXT,
    hit_count INTEGER DEFAULT 0,  -- How many times this rule matched
    UNIQUE(rule_type, rule_value)
);
```

## Why This Approach?

- **No OAuth complexity**: Uses Himalaya CLI (IMAP) instead of Gmail API
- **No external dependencies**: Pure Python stdlib + Flask only
- **Privacy-first**: All data stays on your machine
- **Hackable**: Simple SQLite schema, easy to query/extend
- **Fast**: Local processing, no network latency for classification

## License

MIT

## Contributing

Pull requests welcome! Focus areas:
- Better classification heuristics
- Additional notification channels
- Web UI improvements
- Rule analytics dashboard
