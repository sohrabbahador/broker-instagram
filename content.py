"""تولید کپشن/هشتگ و دسته‌بندی پیام‌ها. بدون وابستگی خارجی تا کاملاً قابل تست باشد."""
import re

FA = "۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩"
EN = "01234567890123456789"
def fa_to_en(s): return (s or "").translate(str.maketrans(FA, EN))
def en_to_fa(s): return (s or "").translate(str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹"))

PRIVATE_LINE = re.compile(r"(تلفن|موبایل|همراه|شماره\s*تماس|تماس\s*با|نام\s*مالک|مالک|آدرس\s*دقیق|پلاک|واحد\s*\d)", re.I)
PHONE = re.compile(r"(?<!\d)(?:\+?98|0)?9\d{9}(?!\d)|(?<!\d)0\d{10}(?!\d)")

def sanitize_public_text(text: str) -> str:
    """حذف اطلاعات تماس/مالک/آدرس دقیق و نشانه‌گذاری مارک‌داون بله."""
    out = []
    for line in (text or "").splitlines():
        if line.strip().startswith("———") and "خصوصی" in line:
            break
        if PRIVATE_LINE.search(line):
            continue
        if PHONE.search(fa_to_en(line)):
            continue
        line = line.replace("*", "").replace("_", " ").strip()
        if line:
            out.append(line)
    return "\n".join(out)

def _t(s, n): s = (s or "").strip(); return s if len(s) <= n else s[:n - 1] + "…"

def money_fa(v):
    """عدد ریال/تومان خام → «۳ میلیارد و ۲۰۰ میلیون تومان». ورودی بر حسب تومان."""
    if not v: return None
    b, m = divmod(int(v), 1_000_000_000)
    m //= 1_000_000
    parts = []
    if b: parts.append(f"{en_to_fa(str(b))} میلیارد")
    if m: parts.append(f"{en_to_fa(str(m))} میلیون")
    return (" و ".join(parts) + " تومان") if parts else None

def hashtags(doc: dict, limit=12):
    kind = doc.get("kind")
    tags = ["#بروکر_املاک", "#املاک_تهران", "#منطقه_۵_تهران"]
    tags += ["#خرید_آپارتمان", "#فروش_آپارتمان"] if kind == "فروش" else ["#رهن_و_اجاره", "#اجاره_آپارتمان"]
    if doc.get("khab"):
        tags.append("#" + _t(en_to_fa(doc["khab"]), 20).replace(" ", "_"))
    loc = (doc.get("location") or "").strip()
    if loc and loc != "نامشخص":
        tags.append("#" + re.sub(r"[^\w]+", "_", loc).strip("_")[:25])
    tags += ["#مشاور_املاک", "#سرمایه_گذاری_ملکی", "#تهران"]
    seen, res = set(), []
    for t in tags:
        if t not in seen and len(t) > 2:
            seen.add(t); res.append(t)
    return res[:limit]

def facts_line(doc):
    bits = []
    if doc.get("meter"): bits.append(f"📏 {en_to_fa(str(doc['meter']))} متر")
    if doc.get("khab"): bits.append(f"🛏 {en_to_fa(doc['khab'])}")
    if doc.get("location") and doc["location"] != "نامشخص": bits.append(f"📍 {_t(doc['location'], 40)}")
    return " | ".join(bits)

def template_caption(doc, cta_url):
    kind = doc.get("kind")
    head = "🏠 فایل جدید خرید و فروش" if kind == "فروش" else "🔑 فایل جدید رهن و اجاره"
    price = money_fa(doc.get("price"))
    price_line = (f"💰 {'قیمت' if kind == 'فروش' else 'رهن کامل'}: {price}" if price else "")
    body = [head, facts_line(doc), price_line]
    return "\n".join(x for x in body if x)

def build_caption(doc: dict, cta_url: str, ai_hook: str | None = None, handle="@broker_amlak.ir") -> str:
    """ساختار ثابت: هوک → مشخصات → CTA → هشتگ. تلفن مالک هرگز وارد نمی‌شود."""
    hook = sanitize_public_text(ai_hook or "").split("\n")[0] if ai_hook else ""
    parts = [hook] if hook else []
    parts.append(template_caption(doc, cta_url))
    code = doc.get("property_code") or doc.get("id")
    if code:
        parts.append(f"🆔 کد فایل: {en_to_fa(str(code))}")
    parts.append(f"📩 برای اطلاعات کامل و هماهنگی بازدید، «دایرکت» بدهید یا از ربات بله ما استفاده کنید:\n{cta_url}")
    parts.append(f"⚖️ {handle}")
    parts.append(" ".join(hashtags(doc)))
    return _t("\n\n".join(p for p in parts if p), 2200)

def ai_hook_prompt(doc):
    facts = sanitize_public_text(doc.get("text", ""))[:900]
    return ("برای یک آگهی ملکی در اینستاگرام فقط یک جمله‌ی جذاب و صادقانه‌ی فارسی (حداکثر ۱۵ کلمه) بنویس. "
            "ادعای اغراق‌آمیز، قیمت یا شماره تلفن ننویس. فقط از اطلاعات زیر استفاده کن:\n" + facts)

# ---------- دسته‌بندی پیام ----------
INTENTS = [
    ("spam", r"(فالوور|کلیک کن|بیت.?کوین|وام فوری|t\.me/|bit\.ly|https?://)"),
    ("phone", r"(شماره|تلفن|تماس|موبایل)"),
    ("visit", r"(بازدید|ببینم|وقت|قرار|حضوری)"),
    ("address", r"(آدرس|کجاست|کجا هست|لوکیشن|موقعیت دقیق)"),
    ("price", r"(قیمت|چنده|چند است|چقدر|رهن|اجاره|تخفیف|قابل مذاکره|بودجه)"),
    ("availability", r"(موجود|هنوز|فروخته|اجاره رفته)"),
]
def classify(text: str) -> str:
    t = fa_to_en(text or "")
    for name, rx in INTENTS:
        if re.search(rx, t, re.I):
            return name
    return "general"

def extract_phone(text: str):
    m = PHONE.search(fa_to_en(text or ""))
    return m.group(0) if m else None

def needs_human(intent: str) -> bool:
    """قیمت نهایی/مذاکره، آدرس دقیق و بازدید را فقط انسان نهایی می‌کند."""
    return intent in ("visit", "address", "phone")
