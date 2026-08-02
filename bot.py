import os
import requests
import logging
import re
import io
from PIL import Image
from google import genai
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- CONFIGURATION & ENV VARIABLES ---
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEEPSEEK_MODEL = "deepseek-v4-flash"

# Inisialisasi Client Gemini
gemini_client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None

# --- PARSER MARKDOWN TO HTML TELEGRAM ---
def markdown_ke_html(text):
    """Ubah **teks** menjadi <b>teks</b> untuk Telegram"""
    text = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', text)
    text = text.replace('**', '')
    text = re.sub(r'^#{1,3}\s+', '', text, flags=re.MULTILINE)
    return text

# --- SYSTEM PROMPT DEEPSEEK ---
SYSTEM_PROMPT = """Kamu adalah seorang kritis, analitis, dan sangat skeptis. Tugasmu bukan menyenangkan pengguna, melainkan menantang asumsi, mengecek validitas data, dan menemukan celah dalam argumen. Jangan bertele-tele, langsung tunjukkan kelemahan logika di kalimat awal.

GAYA JAWABAN:
- Bahasa Indonesia santai tapi profesional, pake "lo" dan "gue"
- Langsung to the point ke letak kesalahan tanpa intro panjang lebar
- Gunakan bullet points dengan - atau *
- **Bold** hanya pada keyword yang penting-penting saja (minimalisir penggunaan bold)

KONTEKS KEUANGAN:
- Investasi, perencanaan keuangan, manajemen utang, tabungan
- Crypto, Stock, Gold, Forex

PENTING:
- Langsung tunjukin kelemahan argumen di kalimat pertama
- Jangan basa-basi atau pemanis kata
- Skeptis terhadap klaim yang gak punya data valid
- Kalo gak ada data pendukung, bilang aja "Gue gak percaya" atau "Ini asumsi lo aja"
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
        return markdown_ke_html(content)
    except Exception as e:
        logger.error(f"Error DeepSeek API: {e}")
        return f"❌ Terjadi kesalahan DeepSeek: {str(e)}"

# --- TELEGRAM HANDLERS ---

async def start(update, context):
    await update.message.reply_text(
        "Halo! Gue Zeuscious AI.\n"
        "Siap tantang asumsi lo, bedah logika finansial, dan baca gambar/chart lo.\n"
        "Kirim teks atau foto, langsung gue bongkar 😏",
        parse_mode="HTML"
    )

async def handle_message(update, context):
    """Handle percakapan teks biasa via DeepSeek"""
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

    if "last_messages" not in context.user_data:
        context.user_data["last_messages"] = []
    context.user_data["last_messages"].append(update.message.text)
    if len(context.user_data["last_messages"]) > 5:
        context.user_data["last_messages"] = context.user_data["last_messages"][-5:]

    try:
        await update.message.reply_text(response, parse_mode="HTML")
    except Exception:
        await update.message.reply_text(response)

async def handle_photo(update, context):
    """Mode Direct Gemini: Mengirim gambar langsung ke Gemini 2.5 Flash"""
    if not gemini_client:
        await update.message.reply_text("❌ GEMINI_API_KEY belum terpasang di Environment Variables Railway.")
        return

    await update.message.chat.send_action(action="typing")

    caption = update.message.caption or "Analisis dan kritisi isi dari gambar ini secara objektif dan detail."

    try:
        # Download gambar dari Telegram ke dalam memory buffer (RAM)
        photo_file = await update.message.photo[-1].get_file()
        photo_bytes = await photo_file.download_as_bytearray()
        image = Image.open(io.BytesIO(photo_bytes))

        # Panggil API Gemini 2.5 Flash dengan menyuntikkan SYSTEM_PROMPT
        prompt_kritis = f"{SYSTEM_PROMPT}\n\nPesan dari Pengguna: {caption}"

        response = gemini_client.models.generate_content(
            model="gemini-3.5-flash-lite",
            contents=[image, prompt_kritis]
        )

        formatted_response = markdown_ke_html(response.text)
        
        try:
            await update.message.reply_text(formatted_response, parse_mode="HTML")
        except Exception:
            await update.message.reply_text(response.text)

    except Exception as e:
        logger.error(f"Error pada Gemini Vision: {e}")
        await update.message.reply_text(f"❌ Gagal memproses gambar via Gemini: {str(e)}")

async def error_handler(update, context):
    logger.error(f"Error: {context.error}")

# --- MAIN RUNNER ---
def main():
    logger.info("Bot sedang berjalan...")
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_error_handler(error_handler)

    app.run_polling()

if __name__ == "__main__":
    main()
