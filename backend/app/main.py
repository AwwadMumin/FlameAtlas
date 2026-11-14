from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router
from app.core import errors
from app.core.config import get_settings

s = get_settings()
app = FastAPI(title="Mission Lens API", version="0.1.0",
              description="Decision support from NASA microgravity combustion data. Every number traces to a NASA record.")
app.add_middleware(CORSMiddleware, allow_origins=[o.strip() for o in s.cors_origins.split(",")],
                   allow_methods=["*"], allow_headers=["*"])
errors.install(app)
app.include_router(router)
