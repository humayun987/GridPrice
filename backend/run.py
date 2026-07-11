import asyncio
import sys
import os
import logging


# ─── Logging configuration ────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
)

# Hide HTTPX request logs
logging.getLogger("httpx").setLevel(logging.WARNING)


# ─── Windows event loop configuration ────────────────────────────────────────

if sys.platform == "win32":
    asyncio.set_event_loop_policy(
        asyncio.WindowsProactorEventLoopPolicy()
    )


# ─── Start Uvicorn ────────────────────────────────────────────────────────────

import uvicorn


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=port,
        reload=False,
        log_level="info",
    )