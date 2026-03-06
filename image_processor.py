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

class DS_conv(nn.Module):
    def __init__(self, in_ch, out_ch):
        super(DS_conv, self).__init__()
        self.depth_conv = nn.Conv2d(in_ch, in_ch, kernel_size=3, stride=1, padding=1, groups=in_ch)
        self.point_conv = nn.Conv2d(in_ch, out_ch, kernel_size=1, stride=1, padding=0)

    def forward(self, x):
        return self.point_conv(self.depth_conv(x))

class DCENet_pp(nn.Module):
    def __init__(self):
        super(DCENet_pp, self).__init__()
        self.e_conv1 = DS_conv(3, 32)
        self.e_conv2 = DS_conv(32, 32)
        self.e_conv3 = DS_conv(32, 32)
        self.e_conv4 = DS_conv(32, 32)
        self.e_conv5 = DS_conv(64, 32)
        self.e_conv6 = DS_conv(64, 32)
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

class LayerNorm2d(nn.Module):
    def __init__(self, channels, eps=1e-6):
        super(LayerNorm2d, self).__init__()
        self.register_parameter('weight', nn.Parameter(torch.ones(channels)))
        self.register_parameter('bias', nn.Parameter(torch.zeros(channels)))
        self.eps = eps

    def forward(self, x):
        u = x.mean(1, keepdim=True)
        s = (x - u).pow(2).mean(1, keepdim=True)
        x = (x - u) / torch.sqrt(s + self.eps)
        x = x * self.weight.view(1, -1, 1, 1) + self.bias.view(1, -1, 1, 1)
        return x

class SimpleGate(nn.Module):
    def forward(self, x):
        x1, x2 = x.chunk(2, dim=1)
        return x1 * x2

class NAFBlock(nn.Module):
    def __init__(self, c):
        super().__init__()
        dw_channel = c * 2
        self.norm1 = LayerNorm2d(c)
        self.conv1 = nn.Conv2d(c, dw_channel, 1, padding=0, stride=1)
        self.conv2 = nn.Conv2d(dw_channel, dw_channel, 3, padding=1, stride=1, groups=dw_channel)
        self.conv3 = nn.Conv2d(dw_channel // 2, c, 1, padding=0, stride=1)
        self.sg = SimpleGate()

        self.sca = nn.Sequential(
            nn.AdaptiveAvgPool2d(1),
            nn.Conv2d(c, c, 1, padding=0, stride=1)
        )
        
        self.norm2 = LayerNorm2d(c)
        self.conv4 = nn.Conv2d(c, dw_channel, 1, padding=0, stride=1)
        self.conv5 = nn.Conv2d(dw_channel // 2, c, 1, padding=0, stride=1)

        self.beta = nn.Parameter(torch.zeros((1, c, 1, 1)), requires_grad=True)
        self.gamma = nn.Parameter(torch.zeros((1, c, 1, 1)), requires_grad=True)

    def forward(self, inp):
        x = self.norm1(inp)
        x = self.conv1(x)
        x = self.conv2(x)
        x = self.sg(x)
        
        x = x * self.sca(x)
        x = self.conv3(x)
        
        y = inp + x * self.beta

        x = self.norm2(y)
        x = self.conv4(x)
        x = self.sg(x)
        x = self.conv5(x)
        
        return y + x * self.gamma

class NAFNet(nn.Module):
    def __init__(self, width=32, enc_blk_nums=[2, 2, 4, 8], middle_blk_num=12, dec_blk_nums=[2, 2, 2, 2]):
        super().__init__()
        self.intro = nn.Conv2d(3, width, 3, padding=1)
        self.ending = nn.Conv2d(width, 3, 3, padding=1)

        self.encoders = nn.ModuleList()
        self.decoders = nn.ModuleList()
        self.middle_blks = nn.ModuleList()
        self.ups = nn.ModuleList()
        self.downs = nn.ModuleList()

        chan = width
        for n in enc_blk_nums:
            self.encoders.append(nn.Sequential(*[NAFBlock(chan) for _ in range(n)]))
            self.downs.append(nn.Conv2d(chan, chan * 2, 2, 2))
            chan *= 2

        self.middle_blks = nn.Sequential(*[NAFBlock(chan) for _ in range(middle_blk_num)])

        for n in dec_blk_nums:
            self.ups.append(nn.Sequential(nn.Conv2d(chan, chan * 2, 1), nn.PixelShuffle(2)))
            chan //= 2
            self.decoders.append(nn.Sequential(*[NAFBlock(chan) for _ in range(n)]))

    def forward(self, inp):
        x = self.intro(inp)
        enc_feats = []
        for enc, down in zip(self.encoders, self.downs):
            x = enc(x)
            enc_feats.append(x)
            x = down(x)

        x = self.middle_blks(x)

        for decoder, up, enc_feat in zip(self.decoders, self.ups, reversed(enc_feats)):
            x = up(x)
            
            if x.shape[2:] != enc_feat.shape[2:]:
                x = F.interpolate(x, size=enc_feat.shape[2:], mode='bilinear', align_corners=False)
            
            x = x + enc_feat
            
            x = decoder(x)

        return self.ending(x) + inp

def enhance_image_ai(image_data, model_path='models/zero_dce_pp.pth', denoise_path='models/nafnet_denoiser.pth'):
    try:
        image_data.seek(0)
        nparr = np.frombuffer(image_data.read(), np.uint8)
        img_cv2 = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if img_cv2 is None: return None

        device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')

        model = DCENet_pp().to(device)
        model.load_state_dict(torch.load(model_path, map_location=device))
        model.eval()

        img_rgb = cv2.cvtColor(img_cv2, cv2.COLOR_BGR2RGB)
        data_lowlight = img_rgb.astype(np.float32) / 255.0
        data_lowlight = torch.from_numpy(data_lowlight).permute(2, 0, 1).unsqueeze(0).to(device)

        with torch.no_grad():
            A = model(data_lowlight)
            enhanced_img = data_lowlight
            for _ in range(8):
                enhanced_img = enhanced_img + A * (torch.pow(enhanced_img, 2) - enhanced_img)
            enhanced_img = torch.clamp(enhanced_img, 0, 1)

        # 4. Прогон через NAFNet (Удаление шума)
        dn_model = NAFNet(width=32).to(device)
        checkpoint = torch.load(denoise_path, map_location=device)
        
        state_dict = checkpoint['params'] if 'params' in checkpoint else checkpoint
        dn_model.load_state_dict(state_dict, strict=False)
        dn_model.eval()

        with torch.no_grad():
            _, _, h, w = enhanced_img.size()

            pad_h = (8 - h % 8) % 8
            pad_w = (8 - w % 8) % 8

            input_padded = F.pad(enhanced_img, (0, pad_w, 0, pad_h), mode='reflect')

            final_tensor = dn_model(input_padded)

            final_tensor = final_tensor[:, :, :h, :w]
            
            final_tensor = torch.clamp(final_tensor, 0, 1)

        result = final_tensor.squeeze().permute(1, 2, 0).cpu().numpy()
        result = (result * 255).astype(np.uint8)
        final_img = cv2.cvtColor(result, cv2.COLOR_RGB2BGR)

        final_img = cv2.filter2D(final_img, -1, DEFAULT_SHARPENING_KERNEL)

        is_success, buffer = cv2.imencode(".jpg", final_img)
        return io.BytesIO(buffer) if is_success else None
        
    except Exception as e:
        print(f"Ошибка каскадного AI процессора: {e}")
        return None