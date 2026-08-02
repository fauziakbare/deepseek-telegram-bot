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
        "Halo! Gue Zeuscious AI.\n"
        "Siap tantang asumsi lo dan bedah logika finansial.\n"
        "Langsung aja tanyakan apapun, gue bongkar 😏",
        parse_mode="HTML"
    )

async def handle_message(update, context):
    """Handle semua pesan - HANYA CHAT, TANPA PERINTAH LAIN"""
    if update.message.text in context.user_data.get("last_messages", []):
        return
    
    user_message = update.message.text
    await update.message.chat.send_action(action="typing")

    # HANYA simpan 4 pesan terakhir
    history = context.user_data.get("history", [])
    if len(history) > 8:  # 4 pasang user-assistant
        history = history[-8:]

    response = call_deepseek_api(user_message, history)

    # Simpan riwayat - MAX 4 PESAN (8 item = 4 pasang)
    context.user_data["history"] = history + [
        {"role": "user", "content": user_message},
        {"role": "assistant", "content": response}
    ]
    if len(context.user_data["history"]) > 8:  # Maksimal 4 pasang
        context.user_data["history"] = context.user_data["history"][-8:]

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

    # HANYA perintah /start yang tersisa
    app.add_handler(CommandHandler("start", start))
    # Semua teks (bukan command) akan masuk ke handle_message
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_error_handler(error_handler)

    app.run_polling()

if __name__ == "__main__":
    main()
