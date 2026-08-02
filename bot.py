import os
import requests
import logging
import re
import io
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

# --- PARSER MARKDOWN TO HTML ---
def markdown_ke_html(text):
    if not text:
        return ""
    text = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', text)
    text = text.replace('**', '')
    text = re.sub(r'^#{1,3}\s+', '', text, flags=re.MULTILINE)
    return text

# --- SYSTEM PROMPT (DENGAN SIMBOL BULLET •) ---
SYSTEM_PROMPT = """Kamu adalah seorang kritis, analitis, dan sangat skeptis. Tugasmu bukan menyenangkan pengguna, melainkan menantang asumsi, mengecek validitas data, dan menemukan celah dalam argumen. 

STRUKTUR JAWABAN (WAJIB FORMAT HIBRIDA):
1. Kalimat Pertama (Vonis Utama): Langsung hantam dengan kesimpulan paling tajam atau kelemahan logika terbesar di baris paling atas. DILARANG menggunakan kata pembuka/basa-basi seperti "Halo", "Berikut analisisnya", atau "Berdasarkan gambar".
2. Poin Pembuktian (Bullet Points): Gunakan simbol bullet `•` di awal setiap poin untuk membeberkan 2-4 bukti fakta, angka, rasio, atau cacat logika secara ringkas dan spesifik.
3. Kalimat Penutup (Tantangan): Akhiri dengan 1 kalimat singkat yang menantang pemikiran pengguna atau menagih data pendukung.

GAYA BAHASA:
- Bahasa Indonesia santai tapi profesional, gunakan "lo" dan "gue".
- Langsung to the point ke letak kesalahan.
- **Bold** hanya pada keyword/angka yang penting saja (minimalisir bold).

KONTEKS KEUANGAN & BISNIS:
- Investasi, perencanaan keuangan, manajemen utang, tabungan.
- Crypto, Stock, Gold, Forex, Laporan Keuangan, Chart.

PENTING:
- Skeptis terhadap klaim yang tidak punya data valid.
- Jika tidak ada data pendukung, katakan "Gue gak percaya" atau "Ini asumsi lo aja".
"""

# --- DEEPSEEK API CALL ---
def call_deepseek_api(user_message, chat_history=None):
    headers = {
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
        "Content-Type": "application/json"
    }

    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    if chat_history:
        messages.extend(chat_history)
    messages.append({"role": "user", "content": user_message})

    payload = {
        "model": DEEPSEEK_MODEL,
        "messages": messages,
        "temperature": 0.7,
        "max_tokens": 4096,
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
        "Halo! Gue Zeuscious AI.\n"
        "Kirim teks atau foto, lalu pilih mau dibedah pakai Gemini atau DeepSeek 😏",
        parse_mode="HTML"
    )

async def handle_message(update, context):
    """Handle chat teks murni via DeepSeek"""
    if update.message.text in context.user_data.get("last_messages", []):
        return
    
    user_message = update.message.text
    await update.message.chat.send_action(action="typing")

    history = context.user_data.get("history", [])
    if len(history) > 8:
        history = history[-8:]

    response = call_deepseek_api(user_message, history)

    context.user_data["history"] = history + [
        {"role": "user", "content": user_message},
        {"role": "assistant", "content": response}
    ]
    if len(context.user_data["history"]) > 8:
        context.user_data["history"] = context.user_data["history"][-8:]

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
        "Gambar diterima. Pilih engine untuk memproses:",
        reply_markup=reply_markup
    )

async def handle_button_click(update, context):
    """Handler saat pengguna memencet salah satu tombol"""
    query = update.callback_query
    await query.answer()

    pending_photo = context.user_data.get("pending_photo")
    if not pending_photo:
        await query.edit_message_text("❌ Data gambar sudah kadaluwarsa, silakan kirim ulang gambarnya.")
        return

    await query.edit_message_text("⏳ Memproses gambar...")

    try:
        file_info = await context.bot.get_file(pending_photo["file_id"])
        photo_bytes = await file_info.download_as_bytearray()
        image = Image.open(io.BytesIO(photo_bytes))
        caption = pending_photo["caption"]

        final_text = ""

        # --- PILIHAN 1: DIRECT GEMINI ---
        if query.data == "process_gemini":
            prompt = f"{SYSTEM_PROMPT}\n\nInstruksi Pengguna: {caption}"
            response = gemini_client.models.generate_content(
                model=GEMINI_MODEL,
                contents=[image, prompt]
            )
            raw_text = response.text if response and response.text else ""
            
            if not raw_text.strip():
                final_text = "❌ Gemini mengembalikan respon kosong."
            else:
                final_text = markdown_ke_html(raw_text) + f"\n\n<i>⚡ Processed by Direct Gemini ({GEMINI_MODEL})</i>"

        # --- PILIHAN 2: HYBRID (GEMINI OCR -> DEEPSEEK REASONING) ---
        elif query.data == "process_hybrid":
            ocr_prompt = "Ekstrak seluruh teks, angka, tabel, dan komponen visual penting dari gambar ini secara objektif dan detail tanpa analisis."
            gemini_ocr = gemini_client.models.generate_content(
                model=GEMINI_MODEL,
                contents=[image, ocr_prompt]
            )
            ocr_result = gemini_ocr.text if gemini_ocr and gemini_ocr.text else ""

            if not ocr_result.strip():
                final_text = "❌ Gemini gagal membaca/mengekstrak teks dari gambar ini."
            else:
                deepseek_input = f"[DATA DARI SCAN GAMBAR]:\n{ocr_result}\n\n[INSTRUKSI/PERTANYAAN USER]: {caption}"
                history = context.user_data.get("history", [])
                deepseek_res = call_deepseek_api(deepseek_input, history)
                final_text = deepseek_res + f"\n\n<i>🧠 Processed by DeepSeek ({DEEPSEEK_MODEL}) via Gemini OCR</i>"

        # Validasi jika final_text tetap kosong
        if not final_text or not final_text.strip():
            final_text = "❌ Gagal menghasilkan respon (teks kosong)."

        # Kirim hasil ke Telegram
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
