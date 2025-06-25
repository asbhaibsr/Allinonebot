import logging
import os
import yt_dlp # youtube_dl को yt_dlp से बदला गया
from instaloader import Instaloader, Post
import requests
import re
import asyncio
import time # time मॉड्यूल इम्पोर्ट किया गया, जो आपके टेराबॉक्स डमी में उपयोग हो रहा था

logger = logging.getLogger(__name__)

# डाउनलोड की गई फ़ाइलों को अस्थायी रूप से सहेजने के लिए निर्देशिका
DOWNLOAD_DIR = "downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# --- Terabox Downloader ---
async def download_terabox(url: str) -> str | None:
    # Terabox डाउनलोडिंग अत्यधिक गतिशील और परिवर्तनों के अधीन है।
    # heroku-dl (या इसी तरह के) को कस्टम समायोजन की आवश्यकता हो सकती है या
    # यदि Terabox अपने आंतरिक API को बदलता है तो उसे बदला जा सकता है।
    # यह उदाहरण एक प्लेसहोल्डर का उपयोग करता है और बाहरी टूल या पुस्तकालयों पर निर्भर करता है
    # जिन्हें सबप्रोसेस के रूप में चलाया जा सकता है या उपलब्ध होने पर इम्पोर्ट किया जा सकता है।

    logger.info(f"Terabox डाउनलोड करने का प्रयास कर रहा है: {url}")
    try:
        # यहाँ असली Terabox डायरेक्ट लिंक एक्सट्रैक्शन लॉजिक की आवश्यकता है।
        # प्रदर्शन के लिए एक डमी फ़ाइल का उपयोग किया गया है। वास्तविक डाउनलोड लॉजिक से बदलें।
        # वास्तविक Terabox के लिए, एक विश्वसनीय API या मजबूत लाइब्रेरी का उपयोग करने पर विचार करें।
        file_name = f"terabox_video_{int(time.time())}.mp4"
        file_path = os.path.join(DOWNLOAD_DIR, file_name)
        
        # उदाहरण: डमी URL से डाउनलोड का अनुकरण (वास्तविक Terabox लॉजिक से बदलें)
        # response = requests.get(direct_link, stream=True)
        # if response.status_code == 200:
        #    with open(file_path, 'wb') as f:
        #        for chunk in response.iter_content(chunk_size=8192):
        #            f.write(chunk)
        #    logger.info(f"Terabox वीडियो {file_path} पर डाउनलोड किया गया")
        #    return file_path
        # else:
        #    logger.error(f"डायरेक्ट लिंक से Terabox वीडियो डाउनलोड करने में विफल रहा। स्थिति: {response.status_code}")
        #    return None
        
        # एक पूर्ण, चलाने योग्य कोड प्रदान करने के उद्देश्य से,
        # मैं एक डमी फ़ाइल निर्माण जोड़ूंगा। इसे वास्तविक TERABOX डाउनलोड से बदलें।
        with open(file_path, 'w') as f:
            f.write("यह एक डमी Terabox वीडियो फ़ाइल है।")
        logger.warning(f"डमी Terabox फ़ाइल बनाई गई: {file_path}. वास्तविक डाउनलोड लॉजिक से बदलें।")
        return file_path

    except Exception as e:
        logger.error(f"Terabox वीडियो {url} डाउनलोड करने में त्रुटि: {e}")
        return None

# --- YouTube Downloader ---
async def download_youtube(url: str) -> str | None:
    logger.info(f"YouTube डाउनलोड करने का प्रयास कर रहा है: {url}")
    ydl_opts = {
        'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best', # mp4 को प्राथमिकता दें
        'outtmpl': os.path.join(DOWNLOAD_DIR, '%(title)s.%(ext)s'),
        'noplaylist': True,
        'concurrent_fragments': 5, # तेजी से डाउनलोड के लिए
        'postprocessors': [{
            'key': 'FFmpegVideoRemuxer',
            'preferedformat': 'mp4',
        }, {
            'key': 'FFmpegExtractAudio', # केवल ऑडियो के लिए यदि फॉर्मेट केवल ऑडियो है
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }],
        'logger': logger,
        'progress_hooks': [lambda d: logger.info(f"YouTube प्रगति: {d['status']}. {d.get('filename', '')}")],
    }

    try:
        # जांचें कि URL वैध है या नहीं
        if not re.match(r"^(https?://)?(www\.)?(youtube\.com|youtu\.be)/.+$", url):
            logger.warning(f"अमान्य YouTube URL: {url}")
            return None

        # youtube_dl के बजाय yt_dlp का उपयोग करें
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info_dict = ydl.extract_info(url, download=False)
            if not info_dict:
                logger.error(f"YouTube URL: {url} के लिए जानकारी निकालने में विफल रहा।")
                return None

            # डाउनलोड करने के लिए अंतिम फ़ाइल नाम निर्धारित करें
            filepath = ydl.prepare_filename(info_dict)
            
            # सुनिश्चित करें कि निर्देशिका मौजूद है
            os.makedirs(os.path.dirname(filepath), exist_ok=True)

            # फ़ाइल डाउनलोड करें
            ydl.download([url])
            
            # जांचें कि डाउनलोड के बाद फ़ाइल मौजूद है या नहीं। ytdl कभी-कभी नाम बदल देता है।
            # एक सामान्य समस्या यह है कि एक्सटेंशन फॉर्मेट के आधार पर बदल सकता है।
            # हमें वास्तविक डाउनलोड की गई फ़ाइल ढूंढने की आवश्यकता है।
            if os.path.exists(filepath):
                logger.info(f"YouTube वीडियो {filepath} पर डाउनलोड किया गया")
                return filepath
            else:
                # फॉलबैक: यदि सीधा पथ मौजूद नहीं है तो शीर्षक से फ़ाइल ढूंढें
                # यह एक सरलीकरण है; एक अधिक मजबूत समाधान वास्तविक डाउनलोड की गई फ़ाइलों को ट्रैक करेगा
                potential_files = [f for f in os.listdir(DOWNLOAD_DIR) if info_dict['title'] in f]
                if potential_files:
                    actual_file_path = os.path.join(DOWNLOAD_DIR, potential_files[0])
                    logger.info(f"शीर्षक द्वारा YouTube फ़ाइल मिली: {actual_file_path}")
                    return actual_file_path
                logger.error(f"YouTube फ़ाइल {url} के लिए डाउनलोड के बाद नहीं मिली।")
                return None

    except Exception as e:
        logger.error(f"YouTube वीडियो {url} डाउनलोड करने में त्रुटि: {e}")
        return None

# --- Instagram Downloader ---
async def download_instagram(url: str) -> str | None:
    logger.info(f"Instagram डाउनलोड करने का प्रयास कर रहा है: {url}")
    L = Instaloader(
        dirname_pattern=DOWNLOAD_DIR,
        quiet=True,
        compress_json=False,
        post_metadata_txt_pattern="" # मेटाडेटा फ़ाइलें न बनाएं
    )

    # --- महत्वपूर्ण ---
    # इंस्टालोडर को अक्सर लॉगिन की आवश्यकता होती है। यदि आपको समस्याएँ आती हैं,
    # तो आपको L.load_session या L.interactive_login का उपयोग करके इंस्टालोडर लॉगिन क्रेडेंशियल सेट करने की आवश्यकता हो सकती है।
    # सुरक्षा कारणों से सार्वजनिक बॉट के लिए इसकी अत्यधिक अनुशंसा नहीं की जाती है।
    # एक मुफ़्त बॉट के लिए, यह सबसे चुनौतीपूर्ण हिस्सा है।
    # बॉट के लिए एक अस्थायी, समर्पित Instagram खाते का उपयोग करने पर विचार करें,
    # या यदि उपलब्ध हो और बजट के भीतर हो तो किसी तृतीय-पक्ष API पर निर्भर रहें।
    # उदाहरण: L.load_session(YOUR_INSTAGRAM_USERNAME, YOUR_SESSION_FILE_PATH)
    # L.login(YOUR_INSTAGRAM_USERNAME, YOUR_INSTAGRAM_PASSWORD) # हार्डकोड करने की अनुशंसा नहीं की जाती है

    try:
        # URL से शॉर्टकोड निकालें
        match = re.search(r'(?:/p/|/reel/|/tv/)([a-zA-Z0-9_-]+)', url)
        if not match:
            logger.error(f"अमान्य Instagram URL: {url}")
            return None
        
        shortcode = match.group(1)
        post = Post.from_shortcode(L.context, shortcode)

        # पोस्ट डाउनलोड करें
        L.download_post(post, "__dummy__") # अस्थायी उप-निर्देशिका के लिए __dummy__, साफ़ किया जाएगा
        
        # डाउनलोड की गई फ़ाइल ढूंढें
        # Instaloader उप-निर्देशिका जैसे `downloads/__dummy__/<username>/` में डाउनलोड करता है
        # हमें वास्तविक फ़ाइल (वीडियो, छवि) ढूंढने की आवश्यकता है
        downloaded_files = []
        for root, _, files in os.walk(os.path.join(DOWNLOAD_DIR, "__dummy__")):
            for file in files:
                if file.endswith(('.mp4', '.jpg', '.jpeg', '.png')): # प्रासंगिक मीडिया फ़ाइलों के लिए फ़िल्टर करें
                    downloaded_files.append(os.path.join(root, file))

        if downloaded_files:
            # हम पहली मिली मीडिया फ़ाइल लौटा रहे हैं।
            # मल्टी-मीडिया पोस्ट के लिए, आपको कई फ़ाइलों को हैंडल करने की आवश्यकता हो सकती है।
            file_path = downloaded_files[0]
            logger.info(f"Instagram मीडिया {file_path} पर डाउनलोड किया गया")
            
            # फ़ाइल को मुख्य DOWNLOAD_DIR में ले जाएं और अस्थायी निर्देशिका को साफ़ करें
            final_path = os.path.join(DOWNLOAD_DIR, os.path.basename(file_path))
            os.rename(file_path, final_path)
            
            # अस्थायी Instaloader निर्देशिका को साफ़ करें
            import shutil
            shutil.rmtree(os.path.join(DOWNLOAD_DIR, "__dummy__"))
            
            return final_path
        else:
            logger.error(f"Instagram पोस्ट {url} के लिए कोई मीडिया नहीं मिला")
            return None

    except Exception as e:
        logger.error(f"Instagram मीडिया {url} डाउनलोड करने में त्रुटि: {e}")
        return None
