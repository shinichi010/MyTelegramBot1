# ═════════════════════════════════════════════════════
#  Telegram Super Bot - Fixed Version
# ═════════════════════════════════════════════════════

import logging
import os
import asyncio
import random
import re
import requests
import tempfile
import shutil
import subprocess
import firebase_admin
from firebase_admin import credentials, db
from telegram import (
    Update,
    ChatPermissions,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    InputMediaPhoto,
)
from telegram.ext import (
    Application,
    MessageHandler,
    CallbackQueryHandler,
    CommandHandler,
    filters,
    ContextTypes,
)

from yt_dlp import YoutubeDL
import imageio_ffmpeg

# ═════════════════════════════════════════════════════
# Logging
# ═════════════════════════════════════════════════════

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ═════════════════════════════════════════════════════
# Firebase
# ═════════════════════════════════════════════════════

cred = credentials.Certificate("firebase.json")

firebase_admin.initialize_app(
    cred,
    {
        "DATABASE_URL": os.environ.get("DATABASE_URL")
    }
)

# ═════════════════════════════════════════════════════
# Database Helpers
# ═════════════════════════════════════════════════════

def db_get(path, default=None):
    try:
        val = db.reference(path).get()
        return val if val is not None else default
    except:
        return default

def db_set(path, data):
    try:
        db.reference(path).set(data)
    except Exception as e:
        logger.error(e)

# ═════════════════════════════════════════════════════
# Settings
# ═════════════════════════════════════════════════════

def get_settings(chat_id):
    return db_get(
        f"settings/{chat_id}",
        {
            "ai_mode": False,
            "welcome": True,
        }
    )

def save_settings(chat_id, data):
    db_set(f"settings/{chat_id}", data)

# ═════════════════════════════════════════════════════
# Roles
# ═════════════════════════════════════════════════════

ROLE_OWNER = "owner"
ROLE_MANAGER = "manager"
ROLE_VIP = "vip"

ROLE_RANK = {
    ROLE_OWNER: 3,
    ROLE_MANAGER: 2,
    ROLE_VIP: 1
}

ROLE_LABEL = {
    ROLE_OWNER: "👑 مالك",
    ROLE_MANAGER: "🛡 مدير",
    ROLE_VIP: "⭐ مميز"
}

def get_role(chat_id, user_id):
    return db_get(f"roles/{chat_id}/{user_id}")

def set_role(chat_id, user_id, role):
    db_set(f"roles/{chat_id}/{user_id}", role)

def remove_role(chat_id, user_id):
    db.reference(f"roles/{chat_id}/{user_id}").delete()

# ═════════════════════════════════════════════════════
# DeepSeek AI
# ═════════════════════════════════════════════════════

async def ask_deepseek(prompt):

    api_key = os.environ.get("DEEPSEEK_API")

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    data = {
        "model": "deepseek-chat",
        "messages": [
            {
                "role": "system",
                "content": "أنت بوت ذكي تتكلم باللهجة العراقية."
            },
            {
                "role": "user",
                "content": prompt
            }
        ],
        "max_tokens": 1000
    }

    try:

        res = requests.post(
            "https://api.deepseek.com/chat/completions",
            headers=headers,
            json=data,
            timeout=30
        )

        response = res.json()

        logger.info(response)

        return response["choices"][0]["message"]["content"]

    except Exception as e:

        logger.error(f"DeepSeek Error: {e}")

        return "❌ الذكاء الاصطناعي حالياً ما يشتغل."

# ═════════════════════════════════════════════════════
# Progress
# ═════════════════════════════════════════════════════

active_downloads = {}

def progress_hook(d, msg_id):

    if d["status"] == "downloading":

        percent = d.get("_percent_str", "0%")

        percent = re.sub(r"\x1b\[[0-9;]*m", "", percent)

        active_downloads[msg_id] = percent.strip()

# ═════════════════════════════════════════════════════
# Download Media
# ═════════════════════════════════════════════════════

async def download_media(
    url,
    media_type,
    quality,
    msg_id
):

    tmp = tempfile.mkdtemp()

    ydl_opts = {

        "outtmpl": os.path.join(tmp, "%(title)s.%(ext)s"),

        "quiet": True,

        "noplaylist": True,

        "nocheckcertificate": True,

        "geo_bypass": True,

        "extract_flat": False,

        "cookiefile": "cookies.txt",

        "ffmpeg_location": imageio_ffmpeg.get_ffmpeg_exe(),

        "progress_hooks": [
            lambda d: progress_hook(d, msg_id)
        ],
    }

    # Audio

    if media_type == "audio":

        ydl_opts["format"] = "bestaudio/best"

        ydl_opts["postprocessors"] = [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }
        ]

    # Video

    else:

        if quality == "360":
            ydl_opts["format"] = "bestvideo[height<=360]+bestaudio/best"

        elif quality == "720":
            ydl_opts["format"] = "bestvideo[height<=720]+bestaudio/best"

        elif quality == "1080":
            ydl_opts["format"] = "bestvideo[height<=1080]+bestaudio/best"

        else:
            ydl_opts["format"] = "best"

        ydl_opts["merge_output_format"] = "mp4"

    def run():

        with YoutubeDL(ydl_opts) as ydl:

            info = ydl.extract_info(url, download=True)

            for f in os.listdir(tmp):

                if f.endswith((".mp3", ".mp4")):

                    return os.path.join(tmp, f), info.get("title")

        return None, None

    loop = asyncio.get_running_loop()

    try:

        path, title = await loop.run_in_executor(None, run)

        return path, title, tmp

    except Exception as e:

        logger.error(f"DOWNLOAD ERROR: {e}")

        shutil.rmtree(tmp, ignore_errors=True)

        return None, None, None

# ═════════════════════════════════════════════════════
# TikTok
# ═════════════════════════════════════════════════════

def download_tiktok(url):

    try:

        api = f"https://www.tikwm.com/api/?url={url}&hd=1"

        res = requests.get(api, timeout=15).json()

        if res.get("code") == 0:

            d = res["data"]

            return d.get("hdplay") or d.get("play")

    except:
        pass

    return None

# ═════════════════════════════════════════════════════
# Whisper Fix
# ═════════════════════════════════════════════════════

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):

    msg = update.message

    if msg.chat.type == "private" and msg.text.startswith("/start w_"):

        try:

            parts = msg.text.replace("/start w_", "").split("_")

            sender_id = int(parts[0])

            target_id = int(parts[1])

            chat_id = int(parts[2].replace("m", "-"))

            if msg.from_user.id != sender_id:

                return await msg.reply_text("❌ الرابط مو إلك")

            context.user_data["whisper_target"] = target_id
            context.user_data["whisper_chat"] = chat_id

            await msg.reply_text("✍️ اكتب الهمسة هسه")

        except:
            await msg.reply_text("❌ خطأ بالرابط")

# ═════════════════════════════════════════════════════
# Handle Messages
# ═════════════════════════════════════════════════════

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if not update.message:
        return

    msg = update.message

    text = (msg.text or "").strip()

    chat_id = msg.chat.id

    user_id = msg.from_user.id

    settings = get_settings(chat_id)

    # ═══════════════════════════════════
    # Whisper Send
    # ═══════════════════════════════════

    if msg.chat.type == "private":

        if "whisper_target" in context.user_data:

            target_id = context.user_data["whisper_target"]

            group_id = context.user_data["whisper_chat"]

            w_id = str(random.randint(100000, 999999))

            whisper_data = {

                "text": text,

                "sender": str(user_id),

                "target": str(target_id)

            }

            db.reference(f"whispers/{w_id}").set(whisper_data)

            keyboard = InlineKeyboardMarkup([

                [
                    InlineKeyboardButton(
                        "🔒 قراءة الهمسة",
                        callback_data=f"show_w_{w_id}"
                    )
                ]

            ])

            await context.bot.send_message(

                group_id,

                "🤫 همسة جديدة",

                reply_markup=keyboard

            )

            context.user_data.clear()

            return await msg.reply_text("✅ انرسلت الهمسة")

    # ═══════════════════════════════════
    # Commands
    # ═══════════════════════════════════

    if text == "تشغيل سيك":

        settings["ai_mode"] = True

        save_settings(chat_id, settings)

        return await msg.reply_text("✅ تم تشغيل الذكاء الاصطناعي")

    if text == "ايقاف سيك":

        settings["ai_mode"] = False

        save_settings(chat_id, settings)

        return await msg.reply_text("❌ تم إيقاف الذكاء الاصطناعي")

    # ═══════════════════════════════════
    # YouTube
    # ═══════════════════════════════════

    if re.search(r"(youtube\.com|youtu\.be|youtube\.com/shorts/)", text, re.I):

        url = re.search(r'https?://[^\s]+', text).group()

        url_hash = str(random.randint(1000, 9999))

        context.bot_data[url_hash] = url

        keyboard = InlineKeyboardMarkup([

            [
                InlineKeyboardButton(
                    "🎵 صوت",
                    callback_data=f"dl_audio_{user_id}_{url_hash}"
                )
            ],

            [
                InlineKeyboardButton(
                    "360p",
                    callback_data=f"dl_vid360_{user_id}_{url_hash}"
                ),

                InlineKeyboardButton(
                    "720p",
                    callback_data=f"dl_vid720_{user_id}_{url_hash}"
                )
            ],

            [
                InlineKeyboardButton(
                    "1080p",
                    callback_data=f"dl_vid1080_{user_id}_{url_hash}"
                )
            ]

        ])

        return await msg.reply_text(
            "📥 اختر الجودة",
            reply_markup=keyboard
        )

    # ═══════════════════════════════════
    # TikTok
    # ═══════════════════════════════════

    if "tiktok.com" in text:

        url = re.search(r'https?://[^\s]+', text).group()

        wait = await msg.reply_text("⏳ جاري التحميل")

        video = download_tiktok(url)

        if video:

            await context.bot.send_video(chat_id, video)

            return await wait.delete()

        return await wait.edit_text("❌ فشل التحميل")

    # ═══════════════════════════════════
    # AI Reply
    # ═══════════════════════════════════

    blocked_commands = (

        "تشغيل سيك",
        "ايقاف سيك",

    )

    if settings.get("ai_mode") and not text.startswith(blocked_commands):

        await context.bot.send_chat_action(chat_id, "typing")

        reply = await ask_deepseek(text)

        return await msg.reply_text(reply)

# ═════════════════════════════════════════════════════
# Buttons
# ═════════════════════════════════════════════════════

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):

    query = update.callback_query

    data = query.data

    # ═══════════════════════════════════
    # Whisper Read
    # ═══════════════════════════════════

    if data.startswith("show_w_"):

        w_id = data.replace("show_w_", "")

        w = db_get(f"whispers/{w_id}")

        if not w:

            return await query.answer(
                "❌ الهمسة مو موجودة",
                show_alert=True
            )

        if str(query.from_user.id) in [

            w["target"],
            w["sender"]

        ]:

            return await query.answer(
                w["text"],
                show_alert=True
            )

        return await query.answer(
            "❌ هاي الهمسة مو إلك",
            show_alert=True
        )

    # ═══════════════════════════════════
    # Download
    # ═══════════════════════════════════

    if data.startswith("dl_"):

        parts = data.split("_", 3)

        if len(parts) < 4:

            return await query.answer(
                "❌ خطأ",
                show_alert=True
            )

        _, action, uid, url_hash = parts

        if str(query.from_user.id) != uid:

            return await query.answer(
                "❌ مو إلك",
                show_alert=True
            )

        url = context.bot_data.get(url_hash)

        if not url:

            return await query.answer(
                "❌ الرابط انتهى",
                show_alert=True
            )

        await query.message.edit_text("⏳ جاري التحميل")

        media_type = "audio" if action == "audio" else "video"

        quality = action.replace("vid", "")

        path, title, tmp = await download_media(
            url,
            media_type,
            quality,
            query.message.message_id
        )

        if path and os.path.exists(path):

            try:

                with open(path, "rb") as f:

                    if media_type == "audio":

                        await context.bot.send_audio(
                            query.message.chat.id,
                            f,
                            title=title
                        )

                    else:

                        await context.bot.send_video(
                            query.message.chat.id,
                            f,
                            caption=title
                        )

                await query.message.delete()

            except Exception as e:

                logger.error(e)

                await query.message.edit_text("❌ فشل الإرسال")

        else:

            await query.message.edit_text("❌ فشل التحميل")

        if tmp:
            shutil.rmtree(tmp, ignore_errors=True)

# ═══════════════════════════════════════
# ترحيب الأعضاء الجدد
# ═══════════════════════════════════════
async def welcome_member(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if not update.message:
        return

    for member in update.message.new_chat_members:

        if member.is_bot:
            continue

        chat_id = update.message.chat.id

        try:
            photos = await context.bot.get_user_profile_photos(
                member.id,
                limit=1
            )

            caption = (
                f"👋 أهلاً نورت المجموعة\n\n"
                f"✨ {member.first_name}"
            )

            if photos.total_count > 0:

                await context.bot.send_photo(
                    chat_id=chat_id,
                    photo=photos.photos[0][-1].file_id,
                    caption=caption
                )

            else:

                await context.bot.send_message(
                    chat_id=chat_id,
                    text=caption
                )

        except Exception as e:
            print(e)

# ═══════════════════════════════════════════════════════════════════
# 9. تشغيل البوت
# ═══════════════════════════════════════════════════════════════════
def main():
    token = os.environ.get(
        "BOT_TOKEN",
        "8159446452:AAHvUE5aEvuTmGfwAYAV7EqfshKD9Nv-B5o"
    )

    app = Application.builder().token(token).build()

    app.add_handler(CommandHandler("start", start_command))

    app.add_handler(
        CallbackQueryHandler(
            button_callback,
            pattern=r"^(show_w_|cmd_|dl_)"
        )
    )

    app.add_handler(
        MessageHandler(
            filters.StatusUpdate.NEW_CHAT_MEMBERS,
            welcome_member
        )
    )

    app.add_handler(
        MessageHandler(
            filters.UpdateType.EDITED_MESSAGE & filters.TEXT,
            edited_message_handler
        )
    )

    app.add_handler(
        MessageHandler(
            filters.ChatType.GROUPS &
            filters.TEXT &
            ~filters.COMMAND,
            track_messages_handler
        ),
        group=1
    )

    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            handle_message
        ),
        group=2
    )

app.add_handler(
    MessageHandler(
        filters.StatusUpdate.NEW_CHAT_MEMBERS,
        welcome_member
    )
)

    print("✅ Bot Started")

    app.run_polling()

if __name__ == "__main__":
    main()
