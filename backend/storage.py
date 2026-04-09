import os
import wave
import datetime
from typing import Optional
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.units import cm
from reportlab.lib import colors

def get_save_folder(drive_folder: str, user_name: str, timestamp: str) -> str:
    safe_name = user_name.replace(" ", "_").lower()
    folder = os.path.join(drive_folder, safe_name, timestamp)
    os.makedirs(folder, exist_ok=True)
    return folder

def build_transcript_text(transcriptions: list[dict]) -> str:
    lines = []
    for t in transcriptions:
        lines.append(f"[{t['timestamp']}] {t['speaker']}: {t['original']}")
        if t["original"] != t["translation"]:
            lines.append(f"  ↳ {t['translation']}")
    return "\n".join(lines)

def save_transcript_txt(folder: str, transcriptions: list[dict]) -> str:
    path = os.path.join(folder, "transcricao.txt")
    with open(path, "w", encoding="utf-8") as f:
        f.write(build_transcript_text(transcriptions))
    return path

def save_audio_wav(folder: str, audio_frames: bytes) -> str:
    path = os.path.join(folder, "audio.wav")
    with wave.open(path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(16000)
        wf.writeframes(audio_frames)
    return path

def save_pdf(folder: str, transcriptions: list[dict], summary: str,
             meeting_date: str) -> str:
    path = os.path.join(folder, "reuniao.pdf")
    doc = SimpleDocTemplate(path, pagesize=A4,
                            leftMargin=2*cm, rightMargin=2*cm,
                            topMargin=2*cm, bottomMargin=2*cm)
    titulo = ParagraphStyle("titulo", fontSize=18, fontName="Helvetica-Bold",
                             spaceAfter=12, textColor=colors.HexColor("#1a1a2e"))
    subtit = ParagraphStyle("subtit", fontSize=12, fontName="Helvetica-Bold",
                             spaceAfter=6, textColor=colors.HexColor("#e94560"))
    normal = ParagraphStyle("normal", fontSize=10, fontName="Helvetica",
                             spaceAfter=4, leading=14)
    conteudo = [
        Paragraph("Transcricao da Reuniao", titulo),
        Paragraph(f"Data: {meeting_date}", normal),
        Spacer(1, 0.5*cm),
        Paragraph("Resumo com IA", subtit),
        Paragraph(summary.replace("\n", "<br/>") if summary else "Resumo indisponivel.", normal),
        Spacer(1, 0.5*cm),
        Paragraph("Transcricao Completa", subtit),
    ]
    for t in transcriptions:
        conteudo.append(Paragraph(
            f"<b>[{t['timestamp']}] {t['speaker']}:</b> {t['original']}", normal))
        if t["original"] != t["translation"]:
            conteudo.append(Paragraph(
                f"&nbsp;&nbsp;&#8627; <i>{t['translation']}</i>", normal))
    doc.build(conteudo)
    return path

def generate_summary(transcriptions: list[dict], openai_client) -> str:
    if not transcriptions:
        return "Nenhuma transcricao disponivel."
    texto = build_transcript_text(transcriptions)
    try:
        response = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{
                "role": "user",
                "content": (
                    "Faca um resumo executivo desta transcricao de reuniao em portugues. "
                    "Inclua: 1) Principais topicos discutidos, 2) Decisoes tomadas, "
                    "3) Proximos passos.\n\n" + texto
                )
            }]
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"Resumo indisponivel: {e}"
