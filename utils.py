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

def process_image_with_timeout(image, timeout_seconds=30):
    """Process a single image with OCR and timeout"""
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(pytesseract.image_to_string, 
                               image, 
                               config=r'--oem 3 --psm 6 -l ita+eng')
        try:
            return future.result(timeout=timeout_seconds)
        except TimeoutError:
            raise OCRTimeoutError("OCR processing timed out")

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

    # Enhanced list of Italian terms for gas bills
    gas_terms = [
        'gas', 'metano', 'gas naturale',
        'smc', 'standard m³', 'metri cubi', 'metro cubo',
        'consumo gas', 'lettura gas', 'fornitura gas',
        'materia gas', 'importi gas', 'consumi gas',
        'bolletta gas', 'riepilogo gas', 'spesa gas',
        'costo gas', 'tariffa gas', 'volume gas',
        'pcs', 'potere calorifico', 'coefficiente c',
        'm³', 'mc', 'standard metro cubo',
        'consumo metri cubi', 'lettura precedente mc',
        'lettura attuale mc', 'consumo mc', 'consumo smc',
        'letture gas', 'importo gas', 'quota gas'
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
        'servizio elettrico', 'contatore elettrico'
    ]

    # Terms that might indicate a mixed bill
    mix_terms = [
        'offerta dual', 'dual fuel', 'doppia fornitura',
        'gas e luce', 'luce e gas', 'energia e gas',
        'gas ed energia', 'bolletta unica',
        'fattura combinata', 'servizi congiunti',
        'eni gas e luce', 'enel gas e luce',
        'a2a gas e luce', 'edison gas e luce',
        'iren gas e luce', 'sorgenia gas e luce'
    ]

    try:
        # Initialize counters for found terms
        gas_terms_found = []
        electricity_terms_found = []
        mix_terms_found = []

        # Check for SMC measurements (strong indicator of gas)
        smc_pattern = r'\d+(?:[.,]\d+)?\s*(?:smc|Smc|SMC|m³|mc)'
        if re.search(smc_pattern, text):
            logging.info("Found SMC/cubic meter measurement - strong indicator of gas presence")
            gas_terms_found.append('smc_measurement')

        # Check for KWH measurements (strong indicator of electricity)
        kwh_pattern = r'\d+(?:[.,]\d+)?\s*(?:kwh|kw/h|kw)'
        if re.search(kwh_pattern, text):
            logging.info("Found KWH measurement - strong indicator of electricity presence")
            electricity_terms_found.append('kwh_measurement')

        # Split text into sections and search for terms
        sections = text.split('\n\n')
        for section in sections:
            # Search for gas terms
            found_gas_terms = [term for term in gas_terms if term in section]
            if found_gas_terms:
                gas_terms_found.extend(found_gas_terms)
                logging.info(f"Found gas terms in section: {found_gas_terms}")

            # Search for electricity terms
            found_electricity_terms = [term for term in electricity_terms if term in section]
            if found_electricity_terms:
                electricity_terms_found.extend(found_electricity_terms)
                logging.info(f"Found electricity terms in section: {found_electricity_terms}")

            # Search for mix terms
            found_mix_terms = [term for term in mix_terms if term in section]
            if found_mix_terms:
                mix_terms_found.extend(found_mix_terms)
                logging.info(f"Found mix terms in section: {found_mix_terms}")

        # Count unique terms
        unique_gas_terms = len(set(gas_terms_found))
        unique_electricity_terms = len(set(electricity_terms_found))
        unique_mix_terms = len(set(mix_terms_found))

        # Log findings
        logging.info(f"Gas terms found ({unique_gas_terms}): {set(gas_terms_found)}")
        logging.info(f"Electricity terms found ({unique_electricity_terms}): {set(electricity_terms_found)}")
        logging.info(f"Mix terms found ({unique_mix_terms}): {set(mix_terms_found)}")

        # Decision logic
        has_smc = 'smc_measurement' in gas_terms_found
        has_kwh = 'kwh_measurement' in electricity_terms_found

        # If we have explicit mix terms and both types of measurements
        if unique_mix_terms > 0 and has_smc and has_kwh:
            logging.info("Detected type: MIX (explicit mix terms and both measurements)")
            return 'MIX'

        # If we have both SMC and KWH measurements
        if has_smc and has_kwh:
            logging.info("Detected type: MIX (both SMC and KWH measurements)")
            return 'MIX'

        # If we have SMC measurement or multiple gas terms, it's GAS
        if has_smc or unique_gas_terms >= 2:
            logging.info("Detected type: GAS (SMC measurement or multiple gas terms)")
            return 'GAS'

        # If we have KWH measurement or multiple electricity terms, it's LUCE
        if has_kwh or unique_electricity_terms >= 2:
            logging.info("Detected type: LUCE (KWH measurement or multiple electricity terms)")
            return 'LUCE'

        # If we have both gas and electricity terms (but no measurements)
        if unique_gas_terms > 0 and unique_electricity_terms > 0:
            logging.info("Detected type: MIX (both gas and electricity terms)")
            return 'MIX'

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

        # Process PDF or image
        if file_path.lower().endswith('.pdf'):
            try:
                logging.info("Converting PDF to images")
                # Process only the first page with optimized DPI
                images = convert_from_path(file_path, dpi=200, first_page=1, last_page=1)

                if not images:
                    logging.error("Failed to convert PDF to images")
                    raise ValueError("Failed to convert PDF to images")

                image = images[0]
                # Resize image if too large
                width, height = image.size
                if width > 1500 or height > 1500:
                    ratio = min(1500/width, 1500/height)
                    new_size = (int(width * ratio), int(height * ratio))
                    image = image.resize(new_size, Image.Resampling.LANCZOS)

                processed_image = preprocess_image(image)
                text = process_image_with_timeout(processed_image, timeout_seconds=30)

                if not text.strip():
                    raise ValueError("No text could be extracted from the PDF")

                logging.info("Successfully processed PDF page")
                logging.debug(f"Sample text extracted: {text[:200]}")

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
                if width > 1500 or height > 1500:
                    ratio = min(1500/width, 1500/height)
                    new_size = (int(width * ratio), int(height * ratio))
                    image = image.resize(new_size, Image.Resampling.LANCZOS)

                processed_image = preprocess_image(image)
                text = process_image_with_timeout(processed_image, timeout_seconds=30)

                if not text.strip():
                    raise ValueError("No text could be extracted from the image")

                logging.info("Successfully processed image file")
                logging.debug(f"Sample text extracted: {text[:200]}")

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

    except Exception as e:
        logging.exception(f"Unexpected error during OCR processing: {str(e)}")
        raise