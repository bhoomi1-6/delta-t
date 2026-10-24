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

### Frontend (Node 20+)
```bash
cd frontend
npm install
npm run dev                     # http://localhost:3000
```
