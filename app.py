import os
import tempfile
import shutil
from flask import Flask, render_template, request, send_file, jsonify, after_this_request
import yt_dlp
import threading
import time

app = Flask(__name__)

# Configure upload folder for temporary files
TEMP_FOLDER = tempfile.mkdtemp()
app.config['TEMP_FOLDER'] = TEMP_FOLDER

def cleanup_file(filepath):
    """Delete file after a delay"""
    def delete_after_delay():
        time.sleep(30)  # Wait 30 seconds before cleanup
        try:
            if os.path.exists(filepath):
                os.remove(filepath)
        except:
            pass
    
    thread = threading.Thread(target=delete_after_delay)
    thread.daemon = True
    thread.start()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/convert', methods=['POST'])
def convert_video():
    try:
        data = request.get_json()
        youtube_url = data.get('url', '').strip()
        
        if not youtube_url:
            return jsonify({'error': 'Please provide a YouTube URL'}), 400
        
        # Validate YouTube URL
        if 'youtube.com' not in youtube_url and 'youtu.be' not in youtube_url:
            return jsonify({'error': 'Please provide a valid YouTube URL'}), 400
        
        # Create unique filename
        timestamp = str(int(time.time()))
        output_filename = f"audio_{timestamp}.%(ext)s"
        output_path = os.path.join(app.config['TEMP_FOLDER'], output_filename)
        
        # Configure yt-dlp options with enhanced bypass settings
        ydl_opts = {
            'format': 'bestaudio/best',
            'outtmpl': output_path,
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
            'quiet': True,
            'no_warnings': True,
            # Enhanced options to bypass YouTube restrictions
            'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'referer': 'https://www.youtube.com/',
            'extractor_retries': 3,
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'en-us,en;q=0.5',
                'Accept-Encoding': 'gzip, deflate',
                'DNT': '1',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1',
            },
            # Additional options to help with access
            'cookiefile': None,
            'nocheckcertificate': True,
            'ignoreerrors': False,
        }
        
        # Download and convert
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            # Get video info first
            info = ydl.extract_info(youtube_url, download=False)
            video_title = info.get('title', 'Unknown')
            
            # Download and convert
            ydl.download([youtube_url])
        
        # Find the actual output file (yt-dlp adds .mp3 extension)
        mp3_filename = f"audio_{timestamp}.mp3"
        mp3_path = os.path.join(app.config['TEMP_FOLDER'], mp3_filename)
        
        if not os.path.exists(mp3_path):
            return jsonify({'error': 'Conversion failed. The video might be unavailable, private, age-restricted, or temporarily blocked by YouTube.'}), 500
        
        # Schedule file cleanup
        cleanup_file(mp3_path)
        
        return jsonify({
            'success': True,
            'filename': mp3_filename,
            'title': video_title,
            'download_url': f'/download/{mp3_filename}'
        })
        
    except Exception as e:
        error_msg = str(e)
        if 'HTTP Error 403' in error_msg or 'Forbidden' in error_msg:
            return jsonify({'error': 'YouTube blocked the request. Try again in a few minutes or try a different video.'}), 500
        elif 'HTTP Error 429' in error_msg:
            return jsonify({'error': 'Too many requests. Please wait a few minutes before trying again.'}), 500
        elif 'Video unavailable' in error_msg or 'Private video' in error_msg:
            return jsonify({'error': 'This video is unavailable, private, or restricted.'}), 500
        else:
            return jsonify({'error': f'An error occurred: {error_msg}'}), 500

@app.route('/download/<filename>')
def download_file(filename):
    try:
        file_path = os.path.join(app.config['TEMP_FOLDER'], filename)
        
        if not os.path.exists(file_path):
            return jsonify({'error': 'File not found or has been cleaned up'}), 404
        
        # Get safe filename for download
        safe_filename = filename.replace('audio_', '').replace('.mp3', '') + '.mp3'
        
        return send_file(
            file_path,
            as_attachment=True,
            download_name=safe_filename,
            mimetype='audio/mpeg'
        )
        
    except Exception as e:
        return jsonify({'error': f'Download failed: {str(e)}'}), 500

if __name__ == '__main__':
    # Cleanup temp folder on startup
    if os.path.exists(TEMP_FOLDER):
        shutil.rmtree(TEMP_FOLDER)
    os.makedirs(TEMP_FOLDER, exist_ok=True)
    
    app.run(debug=True, host='0.0.0.0', port=5000) 