# delta-t

## Setup

### Backend (Python 3.13)
```bash
cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload   # http://localhost:8000
```

### Google Calendar constraints

Copy `backend/app/integrations/.env.example` to
`backend/app/integrations/.env` and set the configuration values there. The
integration loads that file automatically; variables already set in the shell
take precedence. Relative credential/token paths are resolved from `backend/`.

Put your Google OAuth client JSON at the configured
`GOOGLE_CALENDAR_CREDENTIALS_FILE` path. On first use the importer opens Google's
local OAuth consent flow and saves a refresh token to
`GOOGLE_CALENDAR_TOKEN_FILE`. The default calendar is `primary`; set
`GOOGLE_CALENDAR_ID` to use another calendar.

The backend can fetch busy blocks with `get_busy_events(start, end)` from
`app.integrations.google_calendar`, where `start` and `end` are timezone-aware Python
datetimes. Cancelled and transparent events are excluded. Keep both credential
files private and out of version control. These OAuth credentials are secrets;
no API key is needed or should be added to source code. The local `.env` and
default credential/token filenames are ignored by git.

### Gemini day-planning agent

From `backend/`, copy `.env.example` to `.env`, add your Gemini key, and
configure Google Calendar OAuth as described above. A Maps key is optional:
without it, the router uses built-in fallback travel estimates; with it, the
router requests live Routes API estimates. The backend loads `backend/.env`
automatically. Then run:

```bash
cp .env.example .env
source venv/bin/activate
python -m pip install -r requirements.txt
python -m app.agents.orchestrator --starting-location "St. Catherine's College" "Meet Alex at 10 at the Mathematical Institute, finish the budget report by 3, and spend about an hour on email."
```

Edit `backend/.env` locally and set `GEMINI_API_KEY`. Set
`GOOGLE_MAPS_API_KEY` only if you want live route estimates. Never put real
keys in `.env.example`. Both `.env` files are ignored by Git.

The orchestrator parses the description, reads busy events from the selected
Google Calendar, fetches Oxford weather and route estimates, and asks Gemini
for a revised plan with reasoning and suggested task start times. It prints a
proposal only; it does not edit Google Calendar. The existing weather and route
helpers are unchanged and use fallback estimates when their APIs fail, so check
their results rather than treating them as verified live data. Both integrations
are Oxford-specific. `GEMINI_MODEL` can override the default model.

Calendar event titles, locations, the supplied plan, and fetched conditions are
sent to Google's Gemini API for the review. Only run it with data you are
comfortable sending to that service. Review the output; this prototype does not
independently prove that the proposed schedule is clash-free. The intake agent
uses the simulated date and local Europe/London datetimes for events and task
deadlines. A task without a stated deadline is simulated as due at the end of
the simulated day. Keep all API keys and OAuth files private and out of source
control.

### Frontend (Node 20+)
```bash
cd frontend
npm install
npm run dev                     # http://localhost:3000
```
