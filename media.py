"""دریافت عکس از بله → استانداردسازی برای اینستاگرام → میزبانی عمومی موقت.
متا باید بتواند عکس را با URL عمومی دانلود کند؛ file_id بله برای آن‌ها قابل استفاده نیست."""
import io, json, secrets, time
import httpx
from PIL import Image, ImageFilter, ImageOps
import config
from db import db

MIN_R, MAX_R = 0.8, 1.9           # بازه‌ی مجاز نسبت تصویر فید (۴:۵ تا ۱٫۹۱:۱)
OUT_W = 1080

def normalize(raw: bytes) -> bytes:
    im = ImageOps.exif_transpose(Image.open(io.BytesIO(raw))).convert("RGB")
    w, h = im.size
    r = w / h
    if r > MAX_R:                                   # خیلی عریض → برش از طرفین
        nw = int(h * MAX_R); x = (w - nw) // 2
        im = im.crop((x, 0, x + nw, h))
    elif r < MIN_R:                                 # خیلی بلند → بوم ۴:۵ با پس‌زمینه‌ی تار
        cw = int(h * MIN_R)
        bg = im.resize((cw, h)).filter(ImageFilter.GaussianBlur(30))
        bg.paste(im, ((cw - w) // 2, 0))
        im = bg
    im = im.resize((OUT_W, int(OUT_W * im.height / im.width)), Image.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=88, optimize=True)
    return buf.getvalue()

async def fetch_bale_photo(source: str, file_id: str) -> bytes:
    tok = config.BALE_TOKENS.get(source)
    if not tok:
        raise RuntimeError(f"توکن بله برای منبع {source} تنظیم نشده")
    async with httpx.AsyncClient(timeout=40) as c:
        r = await c.post(f"https://tapi.bale.ai/bot{tok}/getFile", json={"file_id": file_id})
        path = r.json()["result"]["file_path"]
        f = await c.get(f"https://tapi.bale.ai/file/bot{tok}/{path}")
        f.raise_for_status()
        return f.content

async def host_photos(file_doc: dict, max_n=10):
    """فقط لینک می‌سازد؛ هیچ عکسی ذخیره نمی‌شود.
    در دیتابیس فقط (token ← source, file_id) نگهداری می‌شود (چند ده بایت).
    وقتی متا لینک را باز کند، عکس همان لحظه از بله گرفته، اصلاح و مستقیم تحویل داده می‌شود."""
    ids = file_doc.get("photos") or "[]"
    ids = json.loads(ids) if isinstance(ids, str) else ids
    # ربات‌های بله «سایزهای مختلفِ یک عکس» را در یک لیست ذخیره می‌کنند، نه چند عکس مجزا.
    if not file_doc.get("album"):
        ids = ids[-1:]
    urls = []
    for fid in ids[:max_n]:
        token = secrets.token_urlsafe(16)
        db.ig_media.insert_one({"_id": token, "source": file_doc.get("source", "sale_bale"),
                                "file_id": fid, "created": time.time()})
        urls.append(f"{config.PUBLIC_BASE_URL}/media/{token}.jpg")
    return urls

async def render(token: str):
    """برای مسیر /media: دانلود از بله + اصلاح در حافظه‌ی RAM؛ چیزی ذخیره نمی‌شود."""
    d = db.ig_media.find_one({"_id": token})
    if not d:
        return None
    return normalize(await fetch_bale_photo(d["source"], d["file_id"]))

def cleanup(max_age_h=48):
    db.ig_media.delete_many({"created": {"$lt": time.time() - max_age_h * 3600}})
