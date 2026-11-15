import os
import sys
import json
import subprocess
import requests
from groq import Groq
from google import genai

URL = sys.argv[1] if len(sys.argv) > 1 else None
if not URL:
    print("Erro: Nenhum link do YouTube foi fornecido.")
    sys.exit(1)

GROQ_KEY = os.environ.get("GROQ_API_KEY")
GEMINI_KEY = os.environ.get("GEMINI_API_KEY")
TG_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TG_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

print(f"🎬 Iniciando processamento do link: {URL}")

# Argumentos para driblar a checagem de robô do YouTube
YTDL_ARGS = ["--extractor-args", "youtube:player_client=android,web"]

# 1. Baixar apenas o áudio compacto
print("📥 1/5 Baixando áudio do YouTube...")
subprocess.run([
    "yt-dlp", *YTDL_ARGS,
    "-x", "--audio-format", "mp3", 
    "--audio-quality", "32K", 
    "-o", "audio.mp3", URL
], check=True)

# 2. Transcrição com Whisper na Groq
print("🎙️ 2/5 Transcrevendo áudio com Groq Whisper...")
groq_client = Groq(api_key=GROQ_KEY)
with open("audio.mp3", "rb") as file:
    transcription = groq_client.audio.transcriptions.create(
        file=("audio.mp3", file.read()),
        model="whisper-large-v3-turbo",
        response_format="verbose_json",
    )

transcript_text = ""
for seg in transcription.segments:
    start = round(seg["start"], 1)
    end = round(seg["end"], 1)
    transcript_text += f"[{start}s - {end}s]: {seg['text']}\n"

# 3. Gemini escolhe o melhor trecho
print("🧠 3/5 Gemini escolhendo o momento viral...")
client_gemini = genai.Client(api_key=GEMINI_KEY)

prompt = f"""
Você é um editor de vídeos virais especialista em TikTok, Shorts e Reels.
Abaixo está a transcrição de um vídeo com marcações de tempo em segundos.

Encontre o melhor trecho com duração entre 30 e 70 segundos que seja curioso, viral ou de alto impacto.

Responda EXCLUSIVAMENTE em formato JSON puro, sem marcação markdown (sem ```json), no seguinte padrão:
{{"start": 12.0, "end": 65.0, "reason": "Motivo da escolha"}}

Transcrição:
{transcript_text[:30000]}
"""

response = client_gemini.models.generate_content(
    model="gemini-1.5-flash",
    contents=prompt
)

clean_json = response.text.replace("```json", "").replace("```", "").strip()
cortes = json.loads(clean_json)

start_time = cortes["start"]
end_time = cortes["end"]
motivo = cortes.get("reason", "Corte selecionado")
print(f"🎯 Trecho: {start_time}s até {end_time}s | 💡 Motivo: {motivo}")

# 4. Baixar vídeo e converter para 9:16
print("✂️ 4/5 Baixando vídeo e convertendo para formato vertical (9:16)...")
subprocess.run([
    "yt-dlp", *YTDL_ARGS,
    "-f", "bestvideo[height<=720]+bestaudio/best[height<=720]",
    "--merge-output-format", "mp4",
    "-o", "full_video.mp4", URL
], check=True)

duracao = end_time - start_time
ffmpeg_cmd = [
    "ffmpeg", "-y",
    "-ss", str(start_time),
    "-t", str(duracao),
    "-i", "full_video.mp4",
    "-vf", (
        "[0:v]scale=1080:1920:force_original_aspect_ratio=increase,"
        "crop=1080:1920,boxblur=20:5[bg];"
        "[0:v]scale=1080:1920:force_original_aspect_ratio=decrease[fg];"
        "[bg][fg]overlay=(W-w)/2:(H-h)/2"
    ),
    "-c:v", "libx264", "-preset", "fast", "-crf", "24",
    "-c:a", "aac", "-b:a", "128k",
    "corte_final.mp4"
]
subprocess.run(ffmpeg_cmd, check=True)

# 5. Enviar para o Telegram
print("🚀 5/5 Enviando para o seu Telegram...")
url_tg = f"https://api.telegram.org/bot{TG_TOKEN}/sendVideo"
caption = f"🎬 **Corte Gerado com Sucesso!**\n⏱️ Trecho: {start_time}s a {end_time}s\n💡 {motivo}"

with open("corte_final.mp4", "rb") as video_file:
    res = requests.post(
        url_tg,
        data={"chat_id": TG_CHAT_ID, "caption": caption, "parse_mode": "Markdown"},
        files={"video": video_file}
    )

if res.status_code == 200:
    print("✅ Concluído! O vídeo foi enviado para o seu Telegram.")
else:
    print(f"⚠️ Erro ao enviar para o Telegram: {res.text}")
