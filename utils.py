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

        # Apply advanced preprocessing techniques
        # 1. Noise reduction
        denoised = cv2.fastNlMeansDenoising(gray, None, 10, 7, 21)

        # 2. Adaptive thresholding with optimized parameters
        binary = cv2.adaptiveThreshold(
            denoised, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2
        )

        # 3. Enhanced contrast
        clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8,8))
        enhanced = clahe.apply(binary)

        # 4. Deskewing if needed
        coords = np.column_stack(np.where(enhanced > 0))
        angle = cv2.minAreaRect(coords)[-1]
        if angle < -45:
            angle = 90 + angle
        if abs(angle) > 0.5:  # Only rotate if skew is significant
            (h, w) = enhanced.shape[:2]
            center = (w // 2, h // 2)
            M = cv2.getRotationMatrix2D(center, angle, 1.0)
            enhanced = cv2.warpAffine(enhanced, M, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)

        # 5. Morphological operations for better text clarity
        kernel = np.ones((2,2), np.uint8)
        enhanced = cv2.morphologyEx(enhanced, cv2.MORPH_CLOSE, kernel)

        # Convert back to PIL Image
        enhanced_pil = Image.fromarray(enhanced)

        logging.info("Image pre-processing completed successfully")
        return enhanced_pil
    except Exception as e:
        logging.exception("Error during image pre-processing")
        raise RuntimeError(f"Failed to preprocess image: {str(e)}")

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
        r'(?:componente energia|quota energia)\s*(?:€|EUR)?\s*(\d+[.,]\d*)'
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
        'valore gas', 'volume gas', 'gas consumato', 'componente gas',
        'fornitura di gas', 'servizio gas', 'importo gas', 'letture gas'
    ]

    electricity_terms = [
        'electricity', 'electric', 'kw', 'kwh', 'kilowatt',
        'energia elettrica', 'consumo energia', 'luce', 'elettricità',
        'potenza', 'lettura energia', 'energia', 'corrente elettrica',
        'materia energia', 'importi energia', 'riepilogo energia',
        'spesa energia', 'f1', 'f2', 'f3', 'fascia oraria',
        'consumo elettrico', 'costo energia', 'tariffa energia',
        'spesa energia', 'quota energia', 'potenza impegnata',
        'energia attiva', 'energia reattiva', 'lettura elettrica',
        'servizi di rete', 'dispacciamento', 'fornitura elettrica',
        'potenza disponibile', 'potenza contrattualmente impegnata',
        'consumo fatturato', 'oneri di sistema', 'servizio elettrico'
    ]

    # Count occurrences of terms with improved context analysis
    gas_count = 0
    electricity_count = 0

    try:
        # Split text into sections for better context
        sections = text.split('\n\n')  # Split by double newline to get logical sections

        for section in sections:
            # Check for gas terms
            section_gas_terms = [term for term in gas_terms if term in section]
            if section_gas_terms:
                gas_count += len(section_gas_terms)
                logging.debug(f"Found gas terms in section: {section_gas_terms}")

            # Check for electricity terms
            section_electricity_terms = [term for term in electricity_terms if term in section]
            if section_electricity_terms:
                electricity_count += len(section_electricity_terms)
                logging.debug(f"Found electricity terms in section: {section_electricity_terms}")

        # Log detailed findings
        logging.info(f"Gas terms found: {gas_count}")
        logging.info(f"Electricity terms found: {electricity_count}")

        # Enhanced decision logic with weighted scoring
        if gas_count > 0 and electricity_count > 0:
            logging.info("Detected bill type: MIX (contains both gas and electricity terms)")
            return 'MIX'
        elif gas_count > electricity_count:
            logging.info("Detected bill type: GAS")
            return 'GAS'
        elif electricity_count > gas_count:
            logging.info("Detected bill type: LUCE")
            return 'LUCE'
        elif gas_count == 0 and electricity_count == 0:
            logging.warning("No relevant terms found in the text")
            return 'UNKNOWN'

    except Exception as e:
        logging.exception("Error in detect_bill_type")
        raise RuntimeError(f"Failed to detect bill type: {str(e)}")

def process_bill_ocr(file_path):
    """Process bill file with OCR using improved image processing"""
    try:
        logging.info(f"Starting OCR processing for file: {file_path}")

        # Validate file
        if not os.path.exists(file_path):
            logging.error(f"File not found: {file_path}")
            raise FileNotFoundError(f"File not found: {file_path}")

        if not os.access(file_path, os.R_OK):
            logging.error(f"File is not readable: {file_path}")
            raise PermissionError(f"File is not readable: {file_path}")

        # Process PDF or image
        text = ""
        if file_path.lower().endswith('.pdf'):
            try:
                logging.info("Converting PDF to images")
                # Increased DPI and using all pages for better accuracy
                images = convert_from_path(file_path, dpi=300)

                if not images:
                    logging.error("Failed to convert PDF to images")
                    raise ValueError("Failed to convert PDF to images")

                # Process all pages
                for page_num, image in enumerate(images, 1):
                    logging.info(f"Processing page {page_num}/{len(images)}")
                    processed_image = preprocess_image(image)

                    # Configure tesseract for optimal results
                    custom_config = r'--oem 3 --psm 6 -l ita+eng'
                    page_text = pytesseract.image_to_string(processed_image, config=custom_config)
                    text += page_text + "\n"

                    # Log a sample of extracted text for debugging
                    logging.debug(f"Sample text from page {page_num}: {page_text[:200]}...")

            except Exception as e:
                logging.exception("Error processing PDF")
                raise RuntimeError(f"PDF processing failed: {str(e)}")
        else:
            try:
                logging.info("Processing image file")
                image = Image.open(file_path)
                if image.mode != 'RGB':
                    image = image.convert('RGB')
                processed_image = preprocess_image(image)

                custom_config = r'--oem 3 --psm 6 -l ita+eng'
                text = pytesseract.image_to_string(processed_image, config=custom_config)

            except Exception as e:
                logging.exception("Error processing image")
                raise RuntimeError(f"Image processing failed: {str(e)}")

        if not text.strip():
            logging.error("No text extracted from file")
            raise ValueError("No text could be extracted from the file")

        # Extract bill type first
        bill_type = detect_bill_type(text)
        if bill_type == 'UNKNOWN':
            logging.warning("Could not determine bill type")
            raise ValueError("Could not determine bill type")

        # Extract cost per unit
        cost_per_unit = extract_cost_per_unit(text)
        if cost_per_unit is None:
            logging.warning("Could not extract cost per unit")

        logging.info(f"Successfully processed bill - Type: {bill_type}, Cost per unit: {cost_per_unit}")
        return cost_per_unit, bill_type

    except Exception as e:
        logging.exception(f"Unexpected error during OCR processing: {str(e)}")
        raise