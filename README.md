# Steel Takeoff

Web app with two tools, sharing one history:

- **Phân tích bản vẽ** - a steel drawing (PDF) is read, checked, reviewed on screen and exported to the Excel template (.xlsm).
- **Trích xuất bảng** - tables in any PDF or scan are read into Excel, one sheet per table.

Stack: FastAPI + React, PostgreSQL, JWT login. Prompts live in `assets/prompts/`.

## Run
    cp .env.example .env          # set LLM_API_KEY, JWT_SECRET, POSTGRES_PASSWORD, ADMIN_EMAIL, ADMIN_PASSWORD
    docker compose up -d --build  # http://localhost:8000/app/

Without Docker:

    cd app/frontend && npm install && npm run build
    uvicorn app.main:app --reload

## OCR engine
`OCR_ENGINE=llm` (default) reads tables with a language model. `OCR_ENGINE=local` reads them cell by cell with VietOCR and only
asks the model about doubtful cells; build with `docker build --build-arg LOCAL_OCR=1 .` (see `requirements-ocr.txt`).

## Test
    python -m pytest
    cd app/frontend && npm test
