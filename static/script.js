document.addEventListener('DOMContentLoaded', function() {
    // Поменяли название в логах, раз теперь проект OCV
    console.log("--- OCV: Инициализация ---");

    // === ЭЛЕМЕНТЫ ===
    const fileInput = document.getElementById('fileInput');
    const imagePreview = document.getElementById('imagePreview');
    const placeholder = document.getElementById('previewPlaceholder') || document.getElementById('previewText');
    const resetBtn = document.getElementById('resetSettings');

    // === ЧАСТЬ 1: ПРЕДПРОСМОТР И ЖИВЫЕ ФИЛЬТРЫ ===

    function applyLiveFilters() {
        if (!imagePreview) return;

        // Поиск элементов с проверкой на существование
        const elB = document.getElementById('brightness_beta');
        const elC = document.getElementById('contrast_alpha');
        const elS = document.getElementById('saturation_factor');
        const elD = document.getElementById('denoise_h');
        const elSh = document.getElementById('sharpness_factor');

        // Если ползунков нет на странице (например, в другом режиме), берем дефолты
        const b = elB ? elB.value : 15;
        const c = elC ? elC.value : 1.15;
        const s = elS ? elS.value : 1.3;
        const d = elD ? elD.value : 15.0;
        const sh = elSh ? elSh.value : 1.0;

        // Обновляем текст только если индикатор существует
        if(document.getElementById('brightnessValue')) document.getElementById('brightnessValue').innerText = b;
        if(document.getElementById('contrastValue')) document.getElementById('contrastValue').innerText = c;
        if(document.getElementById('saturationValue')) document.getElementById('saturationValue').innerText = s;
        if(document.getElementById('denoiseValue')) document.getElementById('denoiseValue').innerText = d;
        if(document.getElementById('sharpnessValue')) document.getElementById('sharpnessValue').innerText = sh;

        // Применяем визуальные эффекты
        const brightCSS = (100 + parseInt(b)) / 100;
        const blurCSS = d / 40;

        imagePreview.style.filter = `brightness(${brightCSS}) contrast(${c}) saturate(${s}) blur(${blurCSS}px)`;
    }

    // Логика загрузки файла (теперь универсальная)
    if (fileInput && imagePreview) {
        fileInput.addEventListener('change', function() {
            const file = this.files[0];
            if (file) {
                const reader = new FileReader();
                reader.onload = function(e) {
                    imagePreview.src = e.target.result;
                    imagePreview.classList.remove('d-none');
                    if (placeholder) placeholder.classList.add('d-none');
                    applyLiveFilters();
                }
                reader.readAsDataURL(file);
            }
        });

        // Слушаем изменения всех ползунков
        document.querySelectorAll('.form-range').forEach(slider => {
            slider.addEventListener('input', applyLiveFilters);
        });
    }

    // === ЛОГИКА КНОПКИ СБРОСА ===
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

    // === ЧАСТЬ 2: СЛАЙДЕР СРАВНЕНИЯ ===
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

        window.moveSlider = syncSlider;
        compSlider.addEventListener('input', syncSlider);
        window.addEventListener('resize', syncSlider);
        syncSlider();
    }
});