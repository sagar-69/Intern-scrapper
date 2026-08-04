# Internship Radar

An async, self-healing internship discovery pipeline with Crawl4AI, Instructor-compatible LLM configuration, FastAPI, PostgreSQL, and React.

## Run

There are two ways to run the project.

### 1. Docker Compose (Recommended)
1. Copy `.env.example` to `.env` and set `GEMINI_API_KEY` for cloud extraction if desired.
2. Run `docker compose up --build`.
3. Open http://localhost:5173. 
*(Note: On the first run, 25 popular tech/startup career sites will be automatically seeded into your targets).*

### 2. Local Development (Manual)
1. Ensure you have a running PostgreSQL instance and configure `DATABASE_URL` in your `.env`.
2. **Backend**:
   ```bash
   cd backend
   source .venv/bin/activate
   uvicorn main:app --reload --port 8000
   ```
3. **Frontend**:
   ```bash
   cd frontend
   npm install
   npm run dev
   ```

