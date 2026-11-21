import httpx
import config

async def admin_alert(text, token=None):
    token = token or config.BALE_TOKENS["sale_bale"]
    if not token:
        print("ALERT:", text); return
    async with httpx.AsyncClient(timeout=20) as c:
        await c.post(f"https://tapi.bale.ai/bot{token}/sendMessage",
                     json={"chat_id": config.ADMIN_ID, "text": text})
