"""Process entry point: configures logging and exposes the FastAPI app."""

from __future__ import annotations

import uvicorn

from src.frameworks.fastapi_app import create_app
from src.frameworks.logging_config import configure_logging
from src.frameworks.settings import Settings

settings = Settings.from_env()
configure_logging(environment=settings.environment, log_level=settings.log_level)
app = create_app()


def main() -> None:
    uvicorn.run(
        "src.index:app",
        host="0.0.0.0",  # noqa: S104 - containerized deployment binds all interfaces
        port=settings.port,
        reload=settings.environment == "development",
    )


if __name__ == "__main__":
    main()
