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

        // Визуальная симуляция через CSS
        const brightCSS = (100 + parseInt(b)) / 100;
        const blurCSS = d / 40;
        imagePreview.style.filter = `brightness(${brightCSS}) contrast(${c}) saturate(${s}) blur(${blurCSS}px)`;
    }

    // === 3. ЛОГИКА ЗАГРУЗКИ И ОТОБРАЖЕНИЯ ФАЙЛА ===
    if (fileInput && imagePreview) {
        fileInput.addEventListener('change', function() {
            const file = this.files[0];
            if (file) {
                const reader = new FileReader();
                reader.onload = function(e) {
                    // Устанавливаем фото
                    imagePreview.src = e.target.result;

                    // ГАРАНТИРОВАННО ПОКАЗЫВАЕМ (убираем d-none и форсируем display)
                    imagePreview.classList.remove('d-none');
                    imagePreview.style.display = 'block';

                    // Скрываем плейсхолдер
                    if (placeholder) {
                        placeholder.classList.add('d-none');
                        placeholder.style.display = 'none';
                    }

                    applyLiveFilters();
                }
                reader.readAsDataURL(file);
            }
        });

        // Слушаем ползунки
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
    // Эта часть отвечает за страницу compare.html
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
        syncSlider(); // Инициализация при загрузке
    }
});