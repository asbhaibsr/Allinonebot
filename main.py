import logging
import os
import time
import asyncio
from datetime import datetime, timedelta

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    CallbackQueryHandler,
    ContextTypes,
)
from pymongo.errors import PyMongoError

from config import Config
from database import (
    initialize_database,
    get_user_data,
    update_user_activity,
    increment_user_downloads,
    add_premium_downloads,
    get_platform_premium_limit,
)
from downloaders import download_terabox, download_youtube, download_instagram
from keyboards import (
#    start_keyboard,
    main_menu_keyboard,
    premium_keyboard,
    channel_check_keyboard,
)

# Configure logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- Global state to track user's current action ---
# Helps to know if the bot is expecting a link for a specific platform
user_state = {} # Stores {'user_id': 'platform_key'} e.g., {123: 'terabox'}

# --- Helper function for file deletion ---
async def delete_file_after_delay(file_path, delay_minutes, context: ContextTypes.DEFAULT_TYPE, chat_id, message_id):
    await asyncio.sleep(delay_minutes * 60)
    try:
        os.remove(file_path)
        logger.info(f"Deleted file: {file_path}")
        await context.bot.send_message(chat_id=chat_id, text=f"⚠️ आपकी पिछली डाउनलोड की गई फ़ाइल (मैसेज ID: {message_id}) सर्वर से डिलीट कर दी गई है।")
    except OSError as e:
        logger.error(f"Error deleting file {file_path}: {e}")
        await context.bot.send_message(chat_id=chat_id, text=f"⚠️ फ़ाइल डिलीट करने में समस्या हुई: {e}")


# --- Command Handlers ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    user_name = update.effective_user.full_name
    logger.info(f"User {user_id} ({user_name}) started the bot.")

    await update_user_activity(user_id) # Update last_activity for TTL

    # Channel Join Check
    if Config.REQUIRED_CHANNEL_ID:
        try:
            member = await context.bot.get_chat_member(Config.REQUIRED_CHANNEL_ID, user_id)
            if member.status in ["member", "administrator", "creator"]:
                await show_main_menu(update, context)
            else:
                await update.message.reply_text(
                    "नमस्ते! इस बॉट का उपयोग करने के लिए, कृपया पहले हमारे चैनल को जॉइन करें और फिर 'मैंने जॉइन कर लिया है' पर क्लिक करें।",
                    reply_markup=channel_check_keyboard()
                )
        except Exception as e:
            logger.error(f"Error checking channel membership for user {user_id}: {e}")
            await update.message.reply_text(
                "चैनल सदस्यता की जाँच करने में त्रुटि हुई। कृपया थोड़ी देर बाद पुनः प्रयास करें।"
            )
            await show_main_menu(update, context) # Fallback to main menu if channel check fails
    else:
        await show_main_menu(update, context) # If no channel ID is set, directly show main menu

async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    user_data = await get_user_data(user_id)

    # Display initial message with free limits and temporary file warning
    message_text = (
        "नमस्ते! मैं आपका ऑल-इन-वन डाउनलोडर बॉट हूँ। आप यहाँ Terabox, YouTube "
        "(वीडियो/ऑडियो), और Instagram (रील्स/फोटो) से कंटेंट डाउनलोड कर सकते हैं।"
        "\n\n**महत्वपूर्ण:** मुफ़्त में, आप हर प्लेटफ़ॉर्म से सीमित संख्या में फाइलें डाउनलोड कर सकते हैं:"
        f"\n  📥 **Terabox:** {Config.FREE_LIMITS['terabox']} फाइलें (शेष: {Config.FREE_LIMITS['terabox'] - user_data.get('terabox', {}).get('free_count', 0)})"
        f"\n  🎧 **YouTube:** {Config.FREE_LIMITS['youtube']} फाइलें (शेष: {Config.FREE_LIMITS['youtube'] - user_data.get('youtube', {}).get('free_count', 0)})"
        f"\n  📸 **Instagram:** {Config.FREE_LIMITS['instagram']} फाइलें (शेष: {Config.FREE_LIMITS['instagram'] - user_data.get('instagram', {}).get('free_count', 0)})"
        "\n\nकॉपीराइट से बचने के लिए, डाउनलोड की गई फाइलें 3 मिनट में सर्वर से डिलीट हो जाएंगी। "
        "कृपया इन्हें तुरंत कहीं और फॉरवर्ड कर लें।"
        "\n\nआगे डाउनलोड करने के लिए, आपको हमारा **प्रीमियम वर्जन** लेना होगा।"
    )

    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(
            message_text,
            reply_markup=main_menu_keyboard(),
            parse_mode='Markdown'
        )
    else:
        await update.message.reply_text(
            message_text,
            reply_markup=main_menu_keyboard(),
            parse_mode='Markdown'
        )

async def handle_callback_query(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    data = query.data

    await update_user_activity(user_id) # Update last_activity for TTL

    if data == "check_channel":
        if Config.REQUIRED_CHANNEL_ID:
            try:
                member = await context.bot.get_chat_member(Config.REQUIRED_CHANNEL_ID, user_id)
                if member.status in ["member", "administrator", "creator"]:
                    await show_main_menu(update, context)
                else:
                    await query.edit_message_text(
                        "क्षमा करें, आपने अभी तक चैनल जॉइन नहीं किया है या सदस्यता की पुष्टि नहीं हो पाई है। "
                        "कृपया सुनिश्चित करें कि आप चैनल में शामिल हो गए हैं और फिर पुनः प्रयास करें।",
                        reply_markup=channel_check_keyboard()
                    )
            except Exception as e:
                logger.error(f"Error re-checking channel membership for user {user_id}: {e}")
                await query.edit_message_text(
                    "चैनल सदस्यता की जाँच करने में त्रुटि हुई। कृपया थोड़ी देर बाद पुनः प्रयास करें या बॉट को /start करें।"
                )
        else:
            await show_main_menu(update, context) # If no channel ID is set, proceed

    elif data == "help":
        help_text = (
            "❓ **बॉट का उपयोग कैसे करें:**\n"
            "1.  नीचे दिए गए बटनों में से अपनी पसंद का प्लेटफ़ॉर्म चुनें (Terabox, YouTube, Instagram)।\n"
            "2.  चुने हुए प्लेटफ़ॉर्म के लिए लिंक भेजें।\n"
            "3.  बॉट आपकी फाइल डाउनलोड करके भेज देगा।\n"
            "4.  याद रखें, मुफ़्त डाउनलोड की सीमा है और फाइलें अस्थायी होती हैं (3 मिनट में डिलीट)।\n"
            "5.  अधिक डाउनलोड के लिए 'Premium Version ✨' बटन पर क्लिक करें।"
            "\n\nकिसी भी समस्या के लिए, कृपया हमारे सपोर्ट चैनल पर संपर्क करें।" # Optionally add support link here
        )
        await query.edit_message_text(help_text, reply_markup=main_menu_keyboard(), parse_mode='Markdown')

    elif data == "terabox_download":
        user_state[user_id] = "terabox"
        await query.edit_message_text(
            "📥 **Terabox Video Download:**\nअब आप Terabox लिंक भेज सकते हैं।",
            reply_markup=main_menu_keyboard() # Keep main menu for easy navigation
        )
    elif data == "youtube_download":
        user_state[user_id] = "youtube"
        await query.edit_message_text(
            "🎧 **YouTube Video/Audio Download:**\nअब आप YouTube लिंक भेज सकते हैं।",
            reply_markup=main_menu_keyboard()
        )
    elif data == "instagram_download":
        user_state[user_id] = "instagram"
        await query.edit_message_text(
            "📸 **Instagram Reels/Photo Download:**\nअब आप Instagram लिंक भेज सकते हैं।",
            reply_markup=main_menu_keyboard()
        )
    elif data == "premium_version":
        premium_info = (
            "✨ **हमारे प्रीमियम वर्जन में अपग्रेड करें और असीमित डाउनलोड का आनंद लें!**\n\n"
            "**Terabox Premium:**\n"
            f"  • 50 डाउनलोड: ₹{Config.PREMIUM_PRICES['terabox']['50']}\n"
            f"  • 100 डाउनलोड: ₹{Config.PREMIUM_PRICES['terabox']['100']}\n\n"
            "**YouTube Premium:**\n"
            f"  • 100 डाउनलोड: ₹{Config.PREMIUM_PRICES['youtube']['100']}\n"
            f"  • 200 डाउनलोड: ₹{Config.PREMIUM_PRICES['youtube']['200']}\n\n"
            "**Instagram Premium:**\n"
            f"  • 200 डाउनलोड: ₹{Config.PREMIUM_PRICES['instagram']['200']}\n"
            f"  • 500 डाउनलोड: ₹{Config.PREMIUM_PRICES['instagram']['500']}\n\n"
            "**प्रीमियम कैसे लें:**\n"
            "नीचे दिए गए QR कोड को स्कैन करें या UPI ID पर भुगतान करें।"
            f"\n\n**UPI ID:** `{Config.UPI_ID}`\n"
            "भुगतान के बाद, 'मैंने भुगतान कर दिया है 💸' बटन पर क्लिक करें और अपना UTR नंबर सबमिट करें।"
            "\nहमारी टीम आपके भुगतान की पुष्टि करेगी और आपके प्रीमियम को तुरंत सक्रिय कर देगी।"
        )
        if Config.QR_CODE_IMAGE_URL:
            await context.bot.send_photo(
                chat_id=user_id,
                photo=Config.QR_CODE_IMAGE_URL,
                caption=premium_info,
                reply_markup=premium_keyboard(),
                parse_mode='Markdown'
            )
            await query.delete_message() # Delete the old message to avoid clutter
        else:
            await query.edit_message_text(
                premium_info,
                reply_markup=premium_keyboard(),
                parse_mode='Markdown'
            )

    elif data == "i_have_paid":
        user_state[user_id] = "awaiting_utr"
        await query.edit_message_text(
            "कृपया अपना UTR (Unique Transaction Reference) नंबर दर्ज करें। "
            "आपकी Telegram ID स्वतः प्राप्त कर ली जाएगी।",
            reply_markup=main_menu_keyboard() # Allow user to go back to main menu
        )
    elif data == "back_to_menu":
        user_state.pop(user_id, None) # Clear user state
        await show_main_menu(update, context)


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    message_text = update.message.text
    chat_id = update.effective_chat.id

    await update_user_activity(user_id) # Update last_activity for TTL

    if user_state.get(user_id) == "awaiting_utr":
        utr_number = message_text.strip()
        if not utr_number.isdigit() or len(utr_number) < 6: # Basic UTR validation
            await update.message.reply_text(
                "अमान्य UTR नंबर। कृपया सही UTR नंबर दर्ज करें।",
                reply_markup=main_menu_keyboard()
            )
            return

        # Send UTR to admin channel
        if Config.ADMIN_CHANNEL_ID:
            try:
                await context.bot.send_message(
                    chat_id=Config.ADMIN_CHANNEL_ID,
                    text=(
                        f"🚨 **नई प्रीमियम रिक्वेस्ट!** 🚨\n"
                        f"**यूज़र Telegram ID:** `{user_id}`\n"
                        f"**UTR नंबर:** `{utr_number}`\n"
                        f"**यूज़र लिंक:** tg://user?id={user_id}"
                    ),
                    parse_mode='Markdown'
                )
                logger.info(f"UTR {utr_number} from user {user_id} sent to admin channel.")
                await update.message.reply_text(
                    "आपका UTR नंबर प्राप्त हो गया है। हमारी टीम जल्द ही इसकी पुष्टि करेगी और आपका प्रीमियम सक्रिय कर देगी। धन्यवाद!",
                    reply_markup=main_menu_keyboard()
                )
            except Exception as e:
                logger.error(f"Error sending UTR to admin channel: {e}")
                await update.message.reply_text(
                    "UTR नंबर भेजने में त्रुटि हुई। कृपया थोड़ी देर बाद पुनः प्रयास करें या एडमिन से संपर्क करें।",
                    reply_markup=main_menu_keyboard()
                )
        else:
            await update.message.reply_text(
                "UTR नंबर प्राप्त हो गया है, लेकिन एडमिन चैनल कॉन्फ़िगर नहीं है। कृपया एडमिन से संपर्क करें।",
                reply_markup=main_menu_keyboard()
            )
        user_state.pop(user_id, None) # Clear state after UTR submission
        return

    # Handle download links based on user state
    platform = user_state.get(user_id)

    if not platform:
        await update.message.reply_text(
            "कृपया पहले नीचे दिए गए बटनों में से एक प्लेटफ़ॉर्म चुनें।",
            reply_markup=main_menu_keyboard()
        )
        return

    user_data = await get_user_data(user_id)
    free_count = user_data.get(platform, {}).get('free_count', 0)
    premium_count = user_data.get(platform, {}).get('premium_count', 0)

    # Check limits
    if free_count >= Config.FREE_LIMITS.get(platform, 0) and premium_count <= 0:
        await update.message.reply_text(
            f"**आपकी मुफ़्त डाउनलोड सीमा ({Config.FREE_LIMITS.get(platform, 0)} फाइलें) समाप्त हो गई है!** "
            "इस प्लेटफ़ॉर्म पर और फाइलें डाउनलोड करने के लिए, कृपया हमारा प्रीमियम वर्जन खरीदें। "
            "'Premium Version ✨' बटन पर क्लिक करें।",
            reply_markup=main_menu_keyboard(),
            parse_mode='Markdown'
        )
        return

    await update.message.reply_text(f"लिंक पहचान रहा हूँ और डाउनलोड शुरू कर रहा हूँ... कृपया प्रतीक्षा करें।")

    file_path = None
    try:
        if platform == "terabox":
            file_path = await download_terabox(message_text)
        elif platform == "youtube":
            file_path = await download_youtube(message_text)
        elif platform == "instagram":
            # Instagram download requires login, which is complex for free bots
            # Consider adding Instagram login details to Config for Instaloader
            # Or use a third-party API if Instaloader proves too difficult
            file_path = await download_instagram(message_text)
        else:
            await update.message.reply_text("अवैध प्लेटफ़ॉर्म चयन।")
            user_state.pop(user_id, None)
            return

        if file_path:
            caption = (
                f"📥 **डाउनलोड सफल!**\n"
                f"फ़ाइल: {os.path.basename(file_path)}\n\n"
                "⚠️ **महत्वपूर्ण:** यह फ़ाइल 3 मिनट में सर्वर से डिलीट हो जाएगी। "
                "कृपया इसे तुरंत कहीं और फॉरवर्ड कर लें!"
            )
            sent_message = None
            if os.path.getsize(file_path) > 50 * 1024 * 1024: # 50 MB limit for sending directly, for larger use document
                try:
                    sent_message = await update.message.reply_document(
                        document=open(file_path, 'rb'),
                        caption=caption,
                        parse_mode='Markdown'
                    )
                except Exception as e:
                    logger.warning(f"Failed to send as document, trying as video/photo: {e}")
                    if file_path.endswith(('.mp4', '.mov', '.avi', '.mkv')):
                        sent_message = await update.message.reply_video(
                            video=open(file_path, 'rb'),
                            caption=caption,
                            parse_mode='Markdown'
                        )
                    elif file_path.endswith(('.jpg', '.jpeg', '.png', '.gif')):
                        sent_message = await update.message.reply_photo(
                            photo=open(file_path, 'rb'),
                            caption=caption,
                            parse_mode='Markdown'
                        )
                    else:
                        raise e # If still fails, re-raise
            else: # For smaller files, try specific types first
                if file_path.endswith(('.mp4', '.mov', '.avi', '.mkv')):
                    sent_message = await update.message.reply_video(
                        video=open(file_path, 'rb'),
                        caption=caption,
                        parse_mode='Markdown'
                    )
                elif file_path.endswith(('.jpg', '.jpeg', '.png', '.gif')):
                    sent_message = await update.message.reply_photo(
                        photo=open(file_path, 'rb'),
                        caption=caption,
                        parse_mode='Markdown'
                    )
                elif file_path.endswith(('.mp3', '.wav', '.ogg')):
                    sent_message = await update.message.reply_audio(
                        audio=open(file_path, 'rb'),
                        caption=caption,
                        parse_mode='Markdown'
                    )
                else:
                    sent_message = await update.message.reply_document( # Default to document for others
                        document=open(file_path, 'rb'),
                        caption=caption,
                        parse_mode='Markdown'
                    )

            if sent_message:
                # Schedule file deletion
                context.job_queue.run_once(
                    lambda context: asyncio.create_task(
                        delete_file_after_delay(file_path, Config.FILE_DELETE_DELAY_MINUTES, context, chat_id, sent_message.message_id)
                    ),
                    Config.FILE_DELETE_DELAY_MINUTES * 60 # Convert minutes to seconds
                )
                await increment_user_downloads(user_id, platform)
                remaining_free = Config.FREE_LIMITS.get(platform, 0) - free_count - 1
                remaining_premium = premium_count - 1
                if remaining_free >= 0:
                    await update.message.reply_text(
                        f"इस प्लेटफ़ॉर्म पर आपके **{remaining_free}** मुफ़्त डाउनलोड शेष हैं।",
                        reply_markup=main_menu_keyboard(),
                        parse_mode='Markdown'
                    )
                elif remaining_premium > 0:
                    await update.message.reply_text(
                        f"इस प्लेटफ़ॉर्म पर आपके **{remaining_premium}** प्रीमियम डाउनलोड शेष हैं।",
                        reply_markup=main_menu_keyboard(),
                        parse_mode='Markdown'
                    )
                else:
                    await update.message.reply_text(
                        f"इस प्लेटफ़ॉर्म पर आपकी सभी प्रीमियम लिमिट्स भी समाप्त हो गई हैं। कृपया अधिक डाउनलोड के लिए फिर से प्रीमियम खरीदें।",
                        reply_markup=main_menu_keyboard(),
                        parse_mode='Markdown'
                    )

            else:
                raise Exception("Could not send file to Telegram.")

        else:
            await update.message.reply_text("डाउनलोड विफल रहा या लिंक से कोई फाइल नहीं मिली। कृपया एक वैध लिंक भेजें।")

    except Exception as e:
        logger.error(f"Error handling download for user {user_id}, platform {platform}: {e}")
        await update.message.reply_text(
            f"डाउनलोड करते समय एक त्रुटि हुई: {e}\n"
            "कृपया सुनिश्चित करें कि लिंक सही है या बाद में पुनः प्रयास करें।",
            reply_markup=main_menu_keyboard()
        )
    finally:
        # If file_path exists and was not successfully sent/deleted by schedule, try to clean up
        if file_path and os.path.exists(file_path) and 'sent_message' not in locals():
            try:
                os.remove(file_path)
                logger.info(f"Cleaned up unsent file: {file_path}")
            except OSError as e:
                logger.error(f"Error cleaning up unsent file {file_path}: {e}")
        user_state.pop(user_id, None) # Clear user state after attempting download


# --- Admin Command Handler ---
async def add_premium_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    admin_id = update.effective_user.id

    if str(admin_id) != Config.ADMIN_ID:
        await update.message.reply_text("आपको इस कमांड का उपयोग करने की अनुमति नहीं है।")
        logger.warning(f"Unauthorized attempt to use /add_premium by user {admin_id}")
        return

    args = context.args
    if len(args) != 3:
        await update.message.reply_text(
            "सही उपयोग: `/add_premium <user_telegram_id> <limit_type> <files_count>`\n"
            "उदाहरण: `/add_premium 123456789 terabox 50`",
            parse_mode='Markdown'
        )
        return

    try:
        user_id_to_add_premium = int(args[0])
        limit_type = args[1].lower() # terabox, youtube, instagram
        files_count = int(args[2])

        if limit_type not in Config.FREE_LIMITS: # Use FREE_LIMITS keys for valid types
            await update.message.reply_text("अमान्य 'limit_type'। मान्य प्रकार हैं: `terabox`, `youtube`, `instagram`।")
            return
        if files_count <= 0:
            await update.message.reply_text("फाइलों की संख्या धनात्मक होनी चाहिए।")
            return

        await add_premium_downloads(user_id_to_add_premium, limit_type, files_count)

        await update.message.reply_text(
            f"यूज़र `{user_id_to_add_premium}` को `{limit_type}` के लिए `{files_count}` प्रीमियम डाउनलोड सफलतापूर्वक जोड़े गए हैं।",
            parse_mode='Markdown'
        )
        logger.info(f"Admin {admin_id} added {files_count} premium {limit_type} downloads for user {user_id_to_add_premium}")

        # Send notification to the user
        try:
            total_premium_for_platform = await get_platform_premium_limit(user_id_to_add_premium, limit_type)
            await context.bot.send_message(
                chat_id=user_id_to_add_premium,
                text=(
                    f"🎉 **बधाई हो!** आपका प्रीमियम ({files_count} {limit_type} डाउनलोड) अब सक्रिय हो गया है।\n"
                    f"आपके पास अब कुल {total_premium_for_platform} {limit_type} प्रीमियम डाउनलोड शेष हैं। "
                    "आप अब और डाउनलोड का आनंद ले सकते हैं!"
                ),
                parse_mode='Markdown'
            )
        except Exception as e:
            logger.error(f"Could not send premium activation message to user {user_id_to_add_premium}: {e}")

    except ValueError:
        await update.message.reply_text("कृपया सही संख्यात्मक Telegram ID और फ़ाइलों की संख्या दर्ज करें।")
    except PyMongoError as e:
        logger.error(f"Database error in add_premium_command: {e}")
        await update.message.reply_text(f"डेटाबेस त्रुटि: {e}")
    except Exception as e:
        logger.error(f"Error in add_premium_command: {e}")
        await update.message.reply_text(f"कमांड निष्पादित करते समय एक अज्ञात त्रुटि हुई: {e}")


def main() -> None:
    # Get the Telegram Bot Token from Config
    token = Config.TELEGRAM_BOT_TOKEN
    if not token:
        logger.error("Telegram Bot Token is not set. Please set TELEGRAM_BOT_TOKEN in Koyeb environment variables.")
        exit(1)

    # Initialize MongoDB connection
    # The database initialization (including TTL indexes) will happen on first interaction
    try:
        initialize_database()
        logger.info("MongoDB database connection initialized.")
    except Exception as e:
        logger.critical(f"Failed to initialize MongoDB database: {e}")
        exit(1) # Exit if database connection fails

    application = Application.builder().token(token).build()

    # --- Handlers ---
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(handle_callback_query))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_handler(CommandHandler("add_premium", add_premium_command)) # Admin command

    # Run the bot
    logger.info("Bot started polling...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()

