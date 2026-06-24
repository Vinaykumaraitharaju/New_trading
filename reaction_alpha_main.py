from __future__ import annotations

from pathlib import Path

import uvicorn
from dotenv import load_dotenv

from reaction_alpha import create_app

load_dotenv(dotenv_path=Path(__file__).resolve().parent / ".env", override=False)

app = create_app()


if __name__ == "__main__":
    uvicorn.run("reaction_alpha_main:app", host="0.0.0.0", port=8000, reload=False)
