document.addEventListener('DOMContentLoaded', function() {
    // === 1. Предпросмотр выбранного файла ===
    const fileInput = document.getElementById('fileInput');
    const imagePreview = document.getElementById('imagePreview');
    const placeholder = document.getElementById('previewPlaceholder');

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

    // === 2. Слайдер сравнения (До/После) ===
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

    // === 3. Переключатель описания методов (AI / CLAHE) ===
    const aiSwitch = document.getElementById('use_ai');
    const faceSwitch = document.getElementById('enhance_faces');
    const faceWrapper = document.getElementById('faceEnhanceWrapper');
    const desc = document.getElementById('methodDescription');

    if (aiSwitch && desc) {
        aiSwitch.addEventListener('change', function() {
            const isAi = this.checked;
            desc.innerText = isAi 
                ? "Метод Zero-DCE++: лучшее качество для очень темных кадров." 
                : "Алгоритм CLAHE: быстрая цифровая коррекция освещения.";
            
            // Скрываем/показываем выбор лиц
            if (faceWrapper) {
                faceWrapper.style.opacity = isAi ? "1" : "0.5";
                faceSwitch.disabled = !isAi;
            }
        });
    }

    // === 4. Асинхронное обновление статуса задач (Polling) ===
    const checkTaskStatus = async () => {
        // Ищем все элементы на странице, которые помечены как "в обработке"
        // Предполагается, что в HTML у таких карточек есть класс .task-processing 
        // и атрибут data-task-id
        const processingItems = document.querySelectorAll('.task-processing');

        if (processingItems.length === 0) return;

        for (let item of processingItems) {
            const taskId = item.getAttribute('data-task-id');
            if (!taskId) continue;

            try {
                const response = await fetch(`/task_status/${taskId}`);
                const data = await response.json();

                if (data.status === 'ready') {
                    // Если готово — просто перезагружаем страницу, чтобы увидеть результат
                    // Или можно точечно заменить контент через JS
                    window.location.reload();
                } else if (data.status === 'error') {
                    item.innerHTML = "<span class='text-danger'>Ошибка обработки</span>";
                    item.classList.remove('task-processing');
                }
            } catch (error) {
                console.error('Ошибка при проверке статуса:', error);
            }
        }
    };

    // Запускаем проверку каждые 3 секунды, если есть активные задачи
    if (document.querySelectorAll('.task-processing').length > 0) {
        setInterval(checkTaskStatus, 3000);
    }
});