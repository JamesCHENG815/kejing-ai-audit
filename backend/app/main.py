from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.import_batches import router as import_batches_router
from app.api.review_tasks import router as review_tasks_router
from app.database import BACKEND_DIR, init_db


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    yield


app = FastAPI(title="客经智审 API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(import_batches_router)
app.include_router(review_tasks_router)
app.mount(
    "/storage",
    StaticFiles(directory=BACKEND_DIR / "storage"),
    name="storage",
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
