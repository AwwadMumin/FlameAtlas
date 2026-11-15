from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router
from app.core import errors
from app.core.config import get_settings

s = get_settings()
@asynccontextmanager
async def lifespan(_: FastAPI):
    if not s.mock:  # warm the embedding model so the first assess is fast
        try:
            from app.services import embeddings
            embeddings.embed(["warm-up"])
        except Exception:  # noqa: BLE001
            pass
    try:  # fit the burn-outcome model once at start-up (about a second) so no request pays for it
        from app.services import predictor
        predictor.get_model()
    except Exception:  # noqa: BLE001
        pass
    yield


app = FastAPI(lifespan=lifespan, title="Mission Lens API", version="0.1.0",
              description="Decision support from NASA microgravity combustion data. Every number traces to a NASA record.")
app.add_middleware(CORSMiddleware, allow_origins=[o.strip() for o in s.cors_origins.split(",")],
                   allow_methods=["*"], allow_headers=["*"])
errors.install(app)
app.include_router(router)
