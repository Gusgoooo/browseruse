from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import httpx, os, urllib.parse

BL = os.getenv("BROWSERLESS_TOKEN")   # 在 Render → Environment 设置
SERP = os.getenv("SERPAPI_KEY")       # 可选

app = FastAPI()

# --- 解决 CORS/OPTIONS ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],          # 若需要收敛域名，可改为 ["https://app.lovable.so"]
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True,
)

# --- 请求体：query / prompt 二选一 ---
class Req(BaseModel):
    query: str | None = None
    prompt: str | None = None

    @property
    def text(self) -> str:
        return self.query or self.prompt or ""

# --- 主路由 ---
@app.post("/scrape")
async def scrape(body: Req):
    search_term = body.text.strip()
    if not search_term:
        raise HTTPException(status_code=400, detail="empty input")

    async with httpx.AsyncClient(timeout=30) as client:
        # ① 取首条搜索结果
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

        # ② Browserless 抓正文（新域名 & Accept 头）
        bl_url = f"https://production-sfo.browserless.io/content?token={BL}"
        res = await client.post(
            bl_url,
            json={"url": url},
            headers={"Accept": "application/json"}
        )

        # 200 但非 JSON：很可能目标站反爬 / 返回整页 HTML
        if "application/json" not in res.headers.get("content-type", ""):
            raise HTTPException(status_code=502,
                                detail="Browserless returned non-JSON payload")

        text = res.json().get("data", "")

    return {
        "source": url,
        "excerpt": text[:1500]      # 控制长度，Lovable ≤ 1 MB
    }
