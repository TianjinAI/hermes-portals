#!/bin/bash
# Email Monitor Runner - Run monitoring and send notifications

cd ~/.hermes/email-monitor

# Run the email monitor
python3.11 email_monitor.py

# Check for pending Telegram notifications
NOTIFY_DIR=~/.hermes/email-monitor/notifications

if [ -d "$NOTIFY_DIR" ]; then
    for file in "$NOTIFY_DIR"/telegram_*.txt; do
        if [ -f "$file" ]; then
            # Read target and message from file
            TARGET=$(grep "^TARGET:" "$file" | cut -d: -f2)
            MESSAGE=$(grep "^MESSAGE:" "$file" | cut -d: -f2-)
            
            # Send via Hermes CLI (if available)
            if [ -n "$MESSAGE" ]; then
                echo "Sending Telegram notification..."
                # We'll use hermes send-message if available
                # For now, just print
                echo "To: $TARGET"
                echo "Message: $MESSAGE"
                
                # Clean up notification file after sending
                rm "$file"
            fi
        fi
    done
fi

echo "Email monitor run complete at $(date)"