from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from playwright.async_api import async_playwright, TimeoutError
from readability import Document
from bs4 import BeautifulSoup
import os, httpx, urllib.parse

SERP = os.getenv("SERPAPI_KEY")  # 可为空

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True,
)

class Req(BaseModel):
    query: str | None = None
    prompt: str | None = None

    def text(self) -> str:
        return self.query or self.prompt or ""

@app.post("/scrape")
async def scrape(body: Req):
    term = body.text().strip()
    if not term:
        raise HTTPException(status_code=400, detail="empty input")

    # ① 取首条链接
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

    # ② Playwright 抓取；若失败改走 jina.ai
    async with async_playwright() as p:
        browser = await p.chromium.launch(args=["--no-sandbox"])
        page = await browser.new_page(
            user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/124.0.0.0 Safari/537.36")
        )

        try:
            # ------ 主导航 ------
            await page.goto(url, timeout=45000, wait_until="domcontentloaded")
            try:
                await page.wait_for_load_state("networkidle", timeout=1500)
            except TimeoutError:
                pass
            await page.wait_for_timeout(1500)
            html = await page.content()

            # Cloudflare 骨架检测
            if "Enable JavaScript and cookies to continue" in html:
                raise ValueError("cloudflare challenge")

        except Exception:
            # ------ 兜底：jina.ai ------
            proxy = f"https://r.jina.ai/http://{url}"
            async with httpx.AsyncClient(timeout=20) as c:
                r = await c.get(proxy)
                if r.status_code != 200:
                    await browser.close()
                    raise HTTPException(status_code=502,
                        detail=f"text proxy failed: {r.status_code}")
                text = r.text.strip()
                await browser.close()
                return {"source": proxy, "excerpt": text[:1500]}

        await browser.close()

    # ③ Readability 提纯
    try:
        readable = Document(html).summary(html_partial=True)
        text = BeautifulSoup(readable, "html.parser").get_text(" ", strip=True)
    except Exception:
        text = BeautifulSoup(html, "html.parser").get_text(" ", strip=True)

    if not text:
        raise HTTPException(status_code=502, detail="empty text after parse")

    return {"source": url, "excerpt": text[:1500]}
