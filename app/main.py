import asyncio
from fastapi.middleware.cors import CORSMiddleware
from fastapi import FastAPI
from pydantic import BaseModel
import httpx, os, urllib.parse
from fastapi.middleware.cors import CORSMiddleware

BL = os.getenv("BROWSERLESS_TOKEN")
SERP = os.getenv("SERPAPI_KEY")

app = FastAPI()

# --- CORS: 解决 OPTIONS 预检 ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],      # 需限制可改指定域
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- 请求体：query / prompt 都行 ---
class Req(BaseModel):
    query: str | None = None
    prompt: str | None = None

    @property
    def text(self) -> str:
        return self.query or self.prompt or ""

# --- 路由：全异步 + httpx.AsyncClient ---
@app.post("/scrape")
async def scrape(body: Req):
    search_term = body.text.strip()
    if not search_term:
        return {"error": "blank input"}

    async with httpx.AsyncClient(timeout=30) as client:
        # 1) 拿首条搜索结果
        if SERP:
            r = await client.get(
                "https://serpapi.com/search",
                params={"q": search_term, "api_key": SERP, "num": 1}
            )
            url = r.json()["organic_results"][0]["link"]
        else:
            url = f"https://www.google.com/search?q={urllib.parse.quote(search_term)}"

        # 2) 远程 Browserless 抓正文
        bl_url = f"https://chrome.browserless.io/content?token={BL}"
        res = await client.post(bl_url, json={"url": url})
        print("BL_STATUS:", res.status_code, res.text[:120])
        text = res.json().get("data", "")

        return {
            "source": url,
            "excerpt": text[:1500]
        }

