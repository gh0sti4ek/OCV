document.addEventListener('DOMContentLoaded', function() {
    console.log("--- OCV: Инициализация ---");

    // === 1. ОБЩИЕ ЭЛЕМЕНТЫ ===
    const fileInput = document.getElementById('fileInput');
    const imagePreview = document.getElementById('imagePreview');
    const placeholder = document.getElementById('previewPlaceholder');
    const resetBtn = document.getElementById('resetSettings');

    // === 2. ФУНКЦИЯ ЖИВЫХ ФИЛЬТРОВ (ДЛЯ ПРЕДПРОСМОТРА) ===
    function applyLiveFilters() {
        if (!imagePreview) return;

        const b = document.getElementById('brightness_beta')?.value || 15;
        const c = document.getElementById('contrast_alpha')?.value || 1.15;
        const s = document.getElementById('saturation_factor')?.value || 1.3;
        const d = document.getElementById('denoise_h')?.value || 15.0;

        // Обновляем текст индикаторов
        if(document.getElementById('brightnessValue')) document.getElementById('brightnessValue').innerText = b;
        if(document.getElementById('contrastValue')) document.getElementById('contrastValue').innerText = c;
        if(document.getElementById('saturationValue')) document.getElementById('saturationValue').innerText = s;
        if(document.getElementById('denoiseValue')) document.getElementById('denoiseValue').innerText = d;

        // Визуальная симуляция через CSS (только если это не видео-заглушка)
        if (!imagePreview.dataset.isVideo) {
            const brightCSS = (100 + parseInt(b)) / 100;
            const blurCSS = d / 40;
            imagePreview.style.filter = `brightness(${brightCSS}) contrast(${c}) saturate(${s}) blur(${blurCSS}px)`;
        } else {
            imagePreview.style.filter = 'none';
        }
    }

    // === 3. ЛОГИКА ЗАГРУЗКИ И ОТОБРАЖЕНИЯ ФАЙЛА ===
    if (fileInput && imagePreview) {
        fileInput.addEventListener('change', function() {
            const file = this.files[0];
            if (file) {
                // ПРОВЕРКА: Видео это или Фото?
                const isVideo = file.type.startsWith('video/');

                if (isVideo) {
                    // Если видео — ставим заглушку, так как живой превью видео через CSS фильтры в реальном времени может тормозить
                    imagePreview.src = "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='100' height='100' fill='%23666' viewBox='0 0 16 16'%3E%3Cpath d='M0 1a1 1 0 0 1 1-1h14a1 1 0 0 1 1 1v14a1 1 0 0 1-1 1H1a1 1 0 0 1-1-1V1zm4 0v6h8V1H4zm8 8H4v6h8V9zM1 1v2h2V1H1zm2 3H1v2h2V4zM1 7v2h2V7H1zm2 3H1v2h2v-2zm-2 3v2h2v-2H1zM15 1h-2v2h2V1zm-2 3v2h2V4h-2zm2 3h-2v2h2V7zm-2 3v2h2v-2h-2zm2 3h-2v2h2v-2z'/%3E%3C/svg%3E";
                    imagePreview.dataset.isVideo = "true";
                    if (placeholder) placeholder.innerHTML = "<p class='text-warning'>Предпросмотр видео недоступен.<br>Нажмите 'Обработать', чтобы увидеть результат.</p>";
                } else {
                    const reader = new FileReader();
                    reader.onload = function(e) {
                        imagePreview.src = e.target.result;
                        delete imagePreview.dataset.isVideo;
                        if (placeholder) placeholder.innerHTML = "<p>Выберите фото для предпросмотра</p>";
                        applyLiveFilters();
                    }
                    reader.readAsDataURL(file);
                }

                imagePreview.classList.remove('d-none');
                imagePreview.style.display = 'block';
                if (placeholder) {
                    placeholder.classList.add('d-none');
                    placeholder.style.display = 'none';
                    if (isVideo) {
                        placeholder.classList.remove('d-none');
                        placeholder.style.display = 'block';
                    }
                }
                applyLiveFilters();
            }
        });

        document.querySelectorAll('.form-range').forEach(slider => {
            slider.addEventListener('input', applyLiveFilters);
        });
    }

    // === 4. КНОПКА СБРОСА ===
    if (resetBtn) {
        resetBtn.addEventListener('click', function() {
            const defaults = {
                'brightness_beta': 15,
                'contrast_alpha': 1.15,
                'saturation_factor': 1.3,
                'denoise_h': 15.0,
                'sharpness_factor': 1.0
            };
            for (let id in defaults) {
                const slider = document.getElementById(id);
                if (slider) slider.value = defaults[id];
            }
            applyLiveFilters();
        });
    }

    // === 5. СЛАЙДЕР СРАВНЕНИЯ (ДО/ПОСЛЕ) ===
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
});