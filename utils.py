import re
import logging
import os
import cv2
import numpy as np
from PIL import Image
import pytesseract
from pdf2image import convert_from_path

def preprocess_image(image):
    """
    Pre-process the image to improve OCR accuracy with enhanced number detection
    """
    logging.info("Starting image pre-processing")
    try:
        # Convert PIL Image to cv2 format
        if isinstance(image, Image.Image):
            image = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)

        # Convert to grayscale
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

        # Apply adaptive thresholding
        binary = cv2.adaptiveThreshold(
            gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2
        )

        # Noise removal with different kernel sizes
        denoised = cv2.fastNlMeansDenoising(binary)

        # Increase contrast
        clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8,8))
        enhanced = clahe.apply(denoised)

        # Morphological operations to improve text clarity
        kernel = np.ones((1,1), np.uint8)
        enhanced = cv2.morphologyEx(enhanced, cv2.MORPH_CLOSE, kernel)

        # Convert back to PIL Image
        enhanced_pil = Image.fromarray(enhanced)

        logging.info("Image pre-processing completed successfully")
        return enhanced_pil
    except Exception as e:
        logging.exception("Error during image pre-processing")
        return None

def extract_cost_per_unit(text):
    """Extract cost per unit from OCR text with improved pattern matching"""
    logging.debug("Extracting cost per unit from text")
    if not text:
        logging.error("Empty text provided to extract_cost_per_unit")
        return None

    # Enhanced patterns for cost extraction
    patterns = [
        # Standard format with currency
        r'(?:€|EUR)?\s*(\d+[.,]\d*)\s*(?:\/|\s+per\s+)?\s*(?:kw|kwh|m³|mc)',
        # Format without currency
        r'(\d+[.,]\d*)\s*(?:\/|\s+per\s+)?\s*(?:kw|kwh|m³|mc)',
        # Format with text description
        r'(?:costo|prezzo|tariffa)\s+(?:unitario|per)?\s+(?:€|EUR)?\s*(\d+[.,]\d*)',
        # Enel specific formats
        r'(?:prezzo energia|costo energia)\s*[F1-F3]?\s*(?:€|EUR)?\s*(\d+[.,]\d*)',
        r'(?:componente energia|quota energia)\s*(?:€|EUR)?\s*(\d+[.,]\d*)',
        # Additional number patterns near energy-related terms
        r'(?:fascia|F[1-3]|monorario)\s*(?:€|EUR)?\s*(\d+[.,]\d*)',
        r'energia\s+(?:attiva|reattiva)?\s*(?:€|EUR)?\s*(\d+[.,]\d*)'
    ]

    try:
        # Log the text being analyzed for debugging
        logging.debug("Text to analyze for cost:")
        for line in text.split('\n'):
            if any(term in line.lower() for term in ['€', 'eur', 'costo', 'prezzo', 'tariffa', 'energia']):
                logging.debug(f"Potential cost line: {line}")

        for pattern in patterns:
            matches = re.finditer(pattern, text, re.IGNORECASE)
            for match in matches:
                try:
                    cost = float(match.group(1).replace(',', '.').replace('€', ''))
                    if 0 < cost < 1000:  # Sanity check for reasonable cost range
                        logging.debug(f"Found valid cost: {cost} using pattern: {pattern}")
                        return cost
                    else:
                        logging.debug(f"Found cost outside reasonable range: {cost}")
                except ValueError:
                    continue

        logging.warning("No cost per unit found in text")
        logging.debug(f"Full text analyzed: {text}")
        return None
    except Exception as e:
        logging.exception(f"Error extracting cost per unit from text: {str(e)}")
        return None

def detect_bill_type(text):
    """Detect bill type from OCR text with improved keyword matching"""
    logging.debug("Detecting bill type from text")
    if not text:
        logging.error("Empty text provided to detect_bill_type")
        return 'UNKNOWN'

    text = text.lower()

    # Enhanced keyword sets for better detection
    gas_terms = [
        'gas', 'consumo gas', 'lettura gas', 'fornitura gas',
        'gas naturale', 'metano', 'm³', 'mc', 'metri cubi',
        'gas metano', 'consumo di gas', 'metro cubo',
        'consumi gas', 'contatore gas'
    ]
    electricity_terms = [
        'energia elettrica', 'consumo energia', 'luce', 'elettricità',
        'potenza', 'lettura energia', 'energia', 'corrente elettrica',
        'kw', 'kwh', 'kilowatt', 'consumo elettrico', 'contatore luce',
        'enel', 'eni luce', 'consumo di energia'
    ]

    # Count weighted occurrences (more specific terms have higher weight)
    gas_score = sum(2 if term in ['gas naturale', 'metano', 'consumo gas'] else 1 
                   for term in gas_terms if term in text)
    electricity_score = sum(2 if term in ['energia elettrica', 'consumo energia'] else 1 
                          for term in electricity_terms if term in text)

    logging.debug(f"Gas score: {gas_score}, terms found: {[t for t in gas_terms if t in text]}")
    logging.debug(f"Electricity score: {electricity_score}, terms found: {[t for t in electricity_terms if t in text]}")

    if gas_score > 0 and electricity_score > 0:
        logging.info("Detected bill type: MIX (both gas and electricity terms found)")
        return 'MIX'
    elif gas_score > 0:
        logging.info("Detected bill type: GAS")
        return 'GAS'
    elif electricity_score > 0:
        logging.info("Detected bill type: LUCE")
        return 'LUCE'

    logging.warning("Could not determine bill type")
    logging.debug(f"Text analyzed: {text[:200]}...")
    return 'UNKNOWN'

def process_bill_ocr(file_path):
    """Process bill file with OCR using improved image processing"""
    try:
        logging.info(f"Starting OCR processing for file: {file_path}")

        # Validate file
        if not os.path.exists(file_path):
            logging.error(f"File not found: {file_path}")
            return None, None

        if not os.access(file_path, os.R_OK):
            logging.error(f"File is not readable: {file_path}")
            return None, None

        file_size = os.path.getsize(file_path)
        logging.debug(f"Processing file of size: {file_size} bytes")

        # Process PDF or image
        if file_path.lower().endswith('.pdf'):
            try:
                logging.info("Converting PDF to image")
                # Increased DPI for better quality
                images = convert_from_path(file_path, dpi=300, first_page=1, last_page=1)
                if not images:
                    logging.error("Failed to convert PDF to image")
                    return None, None
                image = images[0]
                logging.info("PDF converted to image successfully")
            except Exception as e:
                logging.exception("Error converting PDF to image")
                return None, None
        else:
            try:
                logging.info("Opening image file")
                image = Image.open(file_path)
                if image.mode != 'RGB':
                    image = image.convert('RGB')
                logging.info(f"Image opened successfully: size={image.size}, mode={image.mode}")
            except Exception as e:
                logging.exception("Error opening image file")
                return None, None

        # Pre-process the image
        processed_image = preprocess_image(image)
        if processed_image is None:
            logging.error("Image pre-processing failed")
            return None, None

        # Perform OCR with multiple attempts
        try:
            logging.info("Starting OCR text extraction")

            # Configure tesseract for better accuracy
            custom_config = r'--oem 3 --psm 6'

            # Try different approaches
            text = None
            for psm in [6, 3, 4]:  # Different page segmentation modes
                try:
                    config = f'--oem 3 --psm {psm}'
                    current_text = pytesseract.image_to_string(processed_image, config=config)
                    if current_text.strip():
                        text = current_text
                        logging.info(f"Successful OCR with PSM {psm}")
                        break
                except Exception as e:
                    logging.warning(f"OCR attempt failed with PSM {psm}: {str(e)}")
                    continue

            if not text:
                logging.error("All OCR attempts failed")
                return None, None

            text_length = len(text)
            logging.info(f"OCR completed, extracted {text_length} characters")
            logging.debug(f"First 200 characters of extracted text: {text[:200]}")

        except Exception as e:
            logging.exception("Error during OCR processing")
            return None, None

        # Extract information
        try:
            cost_per_unit = extract_cost_per_unit(text)
            bill_type = detect_bill_type(text)

            logging.info(f"Information extracted - Cost per unit: {cost_per_unit}, Bill type: {bill_type}")
            return cost_per_unit, bill_type

        except Exception as e:
            logging.exception("Error extracting information from OCR text")
            return None, None

    except Exception as e:
        logging.exception(f"Unexpected error during OCR processing")
        return None, None