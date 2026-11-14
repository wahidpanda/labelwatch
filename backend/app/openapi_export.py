"""Write the OpenAPI schema for client generation: python -m app.openapi_export <path>"""

import json
import sys
from pathlib import Path

from app.config import Settings
from app.main import create_app


def main() -> None:
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("openapi.json")
    schema = create_app(Settings(_env_file=None, env="test")).openapi()
    target.write_text(json.dumps(schema, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
