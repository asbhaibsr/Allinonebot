import logging
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure, PyMongoError
from datetime import datetime, timedelta
from config import Config

logger = logging.getLogger(__name__)

client = None
db = None
users_collection = None

def initialize_database():
    global client, db, users_collection
    if not Config.MONGO_URI:
        raise ValueError("MONGO_URI कॉन्फिग में सेट नहीं है। कृपया इसे Koyeb पर्यावरण चर में सेट करें।")

    try:
        client = MongoClient(Config.MONGO_URI)
        db = client[Config.MONGO_DB_NAME]
        users_collection = db["users"]
        logger.info("MongoDB से सफलतापूर्वक कनेक्ट किया गया।")

        # TTL इंडेक्स बनाएं यदि वे मौजूद नहीं हैं
        # मुफ़्त उपयोगकर्ताओं के लिए: यदि FREE_USER_TTL_SECONDS के लिए कोई गतिविधि नहीं है तो हटा दें
        if "last_activity_ttl" not in users_collection.index_information():
            users_collection.create_index(
                "last_activity",
                expireAfterSeconds=Config.FREE_USER_TTL_SECONDS,
                name="last_activity_ttl"
            )
            logger.info("last_activity के लिए TTL इंडेक्स बनाया गया।")

        # प्रीमियम उपयोगकर्ताओं के लिए जिनकी सीमा समाप्त हो गई है: PREMIUM_EXHAUSTED_TTL_SECONDS के बाद हटा दें
        if "premium_limit_exhausted_ttl" not in users_collection.index_information():
            users_collection.create_index(
                "premium_limit_exhausted_at",
                expireAfterSeconds=Config.PREMIUM_EXHAUSTED_TTL_SECONDS,
                name="premium_limit_exhausted_ttl"
            )
            logger.info("premium_limit_exhausted_at के लिए TTL इंडेक्स बनाया गया।")

    except ConnectionFailure as e:
        logger.critical(f"MongoDB कनेक्शन विफल रहा: {e}")
        raise
    except PyMongoError as e:
        logger.critical(f"आरंभिकरण के दौरान MongoDB त्रुटि: {e}")
        raise
    except Exception as e:
        logger.critical(f"DB आरंभिकरण के दौरान अप्रत्याशित त्रुटि: {e}")
        raise

async def get_user_data(user_id: int) -> dict:
    if users_collection is None:
        initialize_database() # सुनिश्चित करें कि DB आरंभ हो चुका है
    
    user_data = users_collection.find_one({"_id": user_id})
    if not user_data:
        # यदि नहीं मिलता है तो एक नई उपयोगकर्ता प्रविष्टि बनाएं
        default_user_data = {
            "_id": user_id,
            "last_activity": datetime.utcnow(),
            "terabox": {"free_count": 0, "premium_count": 0}, # केवल Terabox रखें
            # "youtube": {"free_count": 0, "premium_count": 0}, # हटा दिया गया
            # "instagram": {"free_count": 0, "premium_count": 0}, # हटा दिया गया
            "premium_limit_exhausted_at": None,
        }
        users_collection.insert_one(default_user_data)
        return default_user_data
    return user_data

async def update_user_activity(user_id: int):
    if users_collection is None:
        initialize_database()
    
    users_collection.update_one(
        {"_id": user_id},
        {"$set": {"last_activity": datetime.utcnow()}},
        upsert=True # यदि दस्तावेज़ मौजूद नहीं है तो उसे बनाता है
    )

async def increment_user_downloads(user_id: int, platform: str):
    if users_collection is None:
        initialize_database()
    
    user_data = await get_user_data(user_id) # नवीनतम डेटा प्राप्त करें
    
    # पहले मुफ़्त सीमाएँ जांचें
    current_free_count = user_data.get(platform, {}).get("free_count", 0)
    current_premium_count = user_data.get(platform, {}).get("premium_count", 0)

    update_fields = {}

    if current_free_count < Config.FREE_LIMITS.get(platform, 0):
        # मुफ़्त डाउनलोड का उपयोग करें
        update_fields[f"{platform}.free_count"] = current_free_count + 1
        logger.info(f"उपयोगकर्ता {user_id} ने {platform} मुफ़्त डाउनलोड का उपयोग किया। नई गणना: {current_free_count + 1}")
    elif current_premium_count > 0:
        # प्रीमियम डाउनलोड का उपयोग करें
        update_fields[f"{platform}.premium_count"] = current_premium_count - 1
        logger.info(f"उपयोगकर्ता {user_id} ने {platform} प्रीमियम डाउनलोड का उपयोग किया। शेष: {current_premium_count - 1}")
    else:
        # यह तब नहीं होना चाहिए जब इस फ़ंक्शन को कॉल करने से पहले सीमा जांच की जाती है
        logger.warning(f"उपयोगकर्ता {user_id} के लिए प्लेटफ़ॉर्म {platform} पर इंक्रीमेंट को कॉल किया गया लेकिन कोई सीमा नहीं बची।")
        return # यदि कोई सीमा नहीं है तो कोई बदलाव नहीं

    # यदि इस डाउनलोड के बाद सभी सीमाएं समाप्त हो गई हैं तो premium_limit_exhausted_at सेट/रीसेट करें
    # यह लॉजिक मानता है कि उपयोगकर्ता के डेटा को premium_limit_exhausted_at के आधार पर हटाने के लिए
    # सभी प्लेटफ़ॉर्मों पर सभी प्रीमियम सीमाएँ समाप्त होनी चाहिए
    updated_user_data = users_collection.find_one_and_update(
        {"_id": user_id},
        {"$set": update_fields},
        return_document=True # अपडेटेड दस्तावेज़ लौटाएं
    )
    
    # जांचें कि क्या सभी मुफ़्त और सभी प्रीमियम सीमाएँ सभी प्लेटफ़ॉर्मों के लिए समाप्त हो गई हैं
    all_limits_exhausted = True
    # अब केवल 'terabox' को लूप में शामिल करें
    if (updated_user_data.get("terabox", {}).get("free_count", 0) >= Config.FREE_LIMITS.get("terabox", 0) and
        updated_user_data.get("terabox", {}).get("premium_count", 0) <= 0):
        pass # Terabox सीमा समाप्त
    else:
        all_limits_exhausted = False # Terabox सीमा समाप्त नहीं हुई
    
    # पुराने लूप को हटा दिया गया था:
    # for p in Config.FREE_LIMITS.keys():
    #     p_free_count = updated_user_data.get(p, {}).get("free_count", 0)
    #     p_premium_count = updated_user_data.get(p, {}).get("premium_count", 0)
    #     if p_free_count < Config.FREE_LIMITS.get(p, 0) or p_premium_count > 0:
    #         all_limits_exhausted = False
    #         break

    if all_limits_exhausted:
        users_collection.update_one(
            {"_id": user_id},
            {"$set": {"premium_limit_exhausted_at": datetime.utcnow()}}
        )
        logger.info(f"उपयोगकर्ता {user_id} ने सभी मुफ़्त और प्रीमियम सीमाएँ समाप्त कर दी हैं। हटाने के लिए चिह्नित किया गया।")
    else:
        # यदि उनके पास अभी भी प्रीमियम है, तो सुनिश्चित करें कि exhausted_at शून्य है
        users_collection.update_one(
            {"_id": user_id},
            {"$set": {"premium_limit_exhausted_at": None}}
        )


async def add_premium_downloads(user_id: int, platform: str, count: int):
    if users_collection is None:
        initialize_database()
    
    users_collection.update_one(
        {"_id": user_id},
        {"$inc": {f"{platform}.premium_count": count},
         "$set": {"premium_limit_exhausted_at": None}}, # समाप्त स्थिति रीसेट करें
        upsert=True
    )
    logger.info(f"उपयोगकर्ता {user_id} के लिए {platform} पर {count} प्रीमियम डाउनलोड जोड़े गए।")

async def get_platform_premium_limit(user_id: int, platform: str) -> int:
    if users_collection is None:
        initialize_database()
    
    user_data = await get_user_data(user_id)
    return user_data.get(platform, {}).get("premium_count", 0)

