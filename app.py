import os
import time
import json
import base64
import requests
import threading
from datetime import datetime
import pytz
from flask import Flask, Response
from pymongo import MongoClient
import dns.resolver

# --- TERMUX / ANDROID DNS FIX ---
dns.resolver.default_resolver = dns.resolver.Resolver(configure=False)
dns.resolver.default_resolver.nameservers = ['8.8.8.8', '1.1.1.1']

app = Flask(__name__)

# --- DATABASE SETUP ---
MONGO_URI = os.environ.get("MONGO_URI", "mongodb+srv://siamkushtia33_db_user:Abdullah%262580@cluster0.kv6h60z.mongodb.net/?appName=Cluster0")
client = MongoClient(MONGO_URI)
db = client['binge_database']
tokens_collection = db['binge_tokens']
playlist_collection = db['binge_playlists']

# --- NextStreamer API Configuration ---
BASE_URL = "https://nextstreamer-api.rockstreamer.com/ca"
AUTH_BASE_URL = "https://nextstreamer-api.rockstreamer.com"

COMMON_HEADERS = {
    "Accept": "application/json",
    "User-Agent": "okhttp/5.0.0-alpha.14",
    "Connection": "Keep-Alive"
}

TARGET_CATEGORIES = {
    "live-channels": "Live TV",
    "live-sports": "Live Sports"
}

# --- GLOBAL MEMORY CACHE ---
CACHED_M3U = "#EXTM3U\n# 🕒 Playlist is initializing, please refresh in a moment...\n"
LAST_UPDATED = 0
IS_UPDATING = False
CACHE_TIMEOUT = 600  # Update the playlist in the background every 10 minutes

# --- INITIALIZE CACHE FROM MONGODB ON STARTUP ---
print("📦 Loading latest playlist cache from MongoDB...")
saved_playlist = playlist_collection.find_one({"_id": "latest_m3u"})
if saved_playlist:
    CACHED_M3U = saved_playlist.get("content", CACHED_M3U)
    LAST_UPDATED = saved_playlist.get("updated_at", 0)
    print("✅ Cache loaded successfully. Ready for instant delivery!")
else:
    print("⚠️ No remote cache found. The first request will trigger a generation loop.")

# --- AUTOMATED JWT LOGIC ---
def get_token_expiration(token):
    if not token or len(token.split('.')) != 3:
        return 0
    try:
        payload_b64 = token.split('.')[1]
        payload_b64 += "=" * ((4 - len(payload_b64) % 4) % 4)
        payload_json = base64.urlsafe_b64decode(payload_b64).decode('utf-8')
        return json.loads(payload_json).get('exp', 0)
    except:
        return 0

def is_token_valid(token, buffer_seconds=300):
    exp_time = get_token_expiration(token)
    return exp_time > (time.time() + buffer_seconds)

def save_tokens_to_db(access_token, refresh_token):
    tokens_collection.update_one(
        {"_id": "binge_token"},
        {"$set": {"access_token": access_token, "refresh_token": refresh_token}},
        upsert=True
    )

def execute_full_login():
    print("⚠️ Token missing or expired. Executing full account login...")
    login_url = f"{AUTH_BASE_URL}/auth/token"
    headers = {**COMMON_HEADERS, "Content-Type": "application/json"}
    payload = {
        "name": "+8801747365714",
        "id": "32L6avi5kmrsQR19GkpNpJ",
        "site": "phone",
        "avater": " https://i.imgur.com/SFuwc2c.jpg",
        "email": "+8801747365714",
        "country_code": "+880",
        "msisdn": "+8801747365714",
        "mobile_number": "+8801747365714",
        "platform": "bingeplus"
    }
    try:
        response = requests.post(login_url, headers=headers, json=payload, timeout=15)
        response.raise_for_status()
        data = response.json()
        save_tokens_to_db(data.get("token"), data.get("refreshToken"))
        return data.get("token")
    except Exception as e:
        print(f"❌ Full login endpoint failed: {e}")
        return None

def execute_token_refresh(current_refresh_token):
    print("🔄 Access token expiring soon. Triggering API token refresh...")
    refresh_url = f"{AUTH_BASE_URL}/auth/token/refresh"
    headers = {**COMMON_HEADERS, "Content-Type": "application/x-www-form-urlencoded"}
    payload = {"token": current_refresh_token}
    try:
        response = requests.post(refresh_url, headers=headers, data=payload, timeout=15)
        response.raise_for_status()
        data = response.json()
        save_tokens_to_db(data.get("token"), data.get("refreshToken"))
        return data.get("token")
    except Exception as e:
        print(f"⚠️ Refresh rejected ({e}). Attempting fallback full login...")
        return execute_full_login()

def get_valid_access_token():
    token_data = tokens_collection.find_one({"_id": "binge_token"}) or {}
    acc_token = token_data.get("access_token", "")
    ref_token = token_data.get("refresh_token", "")

    if is_token_valid(acc_token):
        return acc_token
    if is_token_valid(ref_token):
        return execute_token_refresh(ref_token)
    return execute_full_login()

# --- STABLE SEQUENTIAL SCRAPER PIPELINE ---
def fetch_category_contents(category_slug, headers):
    url = f"{BASE_URL}/category/contents/{category_slug}?page=1&limit=50"
    try:
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        return response.json().get("data", [])
    except Exception as e:
        print(f"❌ Failed to fetch category {category_slug}: {e}")
        return []

def fetch_video_stream(video_slug, headers):
    url = f"{BASE_URL}/content/video/{video_slug}"
    try:
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        return response.json().get("data", {}).get("path")
    except Exception as e:
        print(f"❌ Failed to fetch stream for {video_slug}: {e}")
        return None

# --- BACKGROUND SCRAPER THREAD WORKER ---
def background_scraper_job(access_token):
    global CACHED_M3U, LAST_UPDATED, IS_UPDATING
    print("🔄 [Background Thread] Starting sequential refresh loop...")
    
    try:
        dynamic_headers = {**COMMON_HEADERS, "Authorization": f"Bearer {access_token}"}
        tz = pytz.timezone('Asia/Dhaka')
        timestamp = datetime.now(tz).strftime('%Y-%m-%d %I:%M:%S %p')
        
        m3u_content = f"#EXTM3U\n# 🕒 Binge+ Auto-Updated: {timestamp}\n\n"
        channel_count = 0

        referer = "https://iscreen.com.bd/"
        origin = "https://iscreen.com.bd"
        user_agent = "Dalvik/2.1.0 (Linux; U; Android 16; ELI-NX9 Build/HONORELI-N39)"

        for cat_slug, cat_name in TARGET_CATEGORIES.items():
            contents = fetch_category_contents(cat_slug, dynamic_headers)
            for item in contents:
                title = item.get("title", "Unknown Title")
                video_slug = item.get("slug")
                if not video_slug:
                    continue
                
                stream_url = fetch_video_stream(video_slug, dynamic_headers)
                if stream_url:
                    logo = ""
                    if item.get("horizontalThumbnails"):
                        logo = item["horizontalThumbnails"][0].get("fullPath", "")
                    elif item.get("verticalThumbnails"):
                        logo = item["verticalThumbnails"][0].get("fullPath", "")
                        
                    piped_url = f"{stream_url}|Referer={referer}&Origin={origin}&User-Agent={user_agent}"
                    
                    m3u_content += f'#EXTINF:-1 tvg-id="{title}" tvg-logo="{logo}" group-title="{cat_name}", {title}\n'
                    m3u_content += f'#EXTVLCOPT:http-referrer={referer}\n'
                    m3u_content += f'#EXTVLCOPT:http-origin={origin}\n'
                    m3u_content += f'#EXTVLCOPT:http-user-agent={user_agent}\n'
                    m3u_content += f'{piped_url}\n'
                    channel_count += 1

        # Save to runtime memory cache
        CACHED_M3U = m3u_content
        LAST_UPDATED = time.time()
        
        # Persistent backup to MongoDB
        playlist_collection.update_one(
            {"_id": "latest_m3u"},
            {"$set": {"content": m3u_content, "updated_at": LAST_UPDATED}},
            upsert=True
        )
        print(f"✅ [Background Thread] Scraper complete! {channel_count} channels cached securely.")
        
    except Exception as worker_error:
        print(f"❌ [Background Thread] Encountered fatal process error: {worker_error}")
    finally:
        IS_UPDATING = False

# --- FLASK ENDPOINTS ---

@app.route('/', methods=['GET'])
@app.route('/health', methods=['GET'])
def health_check():
    """Status check for Render/Uptime services."""
    return "✅ Binge+ API Server is awake and fully operational!", 200

@app.route('/playlist.m3u', methods=['GET'])
def serve_playlist():
    global IS_UPDATING
    current_time = time.time()
    
    # Check if cache has expired and no thread is currently processing an update
    if (current_time - LAST_UPDATED > CACHE_TIMEOUT) and not IS_UPDATING:
        access_token = get_valid_access_token()
        if access_token:
            IS_UPDATING = True
            print("\n⏰ Cache expired or empty! Launching isolated background updater thread...")
            threading.Thread(target=background_scraper_job, args=(access_token,), daemon=True).start()
        else:
            print("❌ Background updater skipped: Could not retrieve a valid access token.")

    print("🚀 Delivering playlist immediately from cache (0.0s latency)...")
    return Response(CACHED_M3U, mimetype='application/x-mpegURL')

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5000)
