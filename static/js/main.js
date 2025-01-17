document.addEventListener('DOMContentLoaded', function() {
    const dropZone = document.getElementById('drop-zone');
    const fileInput = document.getElementById('file-input');
    const preview = document.getElementById('preview');
    const form = document.getElementById('upload-form');
    const phoneInput = document.getElementById('phone');

    // Store uploaded files
    let uploadedFiles = [];

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
            if (validateFile(file)) {
                uploadedFiles.push(file);
                displayPreview(file, uploadedFiles.length - 1);
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
        if (file.type.startsWith('image/')) {
            const reader = new FileReader();
            reader.onload = function(e) {
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
        refreshPreviews();
    };

    function refreshPreviews() {
        preview.innerHTML = '';
        uploadedFiles.forEach((file, index) => {
            displayPreview(file, index);
        });
    }

    phoneInput.addEventListener('input', function() {
        this.value = this.value.replace(/[^\d+]/g, '');
    });

    form.addEventListener('submit', async function(e) {
        e.preventDefault();
        console.log('Form submit started');

        try {
            if (!validateForm()) {
                return;
            }

            // Disable submit button to prevent double submission
            const submitButton = form.querySelector('button[type="submit"]');
            submitButton.disabled = true;

            showAlert('info', 'Elaborazione in corso...');

            // First validate files are still valid
            if (!uploadedFiles.length) {
                console.error('No files to upload');
                showAlert('danger', 'Nessun file da caricare');
                submitButton.disabled = false;
                return;
            }

            const formData = new FormData();
            formData.append('phone', phoneInput.value);

            // Add files to FormData
            uploadedFiles.forEach((file, index) => {
                console.log(`Adding file ${index + 1}/${uploadedFiles.length}:`, file.name);
                formData.append('files[]', file);
            });

            console.log('Sending POST request to /upload');
            const response = await fetch('/upload', {
                method: 'POST',
                body: formData
            });

            console.log('Received response:', response.status);
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }

            const result = await response.json();
            console.log('Server response:', result);

            if (result.success) {
                console.log('Upload successful');
                showAlert('success', 'File caricati con successo!');
                resetForm();
            } else {
                console.error('Upload failed:', result.error);
                showAlert('danger', result.error || 'Caricamento fallito');
            }
        } catch (error) {
            console.error('Upload error:', error);
            showAlert('danger', 'Si è verificato un errore durante il caricamento');
        } finally {
            // Re-enable submit button
            const submitButton = form.querySelector('button[type="submit"]');
            submitButton.disabled = false;
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
    }
});