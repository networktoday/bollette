import os
from flask import Flask, render_template, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import DeclarativeBase
import logging

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
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024  # 16MB max file size

db.init_app(app)

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/upload", methods=["POST"])
def upload():
    try:
        phone = request.form.get("phone")
        bill_type = request.form.get("billType")
        file = request.files.get("file")
        
        if not all([phone, bill_type, file]):
            return jsonify({"error": "Missing required fields"}), 400

        # Save file and process with OCR
        # In a real implementation, we'd save the file and process it
        
        return jsonify({
            "success": True,
            "message": "Bill uploaded successfully"
        })
    except Exception as e:
        logging.error(f"Upload error: {str(e)}")
        return jsonify({"error": "Upload failed"}), 500

with app.app_context():
    import models
    db.create_all()
