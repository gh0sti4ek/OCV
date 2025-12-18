# image_processor.py

import cv2
import numpy as np
import io

# --- СТАНДАРТНЫЕ/ОПТИМАЛЬНЫЕ НАСТРОЙКИ (Используются как значения по умолчанию) ---

# CLAHE (яркость/контрастность локально)
DEFAULT_CLIP_LIMIT = 4.0

# Резкость (Ядро будет применяться с силой sharpness_factor)
DEFAULT_SHARPENING_KERNEL = np.array([
    [0, -1, 0],
    [-1, 5, -1],
    [0, -1, 0]
])
DEFAULT_SHARPNESS_FACTOR = 1.0  # Это наш новый множитель для ядра

# Denoising (Удаление шума)
DEFAULT_DENOISE_H = 15.0  # Сильное удаление шума
DEFAULT_DENOISE_H_COLOR = 10.0
DEFAULT_DENOISE_TEMPLATE_WINDOW_SIZE = 7
DEFAULT_DENOISE_SEARCH_WINDOW_SIZE = 21

# Настройка для Усиления Насыщенности
DEFAULT_SATURATION_FACTOR = 1.3

# Настройка для ГЛОБАЛЬНОГО Контраста и Яркости
DEFAULT_CONTRAST_ALPHA = 1.15
DEFAULT_BRIGHTNESS_BETA = 15


def enhance_low_light_clahe(image_data, denoise_h, saturation_factor, sharpness_factor, contrast_alpha,
                            brightness_beta):
    """
    Выполняет комплексную обработку изображения, используя ПЕРЕДАННЫЕ параметры.

    :param image_data: Поток байтов (io.BytesIO) с данными изображения.
    :param denoise_h: Интенсивность шумоподавления (0.0 - 20.0).
    :param saturation_factor: Множитель насыщенности (0.5 - 2.0).
    :param sharpness_factor: Множитель силы резкости (0.0 - 3.0).
    :param contrast_alpha: Глобальный множитель контраста (1.0 - 3.0).
    :param brightness_beta: Глобальная добавка яркости (-100 - 100).
    :return: io.BytesIO с обработанным изображением в формате JPEG или None.
    """


    try:
        # 1. Чтение данных
        nparr = np.frombuffer(image_data.read(), np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

        if img is None:
            return None

        # --- БЛОК 1: Улучшение ЯРКОСТИ (CLAHE) ---
        lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
        l, a, b = cv2.split(lab)
        # CLAHE всегда используется с фиксированным лимитом, чтобы избежать "выгорания"
        clahe = cv2.createCLAHE(clipLimit=DEFAULT_CLIP_LIMIT, tileGridSize=(8, 8))
        cl = clahe.apply(l)
        limg = cv2.merge((cl, a, b))
        clahe_img = cv2.cvtColor(limg, cv2.COLOR_LAB2BGR)

        # --- БЛОК 2: УДАЛЕНИЕ ШУМА (Non-Local Means) ---
        # Используем переданный denoise_h
        denoised_img = cv2.fastNlMeansDenoisingColored(
            clahe_img,
            None,
            int(denoise_h),  # <= Использование пользовательского параметра
            int(denoise_h / 2),  # H_COLOR обычно меньше H
            DEFAULT_DENOISE_TEMPLATE_WINDOW_SIZE,
            DEFAULT_DENOISE_SEARCH_WINDOW_SIZE
        )

        # --- БЛОК 3: УСИЛЕНИЕ НАСЫЩЕННОСТИ ЦВЕТА ---
        hsv_img = cv2.cvtColor(denoised_img, cv2.COLOR_BGR2HSV)
        h, s, v = cv2.split(hsv_img)
        # Используем переданный saturation_factor
        s_enhanced = np.clip(s.astype(np.float32) * saturation_factor, 0, 255).astype(
            np.uint8)  # <= Использование пользовательского параметра
        saturated_img = cv2.merge((h, s_enhanced, v))
        saturated_bgr = cv2.cvtColor(saturated_img, cv2.COLOR_HSV2BGR)

        # --- БЛОК 4: Улучшение ЧЁТКОСТИ (Фильтр) ---
        # Динамически создаем ядро на основе sharpness_factor
        sharpening_kernel = (DEFAULT_SHARPENING_KERNEL * sharpness_factor) + (1.0 - sharpness_factor) * np.array([
            [0, 0, 0],
            [0, 1, 0],
            [0, 0, 0]
        ])
        sharpened_img = cv2.filter2D(saturated_bgr, -1,
                                     sharpening_kernel)  # <= Использование пользовательского параметра

        # --- БЛОК 5: ГЛОБАЛЬНЫЙ КОНТРАСТ И ЯРКОСТЬ ---
        final_img = cv2.convertScaleAbs(
            sharpened_img,
            alpha=contrast_alpha,  # <= Использование пользовательского параметра
            beta=int(brightness_beta)  # <= Использование пользовательского параметра
        )

        # 6. Сохранение результата в буфер (JPEG)
        is_success, buffer = cv2.imencode(".jpg", final_img)

        if is_success:
            return io.BytesIO(buffer)
        else:
            return None

    except Exception as e:
        # Для отладки лучше выводить в консоль
        print(f"Ошибка в image_processor: {e}")
        return None