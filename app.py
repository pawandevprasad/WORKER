import os
import io
import requests
import numpy as np
import cv2
import easyocr
import cloudinary
import cloudinary.uploader
import cloudinary.api
from flask import Flask, render_template, request, jsonify

app = Flask(__name__)

# Cloudinary Setup using Environment Variables
cloudinary.config(
    cloud_name=os.environ.get('CLOUDINARY_CLOUD_NAME'),
    api_key=os.environ.get('CLOUDINARY_API_KEY'),
    api_secret=os.environ.get('CLOUDINARY_API_SECRET'),
    secure=True
)

# AI OCR Model initialize karein (Target text 'EstateX' detect karne ke liye)
print("Loading AI Text Detection Model...")
ocr_reader = easyocr.Reader(['en'], gpu=False)
print("AI Model Loaded Successfully!")

def auto_detect_and_remove_watermark(image_bytes, target_text="EstateX"):
    # 1. Byte stream se image decode karein
    nparr = np.frombuffer(image_bytes, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    h, w = img.shape[:2]

    mask = np.zeros((h, w), dtype=np.uint8)

    # 2. AI Scanning: Image ko top to bottom text ke liye scan karein
    results = ocr_reader.readtext(img)
    found_watermark = False

    for (bbox, text, prob) in results:
        cleaned_text = text.replace(" ", "").strip().lower()
        search_target = target_text.replace(" ", "").strip().lower()

        # Agar text me 'estatex' mila (transparent/light sabhi type)
        if search_target in cleaned_text or cleaned_text in search_target:
            found_watermark = True
            pts = np.array(bbox, np.int32)
            rect_x, rect_y, rect_w, rect_h = cv2.boundingRect(pts)
            
            # Text edges ke aas-paas thoda padding/buffer add karein
            pad_x = int(rect_w * 0.15)
            pad_y = int(rect_h * 0.20)
            
            x1 = max(0, rect_x - pad_x)
            y1 = max(0, rect_y - pad_y)
            x2 = min(w, rect_x + rect_w + pad_x)
            y2 = min(h, rect_y + rect_h + pad_y)

            # Auto mask generate karein
            cv2.rectangle(mask, (x1, y1), (x2, y2), 255, -1)

    # Fallback: Agar text bilkul transparent hone ki wajah se OCR miss kare, toh center area target hoga
    if not found_watermark:
        cv2.rectangle(mask, (int(w * 0.25), int(h * 0.35)), (int(w * 0.75), int(h * 0.65)), 255, -1)

    # 3. Smart Inpainting (Aas-paas ke background colors se transparent text ko erase/fill karein)
    cleaned_img = cv2.inpaint(img, mask, inpaintRadius=7, flags=cv2.INPAINT_TELEA)

    # Output to JPEG Bytes
    is_success, buffer = cv2.imencode(".jpg", cleaned_img, [cv2.IMWRITE_JPEG_QUALITY, 95])
    return buffer.tobytes()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/clean-all-auto', methods=['POST'])
def clean_all_auto():
    try:
        data = request.json or {}
        target_text = data.get('target_text', 'EstateX')

        # Pagination logic: Cloudinary account ke SABHI images fetch karein
        resources = []
        next_cursor = None
        
        while True:
            params = {"type": "upload", "resource_type": "image", "max_results": 500}
            if next_cursor:
                params["next_cursor"] = next_cursor
                
            res = cloudinary.api.resources(**params)
            resources.extend(res.get('resources', []))
            next_cursor = res.get('next_cursor')
            if not next_cursor:
                break

        total_images = len(resources)
        cleaned_count = 0

        # Loop over every single image in Cloudinary
        for item in resources:
            pid = item['public_id']
            img_url = item['secure_url']
            
            resp = requests.get(img_url)
            if resp.status_code == 200:
                cleaned_bytes = auto_detect_and_remove_watermark(resp.content, target_text=target_text)
                
                # Cloudinary overwrite - EXACT SAME PUBLIC_ID (URLs bilkul SAME rahenge)
                cloudinary.uploader.upload(
                    cleaned_bytes,
                    public_id=pid,
                    overwrite=True,
                    invalidate=True  # Instant CDN Cache clear
                )
                cleaned_count += 1

        return jsonify({
            "success": True,
            "message": f"Kamyabi! Account ki kul {total_images} images me se '{target_text}' watermark AI dwara auto-remove ho gaya hai."
        })

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
            
