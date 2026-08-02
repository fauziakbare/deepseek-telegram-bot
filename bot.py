import os
import requests
import logging
import re
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

# Konfigurasi logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# --- Konfigurasi ---
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "YOUR_TELEGRAM_TOKEN")
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "YOUR_DEEPSEEK_API_KEY")

# Konfigurasi DeepSeek API versi terbaru
DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEEPSEEK_MODEL = "deepseek-v4-flash"

# --- Fungsi untuk Membersihkan Format ---
def clean_markdown_to_html(text: str) -> str:
    """
    Mengubah format **markdown** menjadi <b>HTML</b> dan membersihkan
    format lain agar kompatibel dengan Telegram HTML parse_mode
    """
    # 1. Hapus ### heading (ubah menjadi bold)
    text = re.sub(r'^###\s+', '', text, flags=re.MULTILINE)
    text = re.sub(r'^##\s+', '', text, flags=re.MULTILINE)
    text = re.sub(r'^#\s+', '', text, flags=re.MULTILINE)
    
    # 2. Ubah **teks** menjadi <b>teks</b> (BOLD)
    def replace_bold(match):
        return f"<b>{match.group(1)}</b>"
    text = re.sub(r'\*\*(.+?)\*\*', replace_bold, text)
    
    # 3. Ubah *teks* menjadi <i>teks</i> (ITALIC)
    def replace_italic(match):
        return f"<i>{match.group(1)}</i>"
    text = re.sub(r'\*(.+?)\*', replace_italic, text)
    
    # 4. Ubah `teks` menjadi <code>teks</code> (CODE)
    def replace_code(match):
        return f"<code>{match.group(1)}</code>"
    text = re.sub(r'`(.+?)`', replace_code, text)
    
    # 5. Ubah --- menjadi garis pemisah
    text = re.sub(r'^---+$', '───────────', text, flags=re.MULTILINE)
    
    # 6. Hapus karakter ** yang tersisa
    text = text.replace('**', '')
    
    # 7. Hapus karakter * yang tersisa (tapi hati-hati jangan hapus emoji)
    text = re.sub(r'\*\s+', '• ', text)
    text = re.sub(r'\* ', '• ', text)
    
    return text

# --- System Prompt ---
SYSTEM_PROMPT = """Anda adalah asisten AI profesional di bidang keuangan yang bernama Zeuscious AI.

PERSONALITY & PERILAKU:
- Berperilaku sebagai profesional keuangan yang berpengalaman
- Gunakan bahasa Indonesia yang santai dan mudah dipahami
- Bersikap ramah, membantu, dan tidak menggurui

GAYA JAWABAN:
- Simpel, padat, dan jelas
- Hindari jargon teknis yang rumit
- Berikan contoh konkret jika memungkinkan
- Jawaban singkat namun informatif
- Gunakan **bold** untuk menekankan kata kunci (akan otomatis diubah ke HTML)
- Gunakan emoji yang relevan (💰📊📈💼)
- Jawaban harus LENGKAP dan tidak terpotong

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
- Gunakan **bold** untuk menekankan kata kunci
- Jika pertanyaan di luar keuangan, tetap jawab dengan sopan
- Berikan disclaimer jika diperlukan
- Jawab dengan LENGKAP dan jangan terpotong"""

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

    logger.info(f"Sending to DeepSeek: {len(messages)} messages")

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
        
        logger.info(f"DeepSeek response status: {response.status_code}")
        
        if response.status_code != 200:
            error_detail = response.json() if response.text else "No detail"
            logger.error(f"DeepSeek API error: {response.status_code} - {error_detail}")
            return f"❌ Maaf, terjadi error di server DeepSeek (Status: {response.status_code}). Silakan coba lagi nanti."
        
        response.raise_for_status()
        result = response.json()
        
        if not result.get("choices") or len(result["choices"]) == 0:
            logger.error("No choices in DeepSeek response")
            return "❌ Maaf, DeepSeek tidak memberikan respons. Silakan coba lagi."
        
        content = result["choices"][0]["message"]["content"]
        
        # 🔥 BERSIHKAN OUTPUT: Ubah ** ke <b>
        content = clean_markdown_to_html(content)
        
        logger.info(f"Response cleaned, length: {len(content)} characters")
        
        return content
        
    except requests.exceptions.Timeout:
        logger.error("DeepSeek API timeout")
        return "⏰ Maaf, waktu permintaan habis. Silakan coba lagi dengan pertanyaan yang lebih singkat."
    except requests.exceptions.ConnectionError:
        logger.error("DeepSeek API connection error")
        return "🔌 Maaf, tidak dapat terhubung ke server DeepSeek. Periksa koneksi internet Anda."
    except requests.exceptions.RequestException as e:
        logger.error(f"DeepSeek API request error: {e}")
        return f"❌ Terjadi kesalahan: {str(e)}"
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        return f"❌ Terjadi kesalahan tak terduga: {str(e)}"

# --- Handler Telegram ---

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
    logger.info(f"Received message: {user_message[:100]}...")

    await update.message.chat.send_action(action="typing")

    history = context.user_data.get("history", [])
    if len(history) > 20:
        history = history[-20:]

    try:
        response = call_deepseek_api(user_message, history)
        logger.info(f"Response length: {len(response)} characters")
    except Exception as e:
        logger.error(f"Error in handle_message: {e}")
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

    # Kirim dengan parse_mode HTML
    try:
        await update.message.reply_text(response, parse_mode="HTML")
    except Exception as e:
        # Jika HTML error, kirim tanpa parse_mode
        logger.error(f"HTML parse error: {e}")
        await update.message.reply_text(response)

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Update {update} caused error {context.error}")

# --- Main ---

def main():
    logger.info("Starting bot...")
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
