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

        # Apply adaptive thresholding with optimized parameters
        binary = cv2.adaptiveThreshold(
            gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 15, 2
        )

        # Enhanced denoising
        denoised = cv2.fastNlMeansDenoising(binary, None, 10, 7, 21)

        # Increase contrast with optimized parameters
        clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(16,16))
        enhanced = clahe.apply(denoised)

        # Morphological operations for better text clarity
        kernel = np.ones((2,2), np.uint8)
        enhanced = cv2.morphologyEx(enhanced, cv2.MORPH_CLOSE, kernel)
        enhanced = cv2.morphologyEx(enhanced, cv2.MORPH_OPEN, kernel)

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

    # Enhanced list of Italian and English terms for each type
    gas_terms = [
        'gas', 'cubic meter', 'm³', 'mc', 'metano', 'consumo gas',
        'lettura gas', 'fornitura gas', 'gas naturale', 'smc', 'standard m³',
        'metri cubi', 'metro cubo', 'materia gas', 'importi gas',
        'consumi gas', 'bolletta gas', 'gas naturale', 'riepilogo gas',
        'spesa materia gas', 'consumo metri cubi', 'prelievo gas',
        'costo gas', 'tariffa gas', 'spesa gas', 'quota gas',
        'valore gas', 'volume gas', 'gas consumato', 'componente gas'
    ]
    electricity_terms = [
        'electricity', 'electric', 'kw', 'kwh', 'kilowatt',
        'energia elettrica', 'consumo energia', 'luce', 'elettricità',
        'potenza', 'lettura energia', 'energia', 'corrente elettrica',
        'materia energia', 'importi energia', 'riepilogo energia',
        'spesa energia', 'f1', 'f2', 'f3', 'fascia oraria',
        'consumo elettrico', 'costo energia', 'tariffa energia',
        'spesa energia', 'quota energia', 'potenza impegnata',
        'energia attiva', 'energia reattiva', 'lettura elettrica'
    ]

    # Count occurrences of terms with context
    gas_count = 0
    electricity_count = 0

    # Analyze each line separately for better context
    lines = text.split('\n')
    for line in lines:
        # Check for gas terms
        if any(term in line for term in gas_terms):
            gas_count += 1
            logging.debug(f"Found gas term in line: {line}")

        # Check for electricity terms
        if any(term in line for term in electricity_terms):
            electricity_count += 1
            logging.debug(f"Found electricity term in line: {line}")

    # Log detailed findings
    logging.debug(f"Gas terms found: {gas_count}")
    logging.debug(f"Found gas terms: {[term for term in gas_terms if term in text]}")
    logging.debug(f"Electricity terms found: {electricity_count}")
    logging.debug(f"Found electricity terms: {[term for term in electricity_terms if term in text]}")

    # Enhanced decision logic
    if gas_count > 0 and electricity_count > 0:
        logging.info("Detected bill type: MIX (contains both gas and electricity terms)")
        return 'MIX'
    elif gas_count > 0:
        logging.info("Detected bill type: GAS")
        return 'GAS'
    elif electricity_count > 0:
        logging.info("Detected bill type: LUCE")
        return 'LUCE'

    logging.warning("Could not determine bill type")
    logging.debug(f"Full text analyzed: {text}")
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
                images = convert_from_path(file_path, dpi=400, first_page=1, last_page=3)
                if not images:
                    logging.error("Failed to convert PDF to image")
                    return None, None

                # Process multiple pages if available
                text = ""
                for page_num, image in enumerate(images, 1):
                    logging.info(f"Processing page {page_num}")
                    processed_image = preprocess_image(image)
                    if processed_image is None:
                        continue

                    # Configure tesseract for better accuracy
                    custom_config = f'--oem 3 --psm 6 -l ita+eng'
                    page_text = pytesseract.image_to_string(processed_image, config=custom_config)
                    text += page_text + "\n"

                if not text.strip():
                    logging.error("No text extracted from any page")
                    return None, None

            except Exception as e:
                logging.exception("Error processing PDF")
                return None, None
        else:
            try:
                logging.info("Opening image file")
                image = Image.open(file_path)
                if image.mode != 'RGB':
                    image = image.convert('RGB')
                processed_image = preprocess_image(image)
                if processed_image is None:
                    return None, None

                custom_config = '--oem 3 --psm 6 -l ita+eng'
                text = pytesseract.image_to_string(processed_image, config=custom_config)

            except Exception as e:
                logging.exception("Error processing image")
                return None, None

        # Extract information with enhanced logging
        try:
            logging.info("Extracting information from OCR text")
            logging.debug(f"Extracted text length: {len(text)}")
            logging.debug(f"First 500 characters: {text[:500]}")

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