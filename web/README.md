# Perchly review console

React, TypeScript, Vite, and Tailwind UI for the Phase 3 human approval queue.

## Run locally

Start the FastAPI server first on port `8000`, then run:

```powershell
cd D:\perchly\web
bun install
bun run dev
```

Open <http://localhost:5173>. Vite proxies `/reviews` requests to the API at
`http://localhost:8000`.

To use another API origin, create `web/.env.local`:

```env
VITE_API_URL=https://api.example.com
VITE_OBSERVABILITY_API_KEY=the-same-value-as-PERCHLY_OBSERVABILITY_API_KEY
```

Build for production with:

```powershell
bun run build
```
