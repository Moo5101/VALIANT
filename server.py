import asyncio
import aiohttp
from aiohttp import web
import json
import time
import base64
import logging
import uuid
import ssl
from collections import defaultdict

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger(__name__)

cameras = {}
dashboard_clients = set()
motion_history = defaultdict(list)


async def broadcast_to_dashboards(msg: dict):
    global dashboard_clients
    if not dashboard_clients:
        return
    text = json.dumps(msg)
    dead = set()
    for ws in list(dashboard_clients):
        try:
            await ws.send_str(text)
        except Exception:
            dead.add(ws)
    dashboard_clients -= dead


async def broadcast_camera_list():
    await broadcast_to_dashboards({
        "type": "camera_list",
        "cameras": [serialize_camera(cid) for cid in cameras]
    })


def serialize_camera(cam_id):
    cam = cameras.get(cam_id, {})
    return {
        "id": cam_id,
        "name": cam.get("name", "Unknown"),
        "status": cam.get("status", "offline"),
        "motion": cam.get("motion", False),
        "motion_count": cam.get("motion_count", 0),
        "last_seen": cam.get("last_seen"),
    }


# ── HTTP API for phones ───────────────────────────────────────────────────────

async def handle_register(request):
    """POST /api/register — phone registers itself, gets an ID back."""
    data = await request.json()
    cam_id = str(uuid.uuid4())[:8]
    cameras[cam_id] = {
        "name": data.get("name", f"Camera {len(cameras)+1}"),
        "status": "online",
        "last_frame": None,
        "motion": False,
        "motion_count": 0,
        "last_seen": time.time(),
    }
    logger.info(f"Camera registered: {cameras[cam_id]['name']} ({cam_id})")
    await broadcast_camera_list()
    return web.json_response({"id": cam_id})


async def handle_frame(request):
    """POST /api/frame — phone posts a JPEG frame."""
    reader = await request.multipart()
    cam_id = None
    frame_b64 = None

    async for part in reader:
        if part.name == 'camera_id':
            cam_id = (await part.read()).decode()
        elif part.name == 'frame':
            data = await part.read()
            frame_b64 = base64.b64encode(data).decode()

    if not cam_id or cam_id not in cameras:
        return web.json_response({"error": "unknown camera"}, status=400)

    cameras[cam_id]["last_frame"] = frame_b64
    cameras[cam_id]["status"] = "online"
    cameras[cam_id]["last_seen"] = time.time()

    await broadcast_to_dashboards({
        "type": "frame",
        "camera_id": cam_id,
        "data": frame_b64,
        "timestamp": time.time(),
    })

    return web.json_response({"ok": True})


async def handle_motion(request):
    """POST /api/motion — phone reports motion event."""
    data = await request.json()
    cam_id = data.get("camera_id")
    detected = data.get("detected", False)

    if not cam_id or cam_id not in cameras:
        return web.json_response({"error": "unknown camera"}, status=400)

    cameras[cam_id]["motion"] = detected
    if detected:
        cameras[cam_id]["motion_count"] += 1
        motion_history[cam_id].append(time.time())
        motion_history[cam_id] = motion_history[cam_id][-200:]
        await broadcast_to_dashboards({
            "type": "motion",
            "camera_id": cam_id,
            "name": cameras[cam_id]["name"],
            "motion_count": cameras[cam_id]["motion_count"],
            "timestamp": time.time(),
        })
    else:
        await broadcast_to_dashboards({"type": "motion_clear", "camera_id": cam_id})

    return web.json_response({"ok": True})


# ── WebSocket: Dashboard only ─────────────────────────────────────────────────

async def handle_dashboard_ws(request):
    ws = web.WebSocketResponse(heartbeat=15)
    await ws.prepare(request)
    dashboard_clients.add(ws)
    logger.info(f"Dashboard connected. Total: {len(dashboard_clients)}")

    await ws.send_str(json.dumps({
        "type": "camera_list",
        "cameras": [serialize_camera(cid) for cid in cameras]
    }))

    for cam_id, cam in cameras.items():
        if cam.get("last_frame"):
            await ws.send_str(json.dumps({
                "type": "frame",
                "camera_id": cam_id,
                "data": cam["last_frame"],
                "timestamp": cam.get("last_seen", time.time()),
            }))

    try:
        async for msg in ws:
            if msg.type in (aiohttp.WSMsgType.ERROR, aiohttp.WSMsgType.CLOSE):
                break
    finally:
        dashboard_clients.discard(ws)
        logger.info(f"Dashboard disconnected. Total: {len(dashboard_clients)}")

    return ws


# ── Stale camera cleanup ──────────────────────────────────────────────────────

async def cleanup_stale_cameras(app):
    while True:
        await asyncio.sleep(5)
        now = time.time()
        for cam_id, cam in list(cameras.items()):
            if cam.get("last_seen") and now - cam["last_seen"] > 10:
                if cam["status"] == "online":
                    cameras[cam_id]["status"] = "offline"
                    cameras[cam_id]["motion"] = False
                    logger.info(f"Camera went offline: {cam['name']}")
                    await broadcast_camera_list()


async def start_cleanup(app):
    app["cleanup_task"] = asyncio.create_task(cleanup_stale_cameras(app))


async def stop_cleanup(app):
    app["cleanup_task"].cancel()


# ── HTTP Routes ───────────────────────────────────────────────────────────────

async def handle_index(request):
    raise web.HTTPFound("/static/dashboard.html")


async def handle_camera_page(request):
    raise web.HTTPFound("/static/camera.html")


async def handle_api_cameras(request):
    return web.json_response([serialize_camera(cid) for cid in cameras])


def create_app():
    app = web.Application(client_max_size=10 * 1024 * 1024)
    app.router.add_get("/", handle_index)
    app.router.add_get("/camera", handle_camera_page)
    app.router.add_get("/ws/dashboard", handle_dashboard_ws)
    app.router.add_post("/api/register", handle_register)
    app.router.add_post("/api/frame", handle_frame)
    app.router.add_post("/api/motion", handle_motion)
    app.router.add_get("/api/cameras", handle_api_cameras)
    app.router.add_static("/static", "./static")
    app.on_startup.append(start_cleanup)
    app.on_cleanup.append(stop_cleanup)
    return app


if __name__ == "__main__":
    ssl_ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ssl_ctx.load_cert_chain("100.67.172.28.pem", "100.67.172.28-key.pem")

    print("=" * 55)
    print("  Multi-Camera Surveillance Server (HTTP Polling)")
    print("=" * 55)
    print(f"  Dashboard  ->  https://100.67.172.28:8443")
    print(f"  Phone cam  ->  https://100.67.172.28:8443/camera")
    print("=" * 55)

    app = create_app()
    web.run_app(app, host="0.0.0.0", port=8443, ssl_context=ssl_ctx)
