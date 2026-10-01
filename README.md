# AI-Stylist

## Run the backend

From this directory, install the Python dependencies and start FastAPI:

```bash
python -m pip install -r requirements.txt
python -m uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```

Open `http://localhost:8000/docs` for Swagger UI. The styling endpoint is
`POST /api/style` and accepts `user_profile` plus `user_query`.

Set `GROQ_API_KEY` in the runtime environment before sending a styling request.
The database is optional for styling; database-backed routes require
`DATABASE_URL`. Do not commit a `.env` file or include credentials in the
project archive.

## Product source status

The bundled `MockStore` is development/test data, not retailer inventory or
live availability. The current response must not be treated as real shopping
results until a live product provider is configured.

## Run tests

```bash
python -m pytest -q
```