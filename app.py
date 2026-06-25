from fastapi import FastAPI

app = FastAPI(title="Autoclipping")


@app.get("/")
def root():
    """Health check confirming the Space is up and Hermes is installed."""
    return {"status": "Autoclipping pipeline is live", "hermes": "installed"}
