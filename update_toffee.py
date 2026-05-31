import os
import requests
import re
import json
import base64
import time

TOKEN_FILE = "tokens.json"

# --- SAFETY SETTING ---
# The script will force a refresh this many days before the token actually expires.
SAFE_BUFFER_DAYS = 2
SAFE_BUFFER_SECONDS = SAFE_BUFFER_DAYS * 86400

def get_jwt_exp(token):
    """Decodes a JWT string to find its exact expiration timestamp."""
    try:
        # JWTs are split into Header.Payload.Signature
        payload_b64 = token.split('.')[1]
        # Add necessary Base64 padding
        payload_b64 += '=' * (-len(payload_b64) % 4)
        payload_json = base64.urlsafe_b64decode(payload_b64).decode('utf-8')
        payload = json.loads(payload_json)
        return payload.get('exp', 0)
    except Exception:
        return 0

def load_or_seed_tokens():
    """Loads tokens from the file, or uses the GitHub secret if it's the very first run."""
    if os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE, "r") as f:
            return json.load(f)
    
    print("[*] No tokens.json found. Seeding from GitHub Secret...")
    initial_refresh = os.environ.get("DEVICE_TOKEN")
    if not initial_refresh:
        raise ValueError("[-] DEVICE_TOKEN secret is missing and tokens.json does not exist!")
    
    return {"access_token": "", "refresh_token": initial_refresh}

def save_tokens(access_token, refresh_token):
    """Saves the tokens to a file so the GitHub Action can commit them for the next run."""
    with open(TOKEN_FILE, "w") as f:
        json.dump({
            "access_token": access_token, 
            "refresh_token": refresh_token
        }, f, indent=4)
    print(f"[+] Saved updated tokens to {TOKEN_FILE}")

def refresh_api_tokens(current_refresh_token):
    """Hits the Auth API to generate a new Access/Refresh token pair."""
    print("[*] Hitting Auth API for a fresh token pair...")
    url = "https://prod-services.toffeelive.com/auth/v1/token/refresh"
    
    headers = {
        "Authorization": f"Bearer {current_refresh_token}",
        "Content-Length": "0",
        "Host": "prod-services.toffeelive.com",
        "User-Agent": "okhttp/5.1.0"
    }
    
    res = requests.post(url, headers=headers)
    if res.status_code == 200:
        data = res.json().get("data", {})
        new_access = data.get("access_token")
        new_refresh = data.get("refresh_token")
        
        if new_access and new_refresh:
            print("[+] Successfully generated a brand new token pair!")
            return new_access, new_refresh
            
    raise Exception(f"[-] Token refresh failed. HTTP {res.status_code}\n{res.text}")

def get_fresh_cdn_cookie(access_token):
    """Trades the Access Token for a fresh 3-day CDN cookie."""
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
    """Injects the new cookie into the tv.m3u file."""
    file_path = "tv.m3u"
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
            
        updated_content, count = re.subn(
            r'(cookies=Edge-Cache-Cookie=)[^&\s]+',
            f'\\g<1>{new_cookie}',
            content
        )

        with open(file_path, "w", encoding="utf-8") as f:
            f.write(updated_content)
        print(f"[+] SUCCESS! Replaced {count} channel links in {file_path}.")
    except FileNotFoundError:
        print(f"[-] ERROR: {file_path} file not found!")

if __name__ == "__main__":
    try:
        # 1. Load our tokens
        tokens = load_or_seed_tokens()
        access_token = tokens.get("access_token", "")
        refresh_token = tokens.get("refresh_token", "")
        
        # 2. Check the expiration math with our safety buffer
        current_time = int(time.time())
        access_exp = get_jwt_exp(access_token)
        time_remaining = access_exp - current_time
        
        if not access_token or time_remaining < SAFE_BUFFER_SECONDS:
            if access_token:
                print(f"[*] Access token expires in less than {SAFE_BUFFER_DAYS} days. Refreshing now for safety...")
            else:
                print("[*] No access token found. Fetching initial tokens...")
                
            access_token, refresh_token = refresh_api_tokens(refresh_token)
            # Save the new pair so Git commits them
            save_tokens(access_token, refresh_token)
        else:
            days_left = time_remaining / 86400
            print(f"[*] Access token is safely valid for another {days_left:.1f} days. Skipping Auth API.")
            
        # 3. Fetch the CDN cookie and inject it
        cdn_cookie = get_fresh_cdn_cookie(access_token)
        update_m3u_file(cdn_cookie)
        
    except Exception as e:
        print(f"[-] Workflow Failed: {e}")
