# controllers/recognition_controller.py
from flask import Blueprint, request, jsonify
import pytesseract
from models import Student  # Import Student model

recognition_bp = Blueprint('recognition', __name__)

#@recognition_bp.route('/recognize', methods=['POST'])
#def recognize_license_plate():
    # Your image recognition route logic here...
