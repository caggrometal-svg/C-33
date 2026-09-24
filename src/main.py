"""C-33/NEXO service entrypoint."""

from __future__ import annotations

import uvicorn

from config import load_infrastructure_config


def main() -> None:
    config = load_infrastructure_config()
    uvicorn.run("api:app", host="0.0.0.0", port=config.port)


if __name__ == "__main__":
    main()
