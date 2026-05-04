#!/usr/bin/env python3
"""
Email Monitor - Fetches emails via Himalaya, classifies them, and notifies for urgent items.
"""

import json
import subprocess
import sqlite3
import re
import os
import urllib.request
import urllib.error
from datetime import datetime, timedelta
from pathlib import Path

# Configuration
CONFIG = {
    "himalaya_path": "~/.local/bin/himalaya",
    "db_path": "~/.hermes/email-monitor/emails.db",
    "accounts": ["bamboo.ocean", "meditation", "raintea"],  # Himalaya account names
    "urgency_keywords": [
        "bill", "invoice", "payment", "due", "urgent", "action required",
        "deadline", "expire", "expiration", "security alert", "alert",
        "confirm", "verification", "password", "account", "suspended",
        "policy", "document", "legal", "court", "tax", "refund"
    ],
    "urgency_senders": [
        "anthropic", "stripe", "amazon", "google", "yahoo", "apple",
        "bank", "credit", "utility", "electric", "gas", "water",
        "insurance", "policy", "tax", "government", "court",
        "corebridge", "fitbit", "gamma"
    ],
    "newsletter_domains": [
        "substack.com", "medium.com", "bloomberg.com", "deeplearning.ai",
        "notion.so", "a16z.com", "ghost.io", "mailchimp",
        "convertkit", "sendgrid", "sparkpost", "amazonses",
        "trulyrecipes.com", "happyglowwin", "glowhopefun",
        "yh2569.com", "odontocotta.com", "mcknd5.com", "h2y-uae.com",
        "smartjoyhope", "fastsmartcool", "lifeonaire",
        "cfainstitute.org", "axios.com", "politico.com",
        "nytimes.com", "wsj.com", "ft.com",
        "reuters.com", "theinformation.com", "semafor.com",
        "theverge.com", "wired.com", "technologyreview.com",
        "nybooks.com", "economist.com", "hbr.org",
        "expedia.com", "tripadvisor.com", "zerohedge.com",
        "fitbit.com", "nextdoor.com",
        "yahoogroups.com", "google.com", "mail.google.com",
        "readwise.io", "readwise.net",
        "youmayknow.com"
    ],
    "spam_indicators": [
        "75% off", "free trial", "limited time", "act now",
        "don't miss", "exclusive offer", "special discount",
        "your quote", "carpet", "flooring", "lawsuit",
        "warranty", "dental implant", "lawn care", "term life"
    ]
}

def get_himalaya_path():
    return Path(CONFIG["himalaya_path"]).expanduser()

def get_db_path():
    return Path(CONFIG["db_path"]).expanduser()

def get_user_rule_category(sender_email, sender_name, subject):
    """Check user-defined rules for email categorization. Returns (category, rule_id) or (None, None)."""
    db_path = get_db_path()
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    sender_email_lower = sender_email.lower()
    sender_name_lower = sender_name.lower()
    subject_lower = subject.lower()
    
    # Extract domain from email
    domain = ""
    if "@" in sender_email_lower:
        domain = sender_email_lower.split("@")[1]
    
    # Check rules in priority order
    # 1. Exact sender email match
    cursor.execute(
        "SELECT id, category FROM user_rules WHERE rule_type = 'sender' AND LOWER(rule_value) = ?",
        (sender_email_lower,)
    )
    row = cursor.fetchone()
    if row:
        cursor.execute("UPDATE user_rules SET hit_count = hit_count + 1 WHERE id = ?", (row[0],))
        conn.commit()
        conn.close()
        return row[1], row[0]
    
    # 2. Domain match (suffix-based: rule "bloomberg.com" matches "news.bloomberg.com")
    domain_result = None
    if domain:
        cursor.execute(
            "SELECT id, category, rule_value FROM user_rules WHERE rule_type = 'domain'"
        )
        for row in cursor.fetchall():
            rule_domain = row[2].lower()
            if domain == rule_domain or domain.endswith('.' + rule_domain):
                domain_result = (row[0], row[1])
                break
    
    # 3. Subject contains — checked BEFORE returning domain result
    cursor.execute(
        "SELECT id, category, rule_value FROM user_rules WHERE rule_type = 'subject_contains'"
    )
    # Subject urgent/important overrides domain newsletter/spam
    PRIORITY = {"urgent": 3, "important": 2, "normal": 1, "newsletter": 0, "spam": 0}
    for row in cursor.fetchall():
        if row[2].lower() in subject_lower:
            # If subject rule is higher priority than domain rule, use it
            if domain_result is None or PRIORITY.get(row[1], 0) > PRIORITY.get(domain_result[1], 0):
                cursor.execute("UPDATE user_rules SET hit_count = hit_count + 1 WHERE id = ?", (row[0],))
                conn.commit()
                conn.close()
                return row[1], row[0]
            # Otherwise subject matched but domain is same or higher priority — fall through
    
    # No subject override — return domain result if any
    if domain_result:
        cursor.execute("UPDATE user_rules SET hit_count = hit_count + 1 WHERE id = ?", (domain_result[0],))
        conn.commit()
        conn.close()
        return domain_result[1], domain_result[0]
    
    conn.close()
    return None, None

def init_database():
    """Initialize SQLite database for email storage."""
    db_path = get_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS emails (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email_id TEXT NOT NULL,
            account TEXT NOT NULL,
            subject TEXT,
            sender_name TEXT,
            sender_email TEXT,
            date TEXT,
            flags TEXT,
            has_attachment INTEGER,
            body TEXT,
            category TEXT DEFAULT 'unknown',
            urgency_score INTEGER DEFAULT 0,
            processed_at TEXT,
            notified INTEGER DEFAULT 0,
            UNIQUE(email_id, account)
        )
    """)
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS digest_queue (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email_id TEXT NOT NULL,
            account TEXT NOT NULL,
            subject TEXT,
            sender_name TEXT,
            sender_email TEXT,
            date TEXT,
            queued_at TEXT,
            FOREIGN KEY (email_id, account) REFERENCES emails(email_id, account)
        )
    """)
    
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_emails_date ON emails(date)
    """)
    
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_emails_category ON emails(category)
    """)
    
    # User-defined categorization rules
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_rules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            rule_type TEXT NOT NULL,  -- 'sender', 'domain', 'subject_contains', 'subject_regex'
            rule_value TEXT NOT NULL,
            category TEXT NOT NULL,  -- 'urgent', 'important', 'normal', 'newsletter', 'spam'
            created_at TEXT,
            hit_count INTEGER DEFAULT 0,
            UNIQUE(rule_type, rule_value)
        )
    """)
    
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_user_rules_type ON user_rules(rule_type)
    """)
    
    conn.commit()
    conn.close()
    print(f"Database initialized at {db_path}")

def fetch_emails(account):
    """Fetch emails from Himalaya for a given account."""
    himalaya = get_himalaya_path()
    
    # Get emails from last 24 hours
    result = subprocess.run(
        [str(himalaya), "envelope", "list", "--account", account, 
         "--page-size", "50", "--output", "json"],
        capture_output=True, text=True, timeout=60
    )
    
    if result.returncode != 0:
        print(f"Error fetching emails for {account}: {result.stderr}")
        return []
    
    # Parse JSON output
    try:
        emails = json.loads(result.stdout)
        return emails if isinstance(emails, list) else []
    except json.JSONDecodeError:
        print(f"Error parsing JSON for {account}")
        return []

def read_email_body(account, email_id):
    """Read the body of a specific email."""
    himalaya = get_himalaya_path()
    
    result = subprocess.run(
        [str(himalaya), "message", "read", "--account", account, str(email_id)],
        capture_output=True, text=True, timeout=30
    )
    
    if result.returncode != 0:
        return ""
    
    return result.stdout

def classify_email(email, body=""):
    """Classify an email as urgent, newsletter, spam, or normal."""
    subject = email.get("subject", "") or ""
    sender_email = ((email.get("from") or {}).get("addr") or "").lower()
    sender_name = ((email.get("from") or {}).get("name") or "").lower()
    
    # First, check user-defined rules
    user_category, rule_id = get_user_rule_category(sender_email, sender_name, subject)
    if user_category:
        return user_category, 0  # User rules override auto-classification
    
    # Combine all text for analysis
    all_text = f"{subject} {sender_email} {sender_name} {body}".lower()
    subject_lower = subject.lower()
    
    urgency_score = 0
    category = "normal"
    
    # Check for newsletter domains
    for domain in CONFIG["newsletter_domains"]:
        if domain in sender_email:
            category = "newsletter"
            break
    
    # Check for spam indicators
    if category == "normal":
        for indicator in CONFIG["spam_indicators"]:
            if indicator.lower() in all_text:
                category = "spam"
                urgency_score = -1
                break
    
    # Check for urgency keywords
    was_newsletter = False
    if category != "spam":
        for keyword in CONFIG["urgency_keywords"]:
            if keyword.lower() in all_text:
                urgency_score += 2
        
        # Check for urgency senders
        for sender in CONFIG["urgency_senders"]:
            if sender.lower() in sender_email or sender.lower() in sender_name:
                urgency_score += 3
        
        # Security alerts are always urgent
        if "security alert" in all_text or "account" in all_text and "action" in all_text:
            urgency_score += 5
        
        # Bills and invoices
        if "invoice" in all_text or "receipt" in all_text or "bill" in all_text:
            urgency_score += 4
        
        # Policy documents
        if "policy" in all_text and "document" in all_text:
            urgency_score += 4
    
    # Determine final category based on urgency score
    # Newsletters: only urgent if score is VERY high (≥8, e.g. real bank breach)
    if urgency_score >= 5:
        if category == "newsletter" and urgency_score < 8:
            pass  # Keep as newsletter unless truly urgent (≥8)
        else:
            category = "urgent"
    elif category == "normal" and urgency_score > 0:
        category = "important"
    
    return category, urgency_score

def store_email(email, account, body, category, urgency_score):
    """Store email in database, preserving notified status for existing emails."""
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    
    sender = email.get("from") or {}
    flags = json.dumps(email.get("flags", []))
    email_id = str(email.get("id"))
    
    try:
        # Check if email already exists and get its notified status
        cursor.execute("""
            SELECT notified FROM emails WHERE email_id = ? AND account = ?
        """, (email_id, account))
        existing = cursor.fetchone()
        notified_value = existing[0] if existing else 0
        
        cursor.execute("""
            INSERT OR REPLACE INTO emails 
            (email_id, account, subject, sender_name, sender_email, date, 
             flags, has_attachment, body, category, urgency_score, processed_at, notified)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            email_id,
            account,
            email.get("subject", ""),
            sender.get("name", ""),
            sender.get("addr", ""),
            email.get("date", ""),
            flags,
            int(email.get("has_attachment", False)),
            body,
            category,
            urgency_score,
            datetime.now().isoformat(),
            notified_value
        ))
        
        # Add to digest queue if newsletter
        if category == "newsletter":
            cursor.execute("""
                INSERT OR IGNORE INTO digest_queue 
                (email_id, account, subject, sender_name, sender_email, date, queued_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                str(email.get("id")),
                account,
                email.get("subject", ""),
                sender.get("name", ""),
                sender.get("addr", ""),
                email.get("date", ""),
                datetime.now().isoformat()
            ))
        
        conn.commit()
    except sqlite3.Error as e:
        print(f"Database error: {e}")
    finally:
        conn.close()

def get_unnotified_urgent():
    """Get urgent emails that haven't been notified yet."""
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT email_id, account, subject, sender_name, sender_email, date, urgency_score
        FROM emails 
        WHERE category = 'urgent' AND notified = 0
        ORDER BY urgency_score DESC, date DESC
    """)
    
    results = cursor.fetchall()
    conn.close()
    return results

def mark_as_notified(email_ids):
    """Mark emails as notified."""
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    
    for email_id, account in email_ids:
        cursor.execute("""
            UPDATE emails SET notified = 1 
            WHERE email_id = ? AND account = ?
        """, (email_id, account))
    
    conn.commit()
    conn.close()

def send_telegram_notification(urgent_emails):
    """Send Telegram notification for urgent emails via Bot API."""
    if not urgent_emails:
        return
    
    message = "🚨 *Urgent Emails Detected*\n\n"
    
    for email in urgent_emails[:5]:  # Limit to 5 most urgent
        email_id, account, subject, sender_name, sender_email, date, score = email
        account_short = account.split("@")[0] if "@" in account else account
        
        # Escape MarkdownV2 special chars
        def esc(s):
            return re.sub(r'([_*\[\]()~`>#+\-=|{}.!])', r'\\\1', str(s))
        
        message += f"*[{esc(account_short)}]* {esc(subject)}\n"
        message += f"From: {esc(sender_name)} \\({esc(sender_email)}\\)\n"
        message += f"Date: {esc(date)}\n"
        message += f"Urgency: {score}/10\n\n"
    
    if len(urgent_emails) > 5:
        message += f"\\.\\.\\. and {len(urgent_emails) - 5} more urgent emails\\.\n"
    
    message += "_Check the web portal for full details\\._"
    
    # Load credentials from .env
    env_path = Path("~/.hermes/.env").expanduser()
    bot_token = None
    chat_id = None
    if env_path.exists():
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line.startswith("TELEGRAM_BOT_TOKEN="):
                    bot_token = line.split("=", 1)[1].strip()
                if line.startswith("TELEGRAM_HOME_CHANNEL="):
                    chat_id = line.split("=", 1)[1].strip()
    
    if bot_token and chat_id:
        try:
            url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
            data = json.dumps({
                "chat_id": chat_id,
                "text": message,
                "parse_mode": "MarkdownV2"
            }).encode("utf-8")
            req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
            resp = urllib.request.urlopen(req, timeout=10)
            result = json.loads(resp.read().decode())
            if result.get("ok"):
                print(f"✅ Telegram notification sent for {len(urgent_emails)} urgent emails")
            else:
                print(f"❌ Telegram API error: {result}")
        except Exception as e:
            print(f"❌ Failed to send Telegram notification: {e}")
    else:
        print(f"⚠️ No TELEGRAM_BOT_TOKEN or TELEGRAM_HOME_CHANNEL in .env — skipping notification")
        print(f"Would send:\n{message}")
    
    # Also write to notification file as backup
    notify_path = Path("~/.hermes/email-monitor/notifications").expanduser()
    notify_path.mkdir(parents=True, exist_ok=True)
    with open(notify_path / "urgent_pending.txt", "w") as f:
        f.write(message)

def run_monitor():
    """Main monitoring loop."""
    print(f"\n=== Email Monitor Run: {datetime.now().isoformat()} ===")
    
    # Initialize database
    init_database()
    
    # Fetch and process emails from each account
    for account in CONFIG["accounts"]:
        print(f"\nFetching emails for {account}...")
        emails = fetch_emails(account)
        
        print(f"Found {len(emails)} emails")
        
        for email in emails:
            email_id = email.get("id")
            
            # Read email body for all emails
            body = read_email_body(account, email_id)
            
            # Classify email
            category, urgency_score = classify_email(email, body)
            
            # Store in database
            store_email(email, account, body[:5000], category, urgency_score)
            
            if category == "urgent":
                print(f"  [URGENT] {email.get('subject')}")
            elif category == "newsletter":
                print(f"  [NEWSLETTER] {email.get('subject')}")
    
    # Check for unnotified urgent emails
    urgent = get_unnotified_urgent()
    
    if urgent:
        print(f"\n⚠️ Found {len(urgent)} urgent emails to notify")
        send_telegram_notification(urgent)
        mark_as_notified([(e[0], e[1]) for e in urgent])
    else:
        print("\n✓ No new urgent emails")
    
    print("\n=== Monitor run complete ===")

if __name__ == "__main__":
    run_monitor()