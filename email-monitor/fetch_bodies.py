#!/usr/bin/env python3
"""Fetch email bodies for all existing emails in the database."""

import sqlite3
import subprocess
from pathlib import Path
from datetime import datetime

DB_PATH = Path("~/.hermes/email-monitor/emails.db").expanduser()
HIMALAYA_PATH = Path("~/.local/bin/himalaya").expanduser()

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def read_email_body(account, email_id):
    """Read the body of a specific email using Himalaya."""
    result = subprocess.run(
        [str(HIMALAYA_PATH), "message", "read", str(email_id), "--account", account],
        capture_output=True,
        text=True,
        timeout=30
    )
    if result.returncode != 0:
        return ""
    return result.stdout

def fetch_all_bodies():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Get all emails without body
    cursor.execute("""
        SELECT email_id, account, subject 
        FROM emails 
        WHERE body IS NULL OR body = ''
        ORDER BY account, date DESC
    """)
    
    emails = cursor.fetchall()
    print(f"Found {len(emails)} emails without body")
    
    updated = 0
    failed = 0
    
    for i, row in enumerate(emails, 1):
        email_id = row['email_id']
        account = row['account']
        subject = row['subject'][:50]
        
        print(f"[{i}/{len(emails)}] Fetching body for {account}/{email_id}: {subject}...")
        
        body = read_email_body(account, email_id)
        
        if body:
            cursor.execute(
                "UPDATE emails SET body = ? WHERE email_id = ? AND account = ?",
                (body[:5000], email_id, account)
            )
            conn.commit()
            updated += 1
            print(f"  ✓ Body fetched ({len(body)} chars)")
        else:
            failed += 1
            print(f"  ✗ Failed to fetch body")
    
    conn.close()
    print(f"\nDone! Updated {updated} emails, failed {failed}")

if __name__ == "__main__":
    fetch_all_bodies()
