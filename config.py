import os

class Config:
    # Telegram Bot Token (from BotFather)
    TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")

    # MongoDB Connection URI (from MongoDB Atlas)
    MONGO_URI = os.environ.get("MONGO_URI")
    MONGO_DB_NAME = os.environ.get("MONGO_DB_NAME", "download_bot_db") # Default DB name

    # Required Channel ID for mandatory join (e.g., -1001234567890)
    # Get this from @RawDataBot or similar after adding your bot as admin to the channel
    REQUIRED_CHANNEL_ID = os.environ.get("REQUIRED_CHANNEL_ID") # Optional, set to None if not needed

    # Admin Telegram User ID (your Telegram ID) for /add_premium command
    # Get your user ID from @userinfobot
    ADMIN_ID = os.environ.get("ADMIN_ID")

    # Admin Channel ID for UTR notifications (e.g., -1001234567890)
    # Get this from @RawDataBot after adding your bot as admin to the channel
    ADMIN_CHANNEL_ID = os.environ.get("ADMIN_CHANNEL_ID") # Optional, set to None if not needed

    # Free Download Limits per platform
    FREE_LIMITS = {
        "terabox": 5,
        "youtube": 10,
        "instagram": 20,
    }

    # Premium Prices (for display only)
    PREMIUM_PRICES = {
        "terabox": {"50": 100, "100": 200},
        "youtube": {"100": 20, "200": 40},
        "instagram": {"200": 20, "500": 50},
    }

    # QR Code Image URL for Premium Version (direct link to the image)
    QR_CODE_IMAGE_URL = os.environ.get("QR_CODE_IMAGE_URL")

    # Your UPI ID for payments
    UPI_ID = os.environ.get("UPI_ID")

    # File Deletion Delay (in minutes)
    FILE_DELETE_DELAY_MINUTES = int(os.environ.get("FILE_DELETE_DELAY_MINUTES", 3))

    # MongoDB TTL (Time To Live) for free users (in seconds)
    # Default: 18 days (18 * 24 * 60 * 60)
    FREE_USER_TTL_SECONDS = int(os.environ.get("FREE_USER_TTL_SECONDS", 18 * 24 * 60 * 60))

    # MongoDB TTL for premium users whose limits are exhausted (in seconds)
    # Default: 2 days (2 * 24 * 60 * 60)
    PREMIUM_EXHAUSTED_TTL_SECONDS = int(os.environ.get("PREMIUM_EXHAUSTED_TTL_SECONDS", 2 * 24 * 60 * 60))

