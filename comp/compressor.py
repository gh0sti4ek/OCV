import cv2

def compress_video(input_path, output_path):
    cap = cv2.VideoCapture(input_path)

    new_h = 720
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    new_w = int(width * (new_h / height))
    
    # Настройка кодека и записи
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    out = cv2.VideoWriter(output_path, fourcc, 30.0, (new_w, new_h))

    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break
        resized = cv2.resize(frame, (new_w, new_h))
        out.write(resized)

    cap.release()
    out.release()
    print("Готово! Видео сжато до 720p.")

compress_video('12.mp4', 'test_720p.mp4')