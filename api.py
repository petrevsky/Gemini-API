import os
import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, Depends, HTTPException, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.responses import Response
from pydantic import BaseModel

from gemini_webapi import GeminiClient

# --- Config from environment ---
SECURE_1PSID = os.getenv("SECURE_1PSID", "")
SECURE_1PSIDTS = os.getenv("SECURE_1PSIDTS", "")
API_KEY = os.getenv("API_KEY", "")

# --- Auth ---
security = HTTPBearer()


def verify_api_key(credentials: HTTPAuthorizationCredentials = Security(security)):
    if not API_KEY:
        raise HTTPException(status_code=500, detail="API_KEY not configured on server")
    if credentials.credentials != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return credentials.credentials


# --- Client singleton ---
client: GeminiClient | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global client
    if not SECURE_1PSID:
        raise RuntimeError("SECURE_1PSID environment variable is required")

    client = GeminiClient(SECURE_1PSID, SECURE_1PSIDTS or None)
    await client.init(
        auto_refresh=True,
        refresh_interval=600,
        auto_close=False,
        verbose=True,
    )
    yield
    if client:
        await client.close()


app = FastAPI(
    title="Gemini Web API",
    description="REST API wrapper for Google Gemini",
    lifespan=lifespan,
)


# --- Request/Response models ---
class GenerateRequest(BaseModel):
    prompt: str
    model: str | None = None


class GenerateResponse(BaseModel):
    text: str
    thoughts: str | None = None


class ListenRequest(BaseModel):
    text: str
    lang: str = "en"


# --- Routes ---
@app.get("/health")
async def health():
    return {"status": "ok", "client_ready": client is not None}


@app.post("/generate", response_model=GenerateResponse)
async def generate(req: GenerateRequest, _: str = Depends(verify_api_key)):
    if not client:
        raise HTTPException(status_code=503, detail="Client not initialized")

    try:
        output = await client.generate_content(req.prompt)
        return GenerateResponse(text=output.text, thoughts=output.thoughts)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/listen")
async def listen(req: ListenRequest, _: str = Depends(verify_api_key)):
    if not client:
        raise HTTPException(status_code=503, detail="Client not initialized")

    try:
        audio = await client.listen(req.text, lang=req.lang)
        return Response(content=audio, media_type="audio/ogg")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
