from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import httpx, os, urllib.parse

# ⬇️ 从 Render → Environment 里读 token/key
BL   = os.getenv("BROWSERLESS_TOKEN")          # 必填：Browserless API Key
SERP = os.getenv("SERPAPI_KEY")                # 选填：SerpAPI Key（无则走 Google URL）

app = FastAPI()

# --- 允许任意域跨域；正式可收窄 allow_origins ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True,
)

# --- 请求体；支持 query 或 prompt 任意字段 ---
class Req(BaseModel):
    query:  str | None = None
    prompt: str | None = None

    @property
    def text(self) -> str:
        return self.query or self.prompt or ""

# --- 核心路由 ---
@app.post("/scrape")
async def scrape(body: Req):
    search_term = body.text.strip()
    if not search_term:
        raise HTTPException(status_code=400, detail="empty input")

    async with httpx.AsyncClient(timeout=30) as client:
        # ① 搜索：优先用 SerpAPI → 回退 Google URL
        if SERP:
            r = await client.get(
                "https://serpapi.com/search",
                params={"q": search_term, "api_key": SERP, "num": 1}
            )
            try:
                url = r.json()["organic_results"][0]["link"]
            except (KeyError, IndexError):
                raise HTTPException(status_code=502, detail="SerpAPI no results")
        else:
            url = f"https://www.google.com/search?q={urllib.parse.quote(search_term)}"

        # ② Browserless 抽正文（新版 /scrape 端点）
        bl_url = f"https://production-sfo.browserless.io/scrape?token={BL}"
        payload = {
            "url": url,
            "elements": [
                { "selector": "body", "type": "text" }   # 抽取 <body> 全文；可改更精确选择器
            ]
        }
        res = await client.post(
            bl_url,
            json=payload,
            headers={"Accept": "application/json"}
        )

        # 若 Browserless 返回 HTML 而非 JSON，直接抛 502
        if "application/json" not in res.headers.get("content-type", ""):
            raise HTTPException(status_code=502, detail="Browserless non-JSON payload")

        try:
            text = res.json()["data"][0]          # /scrape 格式: {"data": ["纯文本"]}
        except (KeyError, IndexError):
            raise HTTPException(status_code=502, detail="scrape result empty")

    # ③ 返回给 Lovable / 前端
    return {
        "source": url,
        "excerpt": text[:1500]                    # 控制长度 <= 1 MB
    }
