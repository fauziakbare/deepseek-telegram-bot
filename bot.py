import os
import requests
import logging
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

# Konfigurasi logging
logging.basicConfig(level=logging.INFO)

# --- Konfigurasi ---
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "YOUR_TELEGRAM_TOKEN")
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "YOUR_DEEPSEEK_API_KEY")

# Konfigurasi DeepSeek API versi terbaru
DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEEPSEEK_MODEL = "deepseek-v4-flash"  # atau "deepseek-v4-pro"

# --- System Prompt Khusus Keuangan ---
SYSTEM_PROMPT = """Anda adalah asisten AI profesional di bidang keuangan yang bernama Zeuscious AI.

PERSONALITY & PERILAKU:
- Berperilaku sebagai profesional keuangan yang berpengalaman
- Gunakan bahasa Indonesia yang santai dan mudah dipahami
- Bersikap ramah, membantu, dan tidak menggurui

GAYA JAWABAN:
- Simpel, padat, dan jelas
- Hindari jargon teknis yang rumit
- Jika perlu menggunakan istilah keuangan, berikan penjelasan sederhana
- Berikan contoh konkret jika memungkinkan
- Jawaban singkat namun informatif (maksimal 3-4 paragraf)

KONTEKS KEUANGAN:
- Investasi (saham, reksa dana, obligasi, crypto, emas, properti)
- Perencanaan keuangan pribadi
- Manajemen utang dan kredit
- Tabungan dan dana darurat
- Perpajakan dasar
- Ekonomi makro dan mikro

PENTING:
- Selalu gunakan bahasa Indonesia dalam setiap respons
- Jika pertanyaan di luar keuangan, tetap jawab dengan sopan tapi arahkan ke topik keuangan
- Berikan disclaimer jika diperlukan (misal: "ini bukan saran finansial profesional")"""

# --- Fungsi Panggil DeepSeek API ---
def call_deepseek_api(user_message: str, chat_history: list = None) -> str:
    """
    Mengirim pesan ke DeepSeek API dan mengembalikan respons.
    """
    headers = {
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
        "Content-Type": "application/json"
    }

    # Siapkan pesan dengan system prompt dan riwayat chat
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    
    if chat_history:
        messages.extend(chat_history)
    
    messages.append({"role": "user", "content": user_message})

    payload = {
        "model": DEEPSEEK_MODEL,
        "messages": messages,
        "temperature": 0.7,
        "max_tokens": 2048,
        "stream": False
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
        "💼 *Halo! Saya Zeuscious AI - Asisten Keuangan Anda.*\n\n"
        "Saya siap membantu Anda dengan:\n"
        "💰 Investasi (saham, reksa dana, crypto, emas)\n"
        "📊 Perencanaan keuangan pribadi\n"
        "🏦 Manajemen utang & tabungan\n"
        "📈 Analisis ekonomi sederhana\n\n"
        "Cukup tanyakan apapun tentang keuangan, dan saya akan jawab dengan simpel & jelas!\n\n"
        "📌 *Perintah:* /help untuk bantuan"
    )
    await update.message.reply_text(welcome_text, parse_mode="Markdown")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk perintah /help"""
    help_text = (
        "*📋 Perintah yang tersedia:*\n"
        "/start - Mulai bot\n"
        "/help - Tampilkan bantuan ini\n"
        "/clear - Hapus riwayat percakapan\n\n"
        "*💡 Contoh pertanyaan:*\n"
        "- Bagaimana cara mulai investasi saham?\n"
        "- Apa itu reksa dana?\n"
        "- Bagaimana mengatur keuangan gaji 5 juta?\n"
        "- Apakah crypto aman untuk investasi?\n\n"
        "*⚠️ Disclaimer:* Ini bukan saran finansial profesional."
    )
    await update.message.reply_text(help_text, parse_mode="Markdown")

async def clear(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk perintah /clear"""
    context.user_data["history"] = []
    await update.message.reply_text("🧹 Riwayat percakapan telah dihapus!")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk semua pesan teks"""
    # Cegah bot merespon pesan yang sama dua kali
    if update.message.text in context.user_data.get("last_messages", []):
        return
    
    user_message = update.message.text

    # Kirim indikator "sedang mengetik"
    await update.message.chat.send_action(action="typing")

    # Ambil riwayat dari user_data
    history = context.user_data.get("history", [])
    if len(history) > 20:
        history = history[-20:]

    # Panggil DeepSeek API
    try:
        response = call_deepseek_api(user_message, history)
    except Exception as e:
        response = f"❌ Terjadi kesalahan: {e}"

    # Simpan riwayat percakapan
    context.user_data["history"] = history + [
        {"role": "user", "content": user_message},
        {"role": "assistant", "content": response}
    ]
    if len(context.user_data["history"]) > 40:
        context.user_data["history"] = context.user_data["history"][-40:]

    # Simpan pesan terakhir untuk mencegah duplikasi
    if "last_messages" not in context.user_data:
        context.user_data["last_messages"] = []
    context.user_data["last_messages"].append(update.message.text)
    if len(context.user_data["last_messages"]) > 5:
        context.user_data["last_messages"] = context.user_data["last_messages"][-5:]

    # Kirim respons
    await update.message.reply_text(response)

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk error"""
    logging.error(f"Update {update} caused error {context.error}")

# --- Main ---

def main():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("clear", clear))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_error_handler(error_handler)

    logging.info("Bot sedang berjalan...")
    app.run_polling()

if __name__ == "__main__":
    main()
