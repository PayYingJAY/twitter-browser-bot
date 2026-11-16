"""Private runtime configuration. Secrets come from environment variables."""
import json
import os
from pathlib import Path

ENV_FIELDS = {
    "OPENAI_API_KEY": "openai_api_key",
    "TWITTER_USERNAME": "username",
    "TWITTER_PASSWORD": "password",
    "TWITTER_MY_USERNAME": "my_username",
}

def load_config(filename="config.json"):
    with Path(filename).open(encoding="utf-8") as stream:
        config = json.load(stream)
    # Never accept credentials from JSON; keep them out of shareable config.
    for variable, field in ENV_FIELDS.items():
        config.pop(field, None)
        if os.environ.get(variable):
            config[field] = os.environ[variable]
    return config
