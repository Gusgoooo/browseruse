# app/main.py  · Playwright 自托管版
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from playwright.async_api import async_playwright
import os, httpx, urllib.parse

SERP = os.getenv("SERPAPI_KEY")      # 可选；没有就自动走 Google URL

app = FastAPI()

# ---------- CORS ----------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],             # 正式可收窄域名
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True,
)

# ---------- 请求体 ----------
class Req(BaseModel):
    query:  str | None = None
    prompt: str | None = None
    def text(self) -> str: return self.query or self.prompt or ""

# ---------- 主路由 ----------
@app.post("/scrape")
async def scrape(body: Req):
    term = body.text().strip()
    if not term:
        raise HTTPException(status_code=400, detail="empty input")

    # ① 拿目标 URL
    if SERP:
        async with httpx.AsyncClient(timeout=20) as c:
            r = await c.get(
                "https://serpapi.com/search",
                params={"q": term, "api_key": SERP, "num": 1}
            )
            try:
                url = r.json()["organic_results"][0]["link"]
            except (KeyError, IndexError):
                raise HTTPException(status_code=502, detail="SerpAPI no results")
    else:
        url = f"https://www.google.com/search?q={urllib.parse.quote(term)}"

    # ② Playwright 本地浏览器抓正文
    async with async_playwright() as p:
        browser = await p.chromium.launch(args=["--no-sandbox"])
        page = await browser.new_page()
        try:
            await page.goto(url, timeout=30000)
            # 根据站点可改更精确 selector，如 ".article"
            text = await page.inner_text("body")
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"playwright error: {e}")
        finally:
            await browser.close()

    return {
        "source": url,
        "excerpt": text[:1500]        # 控制长度，Lovable ≤ 1 MB
    }
