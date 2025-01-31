import os
import time
import requests
import cv2
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv

load_dotenv()

if not ("INSTANCE" in os.environ and "ACCESS_TOKEN" in os.environ):
    print("Please set the INSTANCE and ACCESS_TOKEN environment variables.")
    exit()

# Settings
INSTANCE = os.environ["INSTANCE"]
ACCESS_TOKEN = os.environ["ACCESS_TOKEN"]
INTERVAL = int(os.environ["INTERVAL"]) if "INTERVAL" in os.environ else 10800 # (3 hours)
VISIBILITY = os.environ["VISIBILITY"] if "VISIBILITY" in os.environ else "public"
HAAR_CASCADE = os.environ["HAAR_CASCADE"] if "HAAR_CASCADE" in os.environ else "haarcascade_frontalcatface_extended.xml"
DEBUG = bool(os.environ["DEBUG"]) if "DEBUG" in os.environ else False

# Do not modify
MC_ENDPOINT = "https://api.meow.camera/"
SCP_ENDPOINT = "http://streetcatpull.hellobike.com/live/"
NEXT_UPLOAD_FILENAME = "next_upload.txt"
FRONT = 0
TOP   = 1
BACK  = 2
FRAME_NUM = 1

# There is no summer time in China, so we can use a fixed timezone
cst = timezone(timedelta(hours=8))


# Device changes

def get_file_contents(filename: str):
    if DEBUG: print(f"[Log] Getting contents from {filename}")
    f = open(filename, "r+")
    contents = f.read()
    f.close()
    return contents

def put_file_contents(filename: str, contents: str):
    if DEBUG: print(f"[Log] Logging contents to {filename}")
    f = open(filename, "w+")
    f.write(contents)
    f.close()

def get_float_from_file(filename: str):
    try:
        date = float(get_file_contents(filename))
    except:
        if DEBUG: print("[Log] Unable to get float from file. Setting to None")
        date = None
    return date

def put_float_to_file(filename: str, timestamp: float):
    put_file_contents(filename, str(timestamp))


# Time

def get_current_local_time():
    return datetime.now(cst).strftime("%-I:%M:%S %p")

# Math

def get_module(num: int):
    return num * -1 if num < 0 else num


# Meow Camera

def get_random_cat_houses():
    url = MC_ENDPOINT + "catHouses/random"
    response = requests.get(url)
    return response.json()

def get_cat_house_info(id: str):
    url = MC_ENDPOINT + "catHouse/" + id
    response = requests.get(url)
    return response.json()

def get_cat_house_frame(id: str, position: str = FRONT):
    if DEBUG: print(f"[Log] Getting feed {SCP_ENDPOINT}{id}_{position}.m3u8")
    cap = cv2.VideoCapture(f"{SCP_ENDPOINT}{id}_{position}.m3u8", cv2.CAP_ANY)
    frame = None

    total_frames = get_module(int(cap.get(cv2.CAP_PROP_FRAME_COUNT)))
    print(f"Total frames: {total_frames}")

    if cap.isOpened():
        if total_frames != 0:
            # Sets frame number to be read
            cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            frame_read = cap.read()

            if frame_read[0]:
                frame = frame_read[1]
            elif DEBUG: print("[Error] Unable to read frame. Skipping to next cached camera")
        elif DEBUG: print("[Error] Frame number exceeds total frames. Skipping to next cached camera")
    elif DEBUG: print("[Error] Unable to open video stream. Skipping to next cached camera")
    
    cap.release()
    return frame

def encode_frame(frame: cv2.typing.MatLike):
    cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    return cv2.imencode(".png", frame)[1].tobytes()

def detect_on_frame(cascade_classifier: cv2.CascadeClassifier, frame: cv2.typing.MatLike):
    if DEBUG: print(f"[Log] Detecting elements on frame")
    img_gray = cv2.convertScaleAbs(frame, alpha=1.2, beta=0)
    img_gray = cv2.cvtColor(img_gray, cv2.COLOR_BGR2GRAY)
    found = cascade_classifier.detectMultiScale(img_gray)
    return found

def get_best_cat_house_image(cascade_classifier: cv2.CascadeClassifier, cat_house_id: str):
    POSITIONS = [BACK, FRONT]
    was_detected = False
    image = None
    i = 0

    while i < len(POSITIONS) - 1 and not was_detected:
        frame = get_cat_house_frame(cat_house_id, POSITIONS[i])
        if frame is not None:
            cats_detected = detect_on_frame(cascade_classifier, frame)
            was_detected = len(cats_detected) != 0
        i += 1

    if not was_detected:
        if DEBUG: print("[Log] No cats detected on others, switching to last position")
        frame = get_cat_house_frame(cat_house_id, POSITIONS[len(POSITIONS) - 1])

    if frame is not None:
        image = encode_frame(frame)
    return image


# Mastodon

def upload_media(file):
    url = "https://" + INSTANCE + "/api/v2/media"
    headers  = {"Authorization": "Bearer " + ACCESS_TOKEN}
    files = {"file": file}
    data = {"description": "Cat picture"}
    response = requests.post(url, headers=headers, files=files, data=data)
    return response.json()

def publish_post(cat_house_id: str, local_time: str, cat_house_info: dict, media: dict):
    url = "https://" + INSTANCE + "/api/v1/statuses"
    headers  = {"Authorization": "Bearer " + ACCESS_TOKEN}
    data = {
        "status":
            f"📷 {cat_house_info['englishName'] if cat_house_info['englishName'] is not None else cat_house_info['translatedName']}\n" +
            f"{'🥡 ' + cat_house_info['stock']['kibble'] + ' / ' if cat_house_info['stock']['kibble'] is not None else ''}" +
            f"{'🍗 ' + cat_house_info['stock']['snack'] + ' / ' if cat_house_info['stock']['snack'] is not None else ''}" +
            f"👁️ {cat_house_info['viewers']['local'] + cat_house_info['viewers']['jiemao'] + cat_house_info['viewers']['purrrr']}\n" +
            f"🕒 {local_time}\n" +
            f"https://meow.camera/#{cat_house_id}\n" +
            f"#bots #hellostreetcat #purrrr {'#mrfresh' if cat_house_id == '5144313095337151915' else ''} #caturday",
        "media_ids": [media["id"]],
        "visibility": VISIBILITY,
        "language": "en"
    }
    response = requests.post(url, headers=headers, json=data)
    if DEBUG: print("[Log] Post published")
    return response.json()


if __name__ == "__main__":
    next_upload = get_float_from_file(NEXT_UPLOAD_FILENAME)
    cascade_classifier = cv2.CascadeClassifier(HAAR_CASCADE)

    try:
        while True:
            if next_upload is None or datetime.timestamp(datetime.now()) >= next_upload:
                cat_houses = get_random_cat_houses()
                cat_houses_pos = 0
                cat_houses_len = len(cat_houses)
                
                image_loaded = False

                while not image_loaded:
                    try:
                        cat_house_id = cat_houses[cat_houses_pos]["id"]

                        image = get_best_cat_house_image(cascade_classifier, cat_house_id)
                        if image is not None:
                            local_time = get_current_local_time()
                            cat_house_info = get_cat_house_info(cat_house_id)
                            image_loaded = True
                    except Exception as e:
                        print(e)
                        exit()

                publish_post(cat_house_id, local_time, cat_house_info, upload_media(image))

                next_upload = datetime.timestamp(datetime.now()) + INTERVAL
                put_float_to_file(NEXT_UPLOAD_FILENAME, next_upload)
    except KeyboardInterrupt:
        print("Goodbye!")