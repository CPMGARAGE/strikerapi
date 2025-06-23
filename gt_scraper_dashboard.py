import asyncio
from datetime import datetime, timedelta
from pathlib import Path
import json
import os
import re

try:
    from playwright.async_api import async_playwright
except ImportError:
    print("❌ Playwright not installed")
    exit(1)

try:
    from bs4 import BeautifulSoup
except ImportError:
    print("❌ BeautifulSoup not installed")
    exit(1)

# === CONFIG ===
WEB_DATA_FOLDER = Path("./assets/data")
WEB_DATA_FOLDER.mkdir(parents=True, exist_ok=True)

URL = "https://www.gtleagues.com/dashboard"

def parse_gt_time_to_datetime(time_str):
    """Convert GT Leagues time format to datetime object"""
    try:
        # GT Leagues shows times like "13:00", "13:15", "13:30"
        if ':' in time_str and len(time_str) <= 6:
            # Clean the time string
            clean_time = time_str.strip()
            
            # Parse hour:minute
            if ':' in clean_time:
                parts = clean_time.split(':')
                if len(parts) >= 2:
                    hour = int(parts[0])
                    minute = int(parts[1])
                    
                    # Create datetime for today
                    now = datetime.now()
                    match_time = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
                    
                    # If time has passed today, it might be tomorrow
                    # But GT Leagues usually shows current day matches
                    if match_time < now - timedelta(hours=1):  # Allow 1 hour buffer
                        match_time += timedelta(days=1)
                        
                    return match_time
    except Exception as e:
        print(f"[⚠️] Error parsing time '{time_str}': {e}")
    
    # Fallback - return current time
    return datetime.now()

def get_match_status_from_indicators(row_html):
    """Extract match status from GT Leagues indicators"""
    row_text = str(row_html).lower()
    
    # Check for status indicators
    if 'not started' in row_text or 'not_started' in row_text:
        return 'Upcoming'
    elif 'live' in row_text or 'playing' in row_text:
        return 'Live'
    elif 'finished' in row_text or 'ended' in row_text:
        return 'Finished'
    elif 'halftime' in row_text or 'ht' in row_text:
        return 'HT'
    else:
        return 'Upcoming'  # Default

def filter_current_and_upcoming_matches(fixtures, hours_ahead=2):
    """Filter to show live + upcoming matches within specified hours"""
    now = datetime.now()
    cutoff_time = now + timedelta(hours=hours_ahead)
    filtered_fixtures = []
    
    print(f"[🕐] Current time: {now.strftime('%H:%M')}")
    print(f"[🎯] Looking for matches until: {cutoff_time.strftime('%H:%M')}")
    
    for fixture in fixtures:
        try:
            match_time = parse_gt_time_to_datetime(fixture['kickoff_time'])
            time_diff_minutes = (match_time - now).total_seconds() / 60
            
            # Include matches that are:
            # 1. Live/ongoing (any status that's not "Upcoming")
            # 2. Starting within the next X hours
            # 3. Started within the last 2 hours (could still be playing)
            
            is_live = fixture.get('status', '').lower() in ['live', 'ht', 'halftime', 'playing']
            is_recent_or_upcoming = -120 <= time_diff_minutes <= (hours_ahead * 60)  # 2 hours past to X hours future
            
            if is_live or is_recent_or_upcoming:
                # Add time metadata
                if time_diff_minutes > 0:
                    fixture['time_until_kickoff'] = f"in {int(time_diff_minutes)}min"
                elif time_diff_minutes > -30:
                    fixture['time_until_kickoff'] = "LIVE"
                else:
                    fixture['time_until_kickoff'] = f"{int(-time_diff_minutes)}min ago"
                
                fixture['calculated_datetime'] = match_time.isoformat()
                fixture['minutes_from_now'] = int(time_diff_minutes)
                filtered_fixtures.append(fixture)
                
                print(f"[✅] Included: {fixture['home_team']} vs {fixture['away_team']} at {fixture['kickoff_time']} ({fixture['time_until_kickoff']})")
                
        except Exception as e:
            print(f"[⚠️] Error filtering match {fixture.get('home_team', 'Unknown')}: {e}")
            # Include anyway if we can't parse
            fixture['time_until_kickoff'] = "TBD"
            fixture['calculated_datetime'] = datetime.now().isoformat()
            filtered_fixtures.append(fixture)
    
    # Sort by time (live matches first, then by kickoff time)
    def sort_key(match):
        if match.get('status', '').lower() in ['live', 'ht', 'playing']:
            return 0  # Live matches first
        return match.get('minutes_from_now', 999)  # Then by time
    
    filtered_fixtures.sort(key=sort_key)
    
    print(f"[📊] Filtered to {len(filtered_fixtures)} relevant matches")
    return filtered_fixtures

async def run_parser():
    """Parse GT Leagues dashboard with correct structure"""
    print("[🔄] Running GT Leagues parser...")
    
    snapshot_path = WEB_DATA_FOLDER / "gt_dashboard_latest.html"
    
    if not snapshot_path.exists():
        print("[❌] No snapshot found to parse")
        return

    with open(snapshot_path, "r", encoding="utf-8") as f:
        soup = BeautifulSoup(f, "html.parser")

    print("[🔍] Analyzing GT Leagues dashboard structure...")
    
    # Find all table rows
    fixtures = []
    rows = soup.find_all("tr")
    
    print(f"[📋] Found {len(rows)} table rows to analyze")
    
    for i, row in enumerate(rows):
        try:
            cells = row.find_all("td")
            if len(cells) >= 6:  # Need at least 6 cells for a valid match row
                
                # Debug: Print first few rows to understand structure
                if i < 5:
                    cell_texts = [cell.get_text(strip=True) for cell in cells[:8]]
                    print(f"[DEBUG] Row {i}: {cell_texts}")
                
                # Extract data based on GT Leagues structure
                # Usually: [Time, Week, Flag, Week#, Home Team, Away Team, Channel, Status]
                time_text = cells[0].get_text(strip=True)
                
                # Try different positions for team names based on structure
                home_team = ""
                away_team = ""
                tv_channel = "GT Leagues"
                
                # Method 1: Look for team names in cells 4 and 5
                if len(cells) > 5:
                    potential_home = cells[4].get_text(strip=True)
                    potential_away = cells[5].get_text(strip=True)
                    
                    # Validate team names (should be more than 2 chars, not numbers)
                    if len(potential_home) > 2 and len(potential_away) > 2 and not potential_home.isdigit():
                        home_team = potential_home
                        away_team = potential_away
                
                # Method 2: If method 1 failed, try different positions
                if not home_team and len(cells) > 7:
                    for j in range(len(cells) - 1):
                        cell1 = cells[j].get_text(strip=True)
                        cell2 = cells[j + 1].get_text(strip=True)
                        
                        # Look for team-like names (longer strings, not numbers)
                        if (len(cell1) > 3 and len(cell2) > 3 and 
                            not cell1.isdigit() and not cell2.isdigit() and
                            'vs' not in cell1.lower() and 'vs' not in cell2.lower()):
                            home_team = cell1
                            away_team = cell2
                            break
                
                # Get status from HTML indicators
                match_status = get_match_status_from_indicators(row)
                
                # Get TV channel if available
                if len(cells) > 6:
                    channel_text = cells[6].get_text(strip=True)
                    if channel_text and len(channel_text) < 20:  # Reasonable channel name length
                        tv_channel = channel_text
                
                # Validate we have good data
                if (time_text and home_team and away_team and 
                    len(home_team) > 2 and len(away_team) > 2 and
                    ':' in time_text):  # Time should contain ':'
                    
                    fixture = {
                        "kickoff_time": time_text,
                        "week": f"GT Week {datetime.now().strftime('%W')}",
                        "home_team": home_team,
                        "away_team": away_team,
                        "tv_channel": tv_channel,
                        "status": match_status,
                        "last_updated": datetime.now().isoformat(),
                        "match_id": f"GT_{home_team}_{away_team}_{time_text}".replace(" ", "_").replace(":", "")
                    }
                    
                    fixtures.append(fixture)
                    print(f"[✅] Parsed: {time_text} - {home_team} vs {away_team} ({match_status})")
                    
        except Exception as e:
            print(f"[⚠️] Error parsing row {i}: {e}")
            continue

    print(f"[📋] Successfully parsed {len(fixtures)} total matches")
    
    # Filter to current and upcoming matches only
    filtered_fixtures = filter_current_and_upcoming_matches(fixtures, hours_ahead=2)

    # Parse player stats (if available in a different table)
    players = []
    
    # Look for player stats tables
    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        for row in rows:
            cols = row.find_all("td")
            if len(cols) >= 5:
                try:
                    # Look for player name and percentages
                    name = cols[1].get_text(strip=True)
                    
                    # Try to find percentage columns
                    win_text = ""
                    draw_text = ""
                    loss_text = ""
                    
                    for i, col in enumerate(cols[2:5]):  # Check next 3 columns
                        text = col.get_text(strip=True)
                        if '%' in text or text.replace('.', '').isdigit():
                            if not win_text:
                                win_text = text.replace('%', '')
                            elif not draw_text:
                                draw_text = text.replace('%', '')
                            elif not loss_text:
                                loss_text = text.replace('%', '')
                    
                    if name and win_text and len(name) > 2:
                        try:
                            win_percent = float(win_text) if win_text else 0
                            draw_percent = float(draw_text) if draw_text else 0
                            loss_percent = float(loss_text) if loss_text else 0
                            
                            players.append({
                                "player": name,
                                "win_percent": win_percent,
                                "draw_percent": draw_percent,
                                "loss_percent": loss_percent,
                                "total_games": 100,
                                "confidence_score": win_percent + (draw_percent * 0.5)
                            })
                        except ValueError:
                            continue
                            
                except Exception:
                    continue

    # Sort players by confidence
    players.sort(key=lambda x: x['confidence_score'], reverse=True)

    # Save files
    fixtures_file = WEB_DATA_FOLDER / "fixtures.json"
    players_file = WEB_DATA_FOLDER / "players.json"
    status_file = WEB_DATA_FOLDER / "status.json"
    
    live_count = len([f for f in filtered_fixtures if f.get('status', '').lower() in ['live', 'ht', 'playing']])
    upcoming_count = len([f for f in filtered_fixtures if f.get('status', '').lower() == 'upcoming'])
    
    status_data = {
        "last_updated": datetime.now().isoformat(),
        "last_updated_readable": datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC"),
        "fixtures_count": len(filtered_fixtures),
        "players_count": len(players),
        "live_matches": live_count,
        "upcoming_matches": upcoming_count,
        "status": "success",
        "data_window": "2 hours from now",
        "source": "gtleagues.com",
        "parsing_method": "improved_gt_structure"
    }

    with open(fixtures_file, "w", encoding="utf-8") as f:
        json.dump(filtered_fixtures, f, indent=2)

    with open(players_file, "w", encoding="utf-8") as f:
        json.dump(players[:20], f, indent=2)
        
    with open(status_file, "w", encoding="utf-8") as f:
        json.dump(status_data, f, indent=2)

    print(f"[✅] Fixtures saved: {len(filtered_fixtures)} matches")
    print(f"[✅] Players saved: {len(players)} players")
    print(f"[📈] Live: {live_count} | Upcoming: {upcoming_count}")
    
    return len(filtered_fixtures), live_count, upcoming_count

async def run():
    """Main scraper function with better error handling"""
    try:
        print(f"[🛰] Starting GT Leagues scraper at {datetime.now().strftime('%H:%M:%S')}")
        web_output_file = WEB_DATA_FOLDER / "gt_dashboard_latest.html"

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
            page = await context.new_page()

            print(f"[🛰] Navigating to {URL}...")
            await page.goto(URL, wait_until="networkidle", timeout=30000)

            print("[⏳] Waiting for GT Leagues dashboard to load...")
            await page.wait_for_timeout(10000)  # Extra time for GT Leagues

            # Wait for specific elements that indicate the page has loaded
            try:
                await page.wait_for_selector("table", timeout=10000)
                print("[✅] Dashboard table found")
            except:
                print("[⚠️] No table found, but continuing with page content")

            html = await page.content()
            web_output_file.write_text(html, encoding='utf-8')

            print(f"[🌐] Snapshot saved: {web_output_file}")
            await browser.close()

            # Run parser
            match_count, live_count, upcoming_count = await run_parser()
            
            print(f"[🚀] Scraper completed successfully!")
            print(f"[📊] Results: {match_count} total, {live_count} live, {upcoming_count} upcoming")
            
            return True
            
    except Exception as e:
        print(f"[❌] Scraper failed: {e}")
        
        # Create error status
        error_status = {
            "last_updated": datetime.now().isoformat(),
            "status": "error",
            "error_message": str(e),
            "fixtures_count": 0,
            "players_count": 0,
            "live_matches": 0,
            "upcoming_matches": 0
        }
        
        status_file = WEB_DATA_FOLDER / "status.json"
        with open(status_file, "w") as f:
            json.dump(error_status, f, indent=2)
            
        return False

if __name__ == "__main__":
    try:
        success = asyncio.run(run())
        if success:
            print("[🚀] StrikerBot GT Leagues update completed successfully!")
        else:
            print("[❌] StrikerBot GT Leagues update failed!")
            exit(1)
    except Exception as e:
        print(f"[💥] Critical error: {e}")
        exit(1)
