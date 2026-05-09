from fastapi import FastAPI

app = FastAPI(title="fastapi-backend")


@app.get("/")
def read_root():
    return {"message": "Hello, FastAPI"}


@app.get("/health")
def health():
    return {"status": "ok"}
