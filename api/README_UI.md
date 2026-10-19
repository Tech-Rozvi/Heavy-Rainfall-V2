# Web UI

```bash
pip install -r requirements.txt
uvicorn api.app:app --host 0.0.0.0 --port 8000
```

Open **http://127.0.0.1:8000/**

- Historical run: mode **API**, pick province, set dates, **Run model**
- Forecast: mode **Forecast**, set forecast days 1–7
- API schema: **http://127.0.0.1:8000/docs**
