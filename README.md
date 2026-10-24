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

Place your Google OAuth client JSON in `backend/google-calendar-credentials.json`
or set `GOOGLE_CALENDAR_CREDENTIALS_FILE` to its path. The first call to the
calendar importer opens Google's local OAuth consent flow and saves a refresh
token to `backend/google-calendar-token.json`; override that path with
`GOOGLE_CALENDAR_TOKEN_FILE`. The default calendar is `primary`; set
`GOOGLE_CALENDAR_ID` to use another calendar.

The backend can fetch busy blocks with `get_busy_events(start, end)` from
`app.integrations.calendar`, where `start` and `end` are timezone-aware Python
datetimes. Cancelled and transparent events are excluded. Keep both credential
files private; they are ignored by git.

### Frontend (Node 20+)
```bash
cd frontend
npm install
npm run dev                     # http://localhost:3000
```
