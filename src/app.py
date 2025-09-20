from src.awake import awake_mode
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.concurrency import run_in_threadpool
from starlette.websockets import WebSocketState
import asyncio
import inspect  # new

app = FastAPI()
MAX_WAV_BYTES = 25 * 1024 * 1024  # 25 MB

def _looks_like_wav(buf: bytes) -> bool:
    return len(buf) >= 44 and buf[0:4] == b"RIFF" and buf[8:12] == b"WAVE"

@app.websocket("/ws")
async def ws_handler(websocket: WebSocket):
    await websocket.accept()
    while True:
        try:
            data = await websocket.receive_bytes()
        except WebSocketDisconnect:
            # client closed; we’re done
            break
        except Exception:
            # protocol/receive error — close politely
            if websocket.client_state == WebSocketState.CONNECTED:
                await websocket.close(code=1003)
            break

        if len(data) > MAX_WAV_BYTES:
            await websocket.send_json(
                {"type": "error",
                 "error": {"code": "PAYLOAD_TOO_LARGE", "message": "Max 25MB"}}
            )
            continue

        if not _looks_like_wav(data):
            # Invalid payload; close but don’t kill the whole server
            if websocket.client_state == WebSocketState.CONNECTED:
                await websocket.close(code=1003)
            break

        # fresh queue per message
        stream_q: asyncio.Queue[str] = asyncio.Queue()

        async def on_chunk(chunk: str):
            await stream_q.put(chunk)

        # Run awake_mode safely
        if inspect.iscoroutinefunction(awake_mode):
            task = asyncio.create_task(awake_mode(data, on_chunk))
        else:
            # If it’s sync or might block, run in a threadpool
            task = asyncio.create_task(run_in_threadpool(awake_mode, data, on_chunk))

        # Stream as chunks arrive; timeout is just a heartbeat
        while True:
            if task.done() and stream_q.empty():
                break
            try:
                chunk = await asyncio.wait_for(stream_q.get(), timeout=30)
                if websocket.client_state == WebSocketState.CONNECTED:
                    await websocket.send_json({"type": "stream", "text": chunk})
            except asyncio.TimeoutError:
                # No chunk yet; loop and check task status again
                continue

        # Deliver final result (and surface any errors cleanly)
        try:
            result = await task
        except Exception as e:
            result = None
            # Optional: send an error frame instead of silently failing
            if websocket.client_state == WebSocketState.CONNECTED:
                await websocket.send_json(
                    {"type": "error",
                     "error": {"code": "SERVER_ERROR", "message": str(e)}}
                )

        if websocket.client_state == WebSocketState.CONNECTED:
            await websocket.send_json(
                {"type": "reply",
                 "text": result or "No transcription or an error occurred."}
            )
    # No unconditional close here; the loop exits only on disconnect or fatal error
