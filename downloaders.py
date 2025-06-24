import logging
import os
import youtube_dl
from instaloader import Instaloader, Post
import requests
import re
import asyncio

logger = logging.getLogger(__name__)

# Directory to save downloaded files temporarily
DOWNLOAD_DIR = "downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# --- Terabox Downloader ---
async def download_terabox(url: str) -> str | None:
    # Terabox downloading is highly dynamic and prone to changes.
    # heroku-dl (or similar) might require custom adjustments or be replaced
    # if Terabox changes its internal APIs.
    # This example uses a placeholder and relies on external tools or libraries
    # that might need to be run as subprocess or imported if available.

    logger.info(f"Attempting to download Terabox: {url}")
    try:
        # For heroku-dl, you'd typically run it as a script or import a function
        # This is a conceptual example. You might need to shell out or use a direct port.
        # Example using requests if a direct link can be extracted:
        # response = requests.get(f"https://some-terabox-api-proxy.com/get_link?url={url}")
        # data = response.json()
        # direct_link = data.get("direct_link")

        # As heroku-dl is a separate project, we can't directly import it here without
        # it being part of the same Python package structure.
        # For a simple, self-contained bot, you might need to find a way to extract
        # direct link or shell out to a pre-installed heroku-dl script.
        # Assuming for now, a conceptual direct link extraction.
        
        # A more robust solution might involve:
        # 1. Running 'python -m heroku_dl <url>' as a subprocess and parsing output.
        # 2. Finding a pure Python library that does it.
        # 3. Using a third-party API for Terabox downloads (might not be free).

        # Placeholder: This part requires the actual Terabox direct link extraction logic.
        # Example using a dummy file for demonstration. Replace with actual download logic.
        # For real Terabox, consider using a reliable API or robust library.
        file_name = f"terabox_video_{int(time.time())}.mp4"
        file_path = os.path.join(DOWNLOAD_DIR, file_name)
        
        # Example: Simulating a download from a dummy URL (replace with actual Terabox logic)
        # response = requests.get(direct_link, stream=True)
        # if response.status_code == 200:
        #     with open(file_path, 'wb') as f:
        #         for chunk in response.iter_content(chunk_size=8192):
        #             f.write(chunk)
        #     logger.info(f"Terabox video downloaded to {file_path}")
        #     return file_path
        # else:
        #     logger.error(f"Failed to download Terabox video from direct link. Status: {response.status_code}")
        #     return None
        
        # For the purpose of providing a complete, runnable code,
        # I'll add a dummy file creation. REPLACE THIS WITH REAL TERABOX DOWNLOAD.
        with open(file_path, 'w') as f:
            f.write("This is a dummy Terabox video file.")
        logger.warning(f"Dummy Terabox file created: {file_path}. Replace with actual download logic.")
        return file_path

    except Exception as e:
        logger.error(f"Error downloading Terabox video {url}: {e}")
        return None

# --- YouTube Downloader ---
async def download_youtube(url: str) -> str | None:
    logger.info(f"Attempting to download YouTube: {url}")
    ydl_opts = {
        'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best', # Prioritize mp4
        'outtmpl': os.path.join(DOWNLOAD_DIR, '%(title)s.%(ext)s'),
        'noplaylist': True,
        'concurrent_fragments': 5, # for faster downloads
        'postprocessors': [{
            'key': 'FFmpegVideoRemuxer',
            'preferedformat': 'mp4',
        }, {
            'key': 'FFmpegExtractAudio', # For audio only if format is audio only
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }],
        'logger': logger,
        'progress_hooks': [lambda d: logger.info(f"YouTube progress: {d['status']}. {d.get('filename', '')}")],
    }

    try:
        # Check if the URL is valid
        if not re.match(r"^(https?://)?(www\.)?(youtube\.com|youtu\.be)/.+$", url):
            logger.warning(f"Invalid YouTube URL: {url}")
            return None

        with youtube_dl.YoutubeDL(ydl_opts) as ydl:
            info_dict = ydl.extract_info(url, download=False)
            if not info_dict:
                logger.error(f"Could not extract info for YouTube URL: {url}")
                return None

            # Determine the final filename to download
            filepath = ydl.prepare_filename(info_dict)
            
            # Ensure the directory exists
            os.makedirs(os.path.dirname(filepath), exist_ok=True)

            # Download the file
            ydl.download([url])
            
            # Check if file exists after download. ytdl sometimes renames.
            # A common issue is the extension might change based on format.
            # We need to find the actual downloaded file.
            if os.path.exists(filepath):
                logger.info(f"YouTube video downloaded to {filepath}")
                return filepath
            else:
                # Fallback: Find file by title if direct path doesn't exist
                # This is a simplification; a more robust solution would track actual downloaded files
                potential_files = [f for f in os.listdir(DOWNLOAD_DIR) if info_dict['title'] in f]
                if potential_files:
                    actual_file_path = os.path.join(DOWNLOAD_DIR, potential_files[0])
                    logger.info(f"Found YouTube file by title: {actual_file_path}")
                    return actual_file_path
                logger.error(f"YouTube file not found after download for {url}.")
                return None

    except Exception as e:
        logger.error(f"Error downloading YouTube video {url}: {e}")
        return None

# --- Instagram Downloader ---
async def download_instagram(url: str) -> str | None:
    logger.info(f"Attempting to download Instagram: {url}")
    L = Instaloader(
        dirname_pattern=DOWNLOAD_DIR,
        quiet=True,
        compress_json=False,
        post_metadata_txt_pattern="" # Do not create metadata files
    )

    # --- IMPORTANT ---
    # Instaloader often requires login. If you face issues,
    # you might need to set up Instaloader login credentials
    # using L.load_session or L.interactive_login.
    # This is highly discouraged for public bots due to security.
    # For a free bot, this is the most challenging part.
    # Consider using a temporary, dedicated Instagram account for the bot,
    # or relying on a third-party API if available and within budget.
    # Example: L.load_session(YOUR_INSTAGRAM_USERNAME, YOUR_SESSION_FILE_PATH)
    # L.login(YOUR_INSTAGRAM_USERNAME, YOUR_INSTAGRAM_PASSWORD) # Not recommended to hardcode

    try:
        # Extract shortcode from URL
        match = re.search(r'(?:/p/|/reel/|/tv/)([a-zA-Z0-9_-]+)', url)
        if not match:
            logger.error(f"Invalid Instagram URL: {url}")
            return None
        
        shortcode = match.group(1)
        post = Post.from_shortcode(L.context, shortcode)

        # Download the post
        L.download_post(post, "__dummy__") # __dummy__ for temporary subdir, will be cleaned
        
        # Find the downloaded file
        # Instaloader downloads to a subdir like `downloads/__dummy__/<username>/`
        # We need to find the actual file (video, image)
        downloaded_files = []
        for root, _, files in os.walk(os.path.join(DOWNLOAD_DIR, "__dummy__")):
            for file in files:
                if file.endswith(('.mp4', '.jpg', '.jpeg', '.png')): # Filter for relevant media files
                    downloaded_files.append(os.path.join(root, file))

        if downloaded_files:
            # We are returning the first found media file.
            # For multi-media posts, you might need to handle multiple files.
            file_path = downloaded_files[0]
            logger.info(f"Instagram media downloaded to {file_path}")
            
            # Move the file to the main DOWNLOAD_DIR and clean up the temp directory
            final_path = os.path.join(DOWNLOAD_DIR, os.path.basename(file_path))
            os.rename(file_path, final_path)
            
            # Clean up the temporary Instaloader directory
            import shutil
            shutil.rmtree(os.path.join(DOWNLOAD_DIR, "__dummy__"))
            
            return final_path
        else:
            logger.error(f"No media found for Instagram post {url}")
            return None

    except Exception as e:
        logger.error(f"Error downloading Instagram media {url}: {e}")
        return None

