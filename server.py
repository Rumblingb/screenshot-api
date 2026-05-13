"""
Screenshot API - REST API server
Capture webpage screenshots via simple REST API
"""

import os
import json
import time
import hashlib
import hmac
import secrets
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Query, HTTPException, Request, Depends
from fastapi.responses import FileResponse, JSONResponse, HTMLResponse, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import uvicorn

# Rate limiting storage (in-memory dict, for production use Redis)
rate_limits: dict = {}

# API keys storage (in-memory, for production use a DB)
api_keys: dict = {}

# Load API keys from env or use defaults
SCREENSHOTLAYER_API_KEY = os.environ.get("SCREENSHOTLAYER_API_KEY", "")
ADMIN_API_KEY = os.environ.get("ADMIN_API_KEY", secrets.token_hex(16))

# Free tier: 50 screenshots/mo per API key
FREE_TIER_LIMIT = int(os.environ.get("FREE_TIER_LIMIT", "50"))
# Pro tier: 10000 screenshots/mo
PRO_TIER_LIMIT = int(os.environ.get("PRO_TIER_LIMIT", "10000"))

app = FastAPI(title="Screenshot API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def generate_api_key() -> str:
    """Generate a new API key."""
    return f"ssapi_{secrets.token_hex(24)}"


def create_api_key(name: str = "Free User", tier: str = "free") -> dict:
    """Create a new API key entry."""
    key = generate_api_key()
    key_data = {
        "key": key,
        "name": name,
        "tier": tier,
        "created_at": datetime.utcnow().isoformat(),
        "usage_count": 0,
        "usage_month": datetime.utcnow().strftime("%Y-%m"),
        "active": True,
    }
    api_keys[key] = key_data
    return key_data


def verify_api_key(api_key: str) -> Optional[dict]:
    """Verify an API key and return its data."""
    if api_key in api_keys and api_keys[api_key].get("active", True):
        return api_keys[api_key]
    return None


def check_rate_limit(api_key: str) -> bool:
    """Check if the API key has remaining quota for this month."""
    if api_key not in api_keys:
        return False
    
    key_data = api_keys[api_key]
    current_month = datetime.utcnow().strftime("%Y-%m")
    
    # Reset counter if month changed
    if key_data.get("usage_month") != current_month:
        key_data["usage_count"] = 0
        key_data["usage_month"] = current_month
    
    limit = PRO_TIER_LIMIT if key_data["tier"] == "pro" else FREE_TIER_LIMIT
    
    if key_data["usage_count"] >= limit:
        return False
    
    return True


def increment_usage(api_key: str):
    """Increment usage counter for an API key."""
    if api_key in api_keys:
        api_keys[api_key]["usage_count"] += 1


async def get_api_key(request: Request) -> str:
    """Extract API key from query params or Authorization header."""
    api_key = request.query_params.get("api_key")
    if not api_key:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            api_key = auth_header[7:]
        elif auth_header.startswith("ApiKey "):
            api_key = auth_header[7:]
    return api_key or ""


@app.get("/")
async def root():
    """Root endpoint - redirects to landing page or returns API info."""
    return {"message": "Screenshot API", "version": "1.0.0", "docs": "/docs"}


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "ok", "timestamp": datetime.utcnow().isoformat()}


@app.get("/screenshot")
async def take_screenshot(
    url: str = Query(..., description="The URL to capture a screenshot of"),
    width: int = Query(1280, description="Viewport width"),
    height: int = Query(720, description="Viewport height"),
    full_page: bool = Query(False, description="Capture full page"),
    delay: int = Query(1000, description="Delay in ms before capture"),
    api_key: str = Depends(get_api_key),
):
    """
    Capture a screenshot of a webpage.
    
    Requires API key authentication.
    Free tier: 50 screenshots/month
    Pro tier: 10,000 screenshots/month ($99/mo)
    """
    if not api_key:
        raise HTTPException(
            status_code=401,
            detail="API key required. Get one at https://screenshot-api.example.com",
        )
    
    key_data = verify_api_key(api_key)
    if not key_data:
        raise HTTPException(
            status_code=403,
            detail="Invalid or inactive API key.",
        )
    
    if not check_rate_limit(api_key):
        limit = PRO_TIER_LIMIT if key_data["tier"] == "pro" else FREE_TIER_LIMIT
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit exceeded. Your tier allows {limit} screenshots/month. Upgrade at https://screenshot-api.example.com",
        )
    
    if not url or not (url.startswith("http://") or url.startswith("https://")):
        raise HTTPException(
            status_code=400,
            detail="Invalid URL. Must start with http:// or https://",
        )
    
    try:
        # Use Screenshotlayer API as the backend
        if SCREENSHOTLAYER_API_KEY:
            import httpx
            
            params = {
                "access_key": SCREENSHOTLAYER_API_KEY,
                "url": url,
                "width": width,
                "height": height,
                "fullpage": "1" if full_page else "0",
                "delay": delay // 1000,
                "format": "png",
            }
            
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.get(
                    "https://api.screenshotlayer.com/api/capture",
                    params=params,
                )
            
            if response.status_code != 200:
                raise HTTPException(
                    status_code=502,
                    detail="Screenshot service unavailable. Please try again later.",
                )
            
            increment_usage(api_key)
            
            # Return the image
            return Response(content=response.content, media_type="image/png")
        
        else:
            # Fallback: Use Playwright if available
            try:
                from playwright.async_api import async_playwright
            except ImportError:
                raise HTTPException(
                    status_code=500,
                    detail="Screenshot backend not configured. Set SCREENSHOTLAYER_API_KEY or install Playwright.",
                )
            
            async with async_playwright() as p:
                browser = await p.chromium.launch()
                page = await browser.new_page(
                    viewport={"width": width, "height": height}
                )
                await page.goto(url, wait_until="networkidle")
                await page.wait_for_timeout(delay)
                
                if full_page:
                    screenshot_bytes = await page.screenshot(full_page=True)
                else:
                    screenshot_bytes = await page.screenshot()
                
                await browser.close()
            
            increment_usage(api_key)
            return Response(content=screenshot_bytes, media_type="image/png")
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to capture screenshot: {str(e)}",
        )


@app.get("/usage")
async def get_usage(api_key: str = Depends(get_api_key)):
    """Get current usage statistics for your API key."""
    if not api_key:
        raise HTTPException(status_code=401, detail="API key required")
    
    key_data = verify_api_key(api_key)
    if not key_data:
        raise HTTPException(status_code=403, detail="Invalid API key")
    
    current_month = datetime.utcnow().strftime("%Y-%m")
    if key_data.get("usage_month") != current_month:
        key_data["usage_count"] = 0
        key_data["usage_month"] = current_month
    
    limit = PRO_TIER_LIMIT if key_data["tier"] == "pro" else FREE_TIER_LIMIT
    
    return {
        "api_key": api_key[:12] + "..." + api_key[-4:],
        "tier": key_data["tier"],
        "used": key_data["usage_count"],
        "limit": limit,
        "remaining": limit - key_data["usage_count"],
        "reset_date": f"{current_month}-01",
    }


# Admin endpoints
@app.get("/admin/keys")
async def list_keys(admin_key: str = Query(...)):
    """List all API keys (admin only)."""
    if admin_key != ADMIN_API_KEY:
        raise HTTPException(status_code=403, detail="Invalid admin key")
    
    safe_keys = {}
    for k, v in api_keys.items():
        safe_keys[k[:12] + "..." + k[-4:]] = {**v, "key": k[:12] + "..." + k[-4:]}
    
    return safe_keys


# Initialize default API keys
create_api_key("Demo", "free")


if __name__ == "__main__":
    print(f"Starting Screenshot API...")
    print(f"Admin API Key: {ADMIN_API_KEY}")
    print(f"Demo API Key: {list(api_keys.keys())[-1]}")
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "8000")))
