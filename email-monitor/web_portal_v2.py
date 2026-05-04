#!/usr/bin/env python3
"""
Email Monitor Web Portal V2 - Grouped by account, click-to-expand summaries.
"""

from flask import Flask, render_template_string, jsonify, request
import sqlite3
from datetime import datetime, date
from pathlib import Path

app = Flask(__name__)

DB_PATH = str(Path.home() / ".hermes" / "email-monitor" / "emails.db")

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Email Dashboard</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg-primary: #ffffff;
            --bg-secondary: #f7f8fa;
            --bg-card: #ffffff;
            --text-primary: #1a1a2e;
            --text-secondary: #4a5568;
            --text-muted: #a0aec0;
            --border-light: #e8ecf0;
            --accent-blue: #4299e1;
            --urgent-red: #e53e3e;
            --urgent-bg: #fff5f5;
            --important-orange: #ed8936;
            --important-bg: #fffaf0;
            --newsletter-green: #48bb78;
            --newsletter-bg: #f0fff4;
            --spam-gray: #718096;
        }
        
        * { margin: 0; padding: 0; box-sizing: border-box; }
        
        body {
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
            background: var(--bg-primary);
            color: var(--text-primary);
            line-height: 1.6;
            min-height: 100vh;
            padding: 0;
        }
        
        /* Sidebar Navigation */
        .sidebar {
            position: fixed;
            left: 0;
            top: 0;
            width: 240px;
            height: 100vh;
            background: var(--bg-secondary);
            border-right: 1px solid var(--border-light);
            padding: 24px 16px;
            display: flex;
            flex-direction: column;
        }
        
        .sidebar-header {
            padding: 0 8px 24px 8px;
            border-bottom: 1px solid var(--border-light);
            margin-bottom: 24px;
        }
        
        .sidebar-title {
            font-size: 20px;
            font-weight: 600;
            color: var(--text-primary);
        }
        
        .sidebar-subtitle {
            font-size: 13px;
            color: var(--text-muted);
            margin-top: 6px;
        }
        
        .nav-section {
            margin-bottom: 32px;
        }
        
        .nav-section-title {
            font-size: 11px;
            font-weight: 600;
            color: var(--text-muted);
            letter-spacing: 0.5px;
            padding: 0 12px;
            margin-bottom: 12px;
            text-transform: uppercase;
        }
        
        .nav-item {
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding: 12px 12px;
            border-radius: 8px;
            font-size: 14px;
            color: var(--text-secondary);
            cursor: pointer;
            transition: all 0.15s ease;
            margin-bottom: 4px;
        }
        
        .nav-item:hover {
            background: rgba(66, 153, 225, 0.1);
        }
        
        .nav-item.active {
            background: var(--accent-blue);
            color: white;
        }
        
        .nav-item.active .nav-count {
            background: rgba(255,255,255,0.25);
            color: white;
        }
        
        .nav-icon {
            width: 20px;
            text-align: center;
        }
        
        .nav-label {
            flex: 1;
            margin-left: 12px;
        }
        
        .nav-count {
            font-size: 12px;
            font-weight: 500;
            padding: 2px 8px;
            border-radius: 12px;
            background: var(--bg-secondary);
            color: var(--text-muted);
        }
        
        .nav-item.urgent { color: var(--urgent-red); }
        .nav-item.urgent .nav-count { background: var(--urgent-bg); color: var(--urgent-red); }
        .nav-item.important { color: var(--important-orange); }
        .nav-item.important .nav-count { background: var(--important-bg); color: var(--important-orange); }
        
        .nav-account {
            font-size: 13px;
            padding: 10px 12px;
        }
        
        .nav-account.gmail .nav-icon::before { content: "📧"; }
        .nav-account.yahoo .nav-icon::before { content: "📮"; }
        
        /* Main Content */
        .main-content {
            margin-left: 240px;
            padding: 32px 48px;
            min-height: 100vh;
            background: var(--bg-primary);
        }
        
        .main-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 24px;
        }
        
        .page-title {
            font-size: 24px;
            font-weight: 600;
            color: var(--text-primary);
        }
        
        .refresh-info {
            font-size: 14px;
            color: var(--text-muted);
            display: flex;
            align-items: center;
            gap: 8px;
        }
        
        .refresh-btn {
            background: var(--accent-blue);
            color: white;
            border: none;
            padding: 6px 12px;
            border-radius: 6px;
            cursor: pointer;
            font-size: 13px;
        }
        
        .refresh-btn:hover {
            background: #3182ce;
        }
        
        .search-container {
            position: relative;
        }
        
        .search-input {
            padding: 12px 16px 12px 44px;
            border: 1px solid var(--border-light);
            border-radius: 10px;
            font-size: 14px;
            width: 300px;
            background: var(--bg-secondary);
            transition: all 0.2s;
        }
        
        .search-input:focus {
            outline: none;
            border-color: var(--accent-blue);
            background: white;
            box-shadow: 0 0 0 3px rgba(66, 153, 225, 0.15);
        }
        
        .search-icon {
            position: absolute;
            left: 16px;
            top: 50%;
            transform: translateY(-50%);
            color: var(--text-muted);
            font-size: 16px;
        }
        
        /* Stats Banner */
        .stats-banner {
            display: flex;
            gap: 24px;
            margin-bottom: 32px;
            padding: 20px 24px;
            background: var(--bg-secondary);
            border-radius: 12px;
        }
        
        .stat-item {
            display: flex;
            align-items: center;
            gap: 12px;
        }
        
        .stat-dot {
            width: 8px;
            height: 8px;
            border-radius: 50%;
        }
        
        .stat-dot.urgent { background: var(--urgent-red); }
        .stat-dot.important { background: var(--important-orange); }
        .stat-dot.newsletter { background: var(--newsletter-green); }
        .stat-dot.spam { background: var(--spam-gray); }
        
        .stat-number {
            font-size: 18px;
            font-weight: 600;
            color: var(--text-primary);
        }
        
        .stat-label {
            font-size: 13px;
            color: var(--text-muted);
        }
        
        /* Account Section */
        .account-section {
            margin-bottom: 32px;
        }
        
        .account-header {
            display: flex;
            align-items: center;
            gap: 12px;
            margin-bottom: 16px;
            padding-bottom: 12px;
            border-bottom: 2px solid var(--border-light);
        }
        
        .account-avatar {
            width: 32px;
            height: 32px;
            border-radius: 8px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 14px;
            font-weight: 600;
            color: white;
        }
        
        .account-avatar.gmail { background: linear-gradient(135deg, #ea4335, #4285f4); }
        .account-avatar.yahoo { background: linear-gradient(135deg, #6001d2, #7b2cbf); }
        
        .account-name {
            font-size: 16px;
            font-weight: 600;
            color: var(--text-primary);
        }
        
        .account-count {
            font-size: 13px;
            color: var(--text-muted);
        }
        
        /* Email List */
        .email-list {
            display: flex;
            flex-direction: column;
            gap: 12px;
        }
        
        .email-card {
            background: var(--bg-card);
            border-radius: 12px;
            padding: 16px 20px;
            border: 1px solid var(--border-light);
            transition: all 0.15s ease;
            cursor: pointer;
        }
        
        .email-card:hover {
            border-color: var(--accent-blue);
            box-shadow: 0 2px 8px rgba(0,0,0,0.06);
        }
        
        .email-card.urgent-card {
            border-left: 4px solid var(--urgent-red);
            background: var(--urgent-bg);
        }
        
        .email-card.important-card {
            border-left: 4px solid var(--important-orange);
            background: var(--important-bg);
        }
        
        .email-card.expanded {
            border-color: var(--accent-blue);
        }
        
        .email-header {
            display: flex;
            align-items: flex-start;
            gap: 16px;
        }
        
        .avatar {
            width: 36px;
            height: 36px;
            border-radius: 8px;
            background: var(--accent-blue);
            color: white;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 14px;
            font-weight: 600;
            flex-shrink: 0;
        }
        
        .email-body {
            flex: 1;
            min-width: 0;
        }
        
        .email-subject {
            font-size: 15px;
            font-weight: 600;
            color: var(--text-primary);
            margin-bottom: 6px;
            line-height: 1.4;
        }
        
        .email-meta {
            display: flex;
            gap: 16px;
            font-size: 13px;
            color: var(--text-secondary);
        }
        
        .email-sender {
            font-weight: 500;
        }
        
        .email-right {
            display: flex;
            flex-direction: column;
            align-items: flex-end;
            gap: 8px;
            min-width: 80px;
        }
        
        .urgency-badge {
            padding: 4px 10px;
            border-radius: 6px;
            font-size: 12px;
            font-weight: 600;
            background: var(--urgent-red);
            color: white;
        }
        
        .urgency-badge.high { background: var(--urgent-red); }
        .urgency-badge.medium { background: var(--important-orange); }
        .urgency-badge.low { background: var(--newsletter-green); }
        
        .email-date {
            font-size: 12px;
            color: var(--text-muted);
        }
        
        .expand-hint {
            font-size: 11px;
            color: var(--text-muted);
            margin-top: 4px;
        }
        
        /* Email Summary (expanded) */
        .email-summary {
            margin-top: 16px;
            padding-top: 16px;
            border-top: 1px solid var(--border-light);
            display: none;
        }
        
        .email-summary.show {
            display: block;
        }
        
        .summary-title {
            font-size: 12px;
            font-weight: 600;
            color: var(--text-muted);
            margin-bottom: 8px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }
        
        .summary-text {
            font-size: 14px;
            color: var(--text-secondary);
            line-height: 1.6;
            white-space: pre-wrap;
        }
        
        .summary-loading {
            color: var(--text-muted);
            font-style: italic;
        }
        
        /* Empty State */
        .empty-state {
            text-align: center;
            padding: 48px 32px;
            color: var(--text-muted);
        }
        
        .empty-icon {
            font-size: 48px;
            margin-bottom: 16px;
            opacity: 0.5;
        }
        
        .empty-text {
            font-size: 15px;
        }
        
        /* Hidden */
        .hidden { display: none; }
        
        /* Mobile Responsive */
        @media (max-width: 1024px) {
            .sidebar {
                width: 200px;
            }
            .main-content {
                margin-left: 200px;
                padding: 24px 32px;
            }
        }
        
        @media (max-width: 768px) {
            .sidebar {
                display: none;
            }
            .main-content {
                margin-left: 0;
                padding: 16px;
            }
            .search-input {
                width: 100%;
            }
            .email-card {
                padding: 14px;
            }
        }
    </style>
</head>
<body>
    <div class="sidebar">
        <div class="sidebar-header">
            <div class="sidebar-title">Inbox</div>
            <div class="sidebar-subtitle">{{ today_date }}</div>
        </div>
        
        <div class="nav-section">
            <div class="nav-section-title">Categories</div>
            
            <div class="nav-item active" onclick="filterCategory('all')" id="nav-all">
                <span class="nav-icon">&#128236;</span>
                <span class="nav-label">All Emails</span>
                <span class="nav-count">{{ total_count }}</span>
            </div>
            
            <div class="nav-item urgent" onclick="filterCategory('urgent')" id="nav-urgent">
                <span class="nav-icon">&#128680;</span>
                <span class="nav-label">Urgent</span>
                <span class="nav-count">{{ stats.urgent }}</span>
            </div>
            
            <div class="nav-item important" onclick="filterCategory('important')" id="nav-important">
                <span class="nav-icon">&#128204;</span>
                <span class="nav-label">Important</span>
                <span class="nav-count">{{ stats.important }}</span>
            </div>
            
            <div class="nav-item" onclick="filterCategory('newsletter')" id="nav-newsletter">
                <span class="nav-icon">&#128240;</span>
                <span class="nav-label">Newsletters</span>
                <span class="nav-count">{{ stats.newsletter }}</span>
            </div>
            
            <div class="nav-item" onclick="filterCategory('spam')" id="nav-spam">
                <span class="nav-icon">&#128465;</span>
                <span class="nav-label">Filtered</span>
                <span class="nav-count">{{ stats.spam }}</span>
            </div>
        </div>
        
        <div class="nav-section">
            <div class="nav-section-title">Accounts</div>
            {% for account in accounts %}
            <div class="nav-item nav-account {{ 'gmail' if 'gmail' in account else 'yahoo' }}" 
                 onclick="filterAccount('{{ account }}')" id="nav-{{ account|replace('@', '_') }}">
                <span class="nav-icon"></span>
                <span class="nav-label">{{ account.split('@')[0] }}</span>
                <span class="nav-count">{{ account_counts.get(account, 0) }}</span>
            </div>
            {% endfor %}
        </div>
        
        <div class="nav-section">
            <div class="nav-section-title">Status</div>
            <div class="nav-item">
                <span class="nav-icon">&#128337;</span>
                <span class="nav-label">Last sync</span>
                <span class="nav-count" style="background: transparent;">{{ last_refresh }}</span>
            </div>
        </div>
    </div>
    
    <div class="main-content">
        <div class="main-header">
            <div>
                <div class="page-title" id="pageTitle">All Emails</div>
                <div class="refresh-info">
                    <span>{{ today_date }}</span>
                    <button class="refresh-btn" onclick="location.reload()">&#8635; Refresh</button>
                </div>
            </div>
            <div class="search-container">
                <span class="search-icon">&#128269;</span>
                <input type="text" class="search-input" placeholder="Search subject or sender..." id="searchInput" onkeyup="filterEmails()">
            </div>
        </div>
        
        <div class="stats-banner" id="statsBanner">
            <div class="stat-item">
                <div class="stat-dot urgent"></div>
                <div class="stat-number">{{ stats.urgent }}</div>
                <div class="stat-label">Urgent</div>
            </div>
            <div class="stat-item">
                <div class="stat-dot important"></div>
                <div class="stat-number">{{ stats.important }}</div>
                <div class="stat-label">Important</div>
            </div>
            <div class="stat-item">
                <div class="stat-dot newsletter"></div>
                <div class="stat-number">{{ stats.newsletter }}</div>
                <div class="stat-label">Newsletters</div>
            </div>
            <div class="stat-item">
                <div class="stat-dot spam"></div>
                <div class="stat-number">{{ stats.spam }}</div>
                <div class="stat-label">Filtered</div>
            </div>
        </div>
        
        <div id="emailContainer">
            {% for account, emails in emails_by_account.items() %}
            <div class="account-section" data-account="{{ account }}">
                <div class="account-header">
                    <div class="account-avatar {{ 'gmail' if 'gmail' in account else 'yahoo' }}">
                        {{ 'G' if 'gmail' in account else 'Y' }}
                    </div>
                    <div class="account-name">{{ account }}</div>
                    <div class="account-count">{{ emails|length }} emails</div>
                </div>
                
                <div class="email-list">
                    {% for email in emails %}
                    <div class="email-card {{ email.category }}-card" 
                         data-category="{{ email.category }}"
                         data-account="{{ account }}"
                         data-email-id="{{ email.email_id }}"
                         data-subject="{{ email.subject|lower }}"
                         data-sender="{{ email.sender_name|lower if email.sender_name else '' }}"
                         onclick="toggleEmail(this)">
                        
                        <div class="email-header">
                            <div class="avatar">
                                {{ email.sender_initial }}
                            </div>
                            
                            <div class="email-body">
                                <div class="email-subject">{{ email.subject }}</div>
                                <div class="email-meta">
                                    <span class="email-sender">{{ email.sender_name or 'Unknown Sender' }}</span>
                                    <span class="email-time">{{ email.time_short }}</span>
                                </div>
                                <div class="expand-hint">Click to expand</div>
                            </div>
                            
                            <div class="email-right">
                                {% if email.urgency_score > 0 %}
                                <div class="urgency-badge {{ email.urgency_class }}">{{ email.urgency_score }}/10</div>
                                {% endif %}
                                <div class="email-date">{{ email.date_short }}</div>
                            </div>
                        </div>
                        
                        <div class="email-summary" id="summary-{{ email.email_id }}">
                            <div class="summary-title">Summary</div>
                            <div class="summary-text summary-loading">Loading...</div>
                        </div>
                    </div>
                    {% endfor %}
                </div>
            </div>
            {% endfor %}
        </div>
        
        <div class="empty-state hidden" id="emptyState">
            <div class="empty-icon">&#128236;</div>
            <div class="empty-text">No emails for today</div>
        </div>
    </div>
    
    <script>
        let currentCategory = 'all';
        let currentAccount = null;
        
        function filterCategory(category) {
            currentCategory = category;
            currentAccount = null;
            
            document.querySelectorAll('.nav-item').forEach(item => {
                item.classList.remove('active');
            });
            
            const navItem = document.getElementById('nav-' + category);
            if (navItem) navItem.classList.add('active');
            
            const titles = {
                'all': 'All Emails',
                'urgent': 'Urgent Emails',
                'important': 'Important Emails',
                'newsletter': 'Newsletters',
                'spam': 'Filtered Emails'
            };
            document.getElementById('pageTitle').textContent = titles[category] || 'All Emails';
            
            // Show stats banner only on 'all'
            document.getElementById('statsBanner').classList.toggle('hidden', category !== 'all');
            
            filterEmails();
        }
        
        function filterAccount(account) {
            currentCategory = null;
            currentAccount = account;
            
            document.querySelectorAll('.nav-item').forEach(item => {
                item.classList.remove('active');
            });
            
            const navId = 'nav-' + account.replace('@', '_');
            const navItem = document.getElementById(navId);
            if (navItem) navItem.classList.add('active');
            
            document.getElementById('pageTitle').textContent = account.split('@')[0];
            document.getElementById('statsBanner').classList.add('hidden');
            
            filterEmails();
        }
        
        function filterEmails() {
            const query = document.getElementById('searchInput').value.toLowerCase().trim();
            const cards = document.querySelectorAll('.email-card');
            const accountSections = document.querySelectorAll('.account-section');
            
            let totalVisible = 0;
            
            accountSections.forEach(section => {
                const sectionAccount = section.dataset.account;
                const cardsInSection = section.querySelectorAll('.email-card');
                let sectionVisible = 0;
                
                cardsInSection.forEach(card => {
                    const matchesCategory = !currentCategory || currentCategory === 'all' || card.dataset.category === currentCategory;
                    const matchesAccount = !currentAccount || sectionAccount === currentAccount;
                    const matchesSearch = !query || 
                        card.dataset.subject.includes(query) || 
                        card.dataset.sender.includes(query);
                    
                    if (matchesCategory && matchesAccount && matchesSearch) {
                        card.classList.remove('hidden');
                        sectionVisible++;
                        totalVisible++;
                    } else {
                        card.classList.add('hidden');
                    }
                });
                
                // Hide account section if no emails visible
                section.classList.toggle('hidden', sectionVisible === 0);
            });
            
            document.getElementById('emptyState').classList.toggle('hidden', totalVisible > 0);
            document.getElementById('emailContainer').classList.toggle('hidden', totalVisible === 0);
        }
        
        function toggleEmail(card) {
            const emailId = card.dataset.emailId;
            const summaryDiv = document.getElementById('summary-' + emailId);
            const summaryText = summaryDiv.querySelector('.summary-text');
            
            // Toggle expanded state
            card.classList.toggle('expanded');
            summaryDiv.classList.toggle('show');
            
            // Fetch summary if not already loaded
            if (summaryDiv.classList.contains('show') && summaryText.classList.contains('summary-loading')) {
                fetch('/api/email/' + emailId)
                    .then(response => response.json())
                    .then(data => {
                        if (data.body) {
                            // Show first 500 chars of body as summary
                            const preview = data.body.substring(0, 500).trim();
                            summaryText.textContent = preview + (data.body.length > 500 ? '...' : '');
                            summaryText.classList.remove('summary-loading');
                        } else {
                            summaryText.textContent = 'No preview available';
                            summaryText.classList.remove('summary-loading');
                        }
                    })
                    .catch(err => {
                        summaryText.textContent = 'Error loading email';
                        summaryText.classList.remove('summary-loading');
                    });
            }
        }
    </script>
</body>
</html>
"""

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def get_stats():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    today = date.today().isoformat()
    
    stats = {"urgent": 0, "important": 0, "newsletter": 0, "spam": 0, "normal": 0}
    
    # Only count today's emails
    cursor.execute("""
        SELECT category, COUNT(*) as count 
        FROM emails 
        WHERE date LIKE ? 
        GROUP BY category
    """, (today + '%',))
    
    for row in cursor.fetchall():
        if row["category"] and row["category"] in stats:
            stats[row["category"]] = row["count"]
    
    conn.close()
    return stats

def get_emails_by_account(limit=100):
    """Get today's emails grouped by account."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    today = date.today().isoformat()
    
    # Only get today's emails
    cursor.execute("""
        SELECT email_id, account, subject, sender_name, sender_email, 
               date, urgency_score, category, body
        FROM emails 
        WHERE date LIKE ?
        ORDER BY 
            CASE category 
                WHEN 'urgent' THEN 1 
                WHEN 'important' THEN 2 
                WHEN 'newsletter' THEN 3 
                ELSE 4 
            END,
            urgency_score DESC,
            date DESC
        LIMIT ?
    """, (today + '%', limit))
    
    emails_by_account = {}
    account_counts = {}
    
    for row in cursor.fetchall():
        account = row["account"] or "unknown"
        
        if account not in emails_by_account:
            emails_by_account[account] = []
            account_counts[account] = 0
        
        account_counts[account] += 1
        
        date_str = row["date"] or ""
        date_short = date_str[:10] if len(date_str) >= 10 else date_str
        time_short = date_str[11:16] if len(date_str) >= 16 else ""
        
        # Get sender initial for avatar
        sender_name = row["sender_name"] or ""
        sender_initial = sender_name[0].upper() if sender_name else "?"
        
        # Cap urgency at 10
        urgency = min(row["urgency_score"] or 0, 10)
        
        # Urgency class for styling
        urgency_class = "low"
        if urgency >= 7:
            urgency_class = "high"
        elif urgency >= 4:
            urgency_class = "medium"
        
        emails_by_account[account].append({
            "email_id": row["email_id"],
            "account": account,
            "subject": row["subject"] or "(No subject)",
            "sender_name": sender_name,
            "sender_email": row["sender_email"] or "",
            "sender_initial": sender_initial,
            "date": row["date"],
            "date_short": date_short,
            "time_short": time_short,
            "urgency_score": urgency,
            "urgency_class": urgency_class,
            "category": row["category"] or "normal"
        })
    
    conn.close()
    return emails_by_account, account_counts

def get_accounts():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT DISTINCT account FROM emails")
    accounts = [row["account"] for row in cursor.fetchall() if row["account"]]
    
    conn.close()
    return accounts

@app.route("/")
def index():
    stats = get_stats()
    accounts = get_accounts()
    emails_by_account, account_counts = get_emails_by_account(limit=100)
    
    total_count = sum(account_counts.values())
    
    return render_template_string(
        HTML_TEMPLATE,
        stats=stats,
        accounts=accounts,
        emails_by_account=emails_by_account,
        account_counts=account_counts,
        total_count=total_count,
        last_refresh=datetime.now().strftime("%H:%M"),
        today_date=datetime.now().strftime("%A, %B %d, %Y")
    )

@app.route("/api/emails")
def api_emails():
    category = request.args.get("category", "all")
    account = request.args.get("account", None)
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    today = date.today().isoformat()
    
    if category == "all" and not account:
        cursor.execute("SELECT * FROM emails WHERE date LIKE ? ORDER BY date DESC LIMIT 50", (today + '%',))
    elif account:
        cursor.execute("SELECT * FROM emails WHERE account = ? AND date LIKE ? ORDER BY date DESC LIMIT 50", (account, today + '%'))
    else:
        cursor.execute("SELECT * FROM emails WHERE category = ? AND date LIKE ? ORDER BY date DESC LIMIT 50", (category, today + '%'))
    
    emails = [dict(row) for row in cursor.fetchall()]
    conn.close()
    
    return jsonify({"emails": emails})

@app.route("/api/stats")
def api_stats():
    return jsonify(get_stats())

@app.route("/api/email/<email_id>")
def api_email_detail(email_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM emails WHERE email_id = ?", (email_id,))
    row = cursor.fetchone()
    conn.close()
    
    if row:
        return jsonify(dict(row))
    return jsonify({"error": "Email not found"}), 404

if __name__ == "__main__":
    print("Starting Email Dashboard V2...")
    print("Access at: http://localhost:5051")
    app.run(host="0.0.0.0", port=5051, debug=False)