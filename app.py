import os
import io
import requests
import cloudinary
import cloudinary.uploader
import cloudinary.api
from PIL import Image, ImageDraw, ImageFont
from flask import Flask, render_template, request, jsonify

app = Flask(__name__)

# Cloudinary Configuration (Environment variables se credentials lega)
cloudinary.config(
    cloud_name=os.environ.get('CLOUDINARY_CLOUD_NAME'),
    api_key=os.environ.get('CLOUDINARY_API_KEY'),
    api_secret=os.environ.get('CLOUDINARY_API_SECRET'),
    secure=True
)

def process_watermark_in_memory(image_bytes, x1, y1, width, height, new_text, bg_color="#FFFFFF", text_color="#000000", font_size=36):
    # Image memory me convert karein
    pil_img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    draw = ImageDraw.Draw(pil_img)
    
    x2 = x1 + width
    y2 = y1 + height
    
    # Hex color code ko RGB tuple me convert karein
    def hex_to_rgb(hex_str):
        hex_str = hex_str.lstrip('#')
        return tuple(int(hex_str[i:i+2], 16) for i in (0, 2, 4))

    bg_rgb = hex_to_rgb(bg_color)
    text_rgb = hex_to_rgb(text_color)
    
    # 1. Purane watermark 'EstateX' ke uper solid patch lagayein
    draw.rectangle([x1, y1, x2, y2], fill=bg_rgb)
    
    # 2. Font setup
    try:
        font = ImageFont.truetype("arial.ttf", font_size)
    except IOError:
        font = ImageFont.load_default()
        
    # 3. Naya watermark ('X') draw karein
    draw.text((x1 + 8, y1 + 5), new_text, fill=text_rgb, font=font)
    
    # Memory stream me output return karein
    buffer = io.BytesIO()
    pil_img.save(buffer, format="JPEG", quality=95)
    buffer.seek(0)
    return buffer.getvalue()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/resources', methods=['GET'])
def list_resources():
    try:
        # Cloudinary se images fetch karein
        result = cloudinary.api.resources(type="upload", resource_type="image", max_results=100)
        return jsonify({"success": True, "resources": result.get('resources', [])})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/process-image', methods=['POST'])
def process_single_image():
    try:
        data = request.json
        public_id = data.get('public_id')
        x1 = int(data.get('x1', 50))
        y1 = int(data.get('y1', 50))
        width = int(data.get('width', 160))
        height = int(data.get('height', 50))
        new_text = data.get('new_text', 'X')
        bg_color = data.get('bg_color', '#FFFFFF')
        text_color = data.get('text_color', '#000000')
        font_size = int(data.get('font_size', 36))

        if not public_id:
            return jsonify({"success": False, "error": "Public ID missing"}), 400

        # Original Image fetch karein Cloudinary URL se
        resource = cloudinary.api.resource(public_id)
        image_url = resource.get('secure_url')
        
        resp = requests.get(image_url)
        if resp.status_code != 200:
            return jsonify({"success": False, "error": "Image download failed"}), 400

        # In-memory watermark update
        processed_bytes = process_watermark_in_memory(
            resp.content, x1, y1, width, height, new_text, bg_color, text_color, font_size
        )

        # Cloudinary overwrite - EXACT SAME PUBLIC_ID (URL CHANGE NAHI HOGA)
        upload_result = cloudinary.uploader.upload(
            processed_bytes,
            public_id=public_id,
            overwrite=True,
            invalidate=True  # CDN cache clear karega taaki instant changes dikhein
        )

        return jsonify({
            "success": True, 
            "message": "Watermark successfully updated!",
            "url": upload_result.get('secure_url')
        })

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/process-all', methods=['POST'])
def process_all_images():
    try:
        data = request.json
        x1 = int(data.get('x1', 50))
        y1 = int(data.get('y1', 50))
        width = int(data.get('width', 160))
        height = int(data.get('height', 50))
        new_text = data.get('new_text', 'X')
        bg_color = data.get('bg_color', '#FFFFFF')
        text_color = data.get('text_color', '#000000')
        font_size = int(data.get('font_size', 36))

        result = cloudinary.api.resources(type="upload", resource_type="image", max_results=100)
        resources = result.get('resources', [])

        updated_count = 0
        for item in resources:
            pid = item['public_id']
            img_url = item['secure_url']
            resp = requests.get(img_url)
            if resp.status_code == 200:
                proc_bytes = process_watermark_in_memory(
                    resp.content, x1, y1, width, height, new_text, bg_color, text_color, font_size
                )
                cloudinary.uploader.upload(
                    proc_bytes,
                    public_id=pid,
                    overwrite=True,
                    invalidate=True
                )
                updated_count += 1

        return jsonify({"success": True, "message": f"{updated_count} Images process ho gayi hain!"})

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)

