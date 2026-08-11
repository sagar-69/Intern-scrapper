# Internship Radar

An async, self-healing internship discovery pipeline with Crawl4AI, Instructor-compatible LLM configuration, FastAPI, PostgreSQL, and React.

## Run

There are two ways to run the project.

### 1. Docker Compose (Recommended)
1. Copy `.env.example` to `.env`. The default model is Ollama `phi3:mini`.
2. Start Ollama and install the model: `ollama serve` and `ollama pull phi3:mini`.
3. Run `docker compose up --build`.
4. Open http://localhost:5173.
*(Note: On the first run, 25 popular tech/startup career sites will be automatically seeded into your targets).*

### 2. Local Development (Manual)
1. Install and start PostgreSQL, then create the database:
   ```bash
   brew install postgresql@16
   brew services start postgresql@16
   createuser radar --createdb
   psql -d postgres -c "ALTER USER radar PASSWORD 'radar';"
   createdb -O radar internship_radar
   ```
2. Start Ollama and install the local model:
   ```bash
   ollama serve
   ollama pull phi3:mini
   ```
3. Ensure `.env` uses `DATABASE_URL=postgresql://radar:radar@localhost:5432/internship_radar` and `LLM_MODE=local`.
4. **Backend**:
   ```bash
   cd backend
   source .venv/bin/activate
   uvicorn main:app --reload --port 8000
   ```
5. **Frontend** (in another terminal):
   ```bash
   cd frontend
   npm install
   npm run dev -- --host 0.0.0.0
   ```

### Open on a phone

Connect the phone and computer to the same Wi-Fi, find the computer's LAN IP with `ipconfig getifaddr en0`, then open `http://<LAN_IP>:5173` on the phone. Start the backend with `uvicorn main:app --host 0.0.0.0 --reload --port 8000` so the phone can reach the API too.
