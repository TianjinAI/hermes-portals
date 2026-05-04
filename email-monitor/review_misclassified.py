#!/usr/bin/env python3
"""
Review misclassified emails flagged by the user.

Usage:
  python3 review_misclassified.py list           # Show un-reviewed flagged emails
  python3 review_misclassified.py auto-review    # Auto-create domain rules for flagged emails
  python3 review_misclassified.py fix <id> <category> [--create-rule sender|domain]
                                                  # Manually fix one flagged email

The misclassified_emails table stores emails the user checked as mislabeled.
When the agent reviews them, it should:
1. Analyze the subject/sender/body to determine the correct category
2. Create a user_rules entry for the sender (or domain)
3. Update the email's category in the emails table
4. Mark as reviewed with new_category set
"""

import sqlite3
import sys
import os
from pathlib import Path

DB_PATH = str(Path.home() / ".hermes" / "email-monitor" / "emails.db")
VALID_CATEGORIES = ['urgent', 'important', 'normal', 'newsletter', 'spam']


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def list_flagged():
    """List all un-reviewed flagged emails with sender info."""
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT m.id, m.email_id, m.subject, m.sender_email, 
               m.original_category, m.urgency_score, m.flagged_at,
               e.account, e.category as current_category
        FROM misclassified_emails m
        LEFT JOIN emails e ON m.email_id = e.email_id
        WHERE m.reviewed = 0
        ORDER BY m.flagged_at DESC
    """)
    rows = cursor.fetchall()
    conn.close()

    if not rows:
        print("No un-reviewed flagged emails.")
        return

    print(f"Found {len(rows)} un-reviewed flagged email(s):\n")
    for r in rows:
        print(f"  ID:            {r['id']}")
        print(f"  Email ID:      {r['email_id']}")
        print(f"  Subject:       {r['subject'][:100]}")
        print(f"  Sender:        {r['sender_email']}")
        print(f"  Account:       {r['account'] or '?'}")
        print(f"  Current Cat:   {r['current_category'] or '?'}")
        print(f"  Original Cat:  {r['original_category']}")
        print(f"  Urgency Score: {r['urgency_score']}")
        print(f"  Flagged At:    {r['flagged_at']}")
        print()


def mark_reviewed(flagged_id, new_category, rule_type, rule_value):
    """Mark a flagged email as reviewed and set its new category."""
    conn = get_conn()
    cursor = conn.cursor()

    # Get the email_id
    cursor.execute("SELECT email_id, sender_email FROM misclassified_emails WHERE id = ?", (flagged_id,))
    row = cursor.fetchone()
    if not row:
        print(f"Error: Flagged entry {flagged_id} not found.")
        conn.close()
        return False

    email_id = row['email_id']
    sender_email = row['sender_email']

    # Update the email's category in emails table
    cursor.execute("UPDATE emails SET category = ? WHERE email_id = ?", (new_category, email_id))
    print(f"  ✓ Updated email {email_id} category → {new_category}")

    # Create rule if requested
    rule_created_id = None
    if rule_type and rule_value:
        try:
            cursor.execute("""
                INSERT OR REPLACE INTO user_rules (rule_type, rule_value, category, created_at, hit_count)
                VALUES (?, ?, ?, datetime('now'), 0)
            """, (rule_type, rule_value, new_category))
            rule_created_id = cursor.lastrowid
            print(f"  ✓ Created {rule_type} rule '{rule_value}' → {new_category} (ID: {rule_created_id})")
        except Exception as e:
            print(f"  ⚠ Rule creation failed: {e}")

    # Mark as reviewed
    cursor.execute("""
        UPDATE misclassified_emails 
        SET reviewed = 1, new_category = ?
        WHERE id = ?
    """, (new_category, flagged_id))
    conn.commit()
    conn.close()
    print(f"  ✓ Marked flagged entry {flagged_id} as reviewed")
    return True


def auto_review():
    """
    Auto-review flagged emails by creating domain-level rules.
    For each un-reviewed flagged email, this creates a sender rule
    with the opposite category thrust (newsletter for non-urgent stuff).
    
    This is a conservative approach — the agent should override these
    decisions with smarter analysis, but this provides a baseline.
    """
    conn = get_conn()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT m.id, m.email_id, m.subject, m.sender_email, 
               m.original_category,
               e.body, e.account
        FROM misclassified_emails m
        LEFT JOIN emails e ON m.email_id = e.email_id
        WHERE m.reviewed = 0
        ORDER BY m.flagged_at DESC
    """)
    rows = cursor.fetchall()
    conn.close()

    if not rows:
        print("No un-reviewed flagged emails.")
        return

    print(f"Auto-reviewing {len(rows)} flagged emails...\n")
    for r in rows:
        print(f"--- Entry #{r['id']}: {r['subject'][:80]} ---")
        print(f"  Sender: {r['sender_email']}")
        print(f"  Original: {r['original_category']}")

        # Decide: if original was 'urgent' and user flagged it,
        # it's likely 'newsletter' (most common case for mis-flagged)
        sender_email = r['sender_email'] or ''
        domain = ''
        if '@' in sender_email:
            domain = sender_email.split('@')[1]

        new_cat = 'newsletter'  # default assumption for urgent→mislabeled
        rule_type = 'sender'
        rule_value = sender_email

        if new_cat != r['original_category']:
            mark_reviewed(r['id'], new_cat, rule_type, rule_value)
        else:
            # Same category doesn't make sense — just mark reviewed
            mark_reviewed(r['id'], new_cat, None, None)
        print()


def fix_one(flagged_id, new_category, create_rule=None):
    """Fix one flagged email by ID with explicit category override."""
    if new_category not in VALID_CATEGORIES:
        print(f"Invalid category: {new_category}. Valid: {', '.join(VALID_CATEGORIES)}")
        sys.exit(1)

    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT m.email_id, m.sender_email
        FROM misclassified_emails m
        WHERE m.id = ? AND m.reviewed = 0
    """, (flagged_id,))
    row = cursor.fetchone()
    conn.close()

    if not row:
        print(f"Flagged entry {flagged_id} not found or already reviewed.")
        return

    sender_email = row['sender_email'] or ''
    domain = ''
    if '@' in sender_email:
        domain = sender_email.split('@')[1]

    if create_rule == 'sender':
        mark_reviewed(flagged_id, new_category, 'sender', sender_email)
    elif create_rule == 'domain':
        mark_reviewed(flagged_id, new_category, 'domain', domain)
    else:
        mark_reviewed(flagged_id, new_category, None, None)


if __name__ == '__main__':
    if len(sys.argv) < 2:
        list_flagged()
        sys.exit(0)

    command = sys.argv[1]

    if command == 'list':
        list_flagged()
    elif command == 'auto-review':
        auto_review()
    elif command == 'fix' and len(sys.argv) >= 4:
        flagged_id = int(sys.argv[2])
        new_category = sys.argv[3]
        create_rule = None
        if '--create-rule' in sys.argv:
            idx = sys.argv.index('--create-rule')
            if idx + 1 < len(sys.argv):
                create_rule = sys.argv[idx + 1]
        fix_one(flagged_id, new_category, create_rule)
    else:
        print(f"Unknown command: {command}")
        print(__doc__)
        sys.exit(1)
