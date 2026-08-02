import os
import requests
import logging
import re
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY")

DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEEPSEEK_MODEL = "deepseek-v4-flash"

# --- FUNGSI MENGUBAH ** ke <b> ---
def markdown_ke_html(text):
    """Ubah **teks** menjadi <b>teks</b> untuk Telegram"""
    # Ubah **teks** menjadi <b>teks</b>
    text = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', text)
    # Hapus sisa ** yang tidak berpasangan
    text = text.replace('**', '')
    # Hapus heading
    text = re.sub(r'^#{1,3}\s+', '', text, flags=re.MULTILINE)
    return text

# --- SYSTEM PROMPT ---
SYSTEM_PROMPT = """Anda adalah asisten AI profesional di bidang keuangan bernama Zeuscious AI.

GAYA JAWABAN:
- Bahasa Indonesia yang santai dan mudah dipahami
- Simpel, padat, jelas
- Gunakan bullet points dengan - atau *
- Gunakan **bold** untuk kata kunci (akan otomatis berubah jadi bold di Telegram)

KONTEKS KEUANGAN:
- Investasi, perencanaan keuangan, manajemen utang, tabungan
- Manajemen keuangan lanjutan, persiapan ujian CA

PENTING:
- Gunakan **bold** untuk menekankan kata kunci
- Jawab dengan LENGKAP dan jangan terpotong"""

# --- PANGGIL DEEPSEEK API ---
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
        
        # Ubah ** ke <b>
        content = markdown_ke_html(content)
        
        return content
    except Exception as e:
        logger.error(f"Error: {e}")
        return f"❌ Terjadi kesalahan: {str(e)}"

# --- HANDLER TELEGRAM ---

async def start(update, context):
    """Perintah /start - SIMPEL"""
    await update.message.reply_text(
        "Halo! Saya Zeuscious AI.\n"
        "Tanyakan soal apapun, saya bantu jawab 😊\n\n"
        "/help - Bantuan",
        parse_mode="HTML"
    )

async def help_command(update, context):
    """Perintah /help"""
    await update.message.reply_text(
        "<b>📋 Perintah:</b>\n"
        "/start - Mulai\n"
        "/help - Bantuan ini\n"
        "/clear - Hapus riwayat\n\n"
        "<i>⚠️ Bukan saran finansial profesional</i>",
        parse_mode="HTML"
    )

async def clear(update, context):
    """Perintah /clear - Hapus riwayat"""
    context.user_data["history"] = []
    await update.message.reply_text("🧹 Riwayat dihapus!")

async def handle_message(update, context):
    """Handle semua pesan"""
    if update.message.text in context.user_data.get("last_messages", []):
        return
    
    user_message = update.message.text
    await update.message.chat.send_action(action="typing")

    history = context.user_data.get("history", [])
    if len(history) > 20:
        history = history[-20:]

    response = call_deepseek_api(user_message, history)

    # Simpan riwayat
    context.user_data["history"] = history + [
        {"role": "user", "content": user_message},
        {"role": "assistant", "content": response}
    ]
    if len(context.user_data["history"]) > 40:
        context.user_data["history"] = context.user_data["history"][-40:]

    if "last_messages" not in context.user_data:
        context.user_data["last_messages"] = []
    context.user_data["last_messages"].append(update.message.text)
    if len(context.user_data["last_messages"]) > 5:
        context.user_data["last_messages"] = context.user_data["last_messages"][-5:]

    # Kirim dengan HTML
    try:
        await update.message.reply_text(response, parse_mode="HTML")
    except Exception:
        # Kalau error HTML, kirim polos
        await update.message.reply_text(response)

async def error_handler(update, context):
    logger.error(f"Error: {context.error}")

# --- MAIN ---
def main():
    logger.info("Bot sedang berjalan...")
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("clear", clear))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_error_handler(error_handler)

    app.run_polling()

if __name__ == "__main__":
    main()
