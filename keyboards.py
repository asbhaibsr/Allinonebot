from telegram import InlineKeyboardButton, InlineKeyboardMarkup

def channel_check_keyboard():
    keyboard = [
        [InlineKeyboardButton("✅ मैंने जॉइन कर लिया है", callback_data="check_channel")],
    ]
    return InlineKeyboardMarkup(keyboard)

def main_menu_keyboard():
    keyboard = [
        [InlineKeyboardButton("❓ Help", callback_data="help")],
        [InlineKeyboardButton("📥 Terabox Video Download", callback_data="terabox_download")],
        # YouTube और Instagram के बटन हटा दिए गए हैं
        # [InlineKeyboardButton("🎧 YouTube Video/Audio Download", callback_data="youtube_download")],
        # [InlineKeyboardButton("📸 Instagram Reels/Photo Download", callback_data="instagram_download")],
        [InlineKeyboardButton("✨ Premium Version", callback_data="premium_version")],
    ]
    return InlineKeyboardMarkup(keyboard)

def premium_keyboard():
    keyboard = [
        [InlineKeyboardButton("💸 मैंने भुगतान कर दिया है", callback_data="i_have_paid")],
        [InlineKeyboardButton("⬅️ मेनू पर वापस", callback_data="back_to_menu")],
    ]
    return InlineKeyboardMarkup(keyboard)

