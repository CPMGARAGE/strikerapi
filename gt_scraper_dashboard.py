import asyncio
from datetime import datetime, timedelta
from pathlib import Path
import json
import os

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

def parse_time_to_datetime(time_str, week_str):
    """Convert kickoff time string to datetime object"""
    try:
        if ':' in time_str:
            time_parts = time_str.strip().split(':')
            hour = int(time_parts[0])
            minute = int(time_parts[1])
            
            now = datetime.now()
            match_time = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            
            if match_time < now:
                match_time += timedelta(days=1)
                
            return match_time
    except:
        pass
    
    return datetime.now() + timedelta(minutes=30 + hash(time_str) % 120)

def filter_matches_by_time_window(fixtures, hours=2):
    """Filter matches to show only those within the next X hours"""
    now = datetime.now()
    filtered_fixtures = []
    
    for fixture in fixtures:
        try:
            match_time = parse_time_to_datetime(fixture['kickoff_time'], fixture.get('week', ''))
            time_diff = (match_time - now).total_seconds() / 3600
            
            is_live = fixture.get('status', '').lower() in ['live', 'ht', '1st half', '2nd half']
            is_upcoming = -0.5 <= time_diff <= hours
            
            if is_live or is_upcoming:
                fixture['calculated_datetime'] = match_time.isoformat()
                fixture['time_until_kickoff'] = f"{time_diff:.1f}h" if time_diff > 0 else "LIVE" if is_live else "FT"
                filtered_fixtures.append(fixture)
                
        except Exception as e:
            print(f"[⚠️] Error processing match time: {e}")
            fixture['calculated_datetime'] = datetime.now().isoformat()
            fixture['time_until_kickoff'] = "TBD"
            filtered_fixtures.append(fixture)
    
    filtered_fixtures.sort(key=lambda x: x.get('calculated_datetime', ''))
    print(f"[📊] Filtered to {len(filtered_fixtures)} matches within {hours} hour window")
    return filtered_fixtures

async def run_parser():
    """Run the parser and save JSON to web-accessible location"""
    print("[🔄] Running parser...")
    
    snapshot_path = WEB_DATA_FOLDER / "gt_dashboard_latest.html"
    
    if not snapshot_path.exists():
        print("[❌] No snapshot found to parse")
        return

    with open(snapshot_path, "r", encoding="utf-8") as f:
        soup = BeautifulSoup(f, "html.parser")

    # Parse fixtures
    fixtures = []
    fixture_rows = soup.find_all("tr")
    
    print(f"[🔍] Found {len(fixture_rows)} table rows to analyze")
    
    for row in fixture_rows:
        cells = row.find_all("td")
        if len(cells) >= 6:
            try:
                time_text = cells[0].get_text(strip=True)
                week_info = cells[3].get_text(strip=True) if len(cells) > 3 else "Week TBD"
                home_team = cells[4].get_text(strip=True) if len(cells) > 4 else ""
                away_team = cells[5].get_text(strip=True) if len(cells) > 5 else ""
                tv_channel = cells[6].get_text(strip=True) if len(cells) > 6 else "TBD"
                match_status = cells[7].get_text(strip=True) if len(cells) > 7 else "Upcoming"
                
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
                win_text = cols[2].get_text(strip=True).replace('%', '')
                draw_text = cols[3].get_text(strip=True).replace('%', '')
                loss_text = cols[4].get_text(strip=True).replace('%', '')
                
                win_percent = float(win_text)
                draw_percent = float(draw_text)
                loss_percent = float(loss_text)
                
                if name and len(name) > 2:
                    players.append({
                        "player": name,
                        "win_percent": win_percent,
                        "draw_percent": draw_percent,
                        "loss_percent": loss_percent,
                        "total_games": 100,
                        "confidence_score": win_percent + (draw_percent * 0.5)
                    })
            except (ValueError, AttributeError):
                continue

    players.sort(key=lambda x: x['confidence_score'], reverse=True)

    # Save files
    fixtures_file = WEB_DATA_FOLDER / "fixtures.json"
    players_file = WEB_DATA_FOLDER / "players.json"
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
        "source": "gtleagues.com"
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

async def run():
    """Main scraper function"""
    today = datetime.now().strftime("%Y%m%d_%H%M")
    web_output_file = WEB_DATA_FOLDER / "gt_dashboard_latest.html"

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        )
        page = await context.new_page()

        print(f"[🛰] Navigating to {URL} ...")
        await page.goto(URL, wait_until="networkidle", timeout=30000)

        print("[⏳] Waiting for page to load...")
        await page.wait_for_timeout(8000)

        html = await page.content()
        web_output_file.write_text(html, encoding='utf-8')

        print(f"[🌐] Snapshot saved: {web_output_file}")
        await browser.close()

        # Run parser
        await run_parser()

if __name__ == "__main__":
    try:
        asyncio.run(run())
        print("[🚀] StrikerBot data update completed successfully!")
    except Exception as e:
        print(f"[❌] StrikerBot data update failed: {e}")
        
        error_status = {
            "last_updated": datetime.now().isoformat(),
            "status": "error",
            "error_message": str(e),
            "fixtures_count": 0,
            "players_count": 0
        }
        
        status_file = WEB_DATA_FOLDER / "status.json"
        with open(status_file, "w") as f:
            json.dump(error_status, f, indent=2)
