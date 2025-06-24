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
        raise ValueError("MONGO_URI is not set in Config. Please set it in Koyeb environment variables.")

    try:
        client = MongoClient(Config.MONGO_URI)
        db = client[Config.MONGO_DB_NAME]
        users_collection = db["users"]
        logger.info("Successfully connected to MongoDB.")

        # Create TTL indexes if they don't exist
        # For free users: delete if no activity for FREE_USER_TTL_SECONDS
        if "last_activity_ttl" not in users_collection.index_information():
            users_collection.create_index(
                "last_activity",
                expireAfterSeconds=Config.FREE_USER_TTL_SECONDS,
                name="last_activity_ttl"
            )
            logger.info("Created TTL index for last_activity.")

        # For premium users whose limits are exhausted: delete after PREMIUM_EXHAUSTED_TTL_SECONDS
        if "premium_limit_exhausted_ttl" not in users_collection.index_information():
            users_collection.create_index(
                "premium_limit_exhausted_at",
                expireAfterSeconds=Config.PREMIUM_EXHAUSTED_TTL_SECONDS,
                name="premium_limit_exhausted_ttl"
            )
            logger.info("Created TTL index for premium_limit_exhausted_at.")

    except ConnectionFailure as e:
        logger.critical(f"MongoDB Connection failed: {e}")
        raise
    except PyMongoError as e:
        logger.critical(f"MongoDB error during initialization: {e}")
        raise
    except Exception as e:
        logger.critical(f"Unexpected error during DB initialization: {e}")
        raise

async def get_user_data(user_id: int) -> dict:
    if users_collection is None:
        initialize_database() # Ensure DB is initialized
    
    user_data = users_collection.find_one({"_id": user_id})
    if not user_data:
        # Create a new user entry if not found
        default_user_data = {
            "_id": user_id,
            "last_activity": datetime.utcnow(),
            "terabox": {"free_count": 0, "premium_count": 0},
            "youtube": {"free_count": 0, "premium_count": 0},
            "instagram": {"free_count": 0, "premium_count": 0},
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
        upsert=True # Creates the document if it doesn't exist
    )

async def increment_user_downloads(user_id: int, platform: str):
    if users_collection is None:
        initialize_database()
    
    user_data = await get_user_data(user_id) # Get latest data
    
    # Check free limits first
    current_free_count = user_data.get(platform, {}).get("free_count", 0)
    current_premium_count = user_data.get(platform, {}).get("premium_count", 0)

    update_fields = {}

    if current_free_count < Config.FREE_LIMITS.get(platform, 0):
        # Use free download
        update_fields[f"{platform}.free_count"] = current_free_count + 1
        logger.info(f"User {user_id} used free {platform} download. New count: {current_free_count + 1}")
    elif current_premium_count > 0:
        # Use premium download
        update_fields[f"{platform}.premium_count"] = current_premium_count - 1
        logger.info(f"User {user_id} used premium {platform} download. Remaining: {current_premium_count - 1}")
    else:
        # Should not happen if limit check is done before calling this function
        logger.warning(f"Increment called for user {user_id} on platform {platform} but no limits left.")
        return # No change if no limits

    # Set/Reset premium_limit_exhausted_at if all limits are exhausted after this download
    # This logic assumes ALL premium limits across ALL platforms must be exhausted
    # for the user's data to be marked for deletion based on premium_limit_exhausted_at
    updated_user_data = users_collection.find_one_and_update(
        {"_id": user_id},
        {"$set": update_fields},
        return_document=True # Return the updated document
    )
    
    # Check if all free and all premium limits are exhausted for ALL platforms
    all_limits_exhausted = True
    for p in Config.FREE_LIMITS.keys():
        p_free_count = updated_user_data.get(p, {}).get("free_count", 0)
        p_premium_count = updated_user_data.get(p, {}).get("premium_count", 0)
        if p_free_count < Config.FREE_LIMITS.get(p, 0) or p_premium_count > 0:
            all_limits_exhausted = False
            break

    if all_limits_exhausted:
        users_collection.update_one(
            {"_id": user_id},
            {"$set": {"premium_limit_exhausted_at": datetime.utcnow()}}
        )
        logger.info(f"User {user_id} has exhausted all free and premium limits. Marked for deletion.")
    else:
        # If they still have premium, ensure exhausted_at is null
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
         "$set": {"premium_limit_exhausted_at": None}}, # Reset exhausted status
        upsert=True
    )
    logger.info(f"Added {count} premium downloads for user {user_id} on {platform}.")

async def get_platform_premium_limit(user_id: int, platform: str) -> int:
    if users_collection is None:
        initialize_database()
    
    user_data = await get_user_data(user_id)
    return user_data.get(platform, {}).get("premium_count", 0)

