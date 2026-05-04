#!/usr/bin/env python3
import re
with open('web_portal_v3.py', 'r', encoding='utf-8') as f:
    content = f.read()
# Replace curly quotes with straight quotes
content = content.replace(chr(0x201C), chr(0x22))  # left double quote
content = content.replace(chr(0x201D), chr(0x22))  # right double quote  
content = content.replace(chr(0x2018), chr(0x27))  # left single quote
content = content.replace(chr(0x2019), chr(0x27))  # right single quote
content = content.replace(chr(0x2014), chr(0x2D))  # em dash
content = content.replace(chr(0x2013), chr(0x2D))  # en dash
with open('web_portal_v3.py', 'w', encoding='utf-8') as f:
    f.write(content)
print('Fixed quotes')