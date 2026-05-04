#!/usr/bin/env python3
"""
Email Monitor Web Portal - Modern dashboard for viewing classified emails.
"""

from flask import Flask, render_template_string, jsonify, request
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

app = Flask(__name__)

DB_PATH = Path.home() / ".hermes" / "email-monitor" / "emails.db"

# Modern, clean HTML template
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Email Dashboard</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg-primary: #f8fafc;
            --bg-secondary: #ffffff;
            --bg-hover: #f1f5f9;
            --text-primary: #1e293b;
            --text-secondary: #64748b;
            --text-muted: #94a3b8;
            --border: #e2e8f0;
            --accent: #3b82f6;
            --urgent: #ef4444;
            --urgent-bg: #fef2f2;
            --important: #f59e0b;
            --important-bg: #fffbeb;
            --newsletter: #10b981;
            --newsletter-bg: #ecfdf5;
            --spam: #6b7280;
            --spam-bg: #f3f4f6;
            --shadow: 0 1px 3px rgba(0,0,0,0.1), 0 1px 2px rgba(0,0,0,0.06);
            --shadow-lg: 0 4px 6px rgba(0,0,0,0.1), 0 2px 4px rgba(0,0,0,0.06);
        }
        
        * { margin: 0; padding: 0; box-sizing: border-box; }
        
        body {
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
            background: var(--bg-primary);
            color: var(--text-primary);
            line-height: 1.5;
            min-height: 100vh;
        }
        
        .container {
            max-width: 1000px;
            margin: 0 auto;
            padding: 32px 24px;
        }
        
        /* Header */
        .header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 32px;
        }
        
        .header-title {
            font-size: 28px;
            font-weight: 700;
            color: var(--text-primary);
        }
        
        .header-subtitle {
            font-size: 14px;
            color: var(--text-secondary);
            margin-top: 4px;
        }
        
        .header-actions {
            display: flex;
            gap: 12px;
            align-items: center;
        }
        
        .search-box {
            position: relative;
        }
        
        .search-input {
            padding: 10px 16px 10px 40px;
            border: 1px solid var(--border);
            border-radius: 8px;
            font-size: 14px;
            width: 220px;
            background: var(--bg-secondary);
            transition: all 0.2s;
        }
        
        .search-input:focus {
            outline: none;
            border-color: var(--accent);
            box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.1);
        }
        
        .search-icon {
            position: absolute;
            left: 12px;
            top: 50%;
            transform: translateY(-50%);
            color: var(--text-muted);
        }
        
        .refresh-btn {
            padding: 10px 16px;
            background: var(--bg-secondary);
            border: 1px solid var(--border);
            border-radius: 8px;
            font-size: 14px;
            color: var(--text-secondary);
            cursor: pointer;
            transition: all 0.2s;
        }
        
        .refresh-btn:hover {
            background: var(--bg-hover);
        }
        
        /* Stats Cards */
        .stats-grid {
            display: grid;
            grid-template-columns: repeat(4, 1fr);
            gap: 16px;
            margin-bottom: 32px;
        }
        
        .stat-card {
            background: var(--bg-secondary);
            border-radius: 12px;
            padding: 20px;
            box-shadow: var(--shadow);
            border: 1px solid var(--border);
            transition: all 0.2s;
        }
        
        .stat-card:hover {
            box-shadow: var(--shadow-lg);
        }
        
        .stat-card.urgent { background: var(--urgent-bg); border-color: #fecaca; }
        .stat-card.important { background: var(--important-bg); border-color: #fde68a; }
        .stat-card.newsletter { background: var(--newsletter-bg); border-color: #a7f3d0; }
        .stat-card.spam { background: var(--spam-bg); border-color: #d1d5db; }
        
        .stat-icon {
            font-size: 24px;
            margin-bottom: 8px;
        }
        
        .stat-number {
            font-size: 32px;
            font-weight: 700;
            color: var(--text-primary);
        }
        
        .stat-label {
            font-size: 13px;
            color: var(--text-secondary);
            margin-top: 4px;
        }
        
        /* Tabs */
        .tabs {
            display: flex;
            gap: 8px;
            margin-bottom: 24px;
            border-bottom: 1px solid var(--border);
            padding-bottom: 16px;
        }
        
        .tab {
            padding: 8px 16px;
            border-radius: 6px;
            font-size: 14px;
            font-weight: 500;
            color: var(--text-secondary);
            cursor: pointer;
            transition: all 0.2s;
            border: none;
            background: transparent;
        }
        
        .tab:hover {
            background: var(--bg-hover);
        }
        
        .tab.active {
            background: var(--accent);
            color: white;
        }
        
        .tab-count {
            font-size: 12px;
            padding: 2px 6px;
            border-radius: 4px;
            background: rgba(0,0,0,0.1);
            margin-left: 6px;
        }
        
        .tab.active .tab-count {
            background: rgba(255,255,255,0.2);
        }
        
        /* Email List */
        .email-list {
            display: flex;
            flex-direction: column;
            gap: 12px;
        }
        
        .email-card {
            background: var(--bg-secondary);
            border-radius: 10px;
            padding: 16px 20px;
            box-shadow: var(--shadow);
            border: 1px solid var(--border);
            display: flex;
            align-items: flex-start;
            gap: 16px;
            transition: all 0.2s;
            cursor: pointer;
        }
        
        .email-card:hover {
            box-shadow: var(--shadow-lg);
            background: var(--bg-hover);
        }
        
        .email-card.urgent-highlight {
            border-left: 4px solid var(--urgent);
            background: var(--urgent-bg);
        }
        
        .email-card.important-highlight {
            border-left: 4px solid var(--important);
            background: var(--important-bg);
        }
        
        .account-badge {
            padding: 4px 10px;
            border-radius: 6px;
            font-size: 12px;
            font-weight: 500;
            background: #e0e7ff;
            color: #4338ca;
            white-space: nowrap;
        }
        
        .account-badge.yahoo {
            background: #fce7f3;
            color: #9d174d;
        }
        
        .email-content {
            flex: 1;
            min-width: 0;
        }
        
        .email-subject {
            font-size: 15px;
            font-weight: 600;
            color: var(--text-primary);
            margin-bottom: 6px;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }
        
        .email-sender {
            font-size: 13px;
            color: var(--text-secondary);
        }
        
        .email-sender-name {
            font-weight: 500;
        }
        
        .email-meta {
            display: flex;
            flex-direction: column;
            align-items: flex-end;
            gap: 8px;
            min-width: 100px;
        }
        
        .urgency-badge {
            padding: 4px 8px;
            border-radius: 4px;
            font-size: 12px;
            font-weight: 600;
            background: var(--urgent);
            color: white;
        }
        
        .email-date {
            font-size: 12px;
            color: var(--text-muted);
        }
        
        /* Empty State */
        .empty-state {
            text-align: center;
            padding: 48px 24px;
            color: var(--text-muted);
        }
        
        .empty-icon {
            font-size: 48px;
            margin-bottom: 16px;
        }
        
        /* Footer */
        .footer {
            text-align: center;
            padding: 24px;
            color: var(--text-muted);
            font-size: 13px;
            margin-top: 32px;
            border-top: 1px solid var(--border);
        }
        
        /* Hidden sections */
        .hidden { display: none; }
        
        /* Mobile Responsive */
        @media (max-width: 768px) {
            .container { padding: 16px; }
            .header { flex-direction: column; gap: 16px; align-items: flex-start; }
            .header-actions { width: 100%; }
            .search-input { width: 100%; }
            .stats-grid { grid-template-columns: repeat(2, 1fr); }
            .email-card { flex-direction: column; }
            .email-meta { align-items: flex-start; }
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <div>
                <div class="header-title">Email Dashboard</div>
                <div class="header-subtitle">{{ accounts|length }} accounts monitored | Last sync: {{ last_refresh }}</div>
            </div>
            <div class="header-actions">
                <div class="search-box">
                    <span class="search-icon">&#128269;</span>
                    <input type="text" class="search-input" placeholder="Search emails..." id="searchInput" onkeyup="filterEmails()">
                </div>
            </div>
        </div>
        
        <div class="stats-grid">
            <div class="stat-card urgent">
                <div class="stat-icon">&#128680;</div>
                <div class="stat-number">{{ stats.urgent }}</div>
                <div class="stat-label">Urgent</div>
            </div>
            <div class="stat-card important">
                <div class="stat-icon">&#128204;</div>
                <div class="stat-number">{{ stats.important }}</div>
                <div class="stat-label">Important</div>
            </div>
            <div class="stat-card newsletter">
                <div class="stat-icon">&#128240;</div>
                <div class="stat-number">{{ stats.newsletter }}</div>
                <div class="stat-label">Newsletters</div>
            </div>
            <div class="stat-card spam">
                <div class="stat-icon">&#128465;</div>
                <div class="stat-number">{{ stats.spam }}</div>
                <div class="stat-label">Filtered</div>
            </div>
        </div>
        
        <div class="tabs">
            <button class="tab active" onclick="showTab('all')" id="tab-all">
                All<span class="tab-count">{{ total_count }}</span>
            </button>
            <button class="tab" onclick="showTab('urgent')" id="tab-urgent">
                Urgent<span class="tab-count">{{ stats.urgent }}</span>
            </button>
            <button class="tab" onclick="showTab('important')" id="tab-important">
                Important<span class="tab-count">{{ stats.important }}</span>
            </button>
            <button class="tab" onclick="showTab('newsletter')" id="tab-newsletter">
                Newsletters<span class="tab-count">{{ stats.newsletter }}</span>
            </button>
        </div>
        
        <div class="email-list" id="emailList">
            {% for email in all_emails %}
            <div class="email-card {{ email.category }}-highlight" data-category="{{ email.category }}" data-subject="{{ email.subject|lower }}" onclick="showEmailDetail('{{ email.email_id }}')">
                <div class="account-badge {{ 'yahoo' if 'yahoo' in email.account else '' }}">{{ email.account_short }}</div>
                <div class="email-content">
                    <div class="email-subject">{{ email.subject }}</div>
                    <div class="email-sender">
                        <span class="email-sender-name">{{ email.sender_name or 'Unknown' }}</span>
                        {% if email.sender_email %} &lt;{{ email.sender_email }}&gt;{% endif %}
                    </div>
                </div>
                <div class="email-meta">
                    {% if email.urgency_score > 0 %}
                    <div class="urgency-badge">{{ email.urgency_score }}/10</div>
                    {% endif %}
                    <div class="email-date">{{ email.date_short }}</div>
                </div>
            </div>
            {% endfor %}
        </div>
        
        <div class="empty-state hidden" id="emptyState">
            <div class="empty-icon">&#128236;</div>
            <div>No emails found in this category</div>
        </div>
        
        <div class="footer">
            Monitoring runs every hour | Telegram alerts for urgent items
        </div>
    </div>
    
    <script>
        function showTab(category) {
            // Update tab buttons
            document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
            document.getElementById('tab-' + category).classList.add('active');
            
            // Filter emails
            const cards = document.querySelectorAll('.email-card');
            let visible = 0;
            
            cards.forEach(card => {
                if (category === 'all' || card.dataset.category === category) {
                    card.classList.remove('hidden');
                    visible++;
                } else {
                    card.classList.add('hidden');
                }
            });
            
            // Show empty state if needed
            document.getElementById('emptyState').classList.toggle('hidden', visible > 0);
        }
        
        function filterEmails() {
            const query = document.getElementById('searchInput').value.toLowerCase();
            const cards = document.querySelectorAll('.email-card');
            const activeTab = document.querySelector('.tab.active').id.replace('tab-', '');
            
            let visible = 0;
            cards.forEach(card => {
                const matchesTab = activeTab === 'all' || card.dataset.category === activeTab;
                const matchesSearch = card.dataset.subject.includes(query);
                
                if (matchesTab && matchesSearch) {
                    card.classList.remove('hidden');
                    visible++;
                } else {
                    card.classList.add('hidden');
                }
            });
            
            document.getElementById('emptyState').classList.toggle('hidden', visible > 0);
        }
        
        function showEmailDetail(emailId) {
            // Could expand to show full email body in future
            console.log('Email ID:', emailId);
        }
    </script>
</body>
</html>
"""

def get_db_connection():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn

def get_stats():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    stats = {"urgent": 0, "important": 0, "newsletter": 0, "spam": 0, "normal": 0}
    
    cursor.execute("SELECT category, COUNT(*) as count FROM emails GROUP BY category")
    for row in cursor.fetchall():
        if row["category"] in stats:
            stats[row["category"]] = row["count"]
    
    conn.close()
    return stats

def get_all_emails(limit=50):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT email_id, account, subject, sender_name, sender_email, 
               date, urgency_score, category
        FROM emails 
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
    """, (limit,))
    
    emails = []
    for row in cursor.fetchall():
        account_short = row["account"].split("@")[0] if "@" in row["account"] else row["account"]
        date_str = row["date"] or ""
        date_short = date_str[:10] if len(date_str) >= 10 else date_str
        
        emails.append({
            "email_id": row["email_id"],
            "account": row["account"],
            "account_short": account_short,
            "subject": row["subject"] or "(No subject)",
            "sender_name": row["sender_name"],
            "sender_email": row["sender_email"],
            "date": row["date"],
            "date_short": date_short,
            "urgency_score": row["urgency_score"] or 0,
            "category": row["category"]
        })
    
    conn.close()
    return emails

def get_accounts():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT DISTINCT account FROM emails")
    accounts = [row["account"] for row in cursor.fetchall()]
    
    conn.close()
    return accounts

@app.route("/")
def index():
    stats = get_stats()
    accounts = get_accounts()
    all_emails = get_all_emails(limit=50)
    
    total_count = sum(stats.values())
    
    return render_template_string(
        HTML_TEMPLATE,
        stats=stats,
        accounts=accounts,
        all_emails=all_emails,
        total_count=total_count,
        last_refresh=datetime.now().strftime("%H:%M")
    )

@app.route("/api/emails")
def api_emails():
    category = request.args.get("category", "all")
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    if category == "all":
        cursor.execute("""
            SELECT * FROM emails ORDER BY date DESC LIMIT 50
        """)
    else:
        cursor.execute("""
            SELECT * FROM emails WHERE category = ? ORDER BY date DESC LIMIT 50
        """, (category,))
    
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
    
    cursor.execute("""
        SELECT * FROM emails WHERE email_id = ?
    """, (email_id,))
    
    row = cursor.fetchone()
    conn.close()
    
    if row:
        return jsonify(dict(row))
    return jsonify({"error": "Email not found"}), 404

if __name__ == "__main__":
    print("Starting Email Dashboard...")
    print("Access at: http://localhost:5050")
    app.run(host="0.0.0.0", port=5050, debug=False)