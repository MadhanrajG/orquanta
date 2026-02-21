#!/bin/sh
# OrQuanta Railway entrypoint
# Railway sets $PORT dynamically - this script ensures it's properly passed
exec uvicorn v4.api.main:app --host 0.0.0.0 --port "$PORT" --workers 1
