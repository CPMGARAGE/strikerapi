import asyncio
from datetime import datetime, timedelta
from pathlib import Path
from playwright.async_api import async_playwright
import json
import os

# === CONFIG ===
# For local development
SNAPSHOT_FOLDER = Path.home() / "Desktop" / "gt_snapshots" if os.path.exists(Path.home() / "Desktop") else Path("./snapshots")
SNAPSHOT_FOLDER.mkdir(parents=True, exist_ok=True)

# For web deployment - save to your website's assets folder
WEB_DATA_FOLDER = Path("./assets/data")
WEB_DATA_FOLDER.mkdir(parents=True, exist_ok=True)

URL = "https://www.gtleagues.com/dashboard"

async def run():
    today = datetime.now().strftime("%Y%m%d_%H%M")
    output_file = SNAPSHOT_FOLDER / f"gt_dashboard_{today}.html"
    
    # Also save with a consistent name for web access
    web_output_file = WEB_DATA_FOLDER / "gt_dashboard_latest.html"

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = await context.new_page()

        print(f"[🛰] Navigating to {URL} ...")
        await page.goto(URL, wait_until="networkidle", timeout=30000)

        print("[⏳] Waiting for visible elements to confirm JS is loaded...")
        await page.wait_for_timeout(8000)

        html = await page.content()
        
        # Save to both locations
        output_file.write_text(html, encoding='utf-8')
        web_output_file.write_text(html, encoding='utf-8')

        print(f"[✅] Snapshot saved to: {output_file}")
        print(f"[🌐] Web snapshot saved to: {web_output_file}")
        
        await browser.close()

        # Automatically run parser after scraping
        await run_parser()

def parse_time_to_datetime(time_str, week_str):
    """Convert kickoff time string to datetime object"""
    try:
        # Handle different time formats
        if ':' in time_str:
            time_parts = time_str.strip().split(':')
            hour = int(time_parts[0])
            minute = int(time_parts[1])
            
            # Create datetime for today with the parsed time
            now = datetime.now()
            match_time = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            
            # If the match time is in the past, assume it's tomorrow
            if match_time < now:
                match_time += timedelta(days=1)
                
            return match_time
    except:
        pass
    
    # Fallback: return current time plus random offset
    return datetime.now() + timedelta(minutes=30 + hash(time_str) % 120)

def filter_matches_by_time_window(fixtures, hours=2):
    """Filter matches to show only those within the next X hours"""
    now = datetime.now()
    cutoff_time = now + timedelta(hours=hours)
    
    filtered_fixtures = []
    
    for fixture in fixtures:
        try:
            match_time = parse_time_to_datetime(fixture['kickoff_time'], fixture.get('week', ''))
            
            # Include matches that are:
            # 1. Within the next 2 hours
            # 2. Currently live
            # 3. Recently finished (within last 30 minutes)
            time_diff = (match_time - now).total_seconds() / 3600  # Hours
            
            is_live = fixture.get('status', '').lower() in ['live', 'ht', '1st half', '2nd half']
            is_upcoming = -0.5 <= time_diff <= hours  # 30 min past to 2 hours future
            
            if is_live or is_upcoming:
                # Add calculated datetime for sorting
                fixture['calculated_datetime'] = match_time.isoformat()
                fixture['time_until_kickoff'] = f"{time_diff:.1f}h" if time_diff > 0 else "LIVE" if is_live else "FT"
                filtered_fixtures.append(fixture)
                
        except Exception as e:
            print(f"[⚠️] Error processing match time for {fixture.get('home_team', 'Unknown')}: {e}")
            # Include anyway if we can't parse the time
            fixture['calculated_datetime'] = datetime.now().isoformat()
            fixture['time_until_kickoff'] = "TBD"
            filtered_fixtures.append(fixture)
    
    # Sort by calculated datetime
    filtered_fixtures.sort(key=lambda x: x.get('calculated_datetime', ''))
    
    print(f"[📊] Filtered to {len(filtered_fixtures)} matches within {hours} hour window")
    return filtered_fixtures

async def run_parser():
    """Run the parser and save JSON to web-accessible location"""
    from bs4 import BeautifulSoup
    
    print("[🔄] Running parser...")
    
    # Load the latest snapshot
    snapshot_path = WEB_DATA_FOLDER / "gt_dashboard_latest.html"
    
    if not snapshot_path.exists():
        print("[❌] No snapshot found to parse")
        return

    with open(snapshot_path, "r", encoding="utf-8") as f:
        soup = BeautifulSoup(f, "html.parser")

    # Parse fixtures with improved logic
    fixtures = []
    fixture_rows = soup.find_all("tr")
    
    print(f"[🔍] Found {len(fixture_rows)} table rows to analyze")
    
    for row in fixture_rows:
        cells = row.find_all("td")
        if len(cells) >= 6:  # Minimum required cells
            try:
                time_text = cells[0].get_text(strip=True)
                week_info = cells[3].get_text(strip=True) if len(cells) > 3 else "Week TBD"
                home_team = cells[4].get_text(strip=True) if len(cells) > 4 else ""
                away_team = cells[5].get_text(strip=True) if len(cells) > 5 else ""
                tv_channel = cells[6].get_text(strip=True) if len(cells) > 6 else "TBD"
                match_status = cells[7].get_text(strip=True) if len(cells) > 7 else "Upcoming"
                
                # Only include if we have team names
                if time_text and home_team and away_team and len(home_team) > 1 and len(away_team) > 1:
                    fixture = {
                        "kickoff_time": time_text,
                        "week": week_info,
                        "home_team": home_team,
                        "away_team": away_team,
                        "tv_channel": tv_channel,
                        "status": match_status,
                        "last_updated": datetime.now().isoformat(),
                        "match_id": f"{home_team}_{away_team}_{time_text}".replace(" ", "_")
                    }
                    fixtures.append(fixture)
                    
            except Exception as e:
                print(f"[⚠️] Error parsing row: {e}")
                continue

    print(f"[📋] Parsed {len(fixtures)} total fixtures")
    
    # Filter to 2-hour window
    filtered_fixtures = filter_matches_by_time_window(fixtures, hours=2)

    # Parse players
    players = []
    for row in soup.find_all("tr"):
        cols = row.find_all("td")
        if len(cols) >= 5:
            try:
                name = cols[1].get_text(strip=True)
                win_percent = float(cols[2].get_text(strip=True).replace('%', ''))
                draw_percent = float(cols[3].get_text(strip=True).replace('%', ''))
                loss_percent = float(cols[4].get_text(strip=True).replace('%', ''))
                
                if name and len(name) > 2:  # Valid player name
                    players.append({
                        "player": name,
                        "win_percent": win_percent,
                        "draw_percent": draw_percent,
                        "loss_percent": loss_percent,
                        "total_games": 100,  # Estimated
                        "confidence_score": win_percent + (draw_percent * 0.5)
                    })
            except (ValueError, AttributeError):
                continue

    # Sort players by confidence score
    players.sort(key=lambda x: x['confidence_score'], reverse=True)

    # Save to web-accessible JSON files
    fixtures_file = WEB_DATA_FOLDER / "fixtures.json"
    players_file = WEB_DATA_FOLDER / "players.json"
    
    # Create a comprehensive status file
    status_file = WEB_DATA_FOLDER / "status.json"
    
    live_count = len([f for f in filtered_fixtures if f.get('status', '').lower() in ['live', 'ht']])
    upcoming_count = len([f for f in filtered_fixtures if f.get('status', '').lower() == 'upcoming'])
    
    status_data = {
        "last_updated": datetime.now().isoformat(),
        "last_updated_readable": datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC"),
        "fixtures_count": len(filtered_fixtures),
        "players_count": len(players),
        "live_matches": live_count,
        "upcoming_matches": upcoming_count,
        "status": "success",
        "data_window": "2 hours",
        "next_update": (datetime.now() + timedelta(minutes=30)).isoformat(),
        "source": "gtleagues.com",
        "version": "1.0"
    }

    # Write files
    with open(fixtures_file, "w", encoding="utf-8") as f:
        json.dump(filtered_fixtures, f, indent=2)

    with open(players_file, "w", encoding="utf-8") as f:
        json.dump(players[:20], f, indent=2)  # Top 20 players only
        
    with open(status_file, "w", encoding="utf-8") as f:
        json.dump(status_data, f, indent=2)

    print(f"[✅] Fixtures saved: {fixtures_file} ({len(filtered_fixtures)} matches in 2h window)")
    print(f"[✅] Players saved: {players_file} ({len(players)} players)")
    print(f"[📊] Status saved: {status_file}")
    print(f"[📈] Live: {live_count} | Upcoming: {upcoming_count}")
    
    # Create backup with timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    backup_fixtures = WEB_DATA_FOLDER / f"fixtures_backup_{timestamp}.json"
    with open(backup_fixtures, "w", encoding="utf-8") as f:
        json.dump(filtered_fixtures, f, indent=2)
    
    print(f"[💾] Backup created: {backup_fixtures}")

if __name__ == "__main__":
    try:
        asyncio.run(run())
        print("[🚀] StrikerBot data update completed successfully!")
    except Exception as e:
        print(f"[❌] StrikerBot data update failed: {e}")
        
        # Create error status file
        error_status = {
            "last_updated": datetime.now().isoformat(),
            "status": "error",
            "error_message": str(e),
            "fixtures_count": 0,
            "players_count": 0
        }
        
        status_file = Path("./assets/data/status.json")
        status_file.parent.mkdir(parents=True, exist_ok=True)
        
        with open(status_file, "w") as f:
            json.dump(error_status, f, indent=2)
_percent = float(cols[2].get_text(strip=True))
                draw_percent = float(cols[3].get_text(strip=True))
                loss_percent = float(cols[4].get_text(strip=True))
                if name:
                    players.append({
                        "player": name,
                        "win_percent": win_percent,
                        "draw_percent": draw_percent,
                        "loss_percent": loss_percent
                    })
            except ValueError:
                continue

    # Save to web-accessible JSON files
    fixtures_file = WEB_DATA_FOLDER / "fixtures.json"
    players_file = WEB_DATA_FOLDER / "players.json"
    
    # Also create a status file for last update tracking
    status_file = WEB_DATA_FOLDER / "status.json"
    
    status_data = {
        "last_updated": datetime.now().isoformat(),
        "fixtures_count": len(fixtures),
        "players_count": len(players),
        "status": "success"
    }

    with open(fixtures_file, "w", encoding="utf-8") as f:
        json.dump(fixtures, f, indent=2)

    with open(players_file, "w", encoding="utf-8") as f:
        json.dump(players, f, indent=2)
        
    with open(status_file, "w", encoding="utf-8") as f:
        json.dump(status_data, f, indent=2)

    print(f"[✅] Fixtures saved to: {fixtures_file} ({len(fixtures)} matches)")
    print(f"[✅] Players saved to: {players_file} ({len(players)} players)")
    print(f"[📊] Status saved to: {status_file}")

if __name__ == "__main__":
    asyncio.run(run())
