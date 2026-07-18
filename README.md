# AcadPlan AI Backend

FastAPI backend for **AcadPlan AI** — automates the generation of Course Delivery Plans (CDP) and CO-PO Affinity Maps from raw syllabus files (PDF/Word) using Generative AI.

## Tech Stack

- **Framework:** FastAPI + Uvicorn
- **Database:** SQLite (SQLAlchemy ORM)
- **Document Parsing:** pdfplumber, python-docx
- **PDF/Word Export:** ReportLab, python-docx
- **AI (optional):** OpenAI GPT-4 API

## Quick Start

```bash
# 1. Clone
git clone https://github.com/Kesa799/AcadPlanAI_Backend.git
cd AcadPlanAI_Backend

# 2. Create virtual environment
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # macOS/Linux

# 3. Install dependencies
pip install -r requirements.txt

# 4. (Optional) Set your OpenAI API key for AI-powered generation
#    Create a .env file:
echo OPENAI_API_KEY=sk-your-key-here > .env

# 5. Run the server
python -m app.main
```

The server starts at `http://127.0.0.1:8000`. Interactive API docs are at `http://127.0.0.1:8000/docs`.

## API Endpoints

### Syllabus Upload

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/upload-syllabus` | Upload a syllabus (PDF/DOCX). Returns `courseId` and `nextRoute`. |

### CDP (Course Delivery Plan)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/courses/{courseId}/cdp` | Fetch the CDP plan (auto-generates if missing). |
| PUT | `/api/courses/{courseId}/cdp/draft` | Save an edited CDP draft. |
| POST | `/api/courses/{courseId}/cdp/generate` | Trigger document generation. |

### CO-PO Matrix

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/courses/{courseId}/copo-matrix` | Fetch the CO-PO affinity matrix. |
| PUT | `/api/courses/{courseId}/copo-matrix` | Save the CO-PO affinity matrix. |

### Export

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/export` | Export CDP as PDF, DOCX, or JSON. |

### Legacy / Utility

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/health` | Health check. |
| POST | `/api/generate` | Generate CDP from syllabus ID. |
| GET | `/api/cdp/{cdp_id}` | Get CDP by numeric ID. |
| GET | `/api/cdps` | List all CDPs. |
| DELETE | `/api/syllabus/{id}` | Delete a syllabus and its CDPs. |

## Project Structure

```
AcadPlanAI_Backend/
├── app/
│   ├── api/
│   │   └── endpoints.py       # All API routes
│   ├── core/
│   │   ├── exceptions.py      # Custom exception classes
│   │   └── middleware.py       # Logging & error middleware
│   ├── models/
│   │   ├── database.py        # SQLAlchemy models & engine
│   │   └── schemas.py         # Pydantic request/response schemas
│   ├── parsers/
│   │   ├── pdf_parser.py      # PDF text & table extraction
│   │   └── word_parser.py     # Word text & table extraction
│   ├── services/
│   │   ├── ai_service.py      # AI-powered CDP generation
│   │   ├── extraction_service.py  # Regex-based extraction fallback
│   │   └── export_service.py  # PDF & Word export
│   ├── utils/
│   │   └── helpers.py         # Utility functions
│   ├── config.py              # Settings (env vars, paths)
│   └── main.py                # FastAPI app entry point
├── requirements.txt
├── create_tables.py           # Manual table creation script
└── README.md
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `OPENAI_API_KEY` | None | OpenAI API key for AI generation (falls back to regex extraction if absent) |
| `GROQ_API_KEY` | None | Groq API key (reserved for future use) |
| `DATABASE_URL` | sqlite:///./acadplan.db | Database connection string |
| `DEBUG` | true | Enable debug mode |

## Frontend Integration

This backend is designed to work with the [AcadPlan AI React frontend](https://github.com/Kesa799/AcadPlan-AI). Set `VITE_API_URL=http://localhost:8000` in the frontend `.env` to connect.

## License

Academic use only.
