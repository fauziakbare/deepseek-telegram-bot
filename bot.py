import os
import requests
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

# Konfigurasi logging
logging.basicConfig(level=logging.INFO)

# --- Konfigurasi ---
# Ambil dari environment variable atau hardcode (tidak disarankan)
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "YOUR_TELEGRAM_TOKEN")
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "YOUR_DEEPSEEK_API_KEY")

# Konfigurasi DeepSeek API versi terbaru (DeepSeek-V4)
DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEEPSEEK_MODEL = "deepseek-v4-flash"  # atau "deepseek-v4-pro"
# Catatan: Model deepseek-chat dan deepseek-reasoner akan dihentikan 24 Juli 2026

# --- Fungsi Panggil DeepSeek API ---
def call_deepseek_api(user_message: str, chat_history: list = None) -> str:
    """
    Mengirim pesan ke DeepSeek API dan mengembalikan respons.
    Mendukung deepseek-v4-flash / deepseek-v4-pro.
    """
    headers = {
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
        "Content-Type": "application/json"
    }

    # Siapkan pesan dengan riwayat chat (opsional)
    messages = []
    if chat_history:
        messages = chat_history
    messages.append({"role": "user", "content": user_message})

    payload = {
        "model": DEEPSEEK_MODEL,
        "messages": messages,
        "temperature": 0.7,
        "max_tokens": 2048
    }

    try:
        response = requests.post(
            f"{DEEPSEEK_BASE_URL}/v1/chat/completions",
            headers=headers,
            json=payload,
            timeout=30
        )
        response.raise_for_status()
        result = response.json()
        return result["choices"][0]["message"]["content"]
    except requests.exceptions.Timeout:
        return "⏰ Maaf, waktu permintaan habis. Silakan coba lagi."
    except requests.exceptions.RequestException as e:
        logging.error(f"DeepSeek API error: {e}")
        return f"❌ Terjadi kesalahan: {e}"

# --- Handler Telegram ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk perintah /start"""
    welcome_text = (
        "🤖 *Halo! Saya bot DeepSeek-V4.*\n\n"
        "Saya dapat membantu menjawab pertanyaan Anda menggunakan "
        "kecerdasan buatan DeepSeek.\n\n"
        "Cukup kirim pesan apa pun, dan saya akan merespons!\n"
        "Gunakan /help untuk bantuan."
    )
    await update.message.reply_text(welcome_text, parse_mode="Markdown")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk perintah /help"""
    help_text = (
        "*Perintah yang tersedia:*\n"
        "/start - Mulai bot\n"
        "/help - Tampilkan bantuan ini\n"
        "/clear - Hapus riwayat percakapan\n\n"
        "*Tips:* Kirim pesan biasa untuk mengobrol dengan AI."
    )
    await update.message.reply_text(help_text, parse_mode="Markdown")

async def clear(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk perintah /clear - menghapus riwayat chat"""
    context.user_data["history"] = []
    await update.message.reply_text("🧹 Riwayat percakapan telah dihapus!")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk semua pesan teks"""
    user_message = update.message.text

    # Kirim indikator "sedang mengetik"
    await update.message.chat.send_action(action="typing")

    # Ambil riwayat dari user_data
    history = context.user_data.get("history", [])
    if len(history) > 20:
        history = history[-20:]  # Batasi riwayat

    # Panggil DeepSeek API
    try:
        response = call_deepseek_api(user_message, history)
    except Exception as e:
        response = f"❌ Terjadi kesalahan: {e}"

    # Simpan riwayat percakapan (role: user dan assistant)
    context.user_data["history"] = history + [
        {"role": "user", "content": user_message},
        {"role": "assistant", "content": response}
    ]
    if len(context.user_data["history"]) > 40:
        context.user_data["history"] = context.user_data["history"][-40:]

    # Kirim respons
    await update.message.reply_text(response)

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk error"""
    logging.error(f"Update {update} caused error {context.error}")

# --- Main ---

def main():
    # Buat aplikasi bot
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    # Daftarkan handler
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("clear", clear))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_error_handler(error_handler)

    # Jalankan bot dengan polling
    logging.info("Bot sedang berjalan...")
    app.run_polling()

if __name__ == "__main__":
    main()
