import os
from flask import Flask, render_template, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import DeclarativeBase
import logging
import json
from werkzeug.utils import secure_filename
import uuid

logging.basicConfig(level=logging.DEBUG)

class Base(DeclarativeBase):
    pass

db = SQLAlchemy(model_class=Base)
app = Flask(__name__)

app.secret_key = os.environ.get("FLASK_SECRET_KEY") or "a secret key"
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL")
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "pool_recycle": 300,
    "pool_pre_ping": True,
}
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024 * 10  # 160MB max-size (10 files * 16MB)
app.config["UPLOAD_FOLDER"] = "uploads"

# Ensure upload directory exists
if not os.path.exists(app.config["UPLOAD_FOLDER"]):
    os.makedirs(app.config["UPLOAD_FOLDER"])

db.init_app(app)

def save_file(file):
    """Save uploaded file and return the file path"""
    if file:
        # Generate unique filename to prevent collisions
        filename = secure_filename(file.filename)
        unique_filename = f"{uuid.uuid4()}_{filename}"
        file_path = os.path.join(app.config["UPLOAD_FOLDER"], unique_filename)
        file.save(file_path)
        return file_path
    return None

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/upload", methods=["POST"])
def upload():
    try:
        phone = request.form.get("phone")
        bill_types = json.loads(request.form.get("billTypes", "[]"))
        files = request.files.getlist("files[]")

        if not phone or not files:
            return jsonify({"error": "Missing required fields"}), 400

        if len(files) != len(bill_types):
            return jsonify({"error": "Mismatch between files and bill types"}), 400

        # Process each file
        saved_bills = []
        for file, bill_type in zip(files, bill_types):
            if file:
                # Save the file
                file_path = save_file(file)
                if file_path:
                    # Create new bill record
                    bill = models.Bill(
                        phone=phone,
                        bill_type=bill_type,
                        file_path=file_path,
                        # cost_per_unit will be updated after OCR processing
                    )
                    db.session.add(bill)
                    saved_bills.append(bill)

        # Commit all bills to database
        db.session.commit()

        # Return success response with bill IDs
        return jsonify({
            "success": True,
            "message": "Bills uploaded successfully",
            "bills": [bill.to_dict() for bill in saved_bills]
        })
    except Exception as e:
        logging.error(f"Upload error: {str(e)}")
        return jsonify({"error": "Upload failed"}), 500

with app.app_context():
    import models
    db.create_all()