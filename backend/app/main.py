from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import get_settings

settings = get_settings()

# Create FastAPI app
app = FastAPI(
    title="tatva.gridprice API",
    description="Electricity market price forecasting platform",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS middleware — allows frontend to talk to this API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # Next.js frontend
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health_check():
    return {
        "status": "ok",
        "environment": settings.APP_ENV,
    }


@app.get("/")
async def root():
    return {"message": "tatva.gridprice API is running"}
