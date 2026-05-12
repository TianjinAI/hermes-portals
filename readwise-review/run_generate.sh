#!/bin/bash
cd ~/.hermes/readwise_review
exec python3.11 -u generate_llmwiki.py > /tmp/generate_log.txt 2>&1
