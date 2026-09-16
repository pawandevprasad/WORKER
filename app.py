import os
import io
import requests
import numpy as np
import cv2
import cloudinary
import cloudinary.uploader
import cloudinary.api
from flask import Flask, render_template, request, jsonify

app = Flask(__name__)

cloudinary.config(
    cloud_name=os.environ.get('CLOUDINARY_CLOUD_NAME'),
    api_key=os.environ.get('CLOUDINARY_API_KEY'),
    api_secret=os.environ.get('CLOUDINARY_API_SECRET'),
    secure=True
)

def auto_detect_and_inpaint_watermark(image_bytes):
    nparr = np.frombuffer(image_bytes, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    h, w = img.shape[:2]

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    thresh = cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 11, 2
    )

    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (15, 5))
    dilated = cv2.dilate(thresh, kernel, iterations=2)

    contours, _ = cv2.findContours(dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    mask = np.zeros((h, w), dtype=np.uint8)
    found_any = False

    for cnt in contours:
        x, y, cw, ch = cv2.boundingRect(cnt)
        aspect_ratio = cw / float(ch)
        
        if cw > 40 and ch > 10 and aspect_ratio > 1.5 and cw < w * 0.8:
            px = int(cw * 0.1)
            py = int(ch * 0.15)
            x1, y1 = max(0, x - px), max(0, y - py)
            x2, y2 = min(w, x + cw + px), min(h, y + ch + py)
            cv2.rectangle(mask, (x1, y1), (x2, y2), 255, -1)
            found_any = True

    if not found_any:
        cv2.rectangle(mask, (int(w * 0.25), int(h * 0.35)), (int(w * 0.75), int(h * 0.65)), 255, -1)
        cv2.rectangle(mask, (0, 0), (int(w * 0.35), int(h * 0.25)), 255, -1)

    cleaned_img = cv2.inpaint(img, mask, inpaintRadius=5, flags=cv2.INPAINT_TELEA)
    is_success, buffer = cv2.imencode(".jpg", cleaned_img, [cv2.IMWRITE_JPEG_QUALITY, 95])
    return buffer.tobytes()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/clean-batch', methods=['POST'])
def clean_batch():
    try:
        data = request.json or {}
        next_cursor = data.get('next_cursor', None)

        params = {"type": "upload", "resource_type": "image", "max_results": 20}
        if next_cursor:
            params["next_cursor"] = next_cursor

        res = cloudinary.api.resources(**params)
        resources = res.get('resources', [])
        new_cursor = res.get('next_cursor', None)

        processed_count = 0
        for item in resources:
            pid = item['public_id']
            img_url = item['secure_url']
            
            resp = requests.get(img_url)
            if resp.status_code == 200:
                cleaned_bytes = auto_detect_and_inpaint_watermark(resp.content)
                cloudinary.uploader.upload(
                    cleaned_bytes,
                    public_id=pid,
                    overwrite=True,
                    invalidate=True
                )
                processed_count += 1

        return jsonify({
            "success": True,
            "processed_count": processed_count,
            "next_cursor": new_cursor,
            "is_complete": new_cursor is None
        })

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
    
