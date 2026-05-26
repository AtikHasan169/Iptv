import asyncio
import aiohttp
import random

PLAYLIST_URL = "https://sm-live-tv-auto-update-playlist.pages.dev/Combined_Live_TV.m3u"
OUTPUT_FILE = "working_channels.m3u"

# STEALTH CONFIGURATION (Crucial for GitHub Actions Safety)
CONCURRENT_LIMIT = 3     # Dropped from 40 to 3. This stops GitHub from flagging it as a network attack.
TIMEOUT_SECONDS = 12     # High timeout to give slow streams plenty of time to respond
DELAY_BETWEEN_CHECKS = 0.5 # Adds a slight human-like pause between stream allocations

def parse_m3u(m3u_content):
    lines = m3u_content.splitlines()
    channels = []
    current_extinf = None
    for line in lines:
        line = line.strip()
        if not line:
            continue
        if line.startswith("#EXTINF:"):
            current_extinf = line
        elif line.startswith("#") and not line.startswith("#EXTM3U"):
            continue
        elif not line.startswith("#"):
            if current_extinf:
                channels.append({"extinf": current_extinf, "url": line})
                current_extinf = None
            else:
                channels.append({"extinf": "#EXTINF:-1,Channel", "url": line})
    return channels

async def check_channel(session, semaphore, channel):
    async with semaphore:
        # Introduce a randomized fractional delay to break up automated traffic patterns
        await asyncio.sleep(random.uniform(0.1, DELAY_BETWEEN_CHECKS))
        
        url = channel["url"]
        timeout = aiohttp.ClientTimeout(total=TIMEOUT_SECONDS)
        
        # Masquerade as a standard Windows 10 Google Chrome Browser
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "*/*",
            "Accept-Language": "en-US,en;q=0.9",
            "Connection": "keep-alive"
        }
        
        try:
            async with session.get(url, timeout=timeout, headers=headers, ssl=False, allow_redirects=True) as response:
                if 200 <= response.status < 400:
                    return channel
        except Exception:
            pass
        return None

async def main():
    connector = aiohttp.TCPConnector(limit=CONCURRENT_LIMIT, ttl_dns_cache=300)
    async with aiohttp.ClientSession(connector=connector) as session:
        print("📥 Downloading remote source playlist...")
        try:
            async with session.get(PLAYLIST_URL) as response:
                response.raise_for_status()
                m3u_text = await response.text()
        except Exception as e:
            print(f"❌ Core playlist download failed: {e}")
            return

        channels = parse_m3u(m3u_text)
        total_channels = len(channels)
        print(f"📋 Loaded {total_channels} streams. Commencing stealth verification loop...")

        semaphore = asyncio.Semaphore(CONCURRENT_LIMIT)
        tasks = [check_channel(session, semaphore, ch) for ch in channels]
        
        working_channels = []
        checked_count = 0

        # Gather tasks natively as they finish
        for future in asyncio.as_completed(tasks):
            result = await future
            checked_count += 1
            if result:
                working_channels.append(result)
            
            if checked_count % 20 == 0 or checked_count == total_channels:
                print(f"⏳ Processed: {checked_count}/{total_channels} | Verified Active: {len(working_channels)}")

        print("\n💾 Filtering loop finalized. Exporting data to code workspace...")
        try:
            with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
                f.write("#EXTM3U\n")
                for ch in working_channels:
                    f.write(f"{ch['extinf']}\n")
                    f.write(f"{ch['url']}\n")
            print("✨ Operation successful.")
        except IOError as e:
            print(f"❌ File I/O Error: {e}")

if __name__ == "__main__":
    asyncio.run(main())
