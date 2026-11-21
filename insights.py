import time
import tokens
from db import db
from ig_client import IGClient, IGError
from notify import admin_alert

async def collect():
    acc = tokens.get_account()
    if not acc:
        return
    ig = IGClient(acc[0], acc[1])
    since = time.time() - 14 * 86400
    for it in db.ig_queue.find({"status": "published", "published_at": {"$gte": since}, "media_id": {"$exists": True}}):
        try:
            d = await ig.media_insights(it["media_id"])
            m = {x["name"]: (x.get("values") or [{}])[0].get("value", 0) for x in d.get("data", [])}
            db.ig_queue.update_one({"_id": it["_id"]}, {"$set": {"insights": m, "insights_at": time.time()}})
        except IGError as e:
            print("insights error", it["_id"], e)

async def weekly_report():
    since = time.time() - 7 * 86400
    posts = list(db.ig_queue.find({"status": "published", "published_at": {"$gte": since}}))
    leads = db.ig_leads.count_documents({"created": {"$gte": since}})
    phones = db.ig_leads.count_documents({"created": {"$gte": since}, "phone": {"$exists": True}})
    def score(p): i = p.get("insights", {}); return i.get("saved", 0) * 3 + i.get("shares", 0) * 3 + i.get("comments", 0) * 2 + i.get("likes", 0)
    by_kind = {}
    for p in posts:
        by_kind.setdefault(p["kind"], []).append(score(p))
    lines = [f"📊 گزارش هفتگی اینستاگرام", f"پست منتشرشده: {len(posts)}", f"سرنخ جدید: {leads} (با شماره: {phones})"]
    for k, v in by_kind.items():
        lines.append(f"میانگین امتیاز تعامل {k}: {sum(v)/len(v):.1f}")
    if posts:
        best = max(posts, key=score)
        lines.append(f"🏆 بهترین پست: #{best['_id']} (فایل {best['file_id']}) با امتیاز {score(best)}")
    await admin_alert("\n".join(lines))
