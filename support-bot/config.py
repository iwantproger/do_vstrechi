import os

BOT_TOKEN = os.getenv("SUPPORT_BOT_TOKEN", "")
ADMIN_CHAT_ID = int(os.getenv("ADMIN_CHAT_ID", "0"))
ADMIN_IDS = [int(x.strip()) for x in os.getenv("ADMIN_IDS", str(ADMIN_CHAT_ID)).split(",") if x.strip()]
