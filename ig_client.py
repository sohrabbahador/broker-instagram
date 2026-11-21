"""کلاینت Instagram API with Instagram Login (میزبان graph.instagram.com؛ بدون Facebook)."""
import asyncio
import httpx
import config

class IGError(Exception):
    def __init__(self, status, body):
        super().__init__(f"IG API {status}: {str(body)[:400]}")
        self.status, self.body = status, body

class IGClient:
    def __init__(self, ig_user_id: str, access_token: str):
        self.uid, self.token = ig_user_id, access_token
        self.base = f"https://graph.instagram.com/{config.IG_API_VERSION}"
        self.h = {"Authorization": f"Bearer {access_token}"}

    async def _req(self, method, path, **kw):
        async with httpx.AsyncClient(timeout=60) as c:
            r = await c.request(method, f"{self.base}/{path.lstrip('/')}", headers=self.h, **kw)
        data = r.json() if r.content else {}
        if r.status_code >= 400:
            raise IGError(r.status_code, data)
        return data

    # ---------- انتشار ----------
    async def create_image_container(self, image_url, caption=None, carousel_item=False, alt_text=None):
        body = {"image_url": image_url}
        if carousel_item:
            body["is_carousel_item"] = True
        else:
            body["caption"] = caption or ""
        if alt_text:
            body["alt_text"] = alt_text
        return (await self._req("POST", f"{self.uid}/media", json=body))["id"]

    async def create_carousel_container(self, children_ids, caption):
        body = {"media_type": "CAROUSEL", "children": children_ids, "caption": caption}
        return (await self._req("POST", f"{self.uid}/media", json=body))["id"]

    async def wait_ready(self, container_id, tries=12, delay=5):
        for _ in range(tries):
            st = (await self._req("GET", container_id, params={"fields": "status_code"})).get("status_code")
            if st == "FINISHED":
                return
            if st in ("ERROR", "EXPIRED"):
                raise IGError(400, f"container {container_id} status={st}")
            await asyncio.sleep(delay)
        raise IGError(408, "container not ready in time")

    async def publish(self, container_id):
        return (await self._req("POST", f"{self.uid}/media_publish", json={"creation_id": container_id}))["id"]

    async def publishing_usage(self):
        d = await self._req("GET", f"{self.uid}/content_publishing_limit",
                            params={"fields": "quota_usage,config"})
        row = (d.get("data") or [{}])[0]
        return row.get("quota_usage", 0), (row.get("config") or {}).get("quota_total", 50)

    # ---------- کامنت ----------
    async def reply_comment(self, comment_id, text):
        return await self._req("POST", f"{comment_id}/replies", json={"message": text})

    async def hide_comment(self, comment_id, hide=True):
        return await self._req("POST", comment_id, json={"hide": hide})

    # ---------- دایرکت ----------
    async def send_dm(self, recipient_id, text):
        return await self._req("POST", f"{self.uid}/messages",
                               json={"recipient": {"id": recipient_id}, "message": {"text": text}})

    async def private_reply(self, comment_id, text):
        """پاسخ خصوصی به کامنت (یک‌بار، در بازه‌ی مجاز پس از ثبت کامنت)."""
        return await self._req("POST", f"{self.uid}/messages",
                               json={"recipient": {"comment_id": comment_id}, "message": {"text": text}})

    # ---------- آمار ----------
    async def media_insights(self, media_id, metrics="reach,likes,comments,saved,shares"):
        return await self._req("GET", f"{media_id}/insights", params={"metric": metrics})

    async def recent_media(self, limit=25):
        return (await self._req("GET", f"{self.uid}/media",
                params={"fields": "id,caption,permalink,timestamp,like_count,comments_count", "limit": limit})).get("data", [])
