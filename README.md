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

### Frontend (Node 20+)
```bash
cd frontend
npm install
npm run dev                     # http://localhost:3000
```
