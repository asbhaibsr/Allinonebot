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
#    start_keyboard, # यह पंक्ति टिप्पणी की गई थी, इसे ऐसे ही रहने दें
    main_menu_keyboard,
    premium_keyboard,
    channel_check_keyboard,
)

# लॉगिंग कॉन्फ़िगर करें
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- उपयोगकर्ता की वर्तमान कार्रवाई को ट्रैक करने के लिए वैश्विक स्थिति ---
# यह जानने में मदद करता है कि बॉट किसी विशिष्ट प्लेटफ़ॉर्म के लिए लिंक की उम्मीद कर रहा है या नहीं
user_state = {} # {'user_id': 'platform_key'} जैसे: {123: 'terabox'}

# --- फ़ाइल हटाने के लिए सहायक फ़ंक्शन ---
async def delete_file_after_delay(file_path, delay_minutes, context: ContextTypes.DEFAULT_TYPE, chat_id, message_id):
    await asyncio.sleep(delay_minutes * 60)
    try:
        os.remove(file_path)
        logger.info(f"फ़ाइल हटाई गई: {file_path}")
        await context.bot.send_message(chat_id=chat_id, text=f"⚠️ आपकी पिछली डाउनलोड की गई फ़ाइल (मैसेज ID: {message_id}) सर्वर से डिलीट कर दी गई है।")
    except OSError as e:
        logger.error(f"फ़ाइल {file_path} हटाने में त्रुटि: {e}")
        await context.bot.send_message(chat_id=chat_id, text=f"⚠️ फ़ाइल डिलीट करने में समस्या हुई: {e}")


# --- कमांड हैंडलर्स ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    user_name = update.effective_user.full_name
    logger.info(f"उपयोगकर्ता {user_id} ({user_name}) ने बॉट शुरू किया।")

    await update_user_activity(user_id) # TTL के लिए अंतिम गतिविधि अपडेट करें

    # चैनल जॉइन चेक
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
            logger.error(f"उपयोगकर्ता {user_id} के लिए चैनल सदस्यता की जाँच में त्रुटि: {e}")
            await update.message.reply_text(
                "चैनल सदस्यता की जाँच करने में त्रुटि हुई। कृपया थोड़ी देर बाद पुनः प्रयास करें।"
            )
            await show_main_menu(update, context) # यदि चैनल चेक विफल हो जाता है तो मुख्य मेनू पर वापस जाएँ
    else:
        await show_main_menu(update, context) # यदि कोई चैनल ID सेट नहीं है, तो सीधे मुख्य मेनू दिखाएं

async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    user_data = await get_user_data(user_id)

    # मुफ़्त सीमा और अस्थायी फ़ाइल चेतावनी के साथ प्रारंभिक संदेश प्रदर्शित करें
    message_text = (
        "नमस्ते! मैं आपका ऑल-इन-वन डाउनलोडर बॉट हूँ। आप यहाँ Terabox, YouTube "
        "(वीडियो/ऑडियो), और Instagram (रील्स/फोटो) से कंटेंट डाउनलोड कर सकते हैं।"
        "\n\n**महत्वपूर्ण:** मुफ़्त में, आप हर प्लेटफ़ॉर्म से सीमित संख्या में फाइलें डाउनलोड कर सकते हैं:"
        f"\n  📥 **Terabox:** {Config.FREE_LIMITS['terabox']} फाइलें (शेष: {Config.FREE_LIMITS['terabox'] - user_data.get('terabox', {}).get('free_count', 0)})"
        f"\n  🎧 **YouTube:** {Config.FREE_LIMITS['youtube']} फाइलें (शेष: {Config.FREE_LIMITS['youtube'] - user_data.get('youtube', {}).get('free_count', 0)})"
        f"\n  📸 **Instagram:** {Config.FREE_LIMITS['instagram']} फाइलें ( शेष: {Config.FREE_LIMITS['instagram'] - user_data.get('instagram', {}).get('free_count', 0)})"
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

    await update_user_activity(user_id) # TTL के लिए अंतिम गतिविधि अपडेट करें

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
                logger.error(f"उपयोगकर्ता {user_id} के लिए चैनल सदस्यता की पुनः जाँच में त्रुटि: {e}")
                await query.edit_message_text(
                    "चैनल सदस्यता की जाँच करने में त्रुटि हुई। कृपया थोड़ी देर बाद पुनः प्रयास करें या बॉट को /start करें।"
                )
        else:
            await show_main_menu(update, context) # यदि कोई चैनल ID सेट नहीं है, तो आगे बढ़ें

    elif data == "help":
        help_text = (
            "❓ **बॉट का उपयोग कैसे करें:**\n"
            "1.  नीचे दिए गए बटनों में से अपनी पसंद का प्लेटफ़ॉर्म चुनें (Terabox, YouTube, Instagram)।\n"
            "2.  चुने हुए प्लेटफ़ॉर्म के लिए लिंक भेजें।\n"
            "3.  बॉट आपकी फाइल डाउनलोड करके भेज देगा।\n"
            "4.  याद रखें, मुफ़्त डाउनलोड की सीमा है और फाइलें अस्थायी होती हैं (3 मिनट में डिलीट)।\n"
            "5.  अधिक डाउनलोड के लिए 'Premium Version ✨' बटन पर क्लिक करें।"
            "\n\nकिसी भी समस्या के लिए, कृपया हमारे सपोर्ट चैनल पर संपर्क करें।" # यहाँ वैकल्पिक रूप से सपोर्ट लिंक जोड़ें
        )
        await query.edit_message_text(help_text, reply_markup=main_menu_keyboard(), parse_mode='Markdown')

    elif data == "terabox_download":
        user_state[user_id] = "terabox"
        await query.edit_message_text(
            "📥 **Terabox Video Download:**\nअब आप Terabox लिंक भेज सकते हैं।",
            reply_markup=main_menu_keyboard() # आसान नेविगेशन के लिए मुख्य मेनू रखें
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
            await query.delete_message() # अव्यवस्था से बचने के लिए पुराने संदेश को हटा दें
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
            reply_markup=main_menu_keyboard() # उपयोगकर्ता को मुख्य मेनू पर वापस जाने की अनुमति दें
        )
    elif data == "back_to_menu":
        user_state.pop(user_id, None) # उपयोगकर्ता की स्थिति साफ़ करें
        await show_main_menu(update, context)


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    message_text = update.message.text
    chat_id = update.effective_chat.id

    await update_user_activity(user_id) # TTL के लिए अंतिम गतिविधि अपडेट करें

    if user_state.get(user_id) == "awaiting_utr":
        utr_number = message_text.strip()
        if not utr_number.isdigit() or len(utr_number) < 6: # मूल UTR सत्यापन
            await update.message.reply_text(
                "अमान्य UTR नंबर। कृपया सही UTR नंबर दर्ज करें।",
                reply_markup=main_menu_keyboard()
            )
            return

        # UTR को एडमिन चैनल पर भेजें
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
                logger.info(f"उपयोगकर्ता {user_id} से UTR {utr_number} एडमिन चैनल पर भेजा गया।")
                await update.message.reply_text(
                    "आपका UTR नंबर प्राप्त हो गया है। हमारी टीम जल्द ही इसकी पुष्टि करेगी और आपका प्रीमियम सक्रिय कर देगी। धन्यवाद!",
                    reply_markup=main_menu_keyboard()
                )
            except Exception as e:
                logger.error(f"UTR को एडमिन चैनल पर भेजने में त्रुटि: {e}")
                await update.message.reply_text(
                    "UTR नंबर भेजने में त्रुटि हुई। कृपया थोड़ी देर बाद पुनः प्रयास करें या एडमिन से संपर्क करें।",
                    reply_markup=main_menu_keyboard()
                )
        else:
            await update.message.reply_text(
                "UTR नंबर प्राप्त हो गया है, लेकिन एडमिन चैनल कॉन्फ़िगर नहीं है। कृपया एडमिन से संपर्क करें।",
                reply_markup=main_menu_keyboard()
            )
        user_state.pop(user_id, None) # UTR सबमिशन के बाद स्थिति साफ़ करें
        return

    # उपयोगकर्ता की स्थिति के आधार पर डाउनलोड लिंक को हैंडल करें
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

    # सीमाएँ जांचें
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
            # Instagram डाउनलोड के लिए लॉगिन की आवश्यकता होती है, जो मुफ़्त बॉट के लिए जटिल है
            # इंस्टालोडर के लिए कॉन्फ़िग में इंस्टाग्राम लॉगिन विवरण जोड़ने पर विचार करें
            # या यदि इंस्टालोडर बहुत मुश्किल साबित होता है तो किसी तृतीय-पक्ष API का उपयोग करें
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
            if os.path.getsize(file_path) > 50 * 1024 * 1024: # सीधे भेजने के लिए 50 MB सीमा, बड़े के लिए दस्तावेज़ का उपयोग करें
                try:
                    sent_message = await update.message.reply_document(
                        document=open(file_path, 'rb'),
                        caption=caption,
                        parse_mode='Markdown'
                    )
                except Exception as e:
                    logger.warning(f"दस्तावेज़ के रूप में भेजने में विफल रहा, वीडियो/फोटो के रूप में प्रयास कर रहा है: {e}")
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
                        raise e # अगर फिर भी विफल रहता है, तो पुनः उत्पन्न करें
            else: # छोटी फ़ाइलों के लिए, पहले विशिष्ट प्रकारों का प्रयास करें
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
                    sent_message = await update.message.reply_document( # दूसरों के लिए दस्तावेज़ को डिफ़ॉल्ट करें
                        document=open(file_path, 'rb'),
                        caption=caption,
                        parse_mode='Markdown'
                    )

            if sent_message:
                # फ़ाइल हटाने का शेड्यूल करें
                context.job_queue.run_once(
                    lambda context: asyncio.create_task(
                        delete_file_after_delay(file_path, Config.FILE_DELETE_DELAY_MINUTES, context, chat_id, sent_message.message_id)
                    ),
                    Config.FILE_DELETE_DELAY_MINUTES * 60 # मिनट को सेकंड में बदलें
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
                raise Exception("टेलीग्राम को फ़ाइल नहीं भेज सका।")

        else:
            await update.message.reply_text("डाउनलोड विफल रहा या लिंक से कोई फाइल नहीं मिली। कृपया एक वैध लिंक भेजें।")

    except Exception as e:
        logger.error(f"उपयोगकर्ता {user_id}, प्लेटफ़ॉर्म {platform} के लिए डाउनलोड हैंडल करते समय त्रुटि: {e}")
        await update.message.reply_text(
            f"डाउनलोड करते समय एक त्रुटि हुई: {e}\n"
            "कृपया सुनिश्चित करें कि लिंक सही है या बाद में पुनः प्रयास करें।",
            reply_markup=main_menu_keyboard()
        )
    finally:
        # यदि file_path मौजूद है और शेड्यूल द्वारा सफलतापूर्वक भेजा/हटाया नहीं गया था, तो साफ़ करने का प्रयास करें
        if file_path and os.path.exists(file_path) and 'sent_message' not in locals():
            try:
                os.remove(file_path)
                logger.info(f"बिना भेजी गई फ़ाइल साफ़ की गई: {file_path}")
            except OSError as e:
                logger.error(f"बिना भेजी गई फ़ाइल {file_path} साफ़ करने में त्रुटि: {e}")
        user_state.pop(user_id, None) # डाउनलोड का प्रयास करने के बाद उपयोगकर्ता की स्थिति साफ़ करें


# --- एडमिन कमांड हैंडलर ---
async def add_premium_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    admin_id = update.effective_user.id

    if str(admin_id) != Config.ADMIN_ID:
        await update.message.reply_text("आपको इस कमांड का उपयोग करने की अनुमति नहीं है।")
        logger.warning(f"उपयोगकर्ता {admin_id} द्वारा /add_premium का उपयोग करने का अनाधिकृत प्रयास")
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

        if limit_type not in Config.FREE_LIMITS: # वैध प्रकारों के लिए FREE_LIMITS कुंजी का उपयोग करें
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
        logger.info(f"एडमिन {admin_id} ने उपयोगकर्ता {user_id_to_add_premium} के लिए {files_count} प्रीमियम {limit_type} डाउनलोड जोड़े")

        # उपयोगकर्ता को अधिसूचना भेजें
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
            logger.error(f"उपयोगकर्ता {user_id_to_add_premium} को प्रीमियम सक्रियण संदेश नहीं भेज सका: {e}")

    except ValueError:
        await update.message.reply_text("कृपया सही संख्यात्मक Telegram ID और फ़ाइलों की संख्या दर्ज करें।")
    except PyMongoError as e:
        logger.error(f"add_premium_command में डेटाबेस त्रुटि: {e}")
        await update.message.reply_text(f"डेटाबेस त्रुटि: {e}")
    except Exception as e:
        logger.error(f"add_premium_command में त्रुटि: {e}")
        await update.message.reply_text(f"कमांड निष्पादित करते समय एक अज्ञात त्रुटि हुई: {e}")


def main() -> None:
    # कॉन्फ़िग से टेलीग्राम बॉट टोकन प्राप्त करें
    token = Config.TELEGRAM_BOT_TOKEN
    if not token:
        logger.error("टेलीग्राम बॉट टोकन सेट नहीं है। कृपया Koyeb पर्यावरण चर में TELEGRAM_BOT_TOKEN सेट करें।")
        exit(1)

    # MongoDB कनेक्शन प्रारंभ करें
    # डेटाबेस इनिशियलाइज़ेशन (TTL इंडेक्स सहित) पहली बातचीत पर होगा
    try:
        initialize_database()
        logger.info("MongoDB डेटाबेस कनेक्शन सफलतापूर्वक प्रारंभ किया गया।")
    except Exception as e:
        logger.critical(f"MongoDB डेटाबेस प्रारंभ करने में विफल रहा: {e}")
        exit(1) # यदि डेटाबेस कनेक्शन विफल रहता है तो बाहर निकलें

    # 'Updater' को हटाकर 'Application' सीधे बिल्ड करें
    # त्रुटि संदेश को देखते हुए, यह सुनिश्चित करना महत्वपूर्ण है कि `Updater` का उपयोग यहाँ न हो।
    application = Application.builder().token(token).build()

    # --- हैंडलर्स ---
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(handle_callback_query))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_handler(CommandHandler("add_premium", add_premium_command)) # एडमिन कमांड

    # बॉट चलाएं
    logger.info("बॉट पोलिंग शुरू हो गया है...")
    # सुनिश्चित करें कि `Updater` का कोई जिक्र नहीं है, केवल `application` पर सीधे `run_polling` कॉल करें।
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()

