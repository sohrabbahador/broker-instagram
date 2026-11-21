import asyncio, hashlib, hmac, secrets, time
from datetime import datetime
from fastapi import FastAPI, Request, BackgroundTasks, HTTPException, Response
from fastapi.responses import RedirectResponse, PlainTextResponse
import config, tokens, publisher, inbox, insights, media
from db import db

app = FastAPI(title="Broker Instagram Service")

@app.get("/")
def home():
    acc = tokens.get_account()
    return {"status": "running", "instagram_connected": bool(acc), "mode": config.PUBLISH_MODE}

# ---------- اتصال رسمی (Business Login for Instagram؛ بدون Facebook) ----------
@app.get("/ig/login")
def ig_login(secret: str = ""):
    if not hmac.compare_digest(secret, config.OAUTH_ADMIN_SECRET):
        raise HTTPException(403)
    state = secrets.token_urlsafe(16)
    db.ig_state.insert_one({"_id": state, "t": time.time()})
    return RedirectResponse(tokens.login_url(state))

@app.get("/ig/callback")
async def ig_callback(code: str = "", state: str = "", error: str = ""):
    state_doc = db.ig_state.find_one_and_delete({"_id": state}) if state else None
    if error or not code or not state_doc or time.time() - state_doc.get("t", 0) > 600:
        raise HTTPException(400, "ورود ناموفق یا state نامعتبر/منقضی")
    uid, username = await tokens.exchange_code(code)
    return PlainTextResponse(f"✅ حساب @{username} ({uid}) متصل شد. این صفحه را ببندید.")

# ---------- وب‌هوک (کامنت و دایرکت) ----------
@app.get("/webhook")
def verify(request: Request):
    q = request.query_params
    if q.get("hub.mode") == "subscribe" and hmac.compare_digest(q.get("hub.verify_token", ""), config.IG_VERIFY_TOKEN):
        return PlainTextResponse(q.get("hub.challenge", ""))
    raise HTTPException(403)

@app.post("/webhook")
async def webhook(request: Request, bg: BackgroundTasks):
    raw = await request.body()
    sig = request.headers.get("X-Hub-Signature-256", "")
    want = "sha256=" + hmac.new(config.IG_APP_SECRET.encode(), raw, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig, want):
        raise HTTPException(403)
    bg.add_task(inbox.dispatch, await request.json())   # پاسخ سریع ۲۰۰ به متا
    return {"ok": True}

# ---------- ارائه‌ی لحظه‌ای عکس به متا (بدون ذخیره) ----------
@app.get("/media/{token}.jpg")
async def serve_media(token: str):
    data = await media.render(token)          # عکس از بله گرفته می‌شود و فقط در RAM می‌ماند
    if not data:
        raise HTTPException(404)
    return Response(data, media_type="image/jpeg", headers={"Cache-Control": "no-store"})

# ---------- تأیید/رد پیش‌نویس توسط مدیر ----------
@app.get("/admin/queue/{item_id}/{action}")
def admin_action(item_id: int, action: str, k: str = ""):
    if action not in ("approve", "reject") or not hmac.compare_digest(k, publisher.sign(item_id, action)):
        raise HTTPException(403)
    st = "scheduled" if action == "approve" else "rejected"
    r = db.ig_queue.update_one({"_id": item_id, "status": "draft"}, {"$set": {"status": st}})
    if not r.matched_count:
        return PlainTextResponse("این مورد قبلاً بررسی شده یا وجود ندارد.")
    if action == "approve":
        t = datetime.fromtimestamp(db.ig_queue.find_one({"_id": item_id})["scheduled_at"], publisher.TZ)
        return PlainTextResponse(f"✅ تأیید شد؛ انتشار: {t:%Y-%m-%d %H:%M}")
    return PlainTextResponse("❌ رد شد.")

# ---------- زمان‌بند داخلی ----------
async def scheduler():
    last_weekly = 0
    while True:
        try:
            await tokens.refresh_if_needed()
            await publisher.fill_queue()
            await publisher.process_due()
            now = datetime.now(publisher.TZ)
            if now.hour == 3 and now.minute < 5:
                media.cleanup(); await insights.collect()
            if now.weekday() == 4 and now.hour == 9 and time.time() - last_weekly > 86400:   # جمعه‌ها
                await insights.weekly_report(); last_weekly = time.time()
        except Exception as e:
            print("scheduler error:", e)
        await asyncio.sleep(60)

@app.on_event("startup")
async def startup():
    required = {
        "MONGODB_URI": config.MONGODB_URI,
        "TOKEN_ENC_KEY": config.TOKEN_ENC_KEY,
        "OAUTH_ADMIN_SECRET": config.OAUTH_ADMIN_SECRET,
    }
    missing = [name for name, value in required.items() if not value]
    if missing:
        raise RuntimeError("Missing required environment variables: " + ", ".join(missing))
    # Validate encryption key before accepting traffic.
    tokens._cipher()
    db.ig_queue.create_index([("status", 1), ("scheduled_at", 1)])
    asyncio.create_task(scheduler())
