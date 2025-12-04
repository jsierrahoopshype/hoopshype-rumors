#!/usr/bin/env python3
"""
HoopsHype Rumors Incremental Updater
Scrapes only NEW rumors since last update and appends to database
Runs 4x daily via GitHub Actions
"""

import requests
from bs4 import BeautifulSoup
import json
from datetime import datetime, timedelta
import time
import sys
import os

def load_latest_date():
    """Find the most recent date in our database"""
    try:
        with open('hoopshype_rumors_part5.json', 'r', encoding='utf-8') as f:
            rumors = json.load(f)
            if rumors:
                # Get the most recent archive_date
                latest = max(rumors, key=lambda x: x['archive_date'])
                return datetime.fromisoformat(latest['archive_date'])
    except FileNotFoundError:
        print("Database file not found, starting from today")
    except Exception as e:
        print(f"Error loading database: {e}")
    
    # Default to yesterday if we can't load
    return datetime.now() - timedelta(days=1)

def scrape_rumors_for_date(date_obj):
    """Scrape all rumors from a specific date"""
    today = datetime.now().date()
    target_date = date_obj.date()
    
    # Authentication for preview site
    username = os.environ.get('HOOPSHYPE_USERNAME', 'preview')
    password = os.environ.get('HOOPSHYPE_PASSWORD', 'hhpreview')
    auth = (username, password)
    
    # Today's rumors are at /rumors, past rumors are in /archive/
    if target_date == today:
        url = "http://preview.hoopshype.com/rumors"
    else:
        date_str = date_obj.strftime('%Y%m%d')
        year = date_obj.strftime('%Y')
        url = f"http://preview.hoopshype.com/archive/rumors/{year}/rumors-{date_str}.htm"
    
    try:
        response = requests.get(url, timeout=10, auth=auth)
        if response.status_code != 200:
            return []
        
        soup = BeautifulSoup(response.content, 'html.parser')
        rumors = []
        
        # Find all rumor blocks
        rumor_divs = soup.find_all('div', class_='rumor')
        
        for rumor_div in rumor_divs:
            rumor_data = {
                'date': '',
                'archive_date': date_obj.strftime('%Y-%m-%d'),
                'text': '',
                'outlet': '',
                'source_url': '',
                'tags': []
            }
            
            # Get display date
            date_span = rumor_div.find('span', class_='rumorDate')
            if date_span:
                rumor_data['date'] = date_span.get_text(strip=True)
            
            # Get rumor text
            rumor_text_p = rumor_div.find('p', class_='rumor-content')
            if rumor_text_p:
                # Get full text
                rumor_data['text'] = rumor_text_p.get_text(strip=True)
                
                # Get source URL
                quote_link = rumor_text_p.find('a', class_='quote')
                if quote_link:
                    rumor_data['source_url'] = quote_link.get('href', '')
                
                # Get outlet
                media_link = rumor_text_p.find('a', class_='rumormedia')
                if media_link:
                    rumor_data['outlet'] = media_link.get_text(strip=True)
            
            # Get tags
            tags_div = rumor_div.find('div', class_='tags')
            if tags_div:
                tag_links = tags_div.find_all('a')
                rumor_data['tags'] = [tag.get_text(strip=True) for tag in tag_links]
            
            if rumor_data['text']:
                rumors.append(rumor_data)
        
        return rumors
        
    except Exception as e:
        print(f"Error scraping {url}: {e}")
        return []

def main():
    print("=" * 60)
    print("HOOPSHYPE RUMORS INCREMENTAL UPDATER")
    print("=" * 60)
    
    # Find latest date in database
    latest_date = load_latest_date()
    print(f"\nLatest rumor in database: {latest_date.strftime('%Y-%m-%d')}")
    
    # Scrape from next day until today
    start_date = latest_date + timedelta(days=1)
    end_date = datetime.now()
    
    if start_date > end_date:
        print("\n✅ Database is already up to date!")
        return
    
    print(f"Scraping from {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}")
    
    # Scrape each day
    new_rumors = []
    current_date = start_date
    
    while current_date <= end_date:
        print(f"\nChecking {current_date.strftime('%Y-%m-%d')}...", end=' ')
        
        day_rumors = scrape_rumors_for_date(current_date)
        
        if day_rumors:
            print(f"✓ Found {len(day_rumors)} rumors")
            new_rumors.extend(day_rumors)
        else:
            print("✗ No rumors")
        
        current_date += timedelta(days=1)
        time.sleep(1)  # Be nice to the server
    
    # Load existing database
    if new_rumors:
        print(f"\n{'='*60}")
        print(f"FOUND {len(new_rumors)} NEW RUMORS")
        print(f"{'='*60}")
        
        try:
            with open('hoopshype_rumors_part5.json', 'r', encoding='utf-8') as f:
                existing_rumors = json.load(f)
        except FileNotFoundError:
            existing_rumors = []
        
        # Append new rumors
        existing_rumors.extend(new_rumors)
        
        # Save updated database
        with open('hoopshype_rumors_part5.json', 'w', encoding='utf-8') as f:
            json.dump(existing_rumors, f, ensure_ascii=False, indent=2)
        
        print(f"\n✅ Successfully appended {len(new_rumors)} new rumors!")
        print(f"📊 Total rumors in database: {len(existing_rumors)}")
        
        # Update index file
        try:
            with open('rumors_index.json', 'r', encoding='utf-8') as f:
                index = json.load(f)
            
            index['last_updated'] = datetime.now().isoformat()
            index['total_rumors'] = len(existing_rumors)
            
            with open('rumors_index.json', 'w', encoding='utf-8') as f:
                json.dump(index, f, indent=2)
        except Exception as e:
            print(f"Note: Could not update index file: {e}")
        
    else:
        print(f"\n✓ No new rumors found")

if __name__ == '__main__':
    main()
