# Настройка параметров фото/видео

import cv2
import numpy as np
import io
import torch
import torch.nn as nn
import torch.nn.functional as F


# CLAHE (яркость)
DEFAULT_CLIP_LIMIT = 4.0

# Резкость
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

# Насыщенность
DEFAULT_SATURATION_FACTOR = 1.3

# Глобальный контраст и яркость
DEFAULT_CONTRAST_ALPHA = 1.15
DEFAULT_BRIGHTNESS__BETA = 15


def enhance_low_light_clahe(image_data, denoise_h, saturation_factor, sharpness_factor, contrast_alpha,
                            brightness_beta):
    """Функция обработки фотографий"""
    try:
        nparr = np.frombuffer(image_data.read(), np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

        if img is None:
            return None

        # БЛОК 1: Улучшение Яркости
        lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
        l, a, b = cv2.split(lab)
        clahe = cv2.createCLAHE(clipLimit=DEFAULT_CLIP_LIMIT, tileGridSize=(8, 8))
        cl = clahe.apply(l)
        limg = cv2.merge((cl, a, b))
        clahe_img = cv2.cvtColor(limg, cv2.COLOR_LAB2BGR)

        # БЛОК 2: Удаление Шума
        denoised_img = cv2.fastNlMeansDenoisingColored(
            clahe_img, None, int(denoise_h), int(denoise_h / 2),
            DEFAULT_DENOISE_TEMPLATE_WINDOW_SIZE, DEFAULT_DENOISE_SEARCH_WINDOW_SIZE
        )

        # БЛОК 3: Усиление Насыщенности
        hsv_img = cv2.cvtColor(denoised_img, cv2.COLOR_BGR2HSV)
        h, s, v = cv2.split(hsv_img)
        s_enhanced = np.clip(s.astype(np.float32) * saturation_factor, 0, 255).astype(np.uint8)
        saturated_img = cv2.merge((h, s_enhanced, v))
        saturated_bgr = cv2.cvtColor(saturated_img, cv2.COLOR_HSV2BGR)

        # БЛОК 4: Улучшение Чёткости
        sharpening_kernel = (DEFAULT_SHARPENING_KERNEL * sharpness_factor) + (1.0 - sharpness_factor) * np.array([
            [0, 0, 0], [0, 1, 0], [0, 0, 0]
        ])
        sharpened_img = cv2.filter2D(saturated_bgr, -1, sharpening_kernel)

        # БЛОК 5: Глобальные Контраст, Яркость
        final_img = cv2.convertScaleAbs(sharpened_img, alpha=contrast_alpha, beta=int(brightness_beta))

        is_success, buffer = cv2.imencode(".jpg", final_img)
        if is_success:
            return io.BytesIO(buffer)
        return None
    except Exception as e:
        print(f"Ошибка в image_processor (фото): {e}")
        return None

def resize_video_if_needed(input_path, output_path, target_height=720):
    cap = cv2.VideoCapture(input_path)
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = cap.get(cv2.CAP_PROP_FPS)

    # Если видео уже подходит под лимит, сжимать не нужно
    if height <= target_height:
        cap.release()
        return False

    # Считаем новые размеры с сохранением пропорций
    new_h = target_height
    new_w = int(width * (new_h / height))
    
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    out = cv2.VideoWriter(output_path, fourcc, fps, (new_w, new_h))

    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break
        resized = cv2.resize(frame, (new_w, new_h), interpolation=cv2.INTER_AREA)
        out.write(resized)

    cap.release()
    out.release()
    return True

def process_video(input_path, output_path, denoise_h, saturation_factor, sharpness_factor, contrast_alpha,
                  brightness_beta):
    """Функция обработки видео"""
    try:
        cap = cv2.VideoCapture(input_path)
        fps = cap.get(cv2.CAP_PROP_FPS)
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        out = cv2.VideoWriter(output_path, fourcc, fps, (width, height))

        while cap.isOpened():
            ret, frame = cap.read()
            if not ret: break

            # 1. БЛОК 1: Улучшение Яркости
            lab = cv2.cvtColor(frame, cv2.COLOR_BGR2LAB)
            l, a, b = cv2.split(lab)
            clahe = cv2.createCLAHE(clipLimit=DEFAULT_CLIP_LIMIT, tileGridSize=(8, 8))
            cl = clahe.apply(l)
            frame = cv2.cvtColor(cv2.merge((cl, a, b)), cv2.COLOR_LAB2BGR)

            # БЛОК 2: Удаление Шума
            if denoise_h > 0:
                frame = cv2.fastNlMeansDenoisingColored(
                    frame, None, int(denoise_h), int(denoise_h / 2),
                    DEFAULT_DENOISE_TEMPLATE_WINDOW_SIZE, DEFAULT_DENOISE_SEARCH_WINDOW_SIZE
                )

            # БЛОК 3: Усиление Насыщенности
            hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
            h, s, v = cv2.split(hsv)
            s_enhanced = np.clip(s.astype(np.float32) * saturation_factor, 0, 255).astype(np.uint8)
            frame = cv2.cvtColor(cv2.merge((h, s_enhanced, v)), cv2.COLOR_HSV2BGR)

            # БЛОК 4: Улучшение Чёткости
            sk = (DEFAULT_SHARPENING_KERNEL * sharpness_factor) + (1.0 - sharpness_factor) * np.array(
                [[0, 0, 0], [0, 1, 0], [0, 0, 0]])
            frame = cv2.filter2D(frame, -1, sk)

            # БЛОК 5: Глобальные Контраст, Яркость
            frame = cv2.convertScaleAbs(frame, alpha=contrast_alpha, beta=int(brightness_beta))

            out.write(frame)

        cap.release()
        out.release()
        return True
    except Exception as e:
        print(f"Ошибка в видео-процессоре: {e}")
        return False

# Описание архитектуры Zero-DCE++ (те самые Depthwise Separable Convolutions)
class DS_conv(nn.Module):
    def __init__(self, in_channels, out_channels):
        super(DS_conv, self).__init__()
        # Глубинная свертка (Depthwise)
        self.depth_conv = nn.Conv2d(in_channels, in_channels, kernel_size=3, padding=1, groups=in_channels)
        # Точечная свертка (Pointwise)
        self.point_conv = nn.Conv2d(in_channels, out_channels, kernel_size=1)

    def forward(self, x):
        out = self.depth_conv(x)
        out = self.point_conv(out)
        return out

class DCENet_pp(nn.Module):
    def __init__(self):
        super(DCENet_pp, self).__init__()
        self.e_conv1 = DS_conv(3, 32)
        self.e_conv2 = DS_conv(32, 32)
        self.e_conv3 = DS_conv(32, 32)
        self.e_conv4 = DS_conv(32, 32)
        self.e_conv5 = DS_conv(64, 32)
        self.e_conv6 = DS_conv(64, 32)
        # ИСПРАВЛЕНО: здесь должно быть 3, а не 24
        self.e_conv7 = DS_conv(64, 3) 

    def forward(self, x):
        x1 = F.relu(self.e_conv1(x))
        x2 = F.relu(self.e_conv2(x1))
        x3 = F.relu(self.e_conv3(x2))
        x4 = F.relu(self.e_conv4(x3))
        x5 = F.relu(self.e_conv5(torch.cat([x3, x4], 1)))
        x6 = F.relu(self.e_conv6(torch.cat([x2, x5], 1)))
        extract_feature = torch.tanh(self.e_conv7(torch.cat([x1, x6], 1)))
        return extract_feature

# Функция для применения AI-улучшения
def enhance_image_ai(image_data, model_path='models/zero_dce_pp.pth'):
    """Функция обработки фото: Zero-DCE++ + Denoise + Sharpening"""
    try:
        # 1. Декодируем входящие данные
        nparr = np.frombuffer(image_data.read(), np.uint8)
        img_cv2 = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if img_cv2 is None: return None

        # 2. Настройка нейросети
        device = torch.device('cpu')
        model = DCENet_pp().to(device)
        model.load_state_dict(torch.load(model_path, map_location=device))
        model.eval()

        # 3. Подготовка тензора
        img_rgb = cv2.cvtColor(img_cv2, cv2.COLOR_BGR2RGB)
        data_lowlight = img_rgb.astype(np.float32) / 255.0
        data_lowlight = torch.from_numpy(data_lowlight).permute(2, 0, 1).unsqueeze(0).to(device)

        # 4. Прогон через нейронку (улучшение освещения)
        with torch.no_grad():
            A = model(data_lowlight)
            enhanced_img = data_lowlight
            for i in range(8):
                enhanced_img = enhanced_img + A * (torch.pow(enhanced_img, 2) - enhanced_img)

        # 5. Конвертация обратно в OpenCV формат
        result = enhanced_img.squeeze().permute(1, 2, 0).cpu().numpy()
        result = (result * 255).clip(0, 255).astype(np.uint8)
        result_bgr = cv2.cvtColor(result, cv2.COLOR_RGB2BGR)

        # --- НОВЫЙ БЛОК: ОЧИСТКА ОТ ШУМА ---
        # fastNlMeansDenoisingColored — один из лучших методов для фото.
        # h=10 — сила очистки. Если шума всё ещё много, можно поднять до 12-15.
        denoised_img = cv2.fastNlMeansDenoisingColored(
            result_bgr, 
            None, 
            h=10, 
            hColor=10, 
            templateWindowSize=7, 
            searchWindowSize=21
        )

        # --- НОВЫЙ БЛОК: ВОЗВРАТ РЕЗКОСТИ ---
        # После денойза края могут размыться, добавим легкую резкость
        sharpen_kernel = np.array([
            [0, -1, 0],
            [-1, 5, -1],
            [0, -1, 0]
        ])
        final_img = cv2.filter2D(denoised_img, -1, sharpen_kernel)

        # 6. Кодируем в JPEG
        is_success, buffer = cv2.imencode(".jpg", final_img)
        if is_success:
            return io.BytesIO(buffer)
        return None
        
    except Exception as e:
        print(f"Ошибка AI процессора: {e}")
        return None