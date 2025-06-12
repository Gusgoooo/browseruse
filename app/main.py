from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from playwright.async_api import async_playwright, TimeoutError
from readability import Document
from bs4 import BeautifulSoup
import os, httpx, urllib.parse

SERP = os.getenv("SERPAPI_KEY")          # 可留空

app = FastAPI()

# ---------- CORS ----------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True,
)

# ---------- 请求体 ----------
class Req(BaseModel):
    query:  str | None = None
    prompt: str | None = None

    def text(self) -> str:
        return self.query or self.prompt or ""

# ---------- 路由 ----------
@app.post("/scrape")
async def scrape(body: Req):
    term = body.text().strip()
    if not term:
        raise HTTPException(status_code=400, detail="empty input")

    # ① 获取目标 URL
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

    # ② Playwright 抓取；若遇 Cloudflare → jina.ai 代理
    async with async_playwright() as p:
        browser = await p.chromium.launch(args=["--no-sandbox"])
        page = await browser.new_page(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            )
        )

        try:
            # DOM 就绪即可，不等所有资源
            await page.goto(url, timeout=45000, wait_until="domcontentloaded")
