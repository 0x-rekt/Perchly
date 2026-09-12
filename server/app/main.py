from fastapi import FastAPI

from app.routers.github_webhooks import router as github_webhook_router

app = FastAPI(title="perchly PR Review Agent")
app.include_router(github_webhook_router)


@app.get("/")
def health_check() -> dict[str, str]:
    return {"message": "Everything ok"}
