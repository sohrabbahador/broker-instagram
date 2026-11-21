import httpx
import config
from content import sanitize_public_text

async def gemini(prompt: str, system: str = "", max_tokens=200, temperature=0.5) -> str | None:
    if not config.GEMINI_API_KEY:
        return None
    payload = {"contents": [{"role": "user", "parts": [{"text": prompt}]}],
               "generationConfig": {"maxOutputTokens": max_tokens, "temperature": temperature}}
    if system:
        payload["systemInstruction"] = {"parts": [{"text": system}]}
    try:
        async with httpx.AsyncClient(timeout=45) as c:
            r = await c.post(f"https://generativelanguage.googleapis.com/v1beta/models/{config.GEMINI_MODEL}:generateContent",
                             headers={"x-goog-api-key": config.GEMINI_API_KEY}, json=payload)
        if r.status_code != 200:
            return None
        parts = r.json()["candidates"][0]["content"]["parts"]
        return "".join(p.get("text", "") for p in parts).strip() or None
    except Exception:
        return None

def inventory_context(limit=25) -> str:
    from db import db
    rows = db.files.find({"$or": [{"is_available": True}, {"is_available": {"$exists": False}}]},
                         {"_id": 0, "id": 1, "kind": 1, "khab": 1, "price": 1, "meter": 1, "location": 1, "text": 1}
                         ).sort("id", -1).limit(limit)
    out = []
    for r in rows:
        out.append(f"کد {r.get('id')}: {r.get('kind')} | {r.get('khab')} | {r.get('meter')}م | {r.get('location')} | "
                   + sanitize_public_text(r.get("text", ""))[:160].replace("\n", " "))
    return "\n".join(out)[:9000]

DM_SYSTEM = ("تو دستیار پاسخ‌گوی پیج اینستاگرام «بروکر املاک» هستی. کوتاه، مؤدب و فارسی پاسخ بده (حداکثر ۳ جمله). "
             "فقط از فهرست فایل‌های زیر استفاده کن. قیمت نهایی، تخفیف، آدرس دقیق، شماره مالک یا قول بازدید نده؛ "
             "بگو مشاور هماهنگ می‌کند. اگر پاسخ را نمی‌دانی صادقانه بگو و از مشتری نام، بودجه و محدوده را بپرس.")
async def dm_answer(user_text: str) -> str | None:
    return await gemini(user_text[:800], system=DM_SYSTEM + "\n\nفایل‌های موجود:\n" + inventory_context(), max_tokens=220, temperature=0.3)
