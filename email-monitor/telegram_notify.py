#!/usr/bin/env python3
"""
Telegram notification sender - sends urgent email alerts via Hermes Telegram integration.
"""

import os
import sys
from pathlib import Path

# Add Hermes agent to path for send_message tool
HERMES_ROOT = Path.home() / ".hermes" / "hermes-agent"
sys.path.insert(0, str(HERMES_ROOT))

def send_telegram_message(message, target="telegram:Shaobin Sun (dm)"):
    """Send message via Hermes Telegram integration."""
    
    # We'll use subprocess to call hermes CLI or use the API directly
    # For now, let's create a simple notification trigger
    
    notify_dir = Path.home() / ".hermes" / "email-monitor" / "notifications"
    notify_dir.mkdir(parents=True, exist_ok=True)
    
    # Write message to a file that will be picked up by the monitor
    timestamp = os.popen('date +%s').read().strip()
    with open(notify_dir / f"telegram_{timestamp}.txt", "w") as f:
        f.write(f"TARGET:{target}\n")
        f.write(f"MESSAGE:{message}\n")
    
    print(f"Telegram notification queued: {target}")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        message = sys.argv[1]
    else:
        message = "Test notification from email monitor"
    
    send_telegram_message(message)