"""ورود با Instagram Login، ذخیره‌ی رمزنگاری‌شده‌ی توکن و تمدید خودکار ۶۰ روزه."""
import time
import httpx
import config
from db import db

from cryptography.fernet import Fernet

# Fail closed: an invalid/missing key must never cause plaintext token storage.
_f = Fernet(config.TOKEN_ENC_KEY.encode()) if config.TOKEN_ENC_KEY else None

def _cipher():
    if _f is None:
        raise RuntimeError("TOKEN_ENC_KEY is required; refusing to store/read Instagram tokens")
    return _f

def _enc(s):
    return _cipher().encrypt(s.encode()).decode()

def _dec(s):
    return _cipher().decrypt(s.encode()).decode()

def login_url(state):
    from urllib.parse import urlencode
    q = urlencode({"client_id": config.IG_APP_ID, "redirect_uri": config.IG_REDIRECT_URI,
                   "response_type": "code", "scope": config.IG_SCOPES, "state": state})
    return f"https://www.instagram.com/oauth/authorize?{q}"

async def exchange_code(code):
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.post("https://api.instagram.com/oauth/access_token", data={
            "client_id": config.IG_APP_ID, "client_secret": config.IG_APP_SECRET,
            "grant_type": "authorization_code", "redirect_uri": config.IG_REDIRECT_URI,
            "code": code.split("#")[0]})
        r.raise_for_status()
        short = r.json()
        short = (short.get("data") or [short])[0]
        r2 = await c.get("https://graph.instagram.com/access_token", params={
            "grant_type": "ig_exchange_token", "client_secret": config.IG_APP_SECRET,
            "access_token": short["access_token"]})
        r2.raise_for_status()
        long_ = r2.json()
        me = await c.get(f"https://graph.instagram.com/{config.IG_API_VERSION}/me",
                         params={"fields": "user_id,username", "access_token": long_["access_token"]})
        me.raise_for_status()
        me = me.json()
    uid = str(me.get("user_id") or short.get("user_id"))
    db.ig_accounts.update_one({"_id": uid}, {"$set": {
        "username": me.get("username"), "access_token": _enc(long_["access_token"]),
        "expires_at": time.time() + long_.get("expires_in", 5184000), "refreshed_at": time.time()}}, upsert=True)
    return uid, me.get("username")

def get_account():
    """تک‌حساب: broker_amlak.ir"""
    doc = db.ig_accounts.find_one({})
    if not doc:
        return None
    return doc["_id"], _dec(doc["access_token"]), doc

async def refresh_if_needed(days_left=10):
    acc = get_account()
    if not acc:
        return
    uid, tok, doc = acc
    left = (doc["expires_at"] - time.time()) / 86400
    age_h = (time.time() - doc.get("refreshed_at", 0)) / 3600
    if left > days_left or age_h < 24:
        return
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.get("https://graph.instagram.com/refresh_access_token",
                        params={"grant_type": "ig_refresh_token", "access_token": tok})
    if r.status_code == 200:
        j = r.json()
        db.ig_accounts.update_one({"_id": uid}, {"$set": {
            "access_token": _enc(j["access_token"]),
            "expires_at": time.time() + j.get("expires_in", 5184000), "refreshed_at": time.time()}})
    else:
        from notify import admin_alert
        await admin_alert(f"⚠️ تمدید توکن اینستاگرام ناموفق بود ({r.status_code}). {left:.0f} روز تا انقضا مانده؛ دوباره /ig/login را بزنید.")
