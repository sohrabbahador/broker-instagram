"""کامنت‌ها و دایرکت: پاسخ خودکار، ثبت سرنخ و ارجاع به انسان."""
import asyncio, random, time
import config, content, ai, tokens
from db import db
from ig_client import IGClient, IGError
from notify import admin_alert

MAX_AUTO_REPLIES_PER_USER_PER_DAY = 6

def _client():
    acc = tokens.get_account()
    return (IGClient(acc[0], acc[1]), acc[0]) if acc else (None, None)

def _seen(kind, key) -> bool:
    try:
        db.ig_seen.insert_one({"_id": f"{kind}:{key}", "t": time.time()})
        return False
    except Exception:
        return True

def _quota_ok(user_id) -> bool:
    day = time.strftime("%Y%m%d")
    r = db.ig_replies.find_one_and_update({"_id": f"{user_id}:{day}"}, {"$inc": {"n": 1}}, upsert=True, return_document=True)
    return r["n"] <= MAX_AUTO_REPLIES_PER_USER_PER_DAY

WELCOME = ("سلام 👋 به پیج «بروکر املاک» خوش آمدید.\n"
           "برای راهنمایی دقیق‌تر بفرمایید دنبال «خرید» هستید یا «رهن و اجاره»؟ بودجه و محدوده‌ی مدنظرتان چیست؟\n"
           "فایل‌های کامل ما در بله:\nخرید و فروش: {sale}\nرهن و اجاره: {rent}")
HANDOFF = "ممنون 🙏 درخواست شما برای مشاور ثبت شد و در اولین فرصت (ساعات کاری) با شما هماهنگ می‌کنیم."

async def handle_comment(v: dict):
    cid, text = v.get("id"), v.get("text", "")
    frm = (v.get("from") or {})
    ig, my_id = _client()
    if not ig or not cid or frm.get("id") == my_id or _seen("c", cid):
        return
    intent = content.classify(text)
    try:
        if intent == "spam":
            await ig.hide_comment(cid, True)
            return
        await asyncio.sleep(random.uniform(20, 90))              # رفتار انسانی‌تر، کاهش ریسک اسپم‌شناسی
        if _quota_ok(frm.get("id", "x")):
            await ig.reply_comment(cid, "سپاس از توجه‌تان 🙏 جزئیات کامل را در دایرکت برایتان ارسال کردیم.")
            await ig.private_reply(cid, WELCOME.format(sale=config.CTA_URLS["فروش"], rent=config.CTA_URLS["رهن_اجاره"]))
        _lead(frm, text, intent, source="comment")
    except IGError as e:
        print("comment handling error:", e)

def _lead(frm, text, intent, source):
    uid = frm.get("id")
    if not uid:
        return None
    phone = content.extract_phone(text)
    upd = {"$set": {"username": frm.get("username"), "last_text": text[:300], "last_intent": intent, "updated": time.time()},
           "$setOnInsert": {"created": time.time(), "source": source}}
    if phone:
        upd["$set"]["phone"] = phone
    db.ig_leads.update_one({"_id": uid}, upd, upsert=True)
    return phone

async def handle_dm(ev: dict):
    sender = (ev.get("sender") or {}).get("id")
    msg = ev.get("message") or {}
    ig, my_id = _client()
    if not ig or not sender or sender == my_id or msg.get("is_echo") or _seen("m", msg.get("mid")):
        return
    text = msg.get("text") or ""
    if not text:
        return
    intent = content.classify(text)
    phone = _lead({"id": sender}, text, intent, source="dm")
    if intent == "spam" or not config.DM_AUTOREPLY or not _quota_ok(sender):
        return
    await asyncio.sleep(random.uniform(5, 25))
    if phone or content.needs_human(intent):
        reply = HANDOFF
        lead = db.ig_leads.find_one({"_id": sender}) or {}
        await admin_alert(f"🔔 سرنخ جدید اینستاگرام\nکاربر: @{lead.get('username') or sender}\nنیت: {intent}\n"
                          f"شماره: {phone or lead.get('phone') or '—'}\nپیام: {text[:300]}")
    elif db.ig_leads.find_one({"_id": sender, "welcomed": True}) is None and intent == "general":
        reply = WELCOME.format(sale=config.CTA_URLS["فروش"], rent=config.CTA_URLS["رهن_اجاره"])
        db.ig_leads.update_one({"_id": sender}, {"$set": {"welcomed": True}})
    else:
        reply = await ai.dm_answer(text) or HANDOFF
    try:
        await ig.send_dm(sender, reply)
    except IGError as e:
        print("dm error:", e)       # معمولاً: خارج از پنجره‌ی ۲۴ ساعته

async def dispatch(payload: dict):
    for entry in payload.get("entry", []):
        for ch in entry.get("changes", []):
            if ch.get("field") == "comments":
                await handle_comment(ch.get("value") or {})
        for ev in entry.get("messaging", []):
            await handle_dm(ev)
