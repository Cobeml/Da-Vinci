"""Keep external SDK errors out of persisted logs and model context."""

from openai import OpenAIError
from pymongo.errors import PyMongoError


def safe_error(exc):
    if isinstance(exc, (OpenAIError, PyMongoError)):
        return type(exc).__name__
    return str(exc)[:2000]
