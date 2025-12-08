#!/usr/bin/env python3
"""
HoopsHype Rumors Incremental Updater
Scrapes only NEW rumors since last update and appends to database
Runs hourly via GitHub Actions
"""

import requests
from bs4 import BeautifulSoup
import json
from datetime import datetime, timedelta, timezone
import time
import sys
import os

# US Eastern timezone offset (UTC-5, or UTC-4 during DST)
# Using -5 to be safe (EST)
US_EASTERN_OFFSET = timedelta(hours=-5)

def get_us_eastern_now():
    """Get current time in US Eastern timezone"""
    utc_now = datetime.now(timezone.utc)
    eastern_now = utc_now + US_EASTERN_OFFSET
    return eastern_now.replace(tzinfo=None)  # Remove tzinfo for compatibility

def load_existing_rumors():
    """Load all existing rumors to check for duplicates"""
    existing_texts = set()
    
    for part_num in range(1, 8):
        filename = f'hoopshype_rumors_part{part_num}.json'
        try:
            with open(filename, 'r', encoding='utf-8') as f:
                rumors = json.load(f)
                for r in rumors:
                    # Use first 100 chars of text as fingerprint
                    existing_texts.add(r['text'][:100] if r['text'] else '')
        except FileNotFoundError:
            continue
        except Exception as e:
            print(f"Error loading {filename}: {e}")
            continue
    
    return existing_texts

def load_latest_date():
    """Find the most recent date in our database by checking all parts"""
    latest_date = None
    
    # Check all 7 parts since data is not sorted by date
    for part_num in range(1, 8):
        filename = f'hoopshype_rumors_part{part_num}.json'
        try:
            with open(filename, 'r', encoding='utf-8') as f:
                rumors = json.load(f)
                if rumors:
                    # Get the most recent archive_date from this part
                    part_latest = max(rumors, key=lambda x: x['archive_date'])
                    part_date = datetime.fromisoformat(part_latest['archive_date'])
                    
                    if latest_date is None or part_date > latest_date:
                        latest_date = part_date
                        
        except FileNotFoundError:
            continue
        except Exception as e:
            print(f"Error loading {filename}: {e}")
            continue
    
    if latest_date is None:
        print("No database files found, starting from yesterday")
        return get_us_eastern_now() - timedelta(days=1)
    
    return latest_date

def scrape_rumors_for_date(date_obj):
    """Scrape all rumors from a specific date"""
    today = get_us_eastern_now().date()
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
        
        for idx, rumor_div in enumerate(rumor_divs):
            rumor_data = {
                'date': '',
                'archive_date': date_obj.strftime('%Y-%m-%d'),  # Default to scrape date
                'text': '',
                'quote': '',
                'outlet': '',
                'source_url': '',
                'tags': []
            }
            
            # Get display date and try to parse it for accurate archive_date
            date_span = rumor_div.find('span', class_='date')
            if date_span:
                date_text = date_span.get_text(strip=True)
                rumor_data['date'] = date_text
                
                # Try to parse the actual date (format: "Dec. 07, 2025, 4:55 AM GMT+1")
                try:
                    # Remove timezone info for parsing
                    date_clean = date_text.split('GMT')[0].strip().rstrip(',')
                    # Try parsing "Dec. 07, 2025, 4:55 AM" or similar
                    for fmt in ['%b. %d, %Y, %I:%M %p', '%b %d, %Y, %I:%M %p', '%B %d, %Y, %I:%M %p']:
                        try:
                            parsed_date = datetime.strptime(date_clean, fmt)
                            rumor_data['archive_date'] = parsed_date.strftime('%Y-%m-%d')
                            break
                        except ValueError:
                            continue
                except:
                    pass  # Keep default archive_date if parsing fails
            
            # Get rumor text - preview site uses 'rumortext' class, not 'rumor-content'
            rumor_text_p = rumor_div.find('p', class_='rumortext')
            
            if rumor_text_p:
                # Get full text
                rumor_data['text'] = rumor_text_p.get_text(strip=True)
                
                # Get the quoted text specifically (will be hyperlinked)
                quote_link = rumor_text_p.find('a', class_='quote')
                if quote_link:
                    rumor_data['quote'] = quote_link.get_text(strip=True)
                    rumor_data['source_url'] = quote_link.get('href', '')
                else:
                    rumor_data['quote'] = ''
                
                # Get all links in the paragraph
                all_links = rumor_text_p.find_all('a')
                
                # If no quote link was found, use first link as source
                if not rumor_data['source_url'] and len(all_links) > 0:
                    first_link = all_links[0]
                    href = first_link.get('href', '')
                    if href and not href.startswith('/rumors'):
                        rumor_data['source_url'] = href
                
                # Last link is often the outlet/media source
                if len(all_links) > 1:
                    last_link = all_links[-1]
                    outlet_text = last_link.get_text(strip=True)
                    if outlet_text:
                        rumor_data['outlet'] = outlet_text
                elif len(all_links) == 1 and not rumor_data['quote']:
                    # If only one link and it's not a quote, it's probably the outlet
                    rumor_data['outlet'] = all_links[0].get_text(strip=True)
            
            # Get tags - preview site uses 'tag' class (singular)
            tags_div = rumor_div.find('div', class_='tag')
            
            if tags_div:
                # Find all <a> tags with class="tag" inside the tag div
                tag_links = tags_div.find_all('a', class_='tag')
                rumor_data['tags'] = [tag.get_text(strip=True) for tag in tag_links]
            else:
                # Try alternative: find all links at the end of the rumor div
                all_links = rumor_div.find_all('a')
                # Skip the first few links (they're source/outlet), take the rest as tags
                if len(all_links) > 2:
                    tag_links = all_links[2:]  # Skip source and outlet links
                    rumor_data['tags'] = [tag.get_text(strip=True) for tag in tag_links if not tag.get('class')]
            
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
    
    # Show current time for debugging
    eastern_now = get_us_eastern_now()
    print(f"\nCurrent time (US Eastern): {eastern_now.strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Load existing rumors to check for duplicates
    existing_texts = load_existing_rumors()
    print(f"Loaded {len(existing_texts)} existing rumor fingerprints")
    
    # Find latest date in database
    latest_date = load_latest_date()
    print(f"Latest rumor date in database: {latest_date.strftime('%Y-%m-%d')}")
    
    # ALWAYS scrape from latest_date (not +1) through today
    # This ensures we catch new rumors posted today after previous scrape
    start_date = latest_date
    end_date = get_us_eastern_now()
    
    print(f"Scraping from {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}")
    
    # Scrape each day
    new_rumors = []
    current_date = start_date
    
    while current_date <= end_date:
        print(f"\nChecking {current_date.strftime('%Y-%m-%d')}...", end=' ')
        
        day_rumors = scrape_rumors_for_date(current_date)
        
        if day_rumors:
            # Filter out duplicates by checking text fingerprint
            truly_new = []
            for rumor in day_rumors:
                fingerprint = rumor['text'][:100] if rumor['text'] else ''
                if fingerprint and fingerprint not in existing_texts:
                    truly_new.append(rumor)
                    existing_texts.add(fingerprint)  # Add to set to avoid duplicates within same run
            
            print(f"Found {len(day_rumors)} rumors, {len(truly_new)} are NEW")
            new_rumors.extend(truly_new)
        else:
            print("No rumors found")
        
        current_date += timedelta(days=1)
        time.sleep(1)  # Be nice to the server
    
    # Load existing database - use LAST part file (part7)
    if new_rumors:
        print(f"\n{'='*60}")
        print(f"FOUND {len(new_rumors)} NEW RUMORS")
        print(f"{'='*60}")
        
        # Find the last part file
        last_part = 'hoopshype_rumors_part7.json'
        
        try:
            with open(last_part, 'r', encoding='utf-8') as f:
                existing_rumors = json.load(f)
        except FileNotFoundError:
            existing_rumors = []
        
        # Reverse new_rumors so newest rumor gets highest index (appears first after sort)
        # The scraper gets newest first from the page, but we want highest index = newest
        existing_rumors.extend(reversed(new_rumors))
        
        # Save updated database
        with open(last_part, 'w', encoding='utf-8') as f:
            json.dump(existing_rumors, f, ensure_ascii=False)
        
        print(f"\n✅ Successfully appended {len(new_rumors)} new rumors to {last_part}!")
        print(f"📊 Rumors in {last_part}: {len(existing_rumors)}")
        
        # Create latest.json with most recent 100 rumors for instant loading
        try:
            # Collect all rumors from all parts to find the newest 100
            all_rumors_for_latest = []
            for part_num in range(1, 8):
                try:
                    with open(f'hoopshype_rumors_part{part_num}.json', 'r', encoding='utf-8') as f:
                        part_data = json.load(f)
                        for i, r in enumerate(part_data):
                            r['_part'] = part_num
                            r['_idx'] = i
                        all_rumors_for_latest.extend(part_data)
                except:
                    pass
            
            # Sort by date DESC, then part DESC, then idx DESC
            all_rumors_for_latest.sort(
                key=lambda x: (x['archive_date'], x.get('_part', 0), x.get('_idx', 0)), 
                reverse=True
            )
            latest_100 = all_rumors_for_latest[:100]
            
            # Remove temp fields
            for r in latest_100:
                r.pop('_part', None)
                r.pop('_idx', None)
            
            with open('hoopshype_rumors_latest.json', 'w', encoding='utf-8') as f:
                json.dump(latest_100, f, ensure_ascii=False)
            
            print(f"⚡ Created hoopshype_rumors_latest.json with {len(latest_100)} rumors for instant load")
        except Exception as e:
            print(f"Note: Could not create latest.json: {e}")
        
        # Update index file
        try:
            with open('rumors_index.json', 'r', encoding='utf-8') as f:
                index = json.load(f)
            
            index['last_updated'] = datetime.now().isoformat()
            
            # Count total rumors across all parts
            total = 0
            for part_num in range(1, 8):
                try:
                    with open(f'hoopshype_rumors_part{part_num}.json', 'r', encoding='utf-8') as f:
                        total += len(json.load(f))
                except:
                    pass
            
            index['total_rumors'] = total
            
            with open('rumors_index.json', 'w', encoding='utf-8') as f:
                json.dump(index, f, indent=2)
                
            print(f"📊 Total rumors across all parts: {total}")
        except Exception as e:
            print(f"Note: Could not update index file: {e}")
        
    else:
        print(f"\n✅ No new rumors found (all already in database)")
    
    # Always ensure latest.json exists with newest 100 rumors
    try:
        all_rumors_for_latest = []
        for part_num in range(1, 8):
            try:
                with open(f'hoopshype_rumors_part{part_num}.json', 'r', encoding='utf-8') as f:
                    part_data = json.load(f)
                    # Add part number and index for secondary sorting
                    for i, r in enumerate(part_data):
                        r['_part'] = part_num
                        r['_idx'] = i
                    all_rumors_for_latest.extend(part_data)
            except:
                pass
        
        if all_rumors_for_latest:
            # Sort by date DESC, then part DESC (higher = newer), then idx DESC (higher = newer within part)
            all_rumors_for_latest.sort(
                key=lambda x: (x['archive_date'], x.get('_part', 0), x.get('_idx', 0)), 
                reverse=True
            )
            
            # Take newest 100 and remove temp fields
            latest_100 = all_rumors_for_latest[:100]
            for r in latest_100:
                r.pop('_part', None)
                r.pop('_idx', None)
            
            with open('hoopshype_rumors_latest.json', 'w', encoding='utf-8') as f:
                json.dump(latest_100, f, ensure_ascii=False)
            
            print(f"⚡ Updated hoopshype_rumors_latest.json ({len(latest_100)} rumors)")
    except Exception as e:
        print(f"Note: Could not update latest.json: {e}")

if __name__ == '__main__':
    main()
