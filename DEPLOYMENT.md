# Frontdesk — Free Cloud Deployment Guide (Render + Vercel)

This guide walks you through hosting the complete Frontdesk application for **100% free** using:
- **Backend (FastAPI + SSE + SQLite/Postgres)**: [Render.com](https://render.com) (Free Web Service)
- **Frontend (React 19 + Vite)**: [Vercel](https://vercel.com) (Free Hobby Tier)

---

## Architecture at a Glance

```
┌─────────────────────────────────┐        ┌───────────────────────────────────┐
│         Vercel (Hobby)          │        │        Render (Free Tier)         │
│   Frontend React 19 + Vite UI   │        │     Backend FastAPI API + SSE     │
│   https://frontdesk.vercel.app  ├───────►│  https://frontdesk-api.onrender.com│
└─────────────────────────────────┘  CORS  └───────────────────────────────────┘
```

---

## Part 1: Deploy Backend to Render (Free)

### Option A: 1-Click Blueprint (Recommended)
1. Push your repository to GitHub: `git push origin main`.
2. Log into [Render Dashboard](https://dashboard.render.com).
3. Click **New +** -> **Blueprint**.
4. Connect your `frontdesk` repository. Render will automatically detect [`render.yaml`](./render.yaml).
5. Click **Apply**. Render will deploy your service automatically!

---

### Option B: Manual Setup on Render
If you prefer configuring it manually:
1. In the Render Dashboard, click **New +** -> **Web Service**.
2. Connect your GitHub repository: `https://github.com/<your-username>/frontdesk`.
3. Fill in the deployment details:
   - **Name**: `frontdesk-api` (or your choice)
   - **Region**: Choose the closest region (e.g., `Singapore` or `Frankfurt`)
   - **Branch**: `main`
   - **Root Directory**: `backend`
   - **Runtime**: `Python 3`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
   - **Instance Type**: `Free`

4. Add **Environment Variables** under the *Environment* tab:
   | Key | Value | Description |
   |-----|-------|-------------|
   | `FRONTDESK_SECRET_KEY` | *(Generate a random 32-char string)* | JWT HMAC secret key |
   | `REQUIRE_AUTH` | `false` | Allows backward-compat demo access |
   | `PYTHON_VERSION` | `3.11.11` | Ensures compatible Python environment |
   | `FRONTDESK_CORS_ORIGINS` | `http://localhost:5173` *(Update with your Vercel URL after Part 2)* | Allowed origins for CORS |

5. Click **Create Web Service**.
6. Once deployed, copy your backend URL:  
   👉 `https://frontdesk-api-xxxx.onrender.com`

---

## Part 2: Deploy Frontend to Vercel (Free)

1. Log into your [Vercel Dashboard](https://vercel.com).
2. Click **Add New...** -> **Project**.
3. Import your `frontdesk` GitHub repository.
4. Configure Project Settings:
   - **Framework Preset**: `Vite`
   - **Root Directory**: Click `Edit` and select `frontend`
   - **Build Command**: `npm run build` (Default)
   - **Output Directory**: `dist` (Default)
   - **Install Command**: `npm install` (Default)
5. Expand **Environment Variables** and add:
   | Key | Value | Description |
   |-----|-------|-------------|
   | `VITE_API_URL` | `https://frontdesk-api-xxxx.onrender.com` | Your Render backend URL (no trailing slash) |

6. Click **Deploy**.
7. Vercel will build and assign your production URL:  
   👉 `https://frontdesk-xxxx.vercel.app`

---

## Part 3: Connect Frontend & Backend (Final CORS Step)

1. Head back to your **Render Dashboard** -> `frontdesk-api` -> **Environment**.
2. Update the `FRONTDESK_CORS_ORIGINS` variable:
   ```env
   FRONTDESK_CORS_ORIGINS=https://frontdesk-xxxx.vercel.app,http://localhost:5173
   ```
3. Click **Save Changes**. Render will automatically restart with the new CORS origin allowed.

---

## Free-Tier Tips & Best Practices

### 1. Handling Render Spin-Downs (Cold Starts)
Render free web services spin down after 15 minutes of inactivity. The first request after a sleep period may take ~30–50 seconds to boot up.
- **Tip**: You can use a free uptime monitor like [UptimeRobot](https://uptimerobot.com) to ping `https://frontdesk-api-xxxx.onrender.com/api/health` every 10 minutes to keep it awake during demo hours.

### 2. Persistent Database Storage
Render's free tier uses ephemeral container disks, which reset SQLite data on service restarts.
- For 100% persistent production data on the free tier:
  1. Create a free PostgreSQL database on [Neon.tech](https://neon.tech) or [Supabase](https://supabase.com).
  2. Set the `DATABASE_URL` environment variable in Render:
     ```env
     DATABASE_URL=postgresql://user:password@ep-host.neon.tech/frontdesk?sslmode=require
     ```
  3. Frontdesk's SQLAlchemy models and lifespan migrations will automatically seed and manage the schema on startup!

---

## Default Demo Credentials

Once deployed, you can log in immediately:

### Customer Portal:
- **Email**: `customer@acmecorp.com`
- **Password**: `arvo2026!`
- **Access**: Customer workspace, create tickets, view updates, reply directly.

### Agent Workspace (Team Lead):
- **Email**: `meera@arvo.in`
- **Password**: `arvo2026!`
- **Access**: Full supervisory access, claim tickets, resolve, reassign, view audit trail.

### Agent Workspace (Support Agent):
- **Email**: `ravi@arvo.in`
- **Password**: `arvo2026!`
- **Access**: Agent workspace, ticket queue, public replies, internal notes.
