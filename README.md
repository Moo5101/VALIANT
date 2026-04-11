# Multi-Camera Surveillance — No App Edition

Stream from any iPhone or Android directly through the browser. No apps to install.

---

## Setup (2 steps)

### 1. Install & run the server
```bash
pip install -r requirements.txt
python server.py
```

The terminal will print your local IP, e.g.:
```
Dashboard  →  http://192.168.1.10:8080
Phone cam  →  http://192.168.1.10:8080/camera
```

### 2. Connect phones
- Open **Safari** on each iPhone (or Chrome on Android)
- Go to the `/camera` URL shown above
- Tap **Allow** when asked for camera permission
- Give the phone a name and tap **Start Streaming**

That's it! The phone will appear live on the dashboard at `/`.

---

## How it works
- The phone page uses the browser's built-in camera API (`getUserMedia`)
- It captures frames and sends them to the server via WebSocket
- Motion detection runs entirely on the phone (pixel diff algorithm)
- The server forwards frames + motion events to the dashboard in real-time
- No apps, no plugins, no accounts needed

## Requirements
- All devices must be on the **same WiFi network**
- iPhone: Safari works best (iOS 14.5+)
- Android: Chrome works best
- Python 3.9+

## Tips
- Keep the phone screen on while streaming (tap screen periodically or use a charger)
- The rear camera is used by default; tap 🔄 to flip
- Motion sensitivity can be tuned in `camera.html` by changing `MOTION_THRESHOLD` and `MOTION_PIXEL_RATIO`
