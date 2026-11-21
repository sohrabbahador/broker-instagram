import os

def _b(name, default=""):
    return os.getenv(name, default).strip()

IG_APP_ID = _b("IG_APP_ID")
IG_APP_SECRET = _b("IG_APP_SECRET")
IG_API_VERSION = _b("IG_API_VERSION", "v25.0")
IG_REDIRECT_URI = _b("IG_REDIRECT_URI")
IG_VERIFY_TOKEN = _b("IG_WEBHOOK_VERIFY_TOKEN")
PUBLIC_BASE_URL = _b("PUBLIC_BASE_URL").rstrip("/")
OAUTH_ADMIN_SECRET = _b("OAUTH_ADMIN_SECRET")
TOKEN_ENC_KEY = _b("TOKEN_ENC_KEY")
IG_SCOPES = ",".join([
    "instagram_business_basic",
    "instagram_business_content_publish",
    "instagram_business_manage_comments",
    "instagram_business_manage_messages",
])

MONGODB_URI = _b("MONGODB_URI") or _b("MONGO_URI")
BALE_TOKENS = {"sale_bale": _b("BALE_TOKEN_SALE"), "rent_bale": _b("BALE_TOKEN_RENT")}
ADMIN_ID = int(_b("ADMIN_ID", "0"))

GEMINI_API_KEY = _b("GEMINI_API_KEY")
GEMINI_MODEL = _b("GEMINI_MODEL", "gemini-2.5-flash-lite")

PUBLISH_MODE = _b("PUBLISH_MODE", "approval")          # approval | auto
POST_SLOTS = [s for s in _b("POST_SLOTS", "10:30,15:00,20:30").split(",") if s]
MAX_POSTS_PER_DAY = min(int(_b("MAX_POSTS_PER_DAY", "3")), 25)  # سقف رسمی متا ۵۰ است؛ عمداً محافظه‌کار
DM_AUTOREPLY = _b("DM_AUTOREPLY", "on") == "on"
CTA_URLS = {"فروش": _b("CTA_SALE_URL", "https://ble.ir/BROKER_amlak"),
            "رهن_اجاره": _b("CTA_RENT_URL", "https://ble.ir/BROKER_amlak2")}
BRAND_HANDLE = "@broker_amlak.ir"
TZ = "Asia/Tehran"
