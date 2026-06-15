from flask import Flask, request, Response
import subprocess
import requests

app = Flask(__name__)

@app.route('/stream')
def stream():
    target_url = request.args.get('url')
    key_value = request.args.get('key') 
    
    # Defaults to '0' (highest quality) if &quality= is omitted
    quality_index = request.args.get('quality', '0') 

    if not target_url or not key_value:
        return {"error": "Missing 'url' or 'key' parameter"}, 400

    # Quick pre-check to validate the stream is alive
    try:
        check = requests.get(target_url, headers={"User-Agent": "okhttp/4.11.0"}, timeout=5)
        if check.status_code != 200:
            return {"error": "Stream offline"}, check.status_code
    except:
        return {"error": "Connection failed"}, 502

    # FFmpeg command
    command = [
        'ffmpeg',
        '-hide_banner', 
        '-loglevel', 'error',
        '-cenc_decryption_key', key_value,
        '-i', target_url,
        '-map', f'0:v:{quality_index}',  # Video track selection
        '-map', '0:a:0',                 # Primary audio track
        '-c', 'copy',                    # Copy without re-encoding
        '-f', 'mpegts',                  # Output as MPEG-TS
        'pipe:1'
    ]

    def generate():
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            while True:
                data = process.stdout.read(8192)
                if not data:
                    break
                yield data
        finally:
            process.kill()

    return Response(generate(), mimetype='video/mp2t')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
