#!/usr/bin/env python3
"""
Bloomberg Intelligence Generator
Analyzes newsletters to generate insights, hot topics, and trends.
"""

import json
import os
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path
from collections import Counter, defaultdict

BLOOMBERG_DIR = os.path.expanduser('~/.hermes/bloomberg_digest')
KNOWLEDGE_BASE = os.path.join(BLOOMBERG_DIR, 'knowledge', 'knowledge_base.json')
SUMMARIES_DIR = os.path.join(BLOOMBERG_DIR, 'summaries')

def load_knowledge_base():
    """Load the cumulative knowledge base."""
    if os.path.exists(KNOWLEDGE_BASE):
        with open(KNOWLEDGE_BASE) as f:
            return json.load(f)
    return {
        'entities': {'companies': {}, 'people': {}, 'sectors': {}, 'countries': {}},
        'themes': {},
        'facts': [],
        'opinions': []
    }

def parse_summary_file(filepath):
    """Parse a text summary file."""
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Extract fields using regex
    headline_match = re.search(r'HEADLINE:\s*(.+?)(?:\n|$)', content)
    category_match = re.search(r'CATEGORY:\s*(.+?)(?:\n|$)', content)
    impact_match = re.search(r'IMPACT:\s*(.+?)(?:\n|$)', content)
    
    # Extract key points
    key_points = []
    key_points_match = re.search(r'KEY POINTS:\s*\n((?:•\s*.+\n?)+)', content)
    if key_points_match:
        for line in key_points_match.group(1).strip().split('\n'):
            if line.startswith('•'):
                key_points.append(line[1:].strip())
    
    # Extract data points
    data_points = []
    data_points_match = re.search(r'DATA POINTS:\s*\n((?:-\s*.+\n?)+)', content)
    if data_points_match:
        for line in data_points_match.group(1).strip().split('\n'):
            if line.startswith('-'):
                data_points.append(line[1:].strip())
    
    # Extract actionable
    actionable = []
    actionable_match = re.search(r'ACTIONABLE:\s*\n((?:-\s*.+\n?)+)', content)
    if actionable_match:
        for line in actionable_match.group(1).strip().split('\n'):
            if line.startswith('-'):
                actionable.append(line[1:].strip())
    
    return {
        'headline': headline_match.group(1).strip() if headline_match else '',
        'category': category_match.group(1).strip() if category_match else '',
        'impact': impact_match.group(1).strip() if impact_match else '',
        'key_points': key_points,
        'data_points': data_points,
        'actionable': actionable
    }

def load_recent_summaries(days=7):
    """Load summaries from the last N days."""
    summaries = []
    today = datetime.now()
    
    for i in range(days):
        date = (today - timedelta(days=i)).strftime('%Y-%m-%d')
        
        # Find all summary files for this date
        pattern = f'{date}_*.txt'
        summary_files = list(Path(SUMMARIES_DIR).glob(pattern))
        
        for filepath in summary_files:
            try:
                parsed = parse_summary_file(filepath)
                parsed['date'] = date
                parsed['source'] = 'Bloomberg'
                summaries.append(parsed)
            except Exception as e:
                print(f"Error parsing {filepath}: {e}")
    
    return summaries

def extract_hot_topics(summaries, knowledge_base):
    """Identify hot topics across recent newsletters."""
    # Count topic frequency
    topic_counts = Counter()
    topic_articles = defaultdict(list)
    
    for summary in summaries:
        date = summary.get('date', '')
        headline = summary.get('headline', '')
        category = summary.get('category', '')
        impact = summary.get('impact', '')
        
        # Use category as topic
        if category:
            topic_counts[category] += 1
            topic_articles[category].append({
                'date': date,
                'headline': headline,
                'impact': impact
            })
        
        # Extract topics from key points
        for point in summary.get('key_points', []):
            # Simple keyword extraction
            words = point.lower().split()
            for word in words:
                if len(word) > 5 and word not in ['about', 'would', 'could', 'should', 'their', 'there', 'these', 'those', 'which', 'where', 'when', 'what']:
                    topic_counts[word] += 1
    
    # Also check knowledge base themes
    for theme, data in knowledge_base.get('themes', {}).items():
        count = data.get('count', 0)
        if count > 0:
            topic_counts[theme] += count
    
    # Get top topics
    hot_topics = []
    for topic, count in topic_counts.most_common(10):
        if count >= 2:  # At least 2 mentions
            articles = topic_articles.get(topic, [])
            
            # Generate insight
            insight = generate_insight(topic, articles, knowledge_base)
            
            # Determine heat level
            if count >= 10:
                heat = 'High'
            elif count >= 5:
                heat = 'Medium'
            else:
                heat = 'Low'
            
            hot_topics.append({
                'title': topic,
                'heat': heat,
                'summary': f'Mentioned {count} times across recent newsletters.',
                'sources': list(set(a.get('source', 'Bloomberg') for a in articles)),
                'insight': insight,
                'articles': articles[:5]  # Top 5 articles
            })
    
    return hot_topics[:5]  # Top 5 hot topics

def generate_insight(topic, articles, knowledge_base):
    """Generate insight for a topic."""
    # Get related entities
    entities = knowledge_base.get('entities', {})
    companies = entities.get('companies', {})
    people = entities.get('people', {})
    
    # Find related companies and people
    related_companies = [c for c in companies if topic.lower() in c.lower()]
    related_people = [p for p in people if topic.lower() in p.lower()]
    
    # Generate insight
    insight_parts = []
    
    if related_companies:
        insight_parts.append(f"Key companies: {', '.join(related_companies[:3])}")
    
    if related_people:
        insight_parts.append(f"Notable voices: {', '.join(related_people[:3])}")
    
    if articles:
        impacts = [a.get('impact', '') for a in articles if a.get('impact')]
        high_impact = [a for a in articles if a.get('impact') == 'HIGH']
        
        if high_impact:
            insight_parts.append(f"{len(high_impact)} high-impact articles on this topic")
        
        dates = sorted(set(a['date'] for a in articles))
        if len(dates) > 1:
            insight_parts.append(f"Discussed across {len(dates)} days ({dates[0]} to {dates[-1]})")
    
    if not insight_parts:
        insight_parts.append(f"This topic appears in {len(articles)} articles, suggesting growing interest.")
    
    return ' '.join(insight_parts)

def identify_trends(summaries, knowledge_base):
    """Identify emerging trends."""
    trends = []
    
    # Analyze category frequency over time
    category_timeline = defaultdict(list)
    
    for summary in summaries:
        date = summary.get('date', '')
        category = summary.get('category', '')
        
        if category:
            category_timeline[category].append(date)
    
    # Identify trends
    for category, dates in category_timeline.items():
        if len(dates) >= 2:
            # Check if trend is increasing
            date_counts = Counter(dates)
            sorted_dates = sorted(date_counts.keys())
            
            if len(sorted_dates) >= 2:
                recent = date_counts[sorted_dates[-1]]
                previous = date_counts[sorted_dates[-2]]
                
                if recent > previous:
                    direction = 'up'
                elif recent < previous:
                    direction = 'down'
                else:
                    direction = 'neutral'
                
                trends.append({
                    'title': category,
                    'direction': direction,
                    'description': f'Frequency: {previous} → {recent} mentions',
                    'dates': sorted_dates
                })
    
    # Sort by recent frequency
    trends.sort(key=lambda x: len(x.get('dates', [])), reverse=True)
    
    return trends[:5]  # Top 5 trends

def get_recent_newsletters(summaries):
    """Get list of recent newsletters."""
    newsletters = []
    
    for summary in summaries:
        date = summary.get('date', '')
        headline = summary.get('headline', 'Untitled')
        category = summary.get('category', 'Bloomberg')
        
        newsletters.append({
            'title': headline,
            'date': date,
            'source': 'Bloomberg',
            'category': category
        })
    
    # Sort by date, most recent first
    newsletters.sort(key=lambda x: x['date'], reverse=True)
    
    return newsletters[:20]  # Last 20 newsletters

def main():
    """Generate intelligence report."""
    print("=" * 60)
    print("Bloomberg Intelligence Generator")
    print("=" * 60)
    
    # Load data
    knowledge_base = load_knowledge_base()
    summaries = load_recent_summaries(days=7)
    
    print(f"Loaded {len(summaries)} summaries from last 7 days")
    print(f"Knowledge base: {len(knowledge_base.get('themes', {}))} themes")
    
    # Generate insights
    hot_topics = extract_hot_topics(summaries, knowledge_base)
    trends = identify_trends(summaries, knowledge_base)
    recent_newsletters = get_recent_newsletters(summaries)
    
    # Create report
    report = {
        'generated_at': datetime.now().isoformat(),
        'hot_topics': hot_topics,
        'trends': trends,
        'recent_newsletters': recent_newsletters,
        'stats': {
            'summaries_analyzed': len(summaries),
            'themes_tracked': len(knowledge_base.get('themes', {})),
            'companies_tracked': len(knowledge_base.get('entities', {}).get('companies', {}))
        }
    }
    
    # Save report
    report_file = os.path.join(BLOOMBERG_DIR, 'intelligence_report.json')
    with open(report_file, 'w') as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    
    print(f"\nReport saved to: {report_file}")
    print(f"\nHot Topics: {len(hot_topics)}")
    for topic in hot_topics:
        print(f"  - {topic['title']} ({topic['heat']})")
    
    print(f"\nTrends: {len(trends)}")
    for trend in trends:
        print(f"  - {trend['title']} ({trend['direction']})")
    
    print(f"\nRecent Newsletters: {len(recent_newsletters)}")

if __name__ == '__main__':
    main()
