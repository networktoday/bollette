document.addEventListener('DOMContentLoaded', function() {
    const dropZone = document.getElementById('drop-zone');
    const fileInput = document.getElementById('file-input');
    const preview = document.getElementById('preview');
    const form = document.getElementById('upload-form');
    const phoneInput = document.getElementById('phone');

    // Store uploaded files and their bill types
    let uploadedFiles = [];
    let billTypes = {};

    // Drag and drop handling
    ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
        dropZone.addEventListener(eventName, preventDefaults, false);
    });

    function preventDefaults(e) {
        e.preventDefault();
        e.stopPropagation();
    }

    ['dragenter', 'dragover'].forEach(eventName => {
        dropZone.addEventListener(eventName, highlight, false);
    });

    ['dragleave', 'drop'].forEach(eventName => {
        dropZone.addEventListener(eventName, unhighlight, false);
    });

    function highlight(e) {
        dropZone.classList.add('drag-hover');
    }

    function unhighlight(e) {
        dropZone.classList.remove('drag-hover');
    }

    dropZone.addEventListener('drop', handleDrop, false);

    function handleDrop(e) {
        const dt = e.dataTransfer;
        const files = dt.files;
        handleFiles(Array.from(files));
    }

    fileInput.addEventListener('change', function() {
        handleFiles(Array.from(this.files));
    });

    function handleFiles(files) {
        files.forEach(file => {
            console.log('File selected:', file.name, file.type);
            if (validateFile(file)) {
                uploadedFiles.push(file);
                displayPreview(file, uploadedFiles.length - 1);
                // Process OCR in background
                setTimeout(() => processBillOCR(file, uploadedFiles.length - 1), 100);
            }
        });
    }

    function validateFile(file) {
        const validTypes = ['image/jpeg', 'image/png', 'application/pdf'];
        if (!validTypes.includes(file.type)) {
            showAlert('danger', 'Per favore carica un\'immagine (JPG, PNG) o un file PDF');
            return false;
        }
        if (file.size > 16 * 1024 * 1024) { // 16MB
            showAlert('danger', 'Il file è troppo grande. Dimensione massima: 16MB');
            return false;
        }
        return true;
    }

    function displayPreview(file, index) {
        console.log('Displaying preview for:', file.name);

        if (file.type.startsWith('image/')) {
            const reader = new FileReader();
            reader.onload = function(e) {
                console.log('FileReader loaded successfully');
                appendPreviewHTML(createPreviewHTML(e.target.result, 'image', index));
            };
            reader.onerror = function(e) {
                console.error('FileReader error:', e);
                showAlert('danger', 'Errore durante la lettura del file');
            };
            reader.readAsDataURL(file);
        } else if (file.type === 'application/pdf') {
            const reader = new FileReader();
            reader.onload = async function(e) {
                try {
                    const typedarray = new Uint8Array(e.target.result);
                    const pdf = await pdfjsLib.getDocument(typedarray).promise;
                    const page = await pdf.getPage(1);
                    const viewport = page.getViewport({ scale: 0.5 });

                    const canvas = document.createElement('canvas');
                    canvas.height = viewport.height;
                    canvas.width = viewport.width;

                    await page.render({
                        canvasContext: canvas.getContext('2d'),
                        viewport: viewport
                    }).promise;

                    appendPreviewHTML(createPreviewHTML(canvas.toDataURL(), 'pdf', index));
                } catch (error) {
                    console.error('PDF preview error:', error);
                    appendPreviewHTML(createPreviewHTML(null, 'pdf-fallback', index, file.name));
                }
            };
            reader.onerror = function(e) {
                console.error('FileReader error:', e);
                showAlert('danger', 'Errore durante la lettura del file');
            };
            reader.readAsArrayBuffer(file);
        }
    }

    function appendPreviewHTML(html) {
        const div = document.createElement('div');
        div.innerHTML = html;
        preview.appendChild(div.firstElementChild);
    }

    function createPreviewHTML(src, type, index, filename = '') {
        let previewContent = '';
        switch (type) {
            case 'image':
                previewContent = `<img src="${src}" alt="Anteprima" class="preview-image">`;
                break;
            case 'pdf':
                previewContent = `<img src="${src}" alt="Anteprima PDF" class="preview-image">`;
                break;
            case 'pdf-fallback':
                previewContent = `
                    <i class="fas fa-file-pdf fa-3x text-danger"></i>
                    <p class="mt-2">${filename}</p>`;
                break;
        }

        return `
            <div class="preview-item" data-index="${index}">
                ${previewContent}
                <button type="button" class="btn btn-danger btn-sm delete-preview" onclick="removeFile(${index})">
                    <i class="fas fa-trash"></i>
                </button>
            </div>`;
    }

    // Add this function to the global scope for the onclick handler
    window.removeFile = function(index) {
        uploadedFiles = uploadedFiles.filter((_, i) => i !== index);
        delete billTypes[index];
        updateBillTypesInput();
        refreshPreviews();
    };

    function refreshPreviews() {
        preview.innerHTML = '';
        uploadedFiles.forEach((file, index) => {
            displayPreview(file, index);
        });
    }

    function updateBillTypesInput() {
        const types = uploadedFiles.map((_, index) => billTypes[index] || 'UNKNOWN');
        document.getElementById('billTypes').value = JSON.stringify(types);
    }

    async function processBillOCR(file, index) {
        try {
            const worker = await Tesseract.createWorker({
                logger: m => console.log(m)
            });

            await worker.load();
            await worker.loadLanguage('eng');
            await worker.initialize('eng');

            if (file.type.startsWith('image/')) {
                const { data: { text } } = await worker.recognize(file);
                billTypes[index] = detectBillType(text);
                updateBillTypesInput();
                console.log('OCR completed, bill type:', billTypes[index]);
            }

            await worker.terminate();
        } catch (error) {
            console.error('OCR Error:', error);
            // Don't show OCR errors to user, just log them
        }
    }

    function detectBillType(text) {
        text = text.toLowerCase();
        if (text.includes('gas') && text.includes('electricity')) return 'MIX';
        if (text.includes('gas')) return 'GAS';
        if (text.includes('electricity') || text.includes('kw')) return 'LUCE';
        return 'UNKNOWN';
    }

    phoneInput.addEventListener('input', function() {
        this.value = this.value.replace(/[^\d+]/g, '');
    });

    form.addEventListener('submit', async function(e) {
        e.preventDefault();

        if (!validateForm()) return;

        const formData = new FormData();
        formData.append('phone', phoneInput.value);
        formData.append('billTypes', document.getElementById('billTypes').value);
        uploadedFiles.forEach((file, index) => {
            formData.append('files[]', file);
        });

        try {
            const response = await fetch('/upload', {
                method: 'POST',
                body: formData
            });

            const result = await response.json();
            if (result.success) {
                showAlert('success', 'File caricati con successo!');
                resetForm();
            } else {
                showAlert('danger', result.error || 'Caricamento fallito');
            }
        } catch (error) {
            console.error('Upload error:', error);
            showAlert('danger', 'Si è verificato un errore durante il caricamento');
        }
    });

    function validateForm() {
        if (!phoneInput.value) {
            showAlert('danger', 'Inserisci un numero di telefono');
            return false;
        }
        if (!uploadedFiles.length) {
            showAlert('danger', 'Seleziona almeno un file');
            return false;
        }
        return true;
    }

    function showAlert(type, message) {
        const alertDiv = document.createElement('div');
        alertDiv.className = `alert alert-${type} alert-dismissible fade show`;
        alertDiv.innerHTML = `
            ${message}
            <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
        `;
        document.querySelector('.alerts').appendChild(alertDiv);
        setTimeout(() => alertDiv.remove(), 5000);
    }

    function resetForm() {
        form.reset();
        preview.innerHTML = '';
        uploadedFiles = [];
        billTypes = {};
        updateBillTypesInput();
    }
});