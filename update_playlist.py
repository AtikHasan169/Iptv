import asyncio
import aiohttp
import os

PLAYLIST_URL = "https://sm-live-tv-auto-update-playlist.pages.dev/Combined_Live_TV.m3u"
OUTPUT_FILE = "working_channels.m3u"
CONCURRENT_LIMIT = 40  
TIMEOUT_SECONDS = 5    

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
            async with session.get(url, timeout=timeout, ssl=False, allow_redirects=True) as response:
                if 200 <= response.status < 400:
                    return channel
        except Exception:
            pass
        return None

async def main():
    connector = aiohttp.TCPConnector(limit=CONCURRENT_LIMIT, ttl_dns_cache=300)
    async with aiohttp.ClientSession(connector=connector) as session:
        print("📥 Fetching raw playlist...")
        async with session.get(PLAYLIST_URL) as response:
            response.raise_for_status()
            m3u_text = await response.text()

        channels = parse_m3u(m3u_text)
        print(f"📋 Found {len(channels)} channels. Checking streams...")

        semaphore = asyncio.Semaphore(CONCURRENT_LIMIT)
        tasks = [check_channel(session, semaphore, ch) for ch in channels]
        
        working_channels = []
        for future in asyncio.as_completed(tasks):
            result = await future
            if result:
                working_channels.append(result)

        print(f"💾 Verification complete. Saving {len(working_channels)} working channels...")
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            f.write("#EXTM3U\n")
            for ch in working_channels:
                f.write(f"{ch['extinf']}\n")
                f.write(f"{ch['url']}\n")
        print("✨ Local file generated successfully.")

if __name__ == "__main__":
    asyncio.run(main())
