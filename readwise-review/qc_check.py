#!/usr/bin/env python3
"""
QC Agent: Validate llm-wiki format for all items in state.json.
Checks: YAML frontmatter, numbered sections, summary prefix, source block.
Returns PASS/FAIL for each item with details.
"""
import json
import re
import os
import sys

STATE_FILE = os.path.expanduser('~/.hermes/readwise_review/state.json')

def load_state():
    with open(STATE_FILE) as f:
        return json.load(f)

def check_item(idx, item):
    """Check a single item's summary for llm-wiki format compliance."""
    title = item.get('title', 'UNKNOWN')[:60]
    summary = item.get('summary', {}) or {}
    ds = summary.get('detailed_summary', '')
    
    checks = {}
    
    # Check 1: Has detailed_summary
    checks['has_detailed_summary'] = bool(ds and len(ds) > 100)
    
    # Check 2: YAML frontmatter starts with ---
    checks['starts_with_yaml'] = ds.startswith('---') if ds else False
    
    # Check 3: Has source: in YAML
    checks['has_yaml_source'] = bool(re.search(r'^---\s*\n\s*source:', ds[:300])) if ds else False
    
    # Check 4: Has tags: in YAML
    checks['has_yaml_tags'] = bool(re.search(r'tags:', ds[:300])) if ds else False
    
    # Check 5: Has ## 一、 numbered sections
    checks['has_chinese_sections'] = bool(re.search(r'## [一二三四五六七八九十]+[、.]', ds))
    
    # Check 6: Section count
    sections = re.findall(r'## ([一二三四五六七八九十]+[、.][^\n]+)', ds)
    checks['section_count'] = len(sections)
    checks['section_titles'] = sections
    
    # Check 7: Has > 摘要： or > 摘要:
    checks['has_summary_prefix'] = bool(re.search(r'>\s*摘要[：:]', ds))
    
    # Check 8: Has [!info] 
    checks['has_info_block'] = bool(re.search(r'\[!info\]', ds))
    
    # Check 9: Has 原始链接 or URL
    checks['has_source_link'] = bool(re.search(r'原始链接|source link|\[!info\]', ds))
    
    # Check 10: Minimum content length (> 500 chars)
    checks['min_length'] = len(ds) > 500
    
    # Overall pass/fail
    critical = ['has_detailed_summary', 'starts_with_yaml', 'has_chinese_sections', 
                'has_summary_prefix', 'has_info_block']
    optional = ['has_yaml_source', 'has_yaml_tags', 'min_length', 'has_source_link']
    
    failures = [c for c in critical if not checks.get(c)]
    warnings = [c for c in optional if not checks.get(c)]
    
    return {
        'idx': idx,
        'title': title,
        'folder': item.get('folder', ''),
        'url': item.get('url', '')[:60],
        'checks': checks,
        'section_titles': checks.get('section_titles', []),
        'content_length': len(ds),
        'pass': len(failures) == 0,
        'failures': failures,
        'warnings': warnings
    }

def main():
    state = load_state()
    items = state.get('items', [])
    
    print(f"QC Report: {len(items)} items")
    print("=" * 80)
    
    results = []
    passed = 0
    failed = 0
    
    for idx, item in enumerate(items):
        result = check_item(idx, item)
        results.append(result)
        
        if result['pass']:
            passed += 1
            status = "✅ PASS"
        else:
            failed += 1
            status = "❌ FAIL"
        
        print(f"\n[{status}] #{idx} {result['title']}")
        print(f"    Folder: {result['folder']} | Length: {result['content_length']} chars | Sections: {len(result['section_titles'])}")
        
        if result['section_titles']:
            for s in result['section_titles']:
                print(f"      - {s}")
        
        if result['failures']:
            print(f"    🔴 Failures: {', '.join(result['failures'])}")
        if result['warnings']:
            print(f"    🟡 Warnings: {', '.join(result['warnings'])}")
    
    print("\n" + "=" * 80)
    print(f"SUMMARY: {passed}/{len(items)} PASSED, {failed}/{len(items)} FAILED")
    
    if failed > 0:
        print("\nFAILED ITEMS:")
        for r in results:
            if not r['pass']:
                print(f"  ❌ #{r['idx']} {r['title']} - {', '.join(r['failures'])}")
    
    # Quality score
    if passed == len(items):
        print("\n🎉 All items pass QC!")
    elif passed >= len(items) * 0.8:
        print(f"\n⚠️ {passed}/{len(items)} pass ({100*passed//len(items)}%) — minor issues")
    else:
        print(f"\n🔴 {passed}/{len(items)} pass ({100*passed//len(items)}%) — needs fixes")
    
    # Return exit code for CI
    return 0 if passed == len(items) else 1

if __name__ == '__main__':
    sys.exit(main())
