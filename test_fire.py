from ultralytics import YOLO
import cvzone
import cv2
import subprocess
import sys
import time
import os

# ================== CONFIG ==================
RTSP_URL = "rtsp://103.110.86.89:8554/firecam"

WIDTH = 640
HEIGHT = 480
FPS = 15
DETECT_EVERY = 3   # detect 1/3 frame (~5 FPS)

# Tự động bật preview nếu có màn hình
SHOW_PREVIEW = os.environ.get("DISPLAY") is not None

# ================== START FFMPEG ==================
ffmpeg_cmd = [
    "ffmpeg",
    "-loglevel", "error",
    "-fflags", "nobuffer",
    "-flags", "low_delay",

    # INPUT từ Python
    "-f", "rawvideo",
    "-pix_fmt", "bgr24",
    "-s", f"{WIDTH}x{HEIGHT}",
    "-r", str(FPS),
    "-i", "-",

    # ENCODE
    "-an",
    "-c:v", "libx264",
    "-preset", "ultrafast",
    "-tune", "zerolatency",
    "-profile:v", "baseline",
    "-level", "3.0",
    "-pix_fmt", "yuv420p",
    "-g", str(FPS),
    "-bf", "0",

    # RTSP
    "-f", "rtsp",
    "-rtsp_transport", "tcp",
    RTSP_URL
]

try:
    ffmpeg = subprocess.Popen(
        ffmpeg_cmd,
        stdin=subprocess.PIPE
    )
    print("✅ FFmpeg started")
except Exception as e:
    print("❌ Không khởi động được FFmpeg:", e)
    sys.exit(1)

# ================== CAMERA ==================
cap = cv2.VideoCapture("/dev/video0", cv2.CAP_V4L2)

cap.set(cv2.CAP_PROP_FRAME_WIDTH, WIDTH)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, HEIGHT)
cap.set(cv2.CAP_PROP_FPS, FPS)

if not cap.isOpened():
    print("❌ Không mở được camera")
    sys.exit(1)

print("✅ Camera started")

# ================== YOLO ==================
try:
    model = YOLO("best.pt")
    classnames = model.names
    print("✅ YOLO loaded")
except Exception as e:
    print("❌ Không load được model:", e)
    sys.exit(1)

frame_id = 0
last_boxes = []

# ================== MAIN LOOP ==================
try:
    while True:
        ret, frame = cap.read()
        if not ret:
            print("❌ Mất camera")
            break

        frame_id += 1

        # ---- YOLO detect (không detect mọi frame) ----
        if frame_id % DETECT_EVERY == 0:
            results = model(frame, conf=0.5, imgsz=640, verbose=False)
            last_boxes = []

            for r in results:
                for box in r.boxes:
                    cls = int(box.cls[0])
                    conf = int(box.conf[0] * 100)
                    x1, y1, x2, y2 = map(int, box.xyxy[0])
                    last_boxes.append((cls, conf, x1, y1, x2, y2))

        # ---- Vẽ lại box cũ ----
        for cls, conf, x1, y1, x2, y2 in last_boxes:
            cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 0, 255), 2)
            cvzone.putTextRect(
                frame,
                f"{classnames[cls]} {conf}%",
                (x1, max(30, y1 - 10)),
                scale=1,
                thickness=2
            )

        # ---- PUSH RTSP ----
        try:
            ffmpeg.stdin.write(frame.tobytes())
        except BrokenPipeError:
            print("❌ FFmpeg đã chết (Broken pipe)")
            break

        # ---- LOCAL PREVIEW (chỉ khi có màn hình) ----
        if SHOW_PREVIEW:
            cv2.imshow("🔥 Fire Detection - Pi", frame)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break

except KeyboardInterrupt:
    print("🛑 Dừng bằng tay")

# ================== CLEANUP ==================
cap.release()

if ffmpeg.stdin:
    ffmpeg.stdin.close()

if SHOW_PREVIEW:
    cv2.destroyAllWindows()

print("✅ Thoát an toàn")
