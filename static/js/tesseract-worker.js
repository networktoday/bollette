// Configure Tesseract.js worker for optimal OCR performance
importScripts('https://unpkg.com/tesseract.js@v2.1.0/dist/worker.min.js');

let recognizeText = async (image) => {
    const worker = new Tesseract.Worker({
        workerPath: 'https://unpkg.com/tesseract.js@v2.1.0/dist/worker.min.js',
        langPath: 'https://tessdata.projectnaptha.com/4.0.0',
        corePath: 'https://unpkg.com/tesseract.js-core@v2.1.0/tesseract-core.wasm.js',
    });

    try {
        // Load Italian and English language data
        await worker.load();
        await worker.loadLanguage('ita+eng');
        await worker.initialize('ita+eng');

        // Configure recognition settings for better accuracy with utility bills
        await worker.setParameters({
            tessedit_char_whitelist: '0123456789.,ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz$/kWm³', 
            preserve_interword_spaces: '1',
            tessedit_ocr_engine_mode: '3',
            tessedit_pageseg_mode: '6'
        });

        let text = '';
        let confidence = 0;

        if (image instanceof ArrayBuffer) {
            // Handle PDF file
            const typedarray = new Uint8Array(image);
            const pdf = await pdfjsLib.getDocument(typedarray).promise;
            const numPages = pdf.numPages;
            console.log(`Processing PDF with ${numPages} pages`);

            // Process all pages
            for (let pageNum = 1; pageNum <= numPages; pageNum++) {
                console.log(`Processing page ${pageNum}/${numPages}`);
                const page = await pdf.getPage(pageNum);
                const viewport = page.getViewport({ scale: 2.0 }); // Increased scale for better quality

                const canvas = new OffscreenCanvas(viewport.width, viewport.height);
                const context = canvas.getContext('2d');

                await page.render({
                    canvasContext: context,
                    viewport: viewport
                }).promise;

                const { data: pageData } = await worker.recognize(canvas);
                text += pageData.text + '\n';
                confidence += pageData.confidence;
            }

            // Average confidence across all pages
            confidence = confidence / numPages;
        } else {
            // Handle image file
            const { data } = await worker.recognize(image);
            text = data.text;
            confidence = data.confidence;
        }

        // Extract utility bill specific information
        const result = {
            text: text,
            confidence: confidence,
            costPerUnit: extractCostPerUnit(text),
            billType: detectBillType(text)
        };

        await worker.terminate();
        return result;

    } catch (error) {
        console.error('OCR Processing Error:', error);
        if (worker) {
            await worker.terminate();
        }
        throw error;
    }
};

function extractCostPerUnit(text) {
    // Regular expressions for cost extraction
    const kwPattern = /(\$?\d+[.,]?\d*)\s*(?:\/|\s+per\s+)?\s*(?:kw|kwh)/i;
    const cubicMeterPattern = /(\$?\d+[.,]?\d*)\s*(?:\/|\s+per\s+)?\s*(?:m³|mc)/i;

    let cost = null;

    // Try to find cost per KW
    const kwMatch = text.match(kwPattern);
    if (kwMatch) {
        cost = parseFloat(kwMatch[1].replace(',', '.').replace('$', ''));
    }

    // Try to find cost per cubic meter
    const cubicMatch = text.match(cubicMeterPattern);
    if (cubicMatch) {
        cost = parseFloat(cubicMatch[1].replace(',', '.').replace('$', ''));
    }

    return cost;
}

function detectBillType(text) {
    text = text.toLowerCase();

    // Define Italian and English terms for each type
    const gasTerms = [
        'gas', 'cubic meter', 'm³', 'mc', 'metano', 'consumo gas',
        'lettura gas', 'fornitura gas', 'gas naturale'
    ];
    const electricityTerms = [
        'electricity', 'electric', 'kw', 'kwh', 'kilowatt',
        'energia elettrica', 'consumo energia', 'luce', 'elettricità',
        'potenza', 'lettura energia', 'energia', 'corrente elettrica'
    ];

    // Count occurrences of terms
    const gasCount = gasTerms.reduce((count, term) => text.includes(term) ? count + 1 : count, 0);
    const electricityCount = electricityTerms.reduce((count, term) => text.includes(term) ? count + 1 : count, 0);

    console.log('Gas terms found:', gasCount, 'Electricity terms found:', electricityCount);
    console.log('Found gas terms:', gasTerms.filter(term => text.includes(term)));
    console.log('Found electricity terms:', electricityTerms.filter(term => text.includes(term)));

    // Se troviamo una qualsiasi combinazione di termini gas ed elettricità, è una bolletta MIX
    if (gasCount > 0 && electricityCount > 0) {
        console.log('Bill type detected: MIX (contains both gas and electricity terms)');
        return 'MIX';
    } else if (gasCount > 0) {
        console.log('Bill type detected: GAS');
        return 'GAS';
    } else if (electricityCount > 0) {
        console.log('Bill type detected: LUCE');
        return 'LUCE';
    }

    console.log('Bill type detected: UNKNOWN');
    return 'UNKNOWN';
}

// Listen for messages from the main thread
self.addEventListener('message', async (e) => {
    try {
        const result = await recognizeText(e.data.image);
        self.postMessage({
            status: 'done',
            result: result
        });
    } catch (error) {
        self.postMessage({
            status: 'error',
            error: error.message
        });
    }
});