from __future__ import annotations

import argparse
import asyncio
from typing import Any, AsyncIterator

from hypercorn.asyncio import serve
from hypercorn.config import Config as HypercornConfig
from pydantic import ValidationError
from quart import Quart, Response, abort, current_app, jsonify, request

from kimi_http import __version__

from .models import CancelResponse, HealthResponse, RunRequest
from .runner import RunExecutor, RunManager, new_handle

API_PREFIX = "/api/v1"


def create_app(run_executor: RunExecutor | None = None) -> Quart:
    app = Quart(__name__, static_folder=None)
    app.config.setdefault("PROVIDE_AUTOMATIC_OPTIONS", True)
    app.config["run_manager"] = RunManager()
    app.config["run_executor"] = run_executor or RunExecutor()

    @app.get(f"{API_PREFIX}/health")
    async def health() -> dict[str, Any]:
        response = HealthResponse(status="ok", version=__version__)
        return response.model_dump()

    @app.post(f"{API_PREFIX}/runs")
    async def create_run() -> Response:
        payload = await request.get_json()
        if payload is None:
            return jsonify({"error": "invalid_request", "details": "missing JSON body"}), 400
        try:
            run_request = RunRequest.model_validate(payload)
        except ValidationError as exc:
            return jsonify({"error": "invalid_request", "details": exc.errors()}), 400

        manager: RunManager = current_app.config["run_manager"]
        executor: RunExecutor = current_app.config["run_executor"]
        handle = new_handle()
        manager.register(handle)
        handle.task = asyncio.create_task(executor.start_run(run_request, handle, manager))

        async def event_stream() -> AsyncIterator[bytes]:
            try:
                async for chunk in handle.stream():
                    yield chunk
            except asyncio.CancelledError:
                await manager.cancel(handle.id)
                raise

        response = Response(event_stream(), status=200, content_type="application/x-ndjson")
        response.timeout = None
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.post(f"{API_PREFIX}/runs/<run_id>/cancel")
    async def cancel_run(run_id: str):
        manager: RunManager = current_app.config["run_manager"]
        cancelled = await manager.cancel(run_id)
        if not cancelled:
            abort(404)
        response = CancelResponse(run_id=run_id, status="cancelling")
        return response.model_dump()

    return app


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the Kimi HTTP service")
    parser.add_argument("--host", default="0.0.0.0", help="Bind address (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=9000, help="Bind port (default: 9000)")
    parser.add_argument(
        "--reload",
        action="store_true",
        help="Reload on code changes (development only)",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    app = create_app()
    config = HypercornConfig()
    config.bind = [f"{args.host}:{args.port}"]
    config.alpn_protocols = ["h2", "http/1.1"]
    config.h2 = True
    config.use_reloader = args.reload

    asyncio.run(serve(app, config))


if __name__ == "__main__":  # pragma: no cover - manual entry point
    main()
