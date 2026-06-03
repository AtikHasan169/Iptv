import os
import requests
import re
import json
import base64
import time

SAFE_BUFFER_DAYS = 2
SAFE_BUFFER_SECONDS = SAFE_BUFFER_DAYS * 86400

def get_jwt_exp(token):
    try:
        payload_b64 = token.split('.')[1]
        payload_b64 += '=' * (-len(payload_b64) % 4)
        payload_json = base64.urlsafe_b64decode(payload_b64).decode('utf-8')
        return json.loads(payload_json).get('exp', 0)
    except Exception:
        return 0

def refresh_api_tokens(current_refresh_token):
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
        if data.get("access_token") and data.get("refresh_token"):
            print("[+] Successfully generated a brand new token pair!")
            return data["access_token"], data["refresh_token"]
            
    raise Exception(f"[-] Token refresh failed. HTTP {res.status_code}\n{res.text}")

def get_fresh_cdn_cookie(access_token):
    print("[*] Requesting fresh CDN Edge-Cache-Cookie...")
    url = "https://entitlement-prod.services.toffeelive.com/toffee/BD/DK/android-mobile/playback/Xi_Ga5oBNnOkwJLWkhKP"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json; charset=utf-8",
        "Host": "entitlement-prod.services.toffeelive.com",
        "User-Agent": "okhttp/5.1.0"
    }
    
    res = requests.post(url, headers=headers, json={})
    if res.status_code == 200 and res.cookies.get("Edge-Cache-Cookie"):
        print("[+] Successfully fetched fresh Edge-Cache-Cookie!")
        return res.cookies.get("Edge-Cache-Cookie")
            
    raise Exception(f"[-] Failed to fetch CDN cookie. HTTP {res.status_code}\n{res.text}")

def update_m3u_file(new_cookie):
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
        print(f"[+] SUCCESS! Replaced {count} channel links.")
    except FileNotFoundError:
        print("[-] ERROR: tv.m3u file not found!")

if __name__ == "__main__":
    try:
        manual_refresh = os.environ.get("MANUAL_REFRESH")
        tokens_env = os.environ.get("TOFFEE_TOKENS")
        
        if manual_refresh:
            print("[*] Manual input detected! Bootstrapping initial setup...")
            access_token = ""
            refresh_token = manual_refresh
        elif tokens_env:
            tokens = json.loads(tokens_env)
            access_token = tokens.get("access_token", "")
            refresh_token = tokens.get("refresh_token", "")
        else:
            raise ValueError("[-] No tokens found in Secrets or manual input!")
        
        current_time = int(time.time())
        access_exp = get_jwt_exp(access_token)
        time_remaining = access_exp - current_time
        
        if not access_token or time_remaining < SAFE_BUFFER_SECONDS:
            print("[*] Token requires refreshing for safety...")
            access_token, refresh_token = refresh_api_tokens(refresh_token)
            
            new_vault_data = json.dumps({"access_token": access_token, "refresh_token": refresh_token})
            
            # --- THE FIX IS HERE ---
            # Using EOF markers forces GitHub Actions to keep the double quotes intact!
            with open(os.environ['GITHUB_ENV'], 'a') as f:
                f.write(f"NEW_VAULT_DATA<<EOF\n{new_vault_data}\nEOF\n")
        else:
            print(f"[*] Access token is safely valid for {time_remaining / 86400:.1f} days.")
            
        cdn_cookie = get_fresh_cdn_cookie(access_token)
        update_m3u_file(cdn_cookie)
        
    except Exception as e:
        print(f"[-] Workflow Failed: {e}")
