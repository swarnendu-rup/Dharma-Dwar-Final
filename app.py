import cv2
import mediapipe as mp
import numpy as np
import threading
import time
import queue
import json
import sounddevice as sd
import serial
from flask import Flask, render_template_string, Response, jsonify
from vosk import Model, KaldiRecognizer

# =========================
# CONFIGURATION
# =========================
VOSK_MODEL_PATH = "models/vosk-model-small-en-us-0.15"
SERIAL_PORT = "COM3"  # UPDATE TO YOUR ARDUINO PORT
BAUD_RATE = 9600
CAMERA_INDEX = 0  # Change to 1 if you have multiple webcams

app = Flask(__name__)

# =========================
# GLOBAL STATES
# =========================
hand_status = "INITIALIZING..."
last_spoken_text = "LISTENING..."
door_state = "CLOSED"
audio_queue = queue.Queue()

# Setup Serial with Arduino
try:
    arduino = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1)
    time.sleep(2)
    print(f"✅ Dharma Dwar linked to Arduino on {SERIAL_PORT}")
except Exception as e:
    print(f"⚠️ Serial Connection Warning: {e}")
    arduino = None

# MediaPipe Initialization
mp_hands = mp.solutions.hands
mp_draw = mp.solutions.drawing_utils
hands = mp_hands.Hands(min_detection_confidence=0.7, min_tracking_confidence=0.7)

# Webcam Initialization (Global Fix for access issues)
cap = cv2.VideoCapture(CAMERA_INDEX, cv2.CAP_DSHOW)


# =========================
# SYSTEM LOGIC
# =========================

def run_door_cycle():
    global door_state
    if door_state != "CLOSED":
        return

    print(">>> ACCESS GRANTED: OPENING DHARMA DWAR")
    if arduino:
        arduino.write(b"OPEN\n")

    door_state = "OPENING"
    time.sleep(1)
    door_state = "GATE OPEN (5S)"
    time.sleep(5)
    door_state = "CLOSING"
    time.sleep(1)
    door_state = "CLOSED"


def audio_callback(indata, frames, time_info, status):
    if status: print(status)
    audio_queue.put(bytes(indata))


def speech_thread():
    global last_spoken_text
    try:
        model = Model(VOSK_MODEL_PATH)
        recognizer = KaldiRecognizer(model, 16000)
        with sd.RawInputStream(samplerate=16000, blocksize=8000, dtype="int16", channels=1, callback=audio_callback):
            while True:
                data = audio_queue.get()
                if recognizer.AcceptWaveform(data):
                    result = json.loads(recognizer.Result())
                    text = result.get("text", "").lower()
                    if text:
                        last_spoken_text = text
                        # COMBINATION CHECK
                        if "open the door" in text:
                            if hand_status == "CLOSED FIST":
                                threading.Thread(target=run_door_cycle).start()
                            else:
                                last_spoken_text = "[ERROR] Close Fist Mudra Required"
    except Exception as e:
        print(f"Voice Processor Error: {e}")


# =========================
# FLASK & CAMERA
# =========================

def generate_video_stream():
    global hand_status
    while True:
        success, frame = cap.read()
        if not success:
            break

        frame = cv2.flip(frame, 1)
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        result = hands.process(rgb)

        current_hand = "NO HAND"

        if result.multi_hand_landmarks:
            for hand_landmarks in result.multi_hand_landmarks:
                mp_draw.draw_landmarks(frame, hand_landmarks, mp_hands.HAND_CONNECTIONS)

                # Finger Logic for Closed Fist Detection
                tips = [8, 12, 16, 20]  # Index, Middle, Ring, Pinky Tips
                pips = [6, 10, 14, 18]  # Index, Middle, Ring, Pinky joints

                h, w, _ = frame.shape
                lm = [(int(p.x * w), int(p.y * h)) for p in hand_landmarks.landmark]

                fist_detected = True
                for t, p in zip(tips, pips):
                    if lm[t][1] < lm[p][1]:  # Tip higher than joint = Finger Open
                        fist_detected = False

                current_hand = "CLOSED FIST" if fist_detected else "OPEN HAND"

                # On-screen HUD color
                hud_color = (0, 0, 255) if fist_detected else (0, 255, 0)
                cv2.putText(frame, current_hand, (20, 60), cv2.FONT_HERSHEY_SIMPLEX, 1, hud_color, 2)

        hand_status = current_hand
        ret, buffer = cv2.imencode('.jpg', frame)
        yield (b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + buffer.tobytes() + b'\r\n')


@app.route('/')
def index():
    return render_template_string(HTML_PAGE)


@app.route('/video')
def video_feed():
    return Response(generate_video_stream(), mimetype='multipart/x-mixed-replace; boundary=frame')


@app.route('/status')
def get_status():
    return jsonify({
        'hand': hand_status,
        'voice': last_spoken_text,
        'door': door_state
    })


# =========================
# WEB UI (Your HTML Code)
# =========================
HTML_PAGE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Dharma Dwar – Celestial AI Gate</title>
    <link href="https://fonts.googleapis.com/css2?family=Cinzel+Decorative:wght@700&family=Orbitron:wght@400;700&family=Rajdhani:wght@300;500;700&display=swap" rel="stylesheet">
    <style>
        :root { --gold: #ffcc33; --saffron: #ff9933; --tech-blue: #00f2ff; --glow: 0 0 15px rgba(255, 204, 51, 0.5); }
        body {
            background: radial-gradient(circle at center, #1a0b2e 0%, #050505 100%);
            color: white; font-family: 'Rajdhani', sans-serif; margin: 0;
            display: flex; flex-direction: column; align-items: center; min-height: 100vh;
        }
        body::before {
            content: ""; position: fixed; top: 50%; left: 50%; width: 800px; height: 800px;
            background: url('https://www.transparenttextures.com/patterns/black-linen.png'), radial-gradient(circle, rgba(255, 153, 51, 0.05) 0%, transparent 70%);
            transform: translate(-50%, -50%); z-index: -1; border-radius: 50%; border: 1px solid rgba(255, 204, 51, 0.1);
            animation: rotateMandala 60s linear infinite;
        }
        @keyframes rotateMandala { from { transform: translate(-50%, -50%) rotate(0deg); } to { transform: translate(-50%, -50%) rotate(360deg); } }
        h1 { font-family: 'Cinzel Decorative', serif; font-size: 3.5rem; color: var(--gold); text-shadow: 0 0 20px rgba(255, 153, 51, 0.8); margin-top: 30px; letter-spacing: 5px; text-transform: uppercase; }
        h1 span { font-size: 1.2rem; display: block; font-family: 'Orbitron'; color: var(--tech-blue); letter-spacing: 10px; text-align: center;}
        .main-container { display: flex; flex-wrap: wrap; justify-content: center; gap: 40px; margin-top: 20px; padding: 20px; }
        .video-wrap { position: relative; border: 4px solid var(--gold); border-radius: 20px; overflow: hidden; background: #000; box-shadow: 0 0 30px rgba(0, 242, 255, 0.3); }
        img { display: block; filter: sepia(20%) hue-rotate(-15deg); }
        .card { width: 380px; background: rgba(11, 15, 26, 0.8); backdrop-filter: blur(15px); border: 2px solid var(--gold); border-radius: 20px; padding: 30px; }
        .stat { background: rgba(255, 255, 255, 0.05); margin: 15px 0; padding: 20px; border-left: 5px solid var(--saffron); border-radius: 8px; transition: 0.3s; }
        .stat b { display: block; color: var(--saffron); font-size: 0.8rem; text-transform: uppercase; }
        .stat span { font-size: 1.5rem; color: #fff; font-family: 'Orbitron'; text-shadow: 0 0 10px white; }
        .gate-status { margin-top: 30px; font-weight: bold; font-size: 1.8rem; color: var(--tech-blue); text-transform: uppercase; animation: pulse 2s infinite; text-align:center;}
        @keyframes pulse { 0% { opacity: 0.6; } 50% { opacity: 1; } 100% { opacity: 0.6; } }
    </style>
</head>
<body>
    <header><h1>Dharma Dwar <span>Celestial Gate OS v4.0</span></h1></header>
    <div class="main-container">
        <div class="video-wrap"><img src="/video" width="640" height="480"></div>
        <div class="card">
            <div class="stat"><b>🖐 Hasta Mudra Analysis</b><span><span id="hand_stat">WAITING...</span></span></div>
            <div class="stat"><b>🎤 Vaca Frequency (Voice)</b><span><span id="voice_stat">WAITING...</span></span></div>
            <div class="gate-status">
                <small style="font-size: 0.7rem; color: var(--gold); display: block;">GATE AUTHORITY</small>
                <div id="door_stat">CLOSED</div>
            </div>
            <p style="text-align:center; color: #666; margin-top: 20px;"><i>"Hold a fist and say 'Open the Door' to enter."</i></p>
        </div>
    </div>
    <script>
        function update() {
            fetch('/status').then(r => r.json()).then(data => {
                document.getElementById('hand_stat').innerText = data.hand;
                document.getElementById('voice_stat').innerText = data.voice;
                document.getElementById('door_stat').innerText = data.door;
                let ds = document.getElementById('door_stat');
                ds.style.color = (data.door === "CLOSED") ? "#ffcc33" : "#00f2ff";
            });
        }
        setInterval(update, 500);
    </script>
</body>
</html>
"""

if __name__ == '__main__':
    threading.Thread(target=speech_thread, daemon=True).start()
    # CRITICAL FIX: use_reloader=False prevents double-accessing camera
    app.run(debug=True, use_reloader=False, host='0.0.0.0', port=5000)
