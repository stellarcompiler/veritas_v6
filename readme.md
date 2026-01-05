# Veritas – Production-Grade CrewAI Backend

Veritas is a **FastAPI + CrewAI** powered backend for fake-news verification, designed with **production-first principles**: explicit state, Redis-backed observability, process-isolated execution, and tool-level telemetry.

This is **not a demo setup**. The system is built to be polled by websites, n8n workflows, and Telegram bots in real time.

---

## Architecture Overview

- **FastAPI** – Web/API layer (non-blocking, stateless)
- **CrewAI** – Multi-agent reasoning pipeline (Claim → Research → Verdict)
- **Redis** – Source of truth for:
  - Job state
  - Agent/tool logs
  - Final results
  - System statistics
- **Multiprocessing** – Each Crew run executes in its own OS process
- **ngrok** – Secure public exposure for n8n / Telegram

---

## Key Design Principles

- **No BackgroundTasks** for Crew execution  
- **No CrewAI internal memory** (`memory=False`)
- **Explicit job_id propagation** to agents and tools
- **Centralized telemetry adapter** for Redis logging
- **Polling-friendly APIs** (no websockets required)

---

## Project Structure (Simplified)

## FASTAPI file struct and Def 
app/
├── api/
│ └── routes/
│ ├── crew.py # start / status / result
│ └── stats.py
├── services/
│ ├── crew_runner.py # process-based Crew execution
│ └── telemetry.py # Redis event logging
├── core/
│ ├── redis.py
│ ├── redis_utils.py
│ └── config.py
├── schemas/
│ ├── requests.py
│ └── responses.py
└── main.py # FastAPI app (definition only)


---

## How the System Works

1. `POST /crew/start`
   - Accepts a news claim
   - Creates a `job_id`
   - Spawns a **new process** for Crew execution

2. Crew execution
   - Claim Agent → Research Agent → Verdict Agent
   - Tools log actions directly to Redis using `job_id`

3. Polling
   - `GET /crew/status/{job_id}` → live agent/tool logs
   - `GET /crew/result/{job_id}` → final JSON verdict

4. Statistics
   - `GET /stats` → historical system metrics

---

## Running the System (Windows)

### 1. Start Redis
```bash
redis-server


## SETUP 

python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt


-FastAPI + CrewAI logic : python run.py

# ngrok reverse proxy
-Open NEW TERMINAL with VENV


run :
    After installing ngrok in powershell (ngrok= 7.0.5)
    ngrok config add-authtoken 37nSPfud6zgc9bAXmGkYuzIjGTy_5XgVkMtJ2HDh2hG9tEKhV
    ngrok http 8000
    Dial URL : https://brunilda-preponderant-legend.ngrok-free.dev/
                                                                /crew/start  (with request body)
                                                                /crew/status/{job_id}  (job_id available via terminal or swaggerUI)
                                                                /crew/result/{job_id}
                                                                /stats

