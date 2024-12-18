from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from yt_dlp import YoutubeDL
from pydub import AudioSegment
from pytubefix import YouTube
from pydantic import BaseModel
import requests
import os
import subprocess
import re
import shutil
import base64

app = FastAPI()
app.mount("/static", StaticFiles(directory="video_output"), name="static")

# Настройка CORS
origins = [
    "http://localhost:3000",  # URL фронтенда
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

STEOSVOICE_API_KEY = "3b0537a8-0b32-4e68-b4a8-4c3ca1e93466"
STEOSVOICE_API_URL = f"https://public.api.voice.steos.io/api/v1/synthesize-controller/synthesis-by-text?authToken={STEOSVOICE_API_KEY}"

class VideoRequest(BaseModel):
    youtube_url: str
    voice: str

@app.post("/process_video/", response_model=dict)
async def process_video(request: VideoRequest):
    youtube_url = request.youtube_url
    voice = request.voice
    
    ydl_opts = {
        'format': 'worstvideo[height<=480]+bestaudio/best[height<=480]',
        'writesubtitles': True,
        'subtitleslangs': ['ru'],  # Указание языка субтитров
        'skip_download': True,
        'cookies': 'E:\proj\www.youtube.com_cookies (3).txt',      # Путь к файлу с куки
        'force_generic_extractor': True,
        'http_headers': {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.5993.54 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'ru,en;q=0.5',
            'Sec-Fetch-Mode': 'navigate',},
        'verbose': True,
    }

    try:
        # Шаг 1: Загрузка субтитров
        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(youtube_url, download=False)
            if 'requested_subtitles' not in info or 'ru' not in info['requested_subtitles']:
                raise HTTPException(status_code=400, detail="Русские субтитры недоступны.")
            subtitles_url = info['requested_subtitles']['ru']['url']
            response = requests.get(subtitles_url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"})
            subtitles = response.text

        # Шаг 2: Генерация озвучки через SteosVoice
        AUDIO_OUTPUT_DIR = "generated_audio"
        if os.path.exists(AUDIO_OUTPUT_DIR):
            shutil.rmtree(AUDIO_OUTPUT_DIR)
        os.makedirs(AUDIO_OUTPUT_DIR)

        audio_files = []
        for line in parse_subtitles(subtitles):
            response = requests.post(
                STEOSVOICE_API_URL,
                headers={"Authorization": f"Bearer {STEOSVOICE_API_KEY}"},
                json={"voiceId": voice, "text": line["text"]}
            )
            answer = response.json()
            decoded_bytes = base64.b64decode(answer["fileContents"])
            safe_start = line["start"].replace(":", "-")
            audio_file = os.path.join(AUDIO_OUTPUT_DIR, f"audio_{safe_start}.mp3")
            with open(audio_file, "wb") as f:
                f.write(decoded_bytes)
            
            audio_files.append((line['start'], audio_file))

        # Шаг 3: Объединение аудио и синхронизация
        final_audio = merge_audio(subtitles)

        # Шаг 4: Объединение аудио с видео
        video_path = download_video(youtube_url)
        output_video = "output.mp4"
        combine_audio_video(video_path, final_audio, output_video)

        output_video = os.path.join("video_output", "output.mp4")

        return {"message": "Видео успешно обработано", "output": f"/static/{os.path.basename(output_video)}"}
    except HTTPException as e:
        raise e
    except Exception as e:
        print("Неизвестная ошибка:", str(e))
        raise HTTPException(status_code=500, detail="Произошла ошибка при обработке видео.")
    
# Конвертация времени из формата HH:MM:SS.mmm в миллисекунды
def time_to_ms(time_str):
    h, m, s = map(float, time_str.split(":"))
    return int((h * 3600 + m * 60 + s) * 1000)

# Разделение субтитров на отдельные реплики
def parse_subtitles(subtitles_text):
    subtitle_pattern = re.compile(r"(\d{2}:\d{2}:\d{2}\.\d{3}) --> (\d{2}:\d{2}:\d{2}\.\d{3})\n(.*?)\n\n", re.DOTALL)
    matches = subtitle_pattern.findall(subtitles_text)
    parsed = []
    for start, end, text in matches:
        parsed.append({
            "start": start.strip(),
            "end": end.strip(),
            "text": text.replace("\n", " ").strip()
        })
    return parsed

# Соединение отдельных сгенерированных аудиофайлов с заполнением пустоты между ними
def merge_audio(subtitles_text):

    FINAL_AUDIO_OUTPUT_DIR = "final_audio"
    if os.path.exists(FINAL_AUDIO_OUTPUT_DIR):
        shutil.rmtree(FINAL_AUDIO_OUTPUT_DIR)
    os.makedirs(FINAL_AUDIO_OUTPUT_DIR)

    a = "E:\proj\generated_audio\\"
    b = os.listdir("E:\proj\generated_audio")
    audio_files = list()
    for i in b:
        audio_files.append(a + i)

    combined = AudioSegment.empty()

    # Парсинг субтитров
    subtitles = parse_subtitles(subtitles_text)

    # Проверка соответствия количества аудиофайлов и субтитров
    if len(audio_files) != len(subtitles):
        raise HTTPException(
            status_code=500,
            detail=f"Количество аудиофайлов ({len(audio_files)}) не соответствует количеству субтитров ({len(subtitles)})."
        )

    for idx, (audio_file, subtitle) in enumerate(zip(audio_files, subtitles)):
        if not os.path.exists(audio_file):
            raise HTTPException(status_code=500, detail=f"Аудиофайл {audio_file} не найден.")

        # Загружается аудиофайл
        audio = AudioSegment.from_file(audio_file)

        # Вычисляется время начала и конца субтитров
        subtitle_start = time_to_ms(subtitle['start'])
        subtitle_end = time_to_ms(subtitle['end'])

        # Вычисляется текущая позиция в аудио
        current_duration = len(combined)

        # Добавляется тишина, если начало субтитров больше текущего времени
        if subtitle_start > current_duration:
            silence_duration = subtitle_start - current_duration
            combined += AudioSegment.silent(duration=silence_duration)

        # Добавляется аудиофайл
        combined += audio

        # Добавляется тишина, если аудиотрек короче времени конца субтитров
        audio_end = current_duration + len(audio)
        if audio_end < subtitle_end:
            silence_duration = subtitle_end - audio_end
            combined += AudioSegment.silent(duration=silence_duration)

    # Проверк, что итоговый файл соответствует времени конца субтитров
    final_end_time = time_to_ms(subtitles[-1]['end'])
    if len(combined) < final_end_time:
        silence_duration = final_end_time - len(combined)
        combined += AudioSegment.silent(duration=silence_duration)

    final_audio_path = os.path.join(FINAL_AUDIO_OUTPUT_DIR, "final_audio.mp3")
    combined.export(final_audio_path, format="mp3")

    return final_audio_path

# Скачивание видео
def download_video(url):
    output_dir = "output"
    if os.path.exists(output_dir):
        shutil.rmtree(output_dir)
    os.makedirs(output_dir)
    
    yt = YouTube(url)
    video_stream = yt.streams.filter(progressive=True, file_extension="mp4").order_by("resolution").desc().first()
    video_path = video_stream.download(output_dir)
    return video_path

# Комбинация аудио и видео ряда
def combine_audio_video(video_path, audio_path, output_path):
    VIDEO_OUTPUT_DIR = "video_output"
    if os.path.exists(VIDEO_OUTPUT_DIR):
        shutil.rmtree(VIDEO_OUTPUT_DIR)
    os.makedirs(VIDEO_OUTPUT_DIR)

    if not os.path.exists(video_path):
        raise HTTPException(status_code=500, detail="Видео файл не найден.")
    if not os.path.exists(audio_path):
        raise HTTPException(status_code=500, detail="Аудио файл не найден.")
    output_path = os.path.join(VIDEO_OUTPUT_DIR, output_path)
    command = [
        "ffmpeg",
        "-i", video_path,
        "-i", audio_path,
        "-map", "0:v:0",
        "-map", "1:a:0",
        "-c:v", "copy",
        "-c:a", "aac",
        "-b:a", "192k",
        "-shortest",
        output_path
    ]
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        raise HTTPException(status_code=500, detail=f"Ошибка FFmpeg: {result.stderr}")