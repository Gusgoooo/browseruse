from fastapi import FastAPI
from pydantic import BaseModel
import httpx, os, urllib.parse

BL = os.getenv("BROWSERLESS_TOKEN")
SERP = os.getenv("SERPAPI_KEY")     # 可选

app = FastAPI()

class Req(BaseModel):
    query: str

@app.post("/scrape")
async def scrape(body: Req):
    # 1️⃣ 使用 SerpAPI（若提供）获取第一个 Google 结果
    url = ""
    if SERP:
        r = await httpx.get(
            "https://serpapi.com/search",
            params={"q": body.query, "api_key": SERP, "num": 1}
        )
        url = r.json()["organic_results"][0]["link"]
    else:
        url = f"https://www.google.com/search?q={urllib.parse.quote(body.query)}"

    # 2️⃣ 调用 Browserless 读取正文
    bl_url = f"https://chrome.browserless.io/content?token={BL}"
    res = await httpx.post(bl_url, json={"url": url})
    text = res.json().get("data", "")

    return {"source": url, "excerpt": text[:1500]}