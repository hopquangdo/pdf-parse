# Steel Takeoff

PDF drawing -> reviewed steel schedule -> Excel template (.xlsm).

## Run with Docker (recommended)
    cp .env.example .env        # then set LLM_API_KEY (and optionally model / base URL)
    docker compose up -d --build
    # UI + API: http://localhost:8000/app/  (bound to 127.0.0.1; set BIND=0.0.0.0 only behind auth / a reverse proxy)
    # PORT=8081 docker compose up -d   changes the port
    docker compose logs -f app
    docker compose down         # keeps the data volume; add -v to delete uploads, run logs and exports

Data (uploads, `runs/<id>.json` run logs, exports) lives in the `app-data` volume mounted at `/data`.
Back it up with: `docker run --rm -v pdf-parse_app-data:/data -v "$PWD":/out alpine tar czf /out/data.tgz -C /data .`

## Run locally
    cd app/frontend && npm install && npm run build      # builds app/frontend/dist
    uvicorn app.main:app --reload                         # http://localhost:8000/app/
    (cd app/frontend && npm run dev)                      # dev server on :5173, proxies to :8000

## Test
    python -m pytest
    (cd app/frontend && npm test)
    node scripts/ui_smoke.mjs <jobId>                     # real-browser smoke test (server running)

## Code layout (one DDD, ports and adapters)

```
src/domain/          business rules + ports.py (interfaces: VisionReader, TableReader, TableLocator, PageRenderer,
                     JobRepository, FileStorage, RunRecorder, TemplateExporter) and steel_members.py
src/application/     use cases: extraction_service, export_service, auth/, table_review/ (LangGraph),
                     drawing_types/ (one plugin per family of drawings, see registry.py)
src/infrastructure/  adapters: db/, security/, llm/, pdf/, vision/, excel/, persistence/, storage/, runs/, prompts.py
app/                 interface: FastAPI (api/) and the React UI (frontend/)
assets/prompts/      the LLM prompts as .md files
evaluation/          offline quality checks (ground_truth.py, review_eval.py); not part of the runtime
```

Add a new family of drawings: write a class with `key`, `label`, `extract(ctx)` in `src/application/drawing_types/`
and add it to `registry.py`. Upload with `POST /extractions?drawing_type=<key>`; `GET /reference/drawing-types` lists them.

Compare a run with a ground-truth file: `python -m evaluation.ground_truth --truth <rows.json>`.

## OCR API (any table image -> text / JSON / Excel)

Signed-in users (Bearer token) can OCR an image or one page of a PDF with the configured model (`LLM_MODEL_NAME`, a DeepSeek
vision model through OpenRouter or any OpenAI-compatible server such as a self-hosted DeepSeek-OCR on vLLM: change `LLM_BASE_URL`).

```
POST /ocr/text                      file, page=1, rotate=0|90|180|270|auto, image=1      -> {"text": "..."}
POST /ocr/table?format=json|xlsx    file, page=1, rotate=auto, image=1, columns='["STT","Tên",...]'
```
* A PDF page that is mostly one embedded picture (a table pasted as an image) is read from that picture at full resolution; `image=2` picks the next one.
* `rotate=auto`: the model looks at the four turns of the page and picks the upright one.
* Long tables are cut into bands of whole rows (the header strip is repeated on each) and read in parallel.
* `columns` (optional, for a table type you know) makes every row come back keyed by column name, so cells cannot slide into the wrong column.
* The JSON answer has `warnings` (bands that failed, rows with a different cell count) and `usage` (tokens, cost).

## OCR engines (Trích xuất bảng)

`OCR_ENGINE` picks how the tables of a page are read (`src/application/page_extractors.py`):

* `llm` (default) - a language model reads every table image. No extra packages.
* `local` - ruling lines give the cells, VietOCR reads each cell on CPU, rules repair the numbers (unit weight from the catalog, count x length = total,
  total x unit weight = mass, index continuity), and the language model only re-reads the cells the rules doubt or a table that is too poor to read cell
  by cell. Build the image with `docker build --build-arg LOCAL_OCR=1 .` (adds torch + VietOCR, about 1.5 GB) and run with `OCR_ENGINE=local`.

Cells a rule repaired or the recognizer doubted are highlighted (yellow, with the reason as a comment) in the result screen and in the Excel file.
Scripts: `scripts/pdf_tables_local.py file.pdf 14,31 out.xlsx [--llm]`; accuracy: `python -m evaluation.score_numeric out.xlsx SHEET evaluation/gold/<table>.json`.
