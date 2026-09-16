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

# Cloudinary Setup (Environment Variables se credentials lega)
cloudinary.config(
    cloud_name=os.environ.get('CLOUDINARY_CLOUD_NAME'),
    api_key=os.environ.get('CLOUDINARY_API_KEY'),
    api_secret=os.environ.get('CLOUDINARY_API_SECRET'),
    secure=True
)

def remove_patches_and_inpaint(image_bytes, patch_x_pct=0, patch_y_pct=0, patch_w_pct=35, patch_h_pct=25):
    # Byte stream se image decode karein
    nparr = np.frombuffer(image_bytes, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    h, w = img.shape[:2]

    mask = np.zeros((h, w), dtype=np.uint8)

    # Percentage coordinates ko pixels me convert karein
    x1 = int((patch_x_pct / 100.0) * w)
    y1 = int((patch_y_pct / 100.0) * h)
    w_px = int((patch_w_pct / 100.0) * w)
    h_px = int((patch_h_pct / 100.0) * h)

    # White box region par mask lagayein
    cv2.rectangle(mask, (x1, y1), (x1 + w_px, y1 + h_px), 255, -1)

    # OpenCV Inpainting - Solid White Box ko aas-paas ke background se mix karke erase karega
    cleaned_img = cv2.inpaint(img, mask, inpaintRadius=7, flags=cv2.INPAINT_TELEA)

    # Save to Bytes
    is_success, buffer = cv2.imencode(".jpg", cleaned_img, [cv2.IMWRITE_JPEG_QUALITY, 95])
    return buffer.tobytes()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/resources', methods=['GET'])
def list_resources():
    try:
        result = cloudinary.api.resources(type="upload", resource_type="image", max_results=500)
        return jsonify({"success": True, "resources": result.get('resources', [])})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/clean-image', methods=['POST'])
def clean_single_image():
    try:
        data = request.json
        public_id = data.get('public_id')
        x_pct = float(data.get('x_pct', 0))
        y_pct = float(data.get('y_pct', 0))
        w_pct = float(data.get('w_pct', 35))
        h_pct = float(data.get('h_pct', 25))

        if not public_id:
            return jsonify({"success": False, "error": "Public ID is required"}), 400

        resource = cloudinary.api.resource(public_id)
        image_url = resource.get('secure_url')

        resp = requests.get(image_url)
        if resp.status_code != 200:
            return jsonify({"success": False, "error": "Failed to fetch image"}), 400

        cleaned_bytes = remove_patches_and_inpaint(resp.content, x_pct, y_pct, w_pct, h_pct)

        # Overwrite on Cloudinary using SAME public_id (URL CHANGE NAHI HOGA)
        upload_result = cloudinary.uploader.upload(
            cleaned_bytes,
            public_id=public_id,
            overwrite=True,
            invalidate=True  # Clear CDN cache instantly
        )

        return jsonify({
            "success": True,
            "message": "Image cleaned & restored successfully!",
            "url": upload_result.get('secure_url')
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/clean-all', methods=['POST'])
def clean_all_images():
    try:
        data = request.json
        x_pct = float(data.get('x_pct', 0))
        y_pct = float(data.get('y_pct', 0))
        w_pct = float(data.get('w_pct', 35))
        h_pct = float(data.get('h_pct', 25))

        result = cloudinary.api.resources(type="upload", resource_type="image", max_results=500)
        resources = result.get('resources', [])
        cleaned_count = 0

        for item in resources:
            pid = item['public_id']
            img_url = item['secure_url']
            resp = requests.get(img_url)
            if resp.status_code == 200:
                cleaned_bytes = remove_patches_and_inpaint(resp.content, x_pct, y_pct, w_pct, h_pct)
                cloudinary.uploader.upload(
                    cleaned_bytes,
                    public_id=pid,
                    overwrite=True,
                    invalidate=True
                )
                cleaned_count += 1

        return jsonify({
            "success": True,
            "message": f"Successfully cleaned {cleaned_count} images!"
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
        
