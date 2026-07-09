# ScopeRecon deploy

## 1. Supabase
1. New project → SQL Editor → paste `supabase/schema.sql` → run
2. Auth → enable Email
3. Copy URL, anon key, service_role key, JWT secret

## 2. Stripe
1. Products: Pro $29/mo, Team $99/mo → copy `price_…` IDs
2. Webhook endpoint: `https://<api>/v1/billing/webhook`
   Events: `checkout.session.completed`, `customer.subscription.*`, `invoice.paid`, `invoice.payment_failed`
3. Copy `whsec_…`

## 3. API (Fly/Railway/Render)
```bash
cd api
cp .env.example .env   # fill all
docker build -t scoperecon-api .
# or: uvicorn app.main:app --host 0.0.0.0 --port 8000
```

## 4. Netlify (frontend/)
```bash
cd frontend
cp .env.example .env   # VITE_*
npm i && npm run build
# netlify deploy --prod --dir=dist
```
Base directory: `frontend`. Build: `npm run build`. Publish: `dist`.

## Env map
| Frontend | API |
|---|---|
| VITE_SUPABASE_URL | SUPABASE_URL |
| VITE_SUPABASE_ANON_KEY | SUPABASE_ANON_KEY |
| VITE_API_URL | PUBLIC_API_URL (CORS via FRONTEND_URL) |
