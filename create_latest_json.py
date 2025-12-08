#!/usr/bin/env python3
"""
Creates hoopshype_rumors_latest.json with the 100 most recent rumors
Run this once to create the file, then update_rumors.py will maintain it
"""

import json

def main():
    print("Creating hoopshype_rumors_latest.json...")
    
    all_rumors = []
    
    # Load all parts
    for part_num in range(1, 8):
        filename = f'hoopshype_rumors_part{part_num}.json'
        try:
            with open(filename, 'r', encoding='utf-8') as f:
                data = json.load(f)
                # Add part number and index for sorting
                for i, r in enumerate(data):
                    r['_part'] = part_num
                    r['_idx'] = i
                all_rumors.extend(data)
                print(f"  Loaded {filename}: {len(data)} rumors")
        except FileNotFoundError:
            print(f"  Skipped {filename} (not found)")
        except Exception as e:
            print(f"  Error loading {filename}: {e}")
    
    if not all_rumors:
        print("No rumors found!")
        return
    
    # Sort by date DESC, then part DESC (higher = newer), then idx DESC (higher = newer within part)
    all_rumors.sort(
        key=lambda x: (x['archive_date'], x.get('_part', 0), x.get('_idx', 0)), 
        reverse=True
    )
    
    # Take newest 100 and remove temp fields
    latest_100 = all_rumors[:100]
    for r in latest_100:
        r.pop('_part', None)
        r.pop('_idx', None)
    
    # Save
    with open('hoopshype_rumors_latest.json', 'w', encoding='utf-8') as f:
        json.dump(latest_100, f, ensure_ascii=False)
    
    print(f"\n✅ Created hoopshype_rumors_latest.json with {len(latest_100)} rumors")
    print(f"   Date range: {latest_100[-1]['archive_date']} to {latest_100[0]['archive_date']}")

if __name__ == '__main__':
    main()
