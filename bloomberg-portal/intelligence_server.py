#!/usr/bin/env python3
"""
Bloomberg Intelligence Portal Server
Serves the intelligence portal with hot topics, trends, and insights.
"""

import json
import os
import sys
import subprocess
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
import urllib.parse
from datetime import datetime

PORT = 5055
BLOOMBERG_DIR = os.path.expanduser('~/.hermes/bloomberg_digest')
PORTAL_DIR = os.path.expanduser('~/.hermes/bloomberg_portal')
REPORT_FILE = os.path.join(BLOOMBERG_DIR, 'intelligence_report.json')

def load_report():
    """Load the intelligence report."""
    if os.path.exists(REPORT_FILE):
        with open(REPORT_FILE) as f:
            return json.load(f)
    return {
        'generated_at': None,
        'hot_topics': [],
        'trends': [],
        'recent_newsletters': [],
        'stats': {}
    }

class IntelligenceHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        """Handle GET requests."""
        parsed_path = urllib.parse.urlparse(self.path)
        
        if parsed_path.path == '/' or parsed_path.path == '/index.html':
            # Serve portal HTML
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.end_headers()
            with open(os.path.join(PORTAL_DIR, 'intelligence_portal.html'), 'rb') as f:
                self.wfile.write(f.read())
        
        elif parsed_path.path == '/api/report':
            # Return intelligence report
            report = load_report()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.end_headers()
            self.wfile.write(json.dumps(report, ensure_ascii=False).encode('utf-8'))
        
        elif parsed_path.path == '/api/refresh':
            # Trigger report generation
            subprocess.Popen(
                [sys.executable, os.path.join(PORTAL_DIR, 'intelligence_generator.py')],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({'success': True, 'message': 'Report generation started'}).encode())
        
        else:
            self.send_response(404)
            self.end_headers()
    
    def log_message(self, format, *args):
        """Suppress default logging."""
        pass

def main():
    """Start the server."""
    print(f"Starting Bloomberg Intelligence Portal on port {PORT}...")
    print(f"URL: http://localhost:{PORT}")
    
    server = HTTPServer(('0.0.0.0', PORT), IntelligenceHandler)
    
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down...")
        server.shutdown()

if __name__ == '__main__':
    main()
