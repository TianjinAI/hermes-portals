#!/usr/bin/env python3
"""
Readwise Review Portal Server
Serves the portal and handles API calls for reviewing items.
"""

import json
import os
import sys
import subprocess
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
import urllib.parse
from datetime import datetime

PORT = 5054
REVIEW_DIR = os.path.expanduser('~/.hermes/readwise_review')
STATE_FILE = os.path.join(REVIEW_DIR, 'state.json')
IGNORE_FILE = os.path.join(REVIEW_DIR, 'ignore_list.json')
VAULT_PATH = os.path.expanduser('~/Second_Brain')


def _get_md_renderer():
    """Lazy-load mistune renderer (cached)."""
    if not hasattr(_get_md_renderer, "_renderer"):
        import mistune
        _get_md_renderer._renderer = mistune.create_markdown(
            escape=False, plugins=["table", "strikethrough", "footnotes", "task_lists"]
        )
    return _get_md_renderer._renderer


def convert_markdown(text):
    """Convert markdown text to HTML. Returns original text if mistune unavailable."""
    if not text:
        return ""
    try:
        return _get_md_renderer()(text)
    except Exception:
        return text.replace("\n", "<br>")

def load_ignore_list():
    """Load the ignore list."""
    if os.path.exists(IGNORE_FILE):
        with open(IGNORE_FILE) as f:
            return json.load(f)
    return {"ignore_sources": [], "keep_all_youtube": True}

def load_state():
    """Load pipeline state."""
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            return json.load(f)
    return {
        'last_export': None,
        'last_updated': None,
        'items': [],
        'decisions': {},
        'processed_ids': [],
        'history_count': 0
    }

def save_state(state):
    """Save pipeline state."""
    os.makedirs(REVIEW_DIR, exist_ok=True)
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f, indent=2, ensure_ascii=False)

def filter_items(items):
    """Filter out ignored sources."""
    ignore_config = load_ignore_list()
    ignore_sources = ignore_config.get('ignore_sources', [])
    keep_all_youtube = ignore_config.get('keep_all_youtube', True)
    
    filtered = []
    for item in items:
        author = item.get('author', '')
        category = item.get('category', '')
        
        # Keep all YouTube items if configured
        if keep_all_youtube and category in ['youtube', 'video']:
            filtered.append(item)
            continue
        
        # Check if author is in ignore list
        if author in ignore_sources:
            continue
        
        # Check if any ignore source is in the author name
        skip = False
        for ignore_source in ignore_sources:
            if ignore_source in author:
                skip = True
                break
        
        if not skip:
            filtered.append(item)
    
    return filtered

def process_keep_decision(item):
    """Process a 'keep' decision - save to In_Process folder."""
    try:
        # Get the detailed summary (llm-wiki format)
        summary = item.get('summary', {})
        detailed_summary = summary.get('detailed_summary', '')
        
        if not detailed_summary:
            return False, "No detailed summary available"
        
        # Save to In_Process folder
        in_process_dir = os.path.join(VAULT_PATH, 'In_Process')
        os.makedirs(in_process_dir, exist_ok=True)
        
        # Generate filename from title
        title = item.get('title', 'Untitled')
        safe_title = "".join(c for c in title if c.isalnum() or c in ' .-_').strip()[:80]
        if not safe_title:
            safe_title = 'Untitled'
        
        # Add date prefix
        pub_date = item.get('published_date', '')
        date_prefix = pub_date[:10] if pub_date else datetime.now().strftime('%Y-%m-%d')
        
        output_path = os.path.join(in_process_dir, f"{date_prefix} {safe_title}.md")
        
        # Write the detailed summary directly (it's already in llm-wiki format)
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(detailed_summary)
        
        return True, f"Saved to {output_path}"
    except Exception as e:
        return False, str(e)

class PortalHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        """Handle GET requests."""
        parsed_path = urllib.parse.urlparse(self.path)
        query_params = urllib.parse.parse_qs(parsed_path.query)
        
        if parsed_path.path == '/' or parsed_path.path == '/index.html':
            # Serve portal HTML
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.end_headers()
            with open(os.path.join(REVIEW_DIR, 'portal.html'), 'rb') as f:
                self.wfile.write(f.read())
        
        elif parsed_path.path == '/api/state':
            # Return current state
            state = load_state()
            
            # Filter by date if provided
            date = query_params.get('date', [None])[0]
            if date:
                items = [i for i in state['items'] if i.get('published_date', '').startswith(date)]
            else:
                items = state['items']
            
            # Apply ignore filter
            filtered_items = filter_items(items)

            # Pre-compute HTML rendering for markdown summaries
            for item in filtered_items:
                summary = item.get("summary", {})
                if summary.get("detailed_summary"):
                    summary["detailed_summary_html"] = convert_markdown(summary["detailed_summary"])

            response = {
                'items': filtered_items,
                'decisions': state.get('decisions', {}),
                'history_count': state.get('history_count', 0)
            }
            
            self.send_response(200)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.end_headers()
            self.wfile.write(json.dumps(response, ensure_ascii=False).encode('utf-8'))
        
        elif parsed_path.path == '/api/ignore':
            # Return ignore list
            ignore_config = load_ignore_list()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.end_headers()
            self.wfile.write(json.dumps(ignore_config, ensure_ascii=False).encode('utf-8'))
        
        else:
            self.send_response(404)
            self.end_headers()
    
    def do_POST(self):
        """Handle POST requests."""
        if self.path == '/api/decide':
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length)
            data = json.loads(body.decode('utf-8'))
            
            item_id = data.get('item_id')
            decision = data.get('decision')
            
            if not item_id or decision not in ['keep', 'discard', 'investigate']:
                self.send_response(400)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'success': False, 'error': 'Invalid request'}).encode())
                return
            
            state = load_state()
            
            # Find the item
            item = next((i for i in state['items'] if i['id'] == item_id), None)
            if not item:
                self.send_response(404)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'success': False, 'error': 'Item not found'}).encode())
                return
            
            # Save decision
            state['decisions'][item_id] = decision
            save_state(state)
            
            # Process keep decision
            message = f'Decision saved: {decision}'
            if decision == 'keep':
                success, message = process_keep_decision(item)
                if not success:
                    print(f"Warning: Failed to process keep decision: {message}")
            
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({
                'success': True,
                'decision': decision,
                'message': message
            }).encode())
        
        elif self.path == '/api/ignore':
            # Update ignore list
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length)
            data = json.loads(body.decode('utf-8'))
            
            # Save ignore list
            with open(IGNORE_FILE, 'w') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({'success': True, 'message': 'Ignore list updated'}).encode())
        
        elif self.path == '/api/refresh':
            # Trigger a refresh (re-run pipeline)
            subprocess.Popen(
                [sys.executable, os.path.join(REVIEW_DIR, 'pipeline.py')],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({'success': True, 'message': 'Pipeline started'}).encode())
        
        else:
            self.send_response(404)
            self.end_headers()
    
    def log_message(self, format, *args):
        """Suppress default logging."""
        pass

def main():
    """Start the server."""
    print(f"Starting Readwise Review Portal on port {PORT}...")
    print(f"URL: http://localhost:{PORT}")
    
    server = HTTPServer(('0.0.0.0', PORT), PortalHandler)
    
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down...")
        server.shutdown()

if __name__ == '__main__':
    main()
