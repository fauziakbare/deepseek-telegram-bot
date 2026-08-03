import os
import requests
import logging
import re
import io
import html
from datetime import datetime
from PIL import Image
from google import genai
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, 
    CommandHandler, 
    MessageHandler, 
    CallbackQueryHandler, 
    filters, 
    ContextTypes
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- CONFIGURATION & ENV VARIABLES ---
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEEPSEEK_MODEL = "deepseek-v4-flash"
GEMINI_MODEL = "gemini-3.5-flash-lite"

gemini_client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None

# --- PARSER MARKDOWN TO HTML (SAFE ESCAPING) ---
def markdown_ke_html(text):
    if not text:
        return ""
    
    # 1. Escape karakter khusus HTML (<, >, &) DULUAN agar Telegram parser tidak crash
    text = html.escape(text)
    
    # 2. Format Bold **text** -> <b>text</b>
    text = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', text)
    text = text.replace('**', '')
    
    # 3. Bersihkan Markdown Header (# Heading)
    text = re.sub(r'^#{1,3}\s+', '', text, flags=re.MULTILINE)
    
    return text

# --- HELPER: DETEKSI & EKSTRAKSI WEB VIA JINA READER ---
def extract_url(text):
    """Mencari URL http/https di dalam pesan user"""
    url_pattern = r'https?://[^\s]+'
    match = re.search(url_pattern, text)
    return match.group(0) if match else None

def fetch_web_content(target_url):
    """Mengambil teks bersih dari web menggunakan Jina Reader API"""
    try:
        jina_url = f"https://r.jina.ai/{target_url}"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
            "X-No-Cache": "true"  # Bypass cache Jina agar artikel berita terbaca utuh
        }
        
        response = requests.get(jina_url, headers=headers, timeout=15)
        response.raise_for_status()
        
        # Batasi output maks 8000 karakter agar artikel lengkap terbaca
        clean_text = response.text[:8000]
        return clean_text
    except Exception as e:
        logger.error(f"Error fetching web ({target_url}): {e}")
        return None

# --- SYSTEM PROMPT & DYNAMIC TIME INJECTION ---
SYSTEM_PROMPT = """Kamu adalah Zeuscious AI, rekan diskusi yang kritis, analitis, dan objektif. Tugasmu adalah mengevaluasi data, strategi bisnis, berita web, dan finansial secara rasional. Jangan asal mengiyakan asumsi pengguna, tapi juga jangan skeptis secara berlebihan tanpa dasar.

ADAPTIVE VERBOSITY (EFISIENSI TOKEN):
1. MODE RINGKAS (Pertanyaan Faktual / Data Singkat):
   - Jika pengguna bertanya fakta, angka spesifik, atau definisi (contoh: "Berapa PER BBRI?", "Apa itu EBITDA?"): Langsung jawab ke intinya dalam 1-2 kalimat murni tanpa poin berbelit.
2. MODE ANALISIS (Bedah Kasus / Evaluasi / Foto / Link Web / Pertanyaan Kompleks):
   - Gunakan struktur analisis mendalam jika pengguna meminta penjelasan, bedah laporan keuangan, kirim link web, atau mengirim gambar.

STRUKTUR & FORMATTING (SAAT MENGGUNAKAN POIN):
1. Tanpa Basa-Basi: DILARANG menggunakan kata pembuka/penutup seperti "Halo", "Berikut analisisnya", atau "Semoga membantu". Kalimat pertama langsung vonis/kesimpulan utama.
2. Spacing Poin (WAJIB): Pisahkan setiap poin bullet dengan 1 BARIS KOSONG (double newline) agar rapi di layar Telegram.
   Contoh format:
   • Poin pertama penjelasan atau argumen data.

   • Poin kedua yang menyoroti risiko atau celah logika.

   • Poin ketiga berisi rekomendasi rasional.
3. Simbol Bullet: Gunakan simbol `•` di awal setiap poin.

GAYA BAHASA & SIKAP:
- Gunakan Bahasa Indonesia santai tapi presisi ("lo" dan "gue").
- Skeptis Secukupnya: Jika ada asumsi pengguna yang janggal, tunjukkan letak celahnya secara rasional pakai data/logika. Jangan terlalu mengiyakan, tapi jangan pula menyerang tanpa alasan.
- Minimalisir Bold: Gunakan **bold** HANYA pada angka, ticker, atau kata kunci paling vital.
"""

def get_dynamic_system_prompt():
    """Menyuntikkan tanggal real-time sistem ke System Prompt"""
    waktu_sekarang = datetime.now().strftime("%A, %d %B %Y")
    return f"""{SYSTEM_PROMPT}

INFORMASI WAKTU REAL-TIME:
Hari ini adalah {waktu_sekarang}. Semua berita, laporan keuangan, atau data yang diterbitkan pada atau sebelum tanggal ini adalah VALID dan nyata (bukan masa depan/sintetis).
"""

# --- DEEPSEEK API CALL ---
def call_deepseek_api(user_message, chat_history=None):
    headers = {
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
        "Content-Type": "application/json"
    }

    # Gunakan System Prompt yang sudah disuntikkan tanggal real-time
    messages = [{"role": "system", "content": get_dynamic_system_prompt()}]
    if chat_history:
        messages.extend(chat_history)
    messages.append({"role": "user", "content": user_message})

    payload = {
        "model": DEEPSEEK_MODEL,
        "messages": messages,
        "temperature": 0.5,
        "max_tokens": 2048,
        "stream": False
    }

    try:
        response = requests.post(
            f"{DEEPSEEK_BASE_URL}/v1/chat/completions",
            headers=headers,
            json=payload,
            timeout=120
        )
        response.raise_for_status()
        result = response.json()
        content = result["choices"][0]["message"]["content"]
        
        if not content:
            return "❌ API DeepSeek mengembalikan respon kosong."
            
        return markdown_ke_html(content)
    except Exception as e:
        logger.error(f"Error DeepSeek API: {e}")
        return f"❌ Terjadi kesalahan DeepSeek: {str(e)}"

# --- TELEGRAM HANDLERS ---

async def start(update, context):
    await update.message.reply_text(
        "Gue Zeuscious AI.\n"
        "Kirim pertanyaan, link web, atau foto/dokumen buat langsung dibedah.",
        parse_mode="HTML"
    )

async def handle_message(update, context):
    """Handle chat teks murni, link web, via DeepSeek"""
    user_message = update.message.text
    if user_message in context.user_data.get("last_messages", []):
        return
    
    await update.message.chat.send_action(action="typing")

    # 1. Cek Apakah Ada Link URL di Pesan User
    detected_url = extract_url(user_message)
    if detected_url:
        await update.message.reply_text("🌐 Membaca dan mengekstrak isi web...")
        web_text = fetch_web_content(detected_url)
        
        if web_text:
            prompt_input = (
                f"[KONTEN WEB DARI LINK {detected_url}]:\n"
                f"{web_text}\n\n"
                f"[INSTRUKSI/PERTANYAAN USER]: {user_message}"
            )
        else:
            await update.message.reply_text("❌ Gagal membaca isi link tersebut (web diblokir atau offline).")
            return
    else:
        prompt_input = user_message

    # 2. Kirim ke DeepSeek
    history = context.user_data.get("history", [])
    if len(history) > 6:
        history = history[-6:]

    response = call_deepseek_api(prompt_input, history)

    context.user_data["history"] = history + [
        {"role": "user", "content": user_message},
        {"role": "assistant", "content": response}
    ]
    if len(context.user_data["history"]) > 6:
        context.user_data["history"] = context.user_data["history"][-6:]

    try:
        await update.message.reply_text(response, parse_mode="HTML")
    except Exception:
        await update.message.reply_text(response)

async def handle_photo(update, context):
    """Tampilkan tombol pilihan ketika pengguna mengirim foto"""
    if not gemini_client:
        await update.message.reply_text("❌ GEMINI_API_KEY belum terpasang.")
        return

    photo_file_id = update.message.photo[-1].file_id
    caption = update.message.caption or "Analisis dan kritisi gambar ini secara detail."

    context.user_data["pending_photo"] = {
        "file_id": photo_file_id,
        "caption": caption
    }

    keyboard = [
        [
            InlineKeyboardButton("⚡ Direct Gemini (Cepat)", callback_data="process_gemini"),
            InlineKeyboardButton("🧠 Hybrid DeepSeek (Kritis)", callback_data="process_hybrid")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "Gambar diterima. Pilih engine pemroses:",
        reply_markup=reply_markup
    )

async def handle_button_click(update, context):
    """Handler saat pengguna memencet tombol"""
    query = update.callback_query
    await query.answer()

    pending_photo = context.user_data.get("pending_photo")
    if not pending_photo:
        await query.edit_message_text("❌ Data gambar kadaluwarsa, silakan kirim ulang.")
        return

    await query.edit_message_text("⏳ Memproses gambar...")

    try:
        file_info = await context.bot.get_file(pending_photo["file_id"])
        photo_bytes = await file_info.download_as_bytearray()
        image = Image.open(io.BytesIO(photo_bytes))
        caption = pending_photo["caption"]

        final_text = ""

        # --- OPTION 1: DIRECT GEMINI ---
        if query.data == "process_gemini":
            prompt = f"{get_dynamic_system_prompt()}\n\nInstruksi Pengguna: {caption}"
            response = gemini_client.models.generate_content(
                model=GEMINI_MODEL,
                contents=[image, prompt]
            )
            raw_text = response.text if response and response.text else ""
            
            if not raw_text.strip():
                final_text = "❌ Gemini mengembalikan respon kosong."
            else:
                final_text = markdown_ke_html(raw_text) + f"\n\n<i>⚡ Direct Gemini ({GEMINI_MODEL})</i>"

        # --- OPTION 2: HYBRID (GEMINI OCR -> DEEPSEEK REASONING) ---
        elif query.data == "process_hybrid":
            ocr_prompt = "Ekstrak seluruh teks, angka, tabel, dan komponen visual penting dari gambar ini secara objektif tanpa analisis."
            gemini_ocr = gemini_client.models.generate_content(
                model=GEMINI_MODEL,
                contents=[image, ocr_prompt]
            )
            ocr_result = gemini_ocr.text if gemini_ocr and gemini_ocr.text else ""

            if not ocr_result.strip():
                final_text = "❌ Gemini gagal membaca teks dari gambar ini."
            else:
                deepseek_input = f"[DATA DARI SCAN GAMBAR]:\n{ocr_result}\n\n[INSTRUKSI USER]: {caption}"
                history = context.user_data.get("history", [])
                deepseek_res = call_deepseek_api(deepseek_input, history)
                final_text = deepseek_res + f"\n\n<i>🧠 DeepSeek ({DEEPSEEK_MODEL}) via Gemini OCR</i>"

        if not final_text or not final_text.strip():
            final_text = "❌ Gagal menghasilkan respon."

        try:
            await query.message.reply_text(final_text, parse_mode="HTML")
        except Exception:
            await query.message.reply_text(final_text)

        context.user_data.pop("pending_photo", None)

    except Exception as e:
        logger.error(f"Error pada callback handler: {e}")
        await query.message.reply_text(f"❌ Terjadi kesalahan: {str(e)}")

async def error_handler(update, context):
    logger.error(f"Error: {context.error}")

# --- MAIN RUNNER ---
def main():
    logger.info("Bot sedang berjalan...")
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(CallbackQueryHandler(handle_button_click))
    app.add_error_handler(error_handler)

    app.run_polling()

if __name__ == "__main__":
    main()
