from fastapi import FastAPI
from app.api.endpoints import router

app = FastAPI(title="Ontology Generating")
app.include_router(router)
