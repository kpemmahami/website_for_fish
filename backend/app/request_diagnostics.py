"""Correlate failed requests without logging bodies, query values or credentials."""

import logging
from traceback import extract_tb
from uuid import uuid4

from fastapi import Request
from starlette.responses import JSONResponse

from .main import app

log = logging.getLogger('aquafarm.requests')


@app.middleware('http')
async def request_diagnostics(request: Request, call_next):
    request_id = uuid4().hex
    error_type = None
    try:
        response = await call_next(request)
    except Exception as error:
        error_type = type(error).__name__
        frames = ' > '.join(f'{frame.name}:{frame.lineno}' for frame in extract_tb(error.__traceback__))
        log.error('request_id=%s exception=%s stack=%s', request_id, error_type, frames)
        response = JSONResponse({'detail': 'Service error'}, status_code=500)
    response.headers['X-Request-ID'] = request_id
    if response.status_code >= 400:
        route = getattr(request.scope.get('route'), 'path', '<unmatched>')
        log.warning('request_id=%s method=%s route=%s status=%s exception=%s',
                    request_id, request.method, route, response.status_code, error_type or '-')
    return response
