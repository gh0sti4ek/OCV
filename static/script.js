document.addEventListener('DOMContentLoaded', function() {
    // Общие константы
    const fileInput = document.getElementById('fileInput');
    const imagePreview = document.getElementById('imagePreview');
    const placeholder = document.getElementById('previewPlaceholder');

    // Функция предпросмотра выбранного файла
    if (fileInput && imagePreview) {
        fileInput.addEventListener('change', function() {
            const file = this.files[0];
            if (file) {
                const reader = new FileReader();
                reader.onload = function(e) {
                    imagePreview.src = e.target.result;
                    imagePreview.classList.remove('d-none');
                    if (placeholder) placeholder.classList.add('d-none');
                }
                reader.readAsDataURL(file);
            }
        });
    }

    // Логика слайдера сравнения (До/После) — оставляем, если используете compare.html
    const compSlider = document.getElementById('slider');
    const processedWrapper = document.getElementById('processedImage');
    const container = document.querySelector('.comparison-container');

    if (compSlider && processedWrapper && container) {
        const syncSlider = () => {
            const val = compSlider.value;
            const containerWidth = container.offsetWidth;
            processedWrapper.style.width = val + "%";

            const btn = document.getElementById('sliderButton');
            if (btn) btn.style.left = val + "%";

            container.querySelectorAll('img').forEach(img => {
                img.style.width = containerWidth + "px";
            });
        };

        compSlider.addEventListener('input', syncSlider);
        window.addEventListener('resize', syncSlider);
        syncSlider();
    }

    const aiSwitch = document.getElementById('use_ai');
    const desc = document.getElementById('methodDescription');

    if (aiSwitch && desc) {
        aiSwitch.addEventListener('change', function() {
            desc.innerText = this.checked 
                ? "Метод Zero-DCE++: лучшее качество для очень темных кадров." 
                : "Алгоритм CLAHE: быстрая цифровая коррекция освещения.";
        });
    }
});