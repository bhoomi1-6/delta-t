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

From `backend/`, install the requirements and configure `GEMINI_API_KEY`,
`GOOGLE_MAPS_API_KEY`, and Google Calendar OAuth credentials. Then run:

```bash
source venv/bin/activate
python -m pip install -r requirements.txt
export GEMINI_API_KEY="your-gemini-api-key"
export GOOGLE_MAPS_API_KEY="your-google-maps-api-key"
python -m app.agents.orchestrator --starting-location "St. Catherine's College" "Meet Alex at 10 at the Mathematical Institute, finish the budget report by 3, and spend about an hour on email."
```

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
run the Monte Carlo simulator or independently prove that the proposed schedule
is clash-free. Times in a plan without an explicit date are interpreted as the
next matching time in the coming 24 hours. Keep all API keys and OAuth files
private and out of source control.

### Frontend (Node 20+)
```bash
cd frontend
npm install
npm run dev                     # http://localhost:3000
```
