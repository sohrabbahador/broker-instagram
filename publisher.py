"""صف انتشار: انتخاب فایل → کپشن → (تأیید مدیر) → زمان‌بندی → انتشار → گزارش."""
import hashlib, hmac, time, asyncio
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import config, content, ai, media, tokens
from db import db
from ig_client import IGClient, IGError
from notify import admin_alert

TZ = ZoneInfo(config.TZ)

def sign(item_id: int, action: str) -> str:
    return hmac.new(config.OAUTH_ADMIN_SECRET.encode(), f"{item_id}:{action}".encode(), hashlib.sha256).hexdigest()[:24]

def next_slot(after: datetime | None = None) -> float:
    """اولین اسلاتِ خالی در ۷ روز آینده (وقت تهران)، با رعایت MAX_POSTS_PER_DAY."""
    now = after or datetime.now(TZ)
    taken = [i["scheduled_at"] for i in db.ig_queue.find({"status": {"$in": ["scheduled", "published", "draft"]}},
                                                         {"scheduled_at": 1})]
    for d in range(0, 8):
        day = (now + timedelta(days=d)).date()
        used = sum(1 for t in taken if datetime.fromtimestamp(t, TZ).date() == day)
        if used >= config.MAX_POSTS_PER_DAY:
            continue
        for slot in config.POST_SLOTS:
            hh, mm = map(int, slot.split(":"))
            ts = datetime(day.year, day.month, day.day, hh, mm, tzinfo=TZ).timestamp()
            if ts > now.timestamp() and all(abs(ts - t) > 1800 for t in taken):
                return ts
    return (now + timedelta(days=1)).timestamp()

def _pick_next_file():
    """یک فروش، یک اجاره به‌صورت متناوب؛ فقط فایل‌های موجود و عکس‌دار که قبلاً در صف نیستند."""
    queued = {i["file_id"] for i in db.ig_queue.find({}, {"file_id": 1})}
    last = db.ig_queue.find_one(sort=[("created", -1)])
    prefer = "رهن_اجاره" if (last and last.get("kind") == "فروش") else "فروش"
    for kind in (prefer, "فروش" if prefer == "رهن_اجاره" else "رهن_اجاره"):
        for f in db.files.find({"kind": kind, "$or": [{"is_available": True}, {"is_available": {"$exists": False}}]}).sort("id", -1).limit(60):
            if f.get("id") in queued:
                continue
            if f.get("photos") and f["photos"] != "[]":
                return f
    return None

async def fill_queue(min_ahead=3):
    pending = db.ig_queue.count_documents({"status": {"$in": ["draft", "scheduled"]}})
    for _ in range(max(0, min_ahead - pending)):
        f = _pick_next_file()
        if not f:
            return
        cta = config.CTA_URLS.get(f.get("kind"), config.CTA_URLS["فروش"])
        hook = await ai.gemini(content.ai_hook_prompt(f), max_tokens=60, temperature=0.7)
        caption = content.build_caption(f, cta, ai_hook=hook)
        item_id = (db.ig_queue.find_one(sort=[("_id", -1)]) or {"_id": 0})["_id"] + 1
        status = "scheduled" if config.PUBLISH_MODE == "auto" else "draft"
        db.ig_queue.insert_one({"_id": item_id, "file_id": f["id"], "kind": f.get("kind"), "caption": caption,
                                "status": status, "scheduled_at": next_slot(), "created": time.time(), "attempts": 0})
        if status == "draft":
            base = f"{config.PUBLIC_BASE_URL}/admin/queue/{item_id}"
            await admin_alert(f"📝 پیش‌نویس اینستاگرام #{item_id}\n\n{caption}\n\n"
                              f"✅ تأیید: {base}/approve?k={sign(item_id,'approve')}\n"
                              f"❌ رد: {base}/reject?k={sign(item_id,'reject')}")

async def publish_item(item: dict):
    acc = tokens.get_account()
    if not acc:
        raise RuntimeError("حساب اینستاگرام متصل نیست")
    uid, tok, _ = acc
    ig = IGClient(uid, tok)
    f = db.files.find_one({"id": item["file_id"]})
    if not f or f.get("is_available") is False:
        db.ig_queue.update_one({"_id": item["_id"]}, {"$set": {"status": "skipped", "note": "فایل دیگر موجود نیست"}})
        return
    used, total = await ig.publishing_usage()
    if used >= min(total, 50) - 1:
        db.ig_queue.update_one({"_id": item["_id"]}, {"$set": {"scheduled_at": time.time() + 3600}})
        return
    urls = await media.host_photos(f)
    if not urls:
        raise RuntimeError("عکسی برای انتشار نیست")
    if len(urls) == 1:
        cid = await ig.create_image_container(urls[0], item["caption"])
    else:
        kids = [await ig.create_image_container(u, carousel_item=True) for u in urls]
        for k in kids:
            await ig.wait_ready(k)
        cid = await ig.create_carousel_container(kids, item["caption"])
    await ig.wait_ready(cid)
    media_id = await ig.publish(cid)
    db.ig_queue.update_one({"_id": item["_id"]}, {"$set": {"status": "published", "media_id": media_id, "published_at": time.time()}})
    await admin_alert(f"✅ پست #{item['_id']} منتشر شد (فایل {item['file_id']}).")

async def process_due():
    now = time.time()
    for item in db.ig_queue.find({"status": "scheduled", "scheduled_at": {"$lte": now}}).limit(2):
        try:
            await publish_item(item)
        except (IGError, Exception) as e:
            n = item.get("attempts", 0) + 1
            st = "failed" if n >= 3 else "scheduled"
            db.ig_queue.update_one({"_id": item["_id"]}, {"$set": {"attempts": n, "status": st, "error": str(e)[:300],
                                                                  "scheduled_at": now + 900 * n}})
            if st == "failed":
                await admin_alert(f"❌ انتشار #{item['_id']} پس از ۳ تلاش ناموفق: {str(e)[:200]}")
