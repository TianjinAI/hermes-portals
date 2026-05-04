#!/usr/bin/env python3
"""
Fetch YouTube transcripts using YouMind API.
"""

import json
import os
import subprocess
import sys
import re
import time

YOUMIND_API_KEY = os.environ.get('YOUMIND_API_KEY', '')
if not YOUMIND_API_KEY:
    # Try to load from .env
    env_file = os.path.expanduser('~/.hermes/.env')
    if os.path.exists(env_file):
        with open(env_file) as f:
            for line in f:
                if line.startswith('YOUMIND_API_KEY='):
                    YOUMIND_API_KEY = line.strip().split('=', 1)[1]
                    break

def get_api_key():
    """Get the YouMind API key."""
    return YOUMIND_API_KEY

def fetch_transcript(url):
    """Fetch YouTube transcript using YouMind."""
    api_key = get_api_key()
    if not api_key:
        return None, "YOUMIND_API_KEY not set"
    
    # Save the URL as material
    env = os.environ.copy()
    env['YOUMIND_API_KEY'] = api_key
    
    try:
        result = subprocess.run(
            ['youmind', 'call', 'createMaterialByUrl', '--url', url],
            capture_output=True,
            text=True,
            env=env,
            timeout=30
        )
        
        if result.returncode != 0:
            return None, f"Error: {result.stderr}"
        
        data = json.loads(result.stdout)
        material_id = data.get('id')
        
        if not material_id:
            return None, "No material ID returned"
        
        # Wait for processing — up to 60 seconds. If YouMind can't get it by then, it won't.
        for attempt in range(12):  # Try for up to 60 seconds
            time.sleep(5)
            
            result = subprocess.run(
                ['youmind', 'call', 'getMaterial', '--id', material_id, '--includeBlocks', 'true'],
                capture_output=True,
                text=True,
                env=env,
                timeout=30
            )
            
            if result.returncode != 0:
                continue
            
            material = json.loads(result.stdout)
            
            # Check for transcript
            transcript = material.get('transcript', {})
            if transcript and transcript.get('contents'):
                content = transcript['contents'][0]
                if content.get('status') == 'completed':
                    # Return the plain text transcript
                    return content.get('plain', ''), None
            
            # Check status
            status = material.get('status')
            if status and status != 'fetching':
                break
        
        return None, "Transcript not available via YouMind (YouTube likely lacks API-accessible captions)"
    
    except subprocess.TimeoutExpired:
        return None, "Timeout"
    except Exception as e:
        return None, str(e)

def main():
    """Test the transcript fetching."""
    if len(sys.argv) < 2:
        print("Usage: python3 youmind_transcript.py <youtube_url>")
        sys.exit(1)
    
    url = sys.argv[1]
    print(f"Fetching transcript for: {url}")
    
    transcript, error = fetch_transcript(url)
    
    if error:
        print(f"Error: {error}")
        sys.exit(1)
    
    print(f"\nTranscript ({len(transcript)} chars):")
    print(transcript[:1000] + "..." if len(transcript) > 1000 else transcript)

if __name__ == '__main__':
    main()
