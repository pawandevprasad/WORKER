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

# Cloudinary Setup using Environment Variables
cloudinary.config(
    cloud_name=os.environ.get('CLOUDINARY_CLOUD_NAME'),
    api_key=os.environ.get('CLOUDINARY_API_KEY'),
    api_secret=os.environ.get('CLOUDINARY_API_SECRET'),
    secure=True
)

def auto_detect_and_inpaint_watermark(image_bytes):
    # Byte stream se image decode karein
    nparr = np.frombuffer(image_bytes, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    h, w = img.shape[:2]

    # Grayscale conversion for edge/contrast detection
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # Adaptive thresholding to detect text edges / watermark contrast
    thresh = cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 11, 2
    )

    # Morphological dilation to combine text characters into boxes
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (15, 5))
    dilated = cv2.dilate(thresh, kernel, iterations=2)

    # Contours find karein (Text regions detect karne ke liye)
    contours, _ = cv2.findContours(dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    mask = np.zeros((h, w), dtype=np.uint8)
    found_any = False

    for cnt in contours:
        x, y, cw, ch = cv2.boundingRect(cnt)
        aspect_ratio = cw / float(ch)
        
        # Text regions filter karein (Jaise 'EstateX' jaisa horizontal text)
        if cw > 40 and ch > 10 and aspect_ratio > 1.5 and cw < w * 0.8:
            px = int(cw * 0.1)
            py = int(ch * 0.15)
            x1 = max(0, x - px)
            y1 = max(0, y - py)
            x2 = min(w, x + cw + px)
            y2 = min(h, y + ch + py)
            
            cv2.rectangle(mask, (x1, y1), (x2, y2), 255, -1)
            found_any = True

    # Fallback: Center aur Top-Left area target karein (jahan watermark hote hain)
    if not found_any:
        cv2.rectangle(mask, (int(w * 0.25), int(h * 0.35)), (int(w * 0.75), int(h * 0.65)), 255, -1)
        cv2.rectangle(mask, (0, 0), (int(w * 0.35), int(h * 0.25)), 255, -1)

    # Inpaint Telea algorithm - Super fast & low RAM usage
    cleaned_img = cv2.inpaint(img, mask, inpaintRadius=5, flags=cv2.INPAINT_TELEA)

    # Encode back to JPEG bytes
    is_success, buffer = cv2.imencode(".jpg", cleaned_img, [cv2.IMWRITE_JPEG_QUALITY, 95])
    return buffer.tobytes()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/clean-all-auto', methods=['POST'])
def clean_all_auto():
    try:
        # Cloudinary ke SABHI images fetch karein (Pagination)
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

        for item in resources:
            pid = item['public_id']
            img_url = item['secure_url']
            
            resp = requests.get(img_url)
            if resp.status_code == 200:
                cleaned_bytes = auto_detect_and_inpaint_watermark(resp.content)
                
                # Cloudinary overwrite - SAME PUBLIC_ID (URLs bilkul SAME rahenge)
                cloudinary.uploader.upload(
                    cleaned_bytes,
                    public_id=pid,
                    overwrite=True,
                    invalidate=True
                )
                cleaned_count += 1

        return jsonify({
            "success": True,
            "message": f"Kamyabi! Account ki kul {total_images} images me se watermark auto-clean ho gaya hai."
        })

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
    
