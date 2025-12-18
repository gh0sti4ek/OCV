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
DEFAULT_SHARPNESS_FACTOR = 1.0

# Denoising (Удаление шума)
DEFAULT_DENOISE_H = 15.0
DEFAULT_DENOISE_H_COLOR = 10.0
DEFAULT_DENOISE_TEMPLATE_WINDOW_SIZE = 7
DEFAULT_DENOISE_SEARCH_WINDOW_SIZE = 21

# Настройка для Усиления Насыщенности
DEFAULT_SATURATION_FACTOR = 1.3

# Настройка для ГЛОБАЛЬНОГО Контраста и Яркости
DEFAULT_CONTRAST_ALPHA = 1.15
DEFAULT_BRIGHTNESS__BETA = 15


def enhance_low_light_clahe(image_data, denoise_h, saturation_factor, sharpness_factor, contrast_alpha,
                            brightness_beta):
    """ТВОЯ ОРИГИНАЛЬНАЯ ФУНКЦИЯ ДЛЯ ФОТО (БЕЗ ИЗМЕНЕНИЙ)"""
    try:
        nparr = np.frombuffer(image_data.read(), np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

        if img is None:
            return None

        # --- БЛОК 1: Улучшение ЯРКОСТИ (CLAHE) ---
        lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
        l, a, b = cv2.split(lab)
        clahe = cv2.createCLAHE(clipLimit=DEFAULT_CLIP_LIMIT, tileGridSize=(8, 8))
        cl = clahe.apply(l)
        limg = cv2.merge((cl, a, b))
        clahe_img = cv2.cvtColor(limg, cv2.COLOR_LAB2BGR)

        # --- БЛОК 2: УДАЛЕНИЕ ШУМА ---
        denoised_img = cv2.fastNlMeansDenoisingColored(
            clahe_img, None, int(denoise_h), int(denoise_h / 2),
            DEFAULT_DENOISE_TEMPLATE_WINDOW_SIZE, DEFAULT_DENOISE_SEARCH_WINDOW_SIZE
        )

        # --- БЛОК 3: УСИЛЕНИЕ НАСЫЩЕННОСТИ ---
        hsv_img = cv2.cvtColor(denoised_img, cv2.COLOR_BGR2HSV)
        h, s, v = cv2.split(hsv_img)
        s_enhanced = np.clip(s.astype(np.float32) * saturation_factor, 0, 255).astype(np.uint8)
        saturated_img = cv2.merge((h, s_enhanced, v))
        saturated_bgr = cv2.cvtColor(saturated_img, cv2.COLOR_HSV2BGR)

        # --- БЛОК 4: Улучшение ЧЁТКОСТИ ---
        sharpening_kernel = (DEFAULT_SHARPENING_KERNEL * sharpness_factor) + (1.0 - sharpness_factor) * np.array([
            [0, 0, 0], [0, 1, 0], [0, 0, 0]
        ])
        sharpened_img = cv2.filter2D(saturated_bgr, -1, sharpening_kernel)

        # --- БЛОК 5: ГЛОБАЛЬНЫЙ КОНТРАСТ И ЯРКОСТЬ ---
        final_img = cv2.convertScaleAbs(sharpened_img, alpha=contrast_alpha, beta=int(brightness_beta))

        is_success, buffer = cv2.imencode(".jpg", final_img)
        if is_success:
            return io.BytesIO(buffer)
        return None
    except Exception as e:
        print(f"Ошибка в image_processor (фото): {e}")
        return None


def process_video(input_path, output_path, denoise_h, saturation_factor, sharpness_factor, contrast_alpha,
                  brightness_beta):
    """НОВАЯ ФУНКЦИЯ ДЛЯ ВИДЕО С ТВОЕЙ ЛОГИКОЙ"""
    try:
        cap = cv2.VideoCapture(input_path)
        fps = cap.get(cv2.CAP_PROP_FPS)
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

        # Используем кодек mp4v для совместимости с .mp4
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        out = cv2.VideoWriter(output_path, fourcc, fps, (width, height))

        while cap.isOpened():
            ret, frame = cap.read()
            if not ret: break

            # 1. CLAHE
            lab = cv2.cvtColor(frame, cv2.COLOR_BGR2LAB)
            l, a, b = cv2.split(lab)
            clahe = cv2.createCLAHE(clipLimit=DEFAULT_CLIP_LIMIT, tileGridSize=(8, 8))
            cl = clahe.apply(l)
            frame = cv2.cvtColor(cv2.merge((cl, a, b)), cv2.COLOR_LAB2BGR)

            # 2. ШУМ (Для видео шум — это долго, но делаем как в оригинале)
            if denoise_h > 0:
                frame = cv2.fastNlMeansDenoisingColored(
                    frame, None, int(denoise_h), int(denoise_h / 2),
                    DEFAULT_DENOISE_TEMPLATE_WINDOW_SIZE, DEFAULT_DENOISE_SEARCH_WINDOW_SIZE
                )

            # 3. НАСЫЩЕННОСТЬ
            hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
            h, s, v = cv2.split(hsv)
            s_enhanced = np.clip(s.astype(np.float32) * saturation_factor, 0, 255).astype(np.uint8)
            frame = cv2.cvtColor(cv2.merge((h, s_enhanced, v)), cv2.COLOR_HSV2BGR)

            # 4. РЕЗКОСТЬ
            sk = (DEFAULT_SHARPENING_KERNEL * sharpness_factor) + (1.0 - sharpness_factor) * np.array(
                [[0, 0, 0], [0, 1, 0], [0, 0, 0]])
            frame = cv2.filter2D(frame, -1, sk)

            # 5. КОНТРАСТ И ЯРКОСТЬ
            frame = cv2.convertScaleAbs(frame, alpha=contrast_alpha, beta=int(brightness_beta))

            out.write(frame)

        cap.release()
        out.release()
        return True
    except Exception as e:
        print(f"Ошибка в видео-процессоре: {e}")
        return False