import os
import requests
import logging
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

# Konfigurasi logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Konfigurasi ---
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "YOUR_TELEGRAM_TOKEN")
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "YOUR_DEEPSEEK_API_KEY")

# Konfigurasi DeepSeek API versi terbaru
DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEEPSEEK_MODEL = "deepseek-v4-flash"

# --- System Prompt dengan Format HTML ---
SYSTEM_PROMPT = """Anda adalah asisten AI profesional di bidang keuangan yang bernama Zeuscious AI.

PERSONALITY & PERILAKU:
- Berperilaku sebagai profesional keuangan yang berpengalaman
- Gunakan bahasa Indonesia yang santai dan mudah dipahami
- Bersikap ramah, membantu, dan tidak menggurui

GAYA JAWABAN:
- Simpel, padat, dan jelas
- Hindari jargon teknis yang rumit
- Berikan contoh konkret jika memungkinkan
- Jawaban singkat namun informatif (maksimal 3-4 paragraf)
- Gunakan format HTML untuk formatting:
  * <b>teks</b> untuk BOLD
  * <i>teks</i> untuk ITALIC
  * <u>teks</u> untuk UNDERLINE
  * Gunakan emoji yang relevan (💰📊📈💼)

KONTEKS KEUANGAN:
- Investasi (saham, reksa dana, obligasi, crypto, emas, properti)
- Perencanaan keuangan pribadi
- Manajemen utang dan kredit
- Tabungan dan dana darurat
- Perpajakan dasar
- Ekonomi makro dan mikro
- Manajemen keuangan lanjutan
- Persiapan ujian CA (Chartered Accountant)

PENTING:
- Selalu gunakan bahasa Indonesia dalam setiap respons
- Gunakan tag HTML <b> untuk menekankan kata kunci
- Jangan gunakan **markdown** karena tidak akan terbaca
- Jika pertanyaan di luar keuangan, tetap jawab dengan sopan
- Berikan disclaimer jika diperlukan"""

# --- Fungsi Panggil DeepSeek API ---
def call_deepseek_api(user_message: str, chat_history: list = None) -> str:
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
        "max_tokens": 2048,
        "stream": False
    }

    try:
        response = requests.post(
            f"{DEEPSEEK_BASE_URL}/v1/chat/completions",
            headers=headers,
            json=payload,
            timeout=60
        )
        response.raise_for_status()
        result = response.json()
        return result["choices"][0]["message"]["content"]
    except Exception as e:
        logger.error(f"DeepSeek API error: {e}")
        return f"❌ Terjadi kesalahan: {str(e)}"

# --- Handler Telegram dengan parse_mode HTML ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    welcome_text = """
<b>💼 Halo! Saya Zeuscious AI - Asisten Keuangan Anda.</b>

Saya siap membantu Anda dengan:
💰 Investasi (saham, reksa dana, crypto, emas)
📊 Perencanaan keuangan pribadi
🏦 Manajemen utang & tabungan
📈 Analisis ekonomi sederhana
📚 Manajemen keuangan lanjutan
🎓 Persiapan ujian CA (Chartered Accountant)

Cukup tanyakan apapun tentang keuangan, dan saya akan jawab dengan simpel & jelas!

📌 <b>Perintah:</b> /help untuk bantuan
"""
    await update.message.reply_text(welcome_text, parse_mode="HTML")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = """
<b>📋 Perintah yang tersedia:</b>
/start - Mulai bot
/help - Tampilkan bantuan ini
/clear - Hapus riwayat percakapan

<b>💡 Contoh pertanyaan:</b>
- Bagaimana cara mulai investasi saham?
- Apa itu reksa dana?
- Bagaimana mengatur keuangan gaji 5 juta?
- Apa itu penciptaan nilai dalam manajemen keuangan?
- Bagaimana persiapan ujian CA?

<i>⚠️ Disclaimer: Ini bukan saran finansial profesional.</i>
"""
    await update.message.reply_text(help_text, parse_mode="HTML")

async def clear(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["history"] = []
    await update.message.reply_text("🧹 Riwayat percakapan telah dihapus!")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text in context.user_data.get("last_messages", []):
        return
    
    user_message = update.message.text

    await update.message.chat.send_action(action="typing")

    history = context.user_data.get("history", [])
    if len(history) > 20:
        history = history[-20:]

    try:
        response = call_deepseek_api(user_message, history)
    except Exception as e:
        response = f"❌ Terjadi kesalahan: {str(e)}"

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

    # 🔥 PASTIKAN MENGGUNAKAN parse_mode="HTML"
    await update.message.reply_text(response, parse_mode="HTML")

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Update {update} caused error {context.error}")

# --- Main ---

def main():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("clear", clear))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_error_handler(error_handler)

    logger.info("Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()
