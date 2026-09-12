# AI PR Review Agent API

Run the development server:

```powershell
uv run uvicorn app.main:app --reload
```

GitHub should send webhooks to `POST /webhooks/github`.

For every accepted pull-request event, the server logs a start line followed by either
the fetched diff size or an error traceback. Keep the terminal running while testing.

Required local configuration in `.env`:

```env
GITHUB_APP_ID=your-app-id
GITHUB_WEBHOOK_SECRET=your-webhook-secret
GITHUB_PRIVATE_KEY_PATH=./your-github-app-private-key.pem
```

## Layout

```text
app/
  core/       Configuration
  routers/    HTTP endpoints
  schemas/    Validated request models
  services/   GitHub-specific domain logic
  workers/    Background job boundaries
  main.py     FastAPI application factory/module
```
