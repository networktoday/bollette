import re
import logging
import os
import cv2
import numpy as np
from PIL import Image
import pytesseract
from pdf2image import convert_from_path
import threading
from concurrent.futures import ThreadPoolExecutor, TimeoutError

class OCRTimeoutError(Exception):
    pass

def process_image_with_timeout(image, timeout_seconds=15):  # Ridotto da 30 a 15 secondi
    """Process a single image with OCR and timeout"""
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(pytesseract.image_to_string, 
                               image, 
                               config=r'--oem 3 --psm 6 -l ita+eng')
        try:
            return future.result(timeout=timeout_seconds)
        except TimeoutError:
            logging.error(f"OCR timeout after {timeout_seconds} seconds")
            raise OCRTimeoutError(f"OCR processing timed out after {timeout_seconds} seconds")

def preprocess_image(image):
    """Pre-process the image to improve OCR accuracy"""
    logging.info("Starting image pre-processing")
    try:
        # Convert PIL Image to cv2 format if needed
        if isinstance(image, Image.Image):
            image = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)

        # Convert to grayscale
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

        # Apply multiple preprocessing techniques
        # 1. Noise reduction
        denoised = cv2.fastNlMeansDenoising(gray)

        # 2. Increase contrast
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8,8))
        contrasted = clahe.apply(denoised)

        # 3. Thresholding
        _, binary = cv2.threshold(contrasted, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

        # 4. Dilation to make text more prominent
        kernel = np.ones((1,1), np.uint8)
        dilated = cv2.dilate(binary, kernel, iterations=1)

        # Convert back to PIL Image
        enhanced_pil = Image.fromarray(dilated)

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

    # Check for SMC measurements (strong indicator of gas)
    smc_patterns = [
        r'\d+(?:[.,]\d+)?\s*(?:smc|Smc|SMC)',  # Standard SMC format
        r'\d+(?:[.,]\d+)?\s*(?:m³|mc|metri cubi)',  # Cubic meters
        r'consumo\s+(?:effettivo|reale|fatturato)?\s*(?:di)?\s*gas\s*:\s*\d+(?:[.,]\d+)?',  # Gas consumption
        r'lettura\s+(?:attuale|precedente)?\s*(?:mc|m³)\s*:\s*\d+(?:[.,]\d+)?'  # Gas meter reading
    ]

    # Check for KWH measurements (strong indicator of electricity)
    kwh_patterns = [
        r'\d+(?:[.,]\d+)?\s*(?:kwh|kw/h|chilowattora)',  # Standard KWH format
        r'consumo\s+(?:effettivo|reale|fatturato)?\s*(?:di)?\s*energia\s*:\s*\d+(?:[.,]\d+)?',  # Energy consumption
        r'(?:f1|f2|f3)\s*:\s*\d+(?:[.,]\d+)?\s*kwh'  # Time-based consumption
    ]

    # Enhanced list of Italian terms for gas bills
    gas_terms = [
        'gas', 'metano', 'gas naturale', 'distribuzione gas',
        'smc', 'standard m³', 'metri cubi', 'metro cubo',
        'consumo gas', 'lettura gas', 'fornitura gas',
        'materia gas', 'importi gas', 'consumi gas',
        'bolletta gas', 'riepilogo gas', 'spesa gas',
        'costo gas', 'tariffa gas', 'volume gas',
        'pcs', 'potere calorifico', 'coefficiente c',
        'm³', 'mc', 'standard metro cubo',
        'consumo metri cubi', 'lettura precedente mc',
        'lettura attuale mc', 'consumo mc', 'consumo smc',
        'letture gas', 'importo gas', 'quota gas',
        'gas naturale', 'punto di riconsegna', 'pdr',
        'codice pdr', 'remi', 'classe del misuratore'
    ]

    # Enhanced list of Italian terms for electricity bills
    electricity_terms = [
        'energia elettrica', 'luce', 'elettricità',
        'kw', 'kwh', 'chilowattora', 'kilowattora',
        'consumo energia', 'potenza', 'energia attiva',
        'f1', 'f2', 'f3', 'fascia oraria', 'fasce',
        'lettura energia', 'potenza impegnata',
        'dispacciamento', 'consumo elettrico',
        'tariffa energia', 'spesa energia',
        'quota energia', 'energia reattiva',
        'servizio elettrico', 'contatore elettrico',
        'pod', 'codice pod', 'punto di prelievo',
        'potenza disponibile', 'tensione di alimentazione'
    ]

    try:
        # Initialize counters and found terms
        gas_terms_found = []
        electricity_terms_found = []

        # Check for SMC measurements
        has_smc = False
        for pattern in smc_patterns:
            if re.search(pattern, text):
                has_smc = True
                logging.info(f"Found gas measurement pattern: {pattern}")
                break

        # Check for KWH measurements
        has_kwh = False
        for pattern in kwh_patterns:
            if re.search(pattern, text):
                has_kwh = True
                logging.info(f"Found electricity measurement pattern: {pattern}")
                break

        # Count gas and electricity terms
        for term in gas_terms:
            if term in text:
                gas_terms_found.append(term)

        for term in electricity_terms:
            if term in text:
                electricity_terms_found.append(term)

        # Log findings
        logging.info(f"Gas terms found: {gas_terms_found}")
        logging.info(f"Electricity terms found: {electricity_terms_found}")
        logging.info(f"Has SMC measurements: {has_smc}")
        logging.info(f"Has KWH measurements: {has_kwh}")

        # Decision logic prioritizing measurements
        if has_smc and has_kwh:
            logging.info("Detected type: MIX (both SMC and KWH measurements)")
            return 'MIX'
        elif has_smc:
            logging.info("Detected type: GAS (SMC measurement found)")
            return 'GAS'
        elif has_kwh:
            logging.info("Detected type: LUCE (KWH measurement found)")
            return 'LUCE'
        elif len(gas_terms_found) > 0 and len(electricity_terms_found) > 0:
            logging.info("Detected type: MIX (both gas and electricity terms)")
            return 'MIX'
        elif len(gas_terms_found) > 2:  # Require multiple gas terms for confidence
            logging.info("Detected type: GAS (multiple gas terms)")
            return 'GAS'
        elif len(electricity_terms_found) > 2:  # Require multiple electricity terms for confidence
            logging.info("Detected type: LUCE (multiple electricity terms)")
            return 'LUCE'

        logging.warning("Could not determine bill type with confidence")
        return 'UNKNOWN'

    except Exception as e:
        logging.exception("Error in detect_bill_type")
        raise RuntimeError(f"Failed to detect bill type: {str(e)}")

def process_bill_ocr(file_path):
    """Process bill file with OCR using improved image processing and timeout handling"""
    try:
        logging.info(f"Starting OCR processing for file: {file_path}")

        # Validate file
        if not os.path.exists(file_path):
            logging.error(f"File not found: {file_path}")
            raise FileNotFoundError(f"File not found: {file_path}")

        if not os.access(file_path, os.R_OK):
            logging.error(f"File is not readable: {file_path}")
            raise PermissionError(f"File is not readable: {file_path}")

        text = ""

        # Process PDF or image with reduced timeout
        if file_path.lower().endswith('.pdf'):
            try:
                logging.info("Converting PDF to images")
                # Process only first page with optimized DPI and reduced quality
                images = convert_from_path(file_path, dpi=150, first_page=1, last_page=1)

                if not images:
                    logging.error("Failed to convert PDF to images")
                    raise ValueError("Failed to convert PDF to images")

                image = images[0]
                # Resize image if too large
                width, height = image.size
                if width > 1200 or height > 1200:  # Ridotto da 1500 a 1200
                    ratio = min(1200/width, 1200/height)
                    new_size = (int(width * ratio), int(height * ratio))
                    image = image.resize(new_size, Image.Resampling.LANCZOS)

                processed_image = preprocess_image(image)
                text = process_image_with_timeout(processed_image, timeout_seconds=15)  # Ridotto timeout

            except TimeoutError:
                logging.error("PDF processing timeout")
                raise OCRTimeoutError("PDF processing timed out")
            except Exception as e:
                logging.exception("Error processing PDF")
                raise RuntimeError(f"PDF processing failed: {str(e)}")

        else:
            try:
                logging.info("Processing image file")
                image = Image.open(file_path)
                if image.mode != 'RGB':
                    image = image.convert('RGB')

                # Resize image if too large
                width, height = image.size
                if width > 1200 or height > 1200:  # Ridotto da 1500 a 1200
                    ratio = min(1200/width, 1200/height)
                    new_size = (int(width * ratio), int(height * ratio))
                    image = image.resize(new_size, Image.Resampling.LANCZOS)

                processed_image = preprocess_image(image)
                text = process_image_with_timeout(processed_image, timeout_seconds=15)  # Ridotto timeout

            except TimeoutError:
                logging.error("Image processing timeout")
                raise OCRTimeoutError("Image processing timed out")
            except Exception as e:
                logging.exception("Error processing image")
                raise RuntimeError(f"Image processing failed: {str(e)}")

        if not text.strip():
            logging.error("No text extracted from file")
            raise ValueError("No text could be extracted from the file")

        # Extract bill type and cost per unit
        logging.info("Starting bill type detection")
        bill_type = detect_bill_type(text)
        logging.info(f"Detected bill type: {bill_type}")

        if bill_type == 'UNKNOWN':
            logging.warning("Could not determine bill type")
            raise ValueError("Could not determine bill type")

        logging.info("Starting cost extraction")
        cost_per_unit = extract_cost_per_unit(text)
        logging.info(f"Extracted cost per unit: {cost_per_unit}")

        return cost_per_unit, bill_type

    except OCRTimeoutError as e:
        logging.error(f"OCR timeout: {str(e)}")
        raise OCRTimeoutError(f"L'elaborazione OCR è durata troppo tempo: {str(e)}")
    except Exception as e:
        logging.exception(f"Unexpected error during OCR processing: {str(e)}")
        raise