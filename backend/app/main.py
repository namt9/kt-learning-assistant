from fastapi import FastAPI

app = FastAPI(title="Trợ lý học tập thông minh", version="0.0.1")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


# TODO(B): POST /submit, GET /problems, GET /result/{submission_id}
