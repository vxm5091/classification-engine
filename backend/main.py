import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.database import engine, Base
from backend.routers import transactions, rules, vendors, gl_codes, classify, stats

app = FastAPI(title="GL Code Classification Tool")

cors_origins = os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(transactions.router, prefix="/api")
app.include_router(rules.router, prefix="/api")
app.include_router(vendors.router, prefix="/api")
app.include_router(gl_codes.router, prefix="/api")
app.include_router(classify.router, prefix="/api")
app.include_router(stats.router, prefix="/api")


@app.on_event("startup")
def on_startup():
    Base.metadata.create_all(bind=engine)
