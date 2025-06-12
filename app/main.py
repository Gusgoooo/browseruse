from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from playwright.async_api import async_playwright
from readability import Document
from bs4 import BeautifulSoup
import os, httpx, urllib.parse

SERP = os.getenv("SERPAPI_KEY")  # 可选；没有就走 Google fallback

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True,
)

class Req(BaseModel):
    query:  str | None = None
    prompt: str | None = None
    def text(self) -> str:
        return self.query or self.prompt or ""

@app.post("/scrape")
async def scrape(body: Req):
    term = body.text().strip()
    if not term:
        raise HTTPException(status_code=400, detail="empty input")

    # ① 获取首条搜索结果链接
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

    # ② Playwright 本地抓取并提取正文
    async with async_playwright() as p:
        browser = await p.chromium.launch(args=["--no-sandbox"])
        page = await browser.new_page()
        try:
    # 1) 先到 DOMReady，不等所有资源
    await page.goto(url, timeout=45000, wait_until="domcontentloaded")

    # 2) 等网络静默 1.5 s；若持续有请求也不再无限等
    try:
        await page.wait_for_load_state("networkidle", timeout=1500)
    except TimeoutError:
        pass                                   # 忽略二级超时

    # 3) 再给 JS 1.5 s 渲染
    await page.wait_for_timeout(1500)
    html = await page.content()

except TimeoutError:
    # ---------- 兜底：导航 45 s 仍超时 → 直接走 jina.ai 纯文本 ----------
    proxy_url = f"https://r.jina.ai/http://{url}"
    async with httpx.AsyncClient(timeout=20) as c:
        r = await c.get(proxy_url)
        if r.status_code != 200:
            raise HTTPException(status_code=502,
                                detail=f"text proxy failed: {r.status_code}")
        text = r.text.strip()
        await browser.close()
        return {"source": proxy_url, "excerpt": text[:1500]}
        except Exception as e:
            await browser.close()
            raise HTTPException(status_code=502, detail=f"playwright error: {e}")
        await browser.close()

    try:
        readable = Document(html).summary(html_partial=True)
        text = BeautifulSoup(readable, "html.parser").get_text(" ", strip=True)
    except Exception:
        text = BeautifulSoup(html, "html.parser").get_text(" ", strip=True)

    if not text:
        raise HTTPException(status_code=502, detail="empty text after parse")

    return {
        "source": url,
        "excerpt": text[:1500]
    }
