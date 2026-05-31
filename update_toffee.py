import os
import requests
import re

# Pulls your 6-month Refresh Token securely from GitHub Secrets
REFRESH_TOKEN = os.environ.get("DEVICE_TOKEN")

if not REFRESH_TOKEN:
    raise ValueError("DEVICE_TOKEN is missing. Ensure TOFFEE_DEVICE_TOKEN is set in GitHub Secrets.")

def get_access_token():
    """Step 1: Trades the 6-Month Refresh Token for a fresh 1-Month Access Token."""
    print("[*] Requesting fresh Access Token from Auth API...")
    url = "https://prod-services.toffeelive.com/auth/v1/token/refresh"
    
    headers = {
        "Authorization": f"Bearer {REFRESH_TOKEN}",
        "Content-Length": "0",
        "Host": "prod-services.toffeelive.com",
        "User-Agent": "okhttp/5.1.0"
    }
    
    res = requests.post(url, headers=headers)
    if res.status_code == 200:
        access_token = res.json().get("data", {}).get("access_token")
        if access_token:
            print("[+] Successfully generated fresh Access Token!")
            return access_token
    
    raise Exception(f"[-] Failed to refresh Access Token. HTTP {res.status_code}\n{res.text}")

def get_fresh_cookie(access_token):
    """Step 2: Trades the Access Token for a fresh 3-day CDN cookie."""
    print("[*] Requesting fresh CDN Edge-Cache-Cookie from Entitlement API...")
    url = "https://entitlement-prod.services.toffeelive.com/toffee/BD/DK/android-mobile/playback/Xi_Ga5oBNnOkwJLWkhKP"
    
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json; charset=utf-8",
        "Host": "entitlement-prod.services.toffeelive.com",
        "User-Agent": "okhttp/5.1.0"
    }
    
    res = requests.post(url, headers=headers, json={})
    
    if res.status_code == 200:
        cookie = res.cookies.get("Edge-Cache-Cookie")
        if cookie:
            print(f"[+] Successfully fetched fresh Edge-Cache-Cookie: {cookie[:30]}...")
            return cookie
    
    raise Exception(f"[-] Failed to fetch CDN cookie. HTTP {res.status_code}\n{res.text}")

def update_m3u_file(new_cookie):
    """Step 3: Injects the new cookie into the tv.m3u file."""
    file_path = "tv.m3u"
    print(f"[*] Updating M3U file: {file_path}")
    
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
    except FileNotFoundError:
        print("[-] ERROR: tv.m3u file not found in this directory!")
        return

    # Replaces all existing cookies in the file with the fresh one
    updated_content, count = re.subn(
        r'(cookies=Edge-Cache-Cookie=)[^&\s]+',
        f'\\g<1>{new_cookie}',
        content
    )

    with open(file_path, "w", encoding="utf-8") as f:
        f.write(updated_content)
        
    print(f"[+] SUCCESS! Replaced {count} channel links in tv.m3u.")

if __name__ == "__main__":
    try:
        # Execute the chain
        fresh_access_token = get_access_token()
        fresh_cdn_cookie = get_fresh_cookie(fresh_access_token)
        update_m3u_file(fresh_cdn_cookie)
    except Exception as e:
        print(f"[-] Workflow Failed: {e}")
