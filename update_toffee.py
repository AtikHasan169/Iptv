import os
import requests
import re

# Pull the golden token securely from GitHub Secrets
DEVICE_ACCESS_TOKEN = os.environ.get("DEVICE_TOKEN")

if not DEVICE_ACCESS_TOKEN:
    raise ValueError("DEVICE_TOKEN is missing. Ensure TOFFEE_DEVICE_TOKEN is set in GitHub Secrets.")

def get_fresh_cookie():
    """Trades the Golden Token for a fresh 3-day CDN cookie."""
    # Using Somoy TV's ID as the master key for the CDN
    url = "https://entitlement-prod.services.toffeelive.com/toffee/BD/DK/android-mobile/playback/Xi_Ga5oBNnOkwJLWkhKP"
    
    headers = {
        "Authorization": f"Bearer {DEVICE_ACCESS_TOKEN}",
        "Content-Type": "application/json; charset=utf-8",
        "Host": "entitlement-prod.services.toffeelive.com",
        "User-Agent": "okhttp/5.1.0"
    }
    
    res = requests.post(url, headers=headers, json={})
    
    # --- DEBUGGING: Print the API Response ---
    print("\n--- TOFFEE SERVER RESPONSE ---")
    print(f"Status Code: {res.status_code}")
    # Printing the first 500 characters so it doesn't flood your GitHub logs too badly
    print(f"JSON Body: {res.text[:500]}...\n") 
    
    if res.status_code == 200:
        cookie = res.cookies.get("Edge-Cache-Cookie")
        if cookie:
            # Print just the start of the cookie to verify it grabbed it
            print(f"[+] Successfully fetched fresh Edge-Cache-Cookie: {cookie[:30]}...")
            return cookie
        else:
            raise Exception("[-] API responded 200 OK, but no Edge-Cache-Cookie was found in headers.")
    else:
        raise Exception(f"[-] Failed to fetch cookie. HTTP {res.status_code}\n{res.text}")

def update_m3u_file(new_cookie):
    """Finds old cookies in tv.m3u and replaces them with the new one."""
    file_path = "tv.m3u"
    
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
    except FileNotFoundError:
        print("[-] ERROR: tv.m3u file not found in this directory!")
        return

    # Using re.subn allows us to count exactly how many replacements were made
    updated_content, count = re.subn(
        r'(cookies=Edge-Cache-Cookie=)[^&\s]+',
        f'\\g<1>{new_cookie}',
        content
    )

    with open(file_path, "w", encoding="utf-8") as f:
        f.write(updated_content)
        
    print(f"[+] Regex executed. Replaced {count} channel links in tv.m3u.")
    
    if count == 0:
        print("[-] WARNING: 0 replacements made. Check if 'cookies=Edge-Cache-Cookie=' actually exists in your tv.m3u file!")

if __name__ == "__main__":
    print("[*] Starting Toffee CDN Cookie Updater...")
    fresh_cookie = get_fresh_cookie()
    
    if fresh_cookie:
        update_m3u_file(fresh_cookie)
