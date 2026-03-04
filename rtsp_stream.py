import cv2
import gi
import numpy as np
import tensorflow.lite as tflite
from threading import Thread, Lock
import time
import subprocess
import os
import threading


import control_gpio
import mqtt_function
import mqtt

gi.require_version("Gst", "1.0")
from gi.repository import Gst, GLib
# published = False
# ── Config ────────────────────────────────────────────
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
MODEL_PATH = os.path.join(SCRIPT_DIR, "best_float16.tflite")

# ── Remote RTSP Server ────────────────────────────────
REMOTE_RTSP_HOST = "103.110.86.89"
REMOTE_RTSP_PORT = "8554"
REMOTE_RTSP_PATH = "/fire"   # đổi path nếu cần, ví dụ: "/live/camera1"
REMOTE_RTSP_URL  = f"rtsp://{REMOTE_RTSP_HOST}:{REMOTE_RTSP_PORT}{REMOTE_RTSP_PATH}"

WIDTH, HEIGHT = 640, 480
FPS           = 20
CONF_THRESH   = 0.5
IMGSZ         = 320
NAMES         = {0: "fire", 1: "smoke"}
# ─────────────────────────────────────────────────────


class FrameBuffer:
    def __init__(self):
        self.frame = None
        self.lock  = Lock()

    def write(self, frame):
        with self.lock:
            self.frame = frame.copy()

    def read(self):
        with self.lock:
            return self.frame.copy() if self.frame is not None else None


class CaptureThread(Thread):
    def __init__(self, buffer: FrameBuffer):
        super().__init__(daemon=True)
        self.buffer        = buffer
        self.running       = True
        self._frame_count  = 0
        self._last_frame   = None
        self._model_logged = False
        self.fire_count   = 0
        self.last_fire_time = 0
        self.published = False

        print(f"Đang load model từ: {MODEL_PATH}")
        if not os.path.exists(MODEL_PATH):
            raise FileNotFoundError(f"Model file not found: {MODEL_PATH}")
        print(f"Model file size: {os.path.getsize(MODEL_PATH)} bytes")

        self.interpreter = tflite.Interpreter(model_path=MODEL_PATH, num_threads=2)
        self.interpreter.allocate_tensors()
        self.input_details  = self.interpreter.get_input_details()
        self.output_details = self.interpreter.get_output_details()

        try:
            id0 = self.input_details[0]
            od0 = self.output_details[0]
            print(f"TFLite input shape={id0['shape']} dtype={id0['dtype']}")
            print(f"TFLite output shape={od0['shape']} dtype={od0.get('dtype','unknown')}")
            self.input_dtype = np.dtype(id0['dtype'])
            shape = id0['shape']
            if len(shape) == 4:
                _, h, w, c = shape
            elif len(shape) == 3:
                h, w, c = shape
            else:
                h = w = IMGSZ
            self.model_in_w = int(w)
            self.model_in_h = int(h)
            print(f"Model expects input (w,h) = ({self.model_in_w},{self.model_in_h})")
        except Exception:
            self.input_dtype = np.float32
            self.model_in_w  = IMGSZ
            self.model_in_h  = IMGSZ
        print("Model loaded OK!")

    # def run(self):
    #     cmd = [
    #         "rpicam-vid",
    #         "--width",     str(WIDTH),
    #         "--height",    str(HEIGHT),
    #         "--framerate", str(FPS),
    #         "--codec",     "mjpeg",
    #         "--output",    "-",
    #         "--timeout",   "0",
    #         "--nopreview",
    #         "--flush",
    #     ]

    #     print("Khởi động rpicam-vid (mjpeg)...")
    #     proc = subprocess.Popen(cmd, stdout=subprocess.PIPE,
    #                             stderr=subprocess.DEVNULL, bufsize=0)
    #     print("Camera OK, bắt đầu inference...")

    #     buf = b""
    #     while self.running:
    #         chunk = proc.stdout.read(65536)
    #         if not chunk:
    #             time.sleep(0.01)
    #             continue
    #         buf += chunk

    #         last_start = buf.rfind(b'\xff\xd8')
    #         last_end   = buf.rfind(b'\xff\xd9')

    #         if last_start != -1 and last_end != -1 and last_end > last_start:
    #             jpg = buf[last_start:last_end + 2]
    #             buf = buf[last_end + 2:]

    #             frame = cv2.imdecode(np.frombuffer(jpg, dtype=np.uint8), cv2.IMREAD_COLOR)
    #             if frame is None:
    #                 continue

    #             self._frame_count += 1
    #             if self._frame_count % 3 == 0:
    #                 frame = self._detect(frame)
    #                 self._last_frame = frame
    #             elif self._last_frame is not None:
    #                 frame = self._last_frame

    #             self.buffer.write(frame)

    #     proc.terminate()
    #     proc.wait()
    def run(self):
        print("Khởi động webcam (cv2.VideoCapture)...")
        
        cap = cv2.VideoCapture(1)  # 0 = webcam đầu tiên, đổi thành 1, 2... nếu có nhiều cam
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, WIDTH)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, HEIGHT)
        cap.set(cv2.CAP_PROP_FPS, FPS)

        if not cap.isOpened():
            print("❌ Không mở được webcam!")
            return

        print("Webcam OK, bắt đầu inference...")

        while self.running:
            ret, frame = cap.read()
            if not ret or frame is None:
                print("⚠️ Không đọc được frame, thử lại...")
                time.sleep(0.05)
                continue

            self._frame_count += 1
            if self._frame_count % 3 == 0:
                frame = self._detect(frame)
                self._last_frame = frame
            elif self._last_frame is not None:
                frame = self._last_frame

            self.buffer.write(frame)

        cap.release()
    def _preprocess(self, frame):
        target_w = getattr(self, 'model_in_w', IMGSZ)
        target_h = getattr(self, 'model_in_h', IMGSZ)
        img = cv2.resize(frame, (target_w, target_h))
        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        if hasattr(self, 'input_dtype') and self.input_dtype == np.float32:
            img = img.astype(np.float32) / 255.0
        else:
            img = img.astype(self.input_dtype)
        return np.expand_dims(img, 0)

    def _postprocess(self, output, orig_w, orig_h):
        preds = np.squeeze(output).T
        boxes, scores, classes = [], [], []

        for pred in preds:
            cx, cy, w, h, cls0, cls1 = pred
            cls_id = int(np.argmax([cls0, cls1]))
            conf   = float(max(cls0, cls1))
            if conf < CONF_THRESH:
                continue
            x1 = float((cx - w / 2) * orig_w)
            y1 = float((cy - h / 2) * orig_h)
            x2 = float((cx + w / 2) * orig_w)
            y2 = float((cy + h / 2) * orig_h)
            x1, y1 = max(0.0, x1), max(0.0, y1)
            x2, y2 = min(float(orig_w), x2), min(float(orig_h), y2)
            if x2 <= x1 or y2 <= y1:
                continue
            boxes.append([x1, y1, x2, y2])
            scores.append(conf)
            classes.append(cls_id)

        if not boxes:
            return []

        boxes   = np.array(boxes)
        scores  = np.array(scores)
        classes = np.array(classes)

        def nms_indices(b, s, iou_thres=0.45):
            x1, y1, x2, y2 = b[:, 0], b[:, 1], b[:, 2], b[:, 3]
            areas = (x2 - x1) * (y2 - y1)
            order = s.argsort()[::-1]
            keep  = []
            while order.size > 0:
                i = order[0]
                keep.append(i)
                if order.size == 1:
                    break
                rest = order[1:]
                iou  = (np.maximum(0, np.minimum(x2[i], x2[rest]) - np.maximum(x1[i], x1[rest])) *
                        np.maximum(0, np.minimum(y2[i], y2[rest]) - np.maximum(y1[i], y1[rest]))) / \
                       (areas[i] + areas[rest] - (np.maximum(0, np.minimum(x2[i], x2[rest]) - np.maximum(x1[i], x1[rest])) *
                        np.maximum(0, np.minimum(y2[i], y2[rest]) - np.maximum(y1[i], y1[rest]))) + 1e-8)
                order = order[1:][iou <= iou_thres]
            return keep

        results = []
        for cls in np.unique(classes):
            idxs      = np.where(classes == cls)[0]
            keep      = nms_indices(boxes[idxs], scores[idxs])
            for k in keep[:50]:
                i = idxs[k]
                x1, y1, x2, y2 = boxes[i].astype(int)
                results.append((x1, y1, x2, y2, float(scores[i]), int(classes[i])))

        results.sort(key=lambda x: x[4], reverse=True)
        return results

    def _detect(self, frame):
        orig_h, orig_w = frame.shape[:2]
        tensor = self._preprocess(frame)
        try:
            self.interpreter.set_tensor(self.input_details[0]["index"], tensor)
            self.interpreter.invoke()
            output = self.interpreter.get_tensor(self.output_details[0]["index"])
            if not self._model_logged:
                print(f"model output shape: {output.shape}")
                self._model_logged = True
        except Exception as e:
            print(f"Inference error: {e}")
            return frame
        fire_detected = False
        detections = self._postprocess(output, orig_w, orig_h)
        for x1, y1, x2, y2, conf, cls_id in detections:
            label = NAMES.get(cls_id, str(cls_id))
            if label == "fire":
                fire_detected = True
            color = (0, 0, 255) if label == "fire" else (0, 140, 255)
            cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
            cv2.putText(frame, f"{label} {conf:.2f}",
                        (x1, max(12, y1 - 8)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
                        
        current_time = time.time()
  
        if fire_detected:
            self.fire_count += 1
            self.last_fire_time = current_time
            print(f"🔥 Fire detected! Count: {self.fire_count}")
            if self.fire_count >= 100:
                print("⚠️  Fire count threshold reached, activating GPIO!")
                if not self.published:
                    mqtt.publish_detected_fire_warning(2, float(detections[0][4]))
                    control_gpio.control_buzzer(True)
                    self.published = True
        else:
            if self.fire_count > 0 and current_time - self.last_fire_time > 3:
                print("✅ No fire detected for 5 seconds, resetting count and deactivating GPIO.")
                self.fire_count = 0
                control_gpio.control_buzzer(False)
                self.published = False
        if detections and not getattr(self, '_debug_saved', False):
            try:
                cv2.imwrite('/home/pi/debug_detect.jpg', frame)
                print("Saved debug image: /home/pi/debug_detect.jpg")
                self._debug_saved = True
            except Exception as e:
                print(f"Failed saving debug image: {e}")

        cv2.putText(frame, time.strftime("%Y-%m-%d %H:%M:%S"),
                    (8, orig_h - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (200, 200, 200), 1)
        return frame

    def stop(self):
        self.running = False


class StreamPushThread(Thread):
    def __init__(self, buffer: FrameBuffer):
        super().__init__(daemon=True)
        self.buffer   = buffer
        self.running  = True
        self.proc     = None
        self._lock    = threading.Lock()  # ✅ thêm lock

    def _start_ffmpeg(self):
        with self._lock:  # ✅ lock khi thay proc
            # Kill process cũ
            if self.proc is not None:
                try:
                    self.proc.stdin.close()
                except Exception:
                    pass
                try:
                    self.proc.terminate()
                    self.proc.wait(timeout=3)
                except Exception:
                    self.proc.kill()
                self.proc = None

            cmd = [
                "ffmpeg",
                "-loglevel", "warning",
                "-f", "rawvideo",
                "-pix_fmt", "bgr24",
                "-s", f"{WIDTH}x{HEIGHT}",
                "-r", str(FPS),
                "-i", "pipe:0",
                "-c:v", "libx264",
                "-preset", "ultrafast",
                "-tune", "zerolatency",
                "-b:v", "800k",
                "-pix_fmt", "yuv420p",
                "-g", str(FPS * 2),
                "-f", "rtsp",
                "-rtsp_transport", "tcp",
                REMOTE_RTSP_URL,
            ]
            print(f"▶ ffmpeg push → {REMOTE_RTSP_URL}")
            self.proc = subprocess.Popen(cmd, stdin=subprocess.PIPE,
                                         stderr=subprocess.PIPE)
            threading.Thread(target=self._drain_stderr, args=(self.proc,), daemon=True).start()

    def run(self):
        self._start_ffmpeg()
        interval = 1.0 / FPS

        while self.running:
            t0 = time.time()

            # Kiểm tra ffmpeg còn sống không
            if self.proc is None or self.proc.poll() is not None:
                print("[ffmpeg] process died, restarting in 3s...")
                time.sleep(3)
                self._start_ffmpeg()
                continue

            frame = self.buffer.read()
            if frame is None:
                time.sleep(interval)
                continue

            if frame.shape[1] != WIDTH or frame.shape[0] != HEIGHT:
                frame = cv2.resize(frame, (WIDTH, HEIGHT))

            with self._lock:  # ✅ lock khi write
                try:
                    if self.proc and self.proc.poll() is None:
                        self.proc.stdin.write(frame.tobytes())
                        self.proc.stdin.flush()
                except (BrokenPipeError, OSError):
                    print("[ffmpeg] pipe broken, restarting...")
                    # _start_ffmpeg sẽ được gọi ở vòng lặp tiếp theo
                    self.proc = None

            elapsed = time.time() - t0
            sleep = interval - elapsed
            if sleep > 0:
                time.sleep(sleep)

    def stop(self):
        self.running = False
        with self._lock:
            if self.proc:
                try:
                    self.proc.stdin.close()
                except Exception:
                    pass
                self.proc.terminate()
                self.proc.wait()
    def _drain_stderr(self, proc):
        try:
            for line in proc.stderr:
                decoded = line.decode(errors="replace").strip()
                if decoded:
                    print(f"[ffmpeg stderr] {decoded}")
        except Exception:
            pass
    def _wait_for_network(self, host: str, port: int = 8554, timeout: int = 30) -> bool:
        import socket
        print(f"⏳ Waiting for network to reach {host}:{port}...")
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                with socket.create_connection((host, port), timeout=2):
                    print(f"✅ Network reachable: {host}:{port}")
                    return True
            except (OSError, socket.timeout):
                time.sleep(2)
        print(f"❌ Network unreachable after {timeout}s")
        return False
    

_streamer: StreamPushThread = None

def restart_stream():
    """Gọi từ setup_wifi sau khi đổi WiFi xong."""
    global _streamer
    
    # ✅ Debug: in trạng thái _streamer
    print(f"[restart_stream] _streamer={_streamer}, alive={_streamer.is_alive() if _streamer else 'N/A'}")
    
    if _streamer is None or not _streamer.is_alive():
        print("⚠️  Streamer not running, cannot restart")
        return

    print("🔄 Killing old ffmpeg proc...")
    with _streamer._lock:
        if _streamer.proc is not None:
            try:
                _streamer.proc.stdin.close()
            except Exception:
                pass
            try:
                _streamer.proc.terminate()
            except Exception:
                pass
            _streamer.proc = None
        else:
            print("[restart_stream] proc was already None")

    # ✅ Chạy wait + restart trong thread riêng, không block BLE callback
def _do_restart():
    print(f"[restart_stream] waiting for network {REMOTE_RTSP_HOST}:{REMOTE_RTSP_PORT}...")
    ok = _streamer._wait_for_network(REMOTE_RTSP_HOST, int(REMOTE_RTSP_PORT), timeout=30)
    if ok:
        print("✅ Network ready, ffmpeg will restart via run() loop")
    else:
        print("❌ Network not ready after 30s")

threading.Thread(target=_do_restart, daemon=True).start()

def start_stream():
    """Bắt đầu push stream lên RTSP server. Camera/detection vẫn chạy bình thường."""
    global _streamer, _buffer  # cần expose _buffer ra global trong main()

    if _streamer is not None and _streamer.is_alive():
        print("⚠️  Stream đang chạy rồi, không cần start lại.")
        return

    if _buffer is None:
        print("❌ Buffer chưa sẵn sàng, hãy chắc chắn camera đã khởi động.")
        return

    print("▶ Bắt đầu stream lên RTSP...")
    _streamer = StreamPushThread(_buffer)
    _streamer.start()
    print(f"✅ Stream started → {REMOTE_RTSP_URL}")


def stop_stream():
    """Dừng push stream lên RTSP server. Camera và fire detection KHÔNG bị ảnh hưởng."""
    global _streamer

    if _streamer is None or not _streamer.is_alive():
        print("⚠️  Stream không chạy, không cần stop.")
        return

    print("⏹ Dừng stream...")
    _streamer.stop()
    _streamer.join(timeout=5)
    _streamer = None
    print("✅ Stream stopped. Camera vẫn đang detect fire bình thường.")
_streamer: StreamPushThread = None
_buffer: FrameBuffer = None   
def main():
    global _streamer, _buffer
    Gst.init(None)

    buffer  = FrameBuffer()
    _buffer = buffer
    capture = CaptureThread(buffer)
    capture.start()

    print("Đợi camera khởi động...")
    start = time.time()
    while buffer.read() is None:
        if time.time() - start > 15:
            print("Camera không khởi động được!")
            capture.stop()
            return
        time.sleep(0.1)

    print(f"\n✓ Camera OK! Bắt đầu push lên {REMOTE_RTSP_URL}")
    # streamer = StreamPushThread(buffer)
    # _streamer = streamer
    # streamer.start()
    start_stream()

    print(f"\n📡 Để xem stream, dùng:")
    print(f"   VLC: vlc {REMOTE_RTSP_URL} --network-caching=500")
    print(f"   ffplay: ffplay -fflags nobuffer {REMOTE_RTSP_URL}\n")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nDừng...")
        capture.stop()
        streamer.stop()
        capture.join()
        streamer.join()
        capture.release()
        print("Done.")


if __name__ == "__main__":
    main()