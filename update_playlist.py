import asyncio
import aiohttp

# Updated Configuration for Home Networks
PLAYLIST_URL = "https://sm-live-tv-auto-update-playlist.pages.dev/Combined_Live_TV.m3u"
OUTPUT_FILE = "working_channels_accurate.m3u"

CONCURRENT_LIMIT = 10  # Reduced from 40 to 10 to protect your router
TIMEOUT_SECONDS = 10   # Increased from 5 to 10 seconds to catch slow streams

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
        url = channel["url"]
        timeout = aiohttp.ClientTimeout(total=TIMEOUT_SECONDS)
        try:
            # Standard browser User-Agent prevents basic anti-bot blocks
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            }
            async with session.get(url, timeout=timeout, headers=headers, ssl=False, allow_redirects=True) as response:
                # 2xx and 3xx status codes mean the server is up and responding
                if 200 <= response.status < 400:
                    return channel
        except Exception:
            pass
        return None

async def main():
    # Keep the connector pool aligned with our new lower limit
    connector = aiohttp.TCPConnector(limit=CONCURRENT_LIMIT, ttl_dns_cache=300)
    
    async with aiohttp.ClientSession(connector=connector) as session:
        print("📥 Fetching raw playlist...")
        try:
            async with session.get(PLAYLIST_URL) as response:
                response.raise_for_status()
                m3u_text = await response.text()
        except Exception as e:
            print(f"❌ Failed to download source playlist: {e}")
            return

        channels = parse_m3u(m3u_text)
        total_channels = len(channels)
        print(f"📋 Found {total_channels} channels. Starting high-accuracy scan...")

        # The semaphore restricts the event loop to exactly 10 open sockets at once
        semaphore = asyncio.Semaphore(CONCURRENT_LIMIT)
        tasks = [check_channel(session, semaphore, ch) for ch in channels]
        
        working_channels = []
        checked_count = 0

        for future in asyncio.as_completed(tasks):
            result = await future
            checked_count += 1
            if result:
                working_channels.append(result)
            
            # Print progress update every 5 channels checked
            if checked_count % 5 == 0 or checked_count == total_channels:
                print(f"⏳ Progress: {checked_count}/{total_channels} checked | Active: {len(working_channels)}", end="\r")

        print("\n\n💾 Saving accurate results locally...")
        try:
            with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
                f.write("#EXTM3U\n")
                for ch in working_channels:
                    f.write(f"{ch['extinf']}\n")
                    f.write(f"{ch['url']}\n")
            print(f"✨ Success! Saved {len(working_channels)} verified channels to '{OUTPUT_FILE}'.")
        except IOError as e:
            print(f"❌ Error writing file: {e}")

if __name__ == "__main__":
    asyncio.run(main())
