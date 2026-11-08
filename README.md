# Delta-T

**Will your day actually work?** Delta-T simulates your plan thousands of times,
shows how likely you are to be late or miss a deadline, and suggests a fix, then
checks that the fix really helps.

Calendars and to-do lists assume everything goes to plan. Real days have late
buses, rain, meetings that overrun and tasks that take longer than expected.
Delta-T measures that risk before you live the day.

## What it does

1. **You plan.** Add tasks (deadline, estimated length, progress) in the
   dashboard and connect your Google Calendar (read-only).
2. **It simulates.** A Monte Carlo simulation plays tomorrow out thousands of
   times with random transit delays, rain, wind, meetings that overrun and
   distractions. The output is a failure percentage for every event and task:
   you count as late if you arrive more than 5 minutes after the start, and a
   task fails if its deadline passes with work left.
3. **AI proposes a fix.** A Gemini repair agent reads the risk numbers and
   proposes a better order for your tasks, with reasons.
4. **The simulation checks it.** The same simulation scores the proposal. A
   judge compares the average risk before and after. The verdict (improved,
   unchanged or worse) is plain arithmetic, and Gemini only writes the
   explanation.

The AI never produces the numbers and cannot overrule the verdict. The
calendar is read-only, and fixed events and deadlines cannot be changed.

## How it works

```
Dashboard (Next.js)
   │  POST /api/predict   (proxied to the backend)
   ▼
FastAPI backend ── review_plan (orchestrator)
   ├─ 1. Context:     Google Calendar, Open-Meteo weather, Google Routes
   ├─ 2. Predictor:   Monte Carlo simulation → risk per event and task
   ├─ 3. Repair:      Gemini proposes a new task order (validated, one retry)
   ├─ 4. Predictor:   re-simulate the proposal
   └─ 5. Judge:       verdict from the average risk + Gemini explanation
```

The orchestrator runs the steps in a fixed order. Each step needs the previous
step's output, so this is a deterministic pipeline with AI steps inside it, and
not an autonomous agent loop.

| Step | Kind | Role |
|---|---|---|
| Orchestrator | code | runs the steps and collects the data |
| Predictor | simulation (no AI) | measures the risk |
| Repair agent | Gemini | proposes a task order, within strict rules |
| Judge | arithmetic + Gemini | decides improved or worse, then explains |

## Tech stack

- **Frontend:** Next.js, React and TypeScript.
- **Backend:** Python 3.13, FastAPI and NumPy.
- **AI:** Google Gemini (repair and judge).
- **Data sources:** Google Calendar, Open-Meteo (weather) and the Google Routes
  API (travel times).
- **Optional:** an ElevenLabs voice assistant for adding tasks and running a
  prediction by voice.

```
backend/app/
  agents/         orchestrator, predictor, repair, judge, shared schemas
  integrations/   Google Calendar and OAuth, weather, routes, the simulation
  predict.py      POST /api/predict
frontend/
  components/     dashboard and voice assistant
  app/            Next.js pages and the voice-session route
```

## Setup

### Backend (Python 3.13)

```bash
cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Create `backend/.env` (it is ignored by git):

```
GEMINI_API_KEY=...
OAUTH_ENCRYPTION_KEY=...                  # see below
GOOGLE_CALENDAR_CREDENTIALS_FILE=google-calendar-credentials.json
GOOGLE_REDIRECT_URI=http://localhost:3000/auth/google/callback
FRONTEND_ORIGIN=http://localhost:3000
COOKIE_SECURE=false                       # keep false for local http
GOOGLE_MAPS_API_KEY=...                   # optional, live route times
```

Generate the encryption key with:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Optional settings: `GEMINI_MODEL` (override the default model),
`STARTING_LOCATION`, `GOOGLE_CALENDAR_ID` and `OAUTH_DB_PATH`.

**Google Calendar sign-in.** In Google Cloud Console, enable the Google
Calendar API and create an OAuth client of type **Web application**. Add the
redirect URI above to it, then download its JSON to
`backend/google-calendar-credentials.json`. If the consent screen is in Testing
mode, add your Google account as a test user. The credentials JSON, the local
`oauth_connections.sqlite3` database and `.env` files hold secrets: keep them
out of version control.

**Maps key (optional).** Without `GOOGLE_MAPS_API_KEY` the router uses
built-in fallback travel estimates. With it, the backend requests live
estimates from the Routes API, which must be enabled in the same Google Cloud
project.

Run the backend:

```bash
uvicorn app.main:app --reload --env-file .env    # http://localhost:8000
```

### Frontend (Node 20+)

```bash
cd frontend
npm install
npm run dev                                       # http://localhost:3000
```

The dashboard proxies `/api/predict` and the Google sign-in routes to the
backend at `http://localhost:8000`. Set `BACKEND_URL` to change that.

For the voice assistant, add `ELEVENLABS_API_KEY` and `ELEVENLABS_AGENT_ID` to
`frontend/.env.local` and attach the client tools to your ElevenLabs agent
(`get_dashboard`, `add_task`, `update_task`, `delete_task`, `run_prediction`).

### Using it

1. Open http://localhost:3000.
2. In Settings, set your starting location, preferred travel mode and workday
   hours.
3. Connect Google Calendar.
4. Add your tasks, then press **Start Prediction**. A prediction makes several
   Gemini calls and can take a couple of minutes. Progress is logged in the
   backend terminal.

The simulated day is always **tomorrow**, from midnight to midnight
(Europe/London). A task deadline is treated as the end of its date.

## Privacy and data

Calendar event titles, descriptions, locations, your tasks, and the fetched
weather and route conditions are sent to Google's Gemini API for the repair and
judge steps. Only run it with data you are comfortable sending to that service.
Calendar access is read-only: the app never edits your calendar.

## Limitations

- The repair step only **reorders tasks**. It does not choose exact time slots,
  and a suggestion to move a calendar event is advisory only and is not
  simulated.
- The simulation is not seeded, so a small before and after difference can be
  random noise. With a single task there is nothing to reorder.
- Weather and routes are Oxford-specific. When a weather or route request
  fails, fallback estimates are used and logged as warnings: check the results
  rather than treating fallback data as verified live data.
- Wind effects on walking and cycling are initial heuristics, not calibrated
  forecasts.
- Disruption forecasting and free-text plan input were prototyped and are not
  part of the current workflow.
- This is a prototype: it does not prove the proposed schedule is clash-free.
  Review the output.
