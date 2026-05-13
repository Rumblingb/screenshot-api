# Screenshot API

A simple REST API for capturing webpage screenshots. Built with FastAPI.

**Free Tier:** 50 screenshots/month with API key
**Pro Tier:** $99/month for 10,000 screenshots

## Quick Start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. (Optional) Install Playwright browser
playwright install chromium

# 3. Set your ScreenshotLayer API key (free at screenshotlayer.net)
export SCREENSHOTLAYER_API_KEY=your_key_here

# 4. Run the server
python server.py
```

## API Usage

### Capture a Screenshot

```bash
curl -o screenshot.png \
  "http://localhost:8000/screenshot?url=https://example.com&api_key=YOUR_API_KEY"
```

### Parameters

| Param      | Type    | Required | Description                          |
|-----------|---------|----------|--------------------------------------|
| url       | string  | Yes      | Webpage URL (must include http/https) |
| api_key   | string  | Yes      | Your API key                         |
| width     | int     | No       | Viewport width (default: 1280)       |
| height    | int     | No       | Viewport height (default: 720)       |
| full_page | bool    | No       | Full-page capture (Pro only)         |
| delay     | int     | No       | Delay in ms (default: 1000)          |

### Check Usage

```bash
curl "http://localhost:8000/usage?api_key=YOUR_API_KEY"
```

## Backend Options

The API supports two screenshot backends:

1. **ScreenshotLayer** (recommended): Set `SCREENSHOTLAYER_API_KEY` env var. Free tier gives 100 screenshots/month.
2. **Playwright** (fallback): Install Playwright and it auto-falls back if no ScreenshotLayer key is set.

## Deployment

### Railway / Render / Fly.io

1. Set environment variables
2. Deploy with `python server.py`

### Docker

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY . .
RUN pip install -r requirements.txt
EXPOSE 8000
CMD ["python", "server.py"]
```

## License

MIT
