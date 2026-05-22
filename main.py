import logging
import os
import asyncio
import random
import re
import requests
import tempfile
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton, InputMediaPhoto
from telegram.ext import Application, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from yt_dlp import YoutubeDL
import firebase_admin
from firebase_admin import credentials, db

# إعداد التسجيل
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════
# 1. مصفوفات التسلية
# ═══════════════════════════════════════════════════════════════════
WA3ED_LIST = [
    "وعد: تعزم أول شخص يرد عليك على شاورما 🌯",
    "وعد: تخلي صورتك بالبروفايل صورة طفل لمدة يوم 👶",
    "وعد: تكتب بالكروب 'أنا أحبكم كلكم' وتثبتها دقيقة ❤️",
    "وعد: تدز بصمة صوتية تغني بيها للكروب 🎤",
    "وعد: تعترف بأكثر موقف محرج صار وياك 🫣"
]

KHAYROK_LIST = [
    "لو خيروك: تسافر عبر الزمن للمستقبل لو للماضي؟ ⏳",
    "لو خيروك: تاكل بيتزا طول عمرك لو بركر طول عمرك؟ 🍕🍔",
    "لو خيروك: تصير غني بس بدون أصدقاء، لو فقير وعندك أصدقاء يحبوك؟ 💰",
    "لو خيروك: تكدر تقرأ أفكار الناس لو تكدر تطير؟ 🦅"
]

# ═══════════════════════════════════════════════════════════════════
# 2. قاعدة البيانات (Firebase)
# ═══════════════════════════════════════════════════════════════════
try:
    cred = credentials.Certificate('firebase.json')
    firebase_url = os.environ.get('DATABASE_URL', 'https://mytelegrambotdb-default-rtdb.europe-west1.firebasedatabase.app/')
    firebase_admin.initialize_app(cred, {'DATABASE_URL': firebase_url})
    logger.info("✅ Firebase connected")
except Exception as e:
    logger.error(f"❌ Firebase error: {e}")

def db_get(path, default):
    try:
        val = db.reference(path).get()
        return val if val is not None else default
    except:
        return default

def db_set(path, data):
    try:
        db.reference(path).set(data)
    except Exception as e:
        logger.error(f"DB set error: {e}")

def get_settings(chat_id):
    key = str(chat_id)
    default = {"welcome": True, "banned_words": [], "locked": False, "links_protection": False, "edit_notify": True, "ai_mode": False}
    return db_get(f"settings/{key}", default)

def save_settings(chat_id, settings):
    db_set(f"settings/{str(chat_id)}", settings)

# ═══════════════════════════════════════════════════════════════════
# 3. الصلاحيات
# ═══════════════════════════════════════════════════════════════════
ROLE_OWNER = "owner"
ROLE_MANAGER = "manager"
ROLE_VIP = "vip"
ROLE_RANK = {ROLE_OWNER: 3, ROLE_MANAGER: 2, ROLE_VIP: 1}

def get_role(chat_id, user_id):
    return db_get(f"roles/{chat_id}/{user_id}", None)

async def is_tg_owner(update: Update, context: ContextTypes.DEFAULT_TYPE):
    admins = await context.bot.get_chat_administrators(update.effective_chat.id)
    return any(a.user.id == update.effective_user.id and a.status == "creator" for a in admins)

async def is_privileged(update: Update, context: ContextTypes.DEFAULT_TYPE, min_role=ROLE_OWNER):
    role = get_role(update.effective_chat.id, update.effective_user.id)
    return bool(role and ROLE_RANK.get(role, 0) >= ROLE_RANK.get(min_role, 99)) or await is_tg_owner(update, context)

# ═══════════════════════════════════════════════════════════════════
# 4. الذكاء الاصطناعي DeepSeek
# ═══════════════════════════════════════════════════════════════════
async def ask_deepseek(prompt: str) -> str:
    api_key = "sk-f5149facf1164e6db0af5fd276c8fbfe"
    url = "https://api.deepseek.com/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    data = {
        "model": "deepseek-chat",
        "messages": [
            {"role": "system", "content": "أنت مساعد ذكي تتحدث باللهجة العراقية أحياناً واسمك بوت الإدارة."},
            {"role": "user", "content": prompt}
        ],
        "max_tokens": 1000
    }
    try:
        res = requests.post(url, headers=headers, json=data, timeout=20)
        return res.json()["choices"][0]["message"]["content"]
    except:
        return "اعذرني، السيرفر مشغول حالياً 😅"

# ═══════════════════════════════════════════════════════════════════
# 5. دوال التحميل (يوتيوب، تويتر، تيك توك)
# ═══════════════════════════════════════════════════════════════════
active_downloads = {}

def progress_hook(d, msg_id):
    if d['status'] == 'downloading':
        percent = d.get('_percent_str', '0%').strip()
        # إزالة أكواد الألوان
        percent = re.sub(r'\x1b\[[0-9;]*m', '', percent)
        active_downloads[msg_id] = percent

async def update_progress(context, chat_id, msg_id, status_msg_id):
    last = ""
    while msg_id in active_downloads:
        current = active_downloads.get(msg_id, "")
        if current and current != last:
            try:
                await context.bot.edit_message_text(f"⏳ جاري التحميل: {current}", chat_id=chat_id, message_id=status_msg_id)
                last = current
            except:
                pass
        await asyncio.sleep(2)

async def download_media(url, media_type, quality, msg_id, chat_id, context, status_msg_id):
    tmp = tempfile.mkdtemp()
    ydl_opts = {
        'outtmpl': os.path.join(tmp, '%(title)s.%(ext)s'),
        'quiet': True,
        'noplaylist': True,
        'progress_hooks': [lambda d: progress_hook(d, msg_id)],
        'nocheckcertificate': True,
        'geo_bypass': True,
        'extractor_retries': 3
    }

    if media_type == "audio":
        ydl_opts['format'] = 'bestaudio/best'
        ydl_opts['postprocessors'] = [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3', 'preferredquality': '192'}]
    else:  # video
        if quality == "1080":
            ydl_opts['format'] = 'bestvideo[height<=1080]+bestaudio/best'
        elif quality == "720":
            ydl_opts['format'] = 'bestvideo[height<=720]+bestaudio/best'
        elif quality == "360":
            ydl_opts['format'] = 'bestvideo[height<=360]+bestaudio/best'
        else:
            ydl_opts['format'] = 'best'
        ydl_opts['merge_output_format'] = 'mp4'

    active_downloads[msg_id] = "0%"
    progress_task = asyncio.create_task(update_progress(context, chat_id, msg_id, status_msg_id))

    def run():
        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            for f in os.listdir(tmp):
                if f.endswith(('.mp3', '.mp4')):
                    return os.path.join(tmp, f), info.get('title', 'media')
        return None, None

    loop = asyncio.get_running_loop()
    try:
        path, title = await loop.run_in_executor(None, run)
        active_downloads.pop(msg_id, None)
        progress_task.cancel()
        return path, title
    except Exception as e:
        logger.error(f"Download error: {e}")
        active_downloads.pop(msg_id, None)
        progress_task.cancel()
        return None, None

def download_tiktok(url):
    api = f'https://www.tikwm.com/api/?url={url}&hd=1'
    try:
        res = requests.get(api, timeout=15).json()
        if res.get('code') == 0 and 'data' in res:
            d = res['data']
            author = d.get('author', {}).get('unique_id', 'مجهول')
            music = d.get('music', '')
            if isinstance(music, dict):
                music = music.get('play', '')
            if 'images' in d and d['images']:
                return {'type': 'images', 'data': d['images'], 'author': author, 'music': music}
            return {'type': 'video', 'data': d.get('hdplay') or d.get('play'), 'author': author, 'music': music}
    except:
        pass
    return None

# ═══════════════════════════════════════════════════════════════════
# 6. أوامر التسلية
# ═══════════════════════════════════════════════════════════════════
async def fun_commands(update: Update, text: str, msg) -> bool:
    if text == "نسبة الحب" and msg.reply_to_message:
        perc = random.randint(0, 100)
        u1 = msg.from_user.first_name
        u2 = msg.reply_to_message.from_user.first_name
        await msg.reply_text(f"💘 نسبة الحب بين {u1} و {u2} هي: {perc}%")
        return True
    if text == "وعد":
        await msg.reply_text(random.choice(WA3ED_LIST))
        return True
    if text == "لو خيروك":
        await msg.reply_text(random.choice(KHAYROK_LIST))
        return True
    if text == "افتار":
        target = msg.reply_to_message.from_user if msg.reply_to_message else msg.from_user
        photos = await target.get_profile_photos()
        if photos and photos.total_count > 0:
            await msg.reply_photo(photos[0][0].file_id, caption=f"🖼 افتار {target.first_name}")
        else:
            await msg.reply_text("هذا العضو ما حاط صورة بروفايل!")
        return True
    if text == "ايدي":
        target = msg.reply_to_message.from_user if msg.reply_to_message else msg.from_user
        await msg.reply_text(f"🆔 ايدي العضو: `{target.id}`", parse_mode="Markdown")
        return True
    return False

# ═══════════════════════════════════════════════════════════════════
# 7. معالج الأزرار (التحميل)
# ═══════════════════════════════════════════════════════════════════
async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    await query.answer()

    if not data.startswith("dl_"):
        return

    parts = data.split('_')
    if len(parts) < 4:
        return
    action = parts[1]      # opts, audio, vid360, vid720, vid1080
    uid = parts[2]
    url_hash = parts[3]

    if str(query.from_user.id) != uid:
        await query.answer("هذه الأزرار لطلب شخص آخر!", show_alert=True)
        return

    url = context.bot_data.get(url_hash)
    if not url:
        await query.edit_message_text("❌ الرابط منتهي الصلاحية، أعد إرساله.")
        return

    if action == "opts":
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🎥 360p", callback_data=f"dl_vid360_{uid}_{url_hash}"),
             InlineKeyboardButton("🎥 720p", callback_data=f"dl_vid720_{uid}_{url_hash}")],
            [InlineKeyboardButton("🎥 1080p", callback_data=f"dl_vid1080_{uid}_{url_hash}")]
        ])
        await query.edit_message_reply_markup(keyboard)
        return

    # تحميل صوت أو فيديو
    await query.edit_message_text("⏳ جاري تحضير الملف...")
    if action == "audio":
        media_type = "audio"
        quality = None
    elif action.startswith("vid"):
        media_type = "video"
        quality = action.replace("vid", "")
    else:
        return

    filepath, title = await download_media(url, media_type, quality, query.message.message_id, query.message.chat_id, context, query.message.message_id)
    if filepath and os.path.exists(filepath):
        await query.edit_message_text("📤 جاري الرفع...")
        with open(filepath, 'rb') as f:
            if media_type == "audio":
                await context.bot.send_audio(query.message.chat_id, f, title=title)
            else:
                await context.bot.send_video(query.message.chat_id, f, caption=title)
        os.remove(filepath)
        await query.message.delete()
    else:
        await query.edit_message_text("❌ فشل التحميل. حاول مرة أخرى.")

# ═══════════════════════════════════════════════════════════════════
# 8. المعالج الرئيسي للرسائل
# ═══════════════════════════════════════════════════════════════════
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return
    msg = update.message
    text = msg.text or ""
    text = text.strip()
    if not text:
        return

    chat_id = msg.chat_id
    user_id = msg.from_user.id
    settings = get_settings(chat_id)
    is_owner = await is_tg_owner(update, context)

    # 1. أوامر التسلية
    if await fun_commands(update, text, msg):
        return

    # 2. تشغيل/إيقاف الذكاء الاصطناعي
    if text == "تشغيل سيك" and is_owner:
        settings["ai_mode"] = True
        save_settings(chat_id, settings)
        await msg.reply_text("🤖 تم تفعيل الذكاء الاصطناعي!")
        return
    if text == "ايقاف سيك" and is_owner:
        settings["ai_mode"] = False
        save_settings(chat_id, settings)
        await msg.reply_text("😴 تم إيقاف الذكاء الاصطناعي.")
        return

    # 3. وضع الذكاء الاصطناعي (إذا كان مفعلاً)
    if settings.get("ai_mode", False) and not text.startswith(('/', 'رفع', 'تنزيل', 'طرد', 'حظر', 'كتم')):
        await context.bot.send_chat_action(chat_id, 'typing')
        reply = await ask_deepseek(text)
        await msg.reply_text(reply)
        return

    # 4. تحميل من يوتيوب (مع أزرار)
    if re.search(r'(youtube\.com|youtu\.be)', text, re.I):
        url_match = re.search(r'https?://[^\s]+', text)
        if url_match:
            url = url_match.group()
            wait_msg = await msg.reply_text("🔍 جاري جلب المعلومات...")
            try:
                with YoutubeDL({'quiet': True, 'noplaylist': True, 'nocheckcertificate': True}) as ydl:
                    info = ydl.extract_info(url, download=False)
                url_hash = str(random.randint(1000, 9999))
                context.bot_data[url_hash] = url
                keyboard = InlineKeyboardMarkup([
                    [InlineKeyboardButton("🎬 تحميل فيديو", callback_data=f"dl_opts_{user_id}_{url_hash}")],
                    [InlineKeyboardButton("🎵 تحميل صوت", callback_data=f"dl_audio_{user_id}_{url_hash}")]
                ])
                if info.get('thumbnail'):
                    await msg.reply_photo(info['thumbnail'], caption=info.get('title', 'اختر الصيغة:'), reply_markup=keyboard)
                else:
                    await msg.reply_text(info.get('title', 'اختر الصيغة:'), reply_markup=keyboard)
                await wait_msg.delete()
            except Exception as e:
                logger.error(f"YouTube error: {e}")
                await wait_msg.edit_text("❌ فشل جلب بيانات الرابط.")
        return

    # 5. تحميل من تويتر (X)
    if re.search(r'(x\.com|twitter\.com)', text, re.I):
        url_match = re.search(r'https?://[^\s]+', text)
        if url_match:
            url = url_match.group()
            wait_msg = await msg.reply_text("⏳ جاري تحميل المقطع من تويتر...")
            filepath, title = await download_media(url, "video", "best", msg.message_id, chat_id, context, wait_msg.message_id)
            if filepath and os.path.exists(filepath):
                await wait_msg.edit_text("📤 جاري الرفع...")
                with open(filepath, 'rb') as f:
                    await context.bot.send_video(chat_id, f, caption="✅ تم التحميل من X")
                os.remove(filepath)
                await wait_msg.delete()
            else:
                await wait_msg.edit_text("❌ فشل التحميل من تويتر.")
        return

    # 6. تحميل من تيك توك
    if 'tiktok.com' in text:
        url_match = re.search(r'https?://[^\s]+', text)
        if url_match:
            url = url_match.group()
            wait_msg = await msg.reply_text("⏳ جاري تحميل التيك توك...")
            data = download_tiktok(url)
            if data:
                caption = f"👤 <b>الحساب:</b> @{data['author']}"
                try:
                    if data['type'] == 'images':
                        media = [InputMediaPhoto(img) for img in data['data']]
                        await context.bot.send_media_group(chat_id, media, reply_to_message_id=msg.message_id)
                        if data.get('music'):
                            await context.bot.send_audio(chat_id, data['music'], caption=caption, parse_mode="HTML")
                    else:
                        await context.bot.send_video(chat_id, data['data'], caption=caption, parse_mode="HTML", reply_to_message_id=msg.message_id)
                    await wait_msg.delete()
                except Exception as e:
                    logger.error(f"TikTok send error: {e}")
                    await wait_msg.edit_text("❌ حدث خطأ أثناء الإرسال.")
            else:
                await wait_msg.edit_text("❌ فشل التحميل من تيك توك.")
        return

# ═══════════════════════════════════════════════════════════════════
# 9. تشغيل البوت
# ═══════════════════════════════════════════════════════════════════
def main():
    token = os.environ.get("BOT_TOKEN", "8159446452:AAHvUE5aEvuTmGfwAYAV7EqfshKD9Nv-B5o")
    app = Application.builder().token(token).build()
    app.add_handler(CallbackQueryHandler(button_callback, pattern=r"^dl_"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.run_polling()

if __name__ == "__main__":
    main()
