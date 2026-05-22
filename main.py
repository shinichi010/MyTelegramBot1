import logging
import json
import os
import asyncio
import random
import re
import requests
import tempfile
import subprocess
import firebase_admin
from firebase_admin import credentials, db
from telegram import Update, ChatPermissions, InlineKeyboardMarkup, InlineKeyboardButton, InputMediaPhoto
from telegram.ext import (
    Application, MessageHandler, CallbackQueryHandler, CommandHandler,
    filters, ContextTypes,
)
from yt_dlp import YoutubeDL

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════
#  مصفوفات التسلية (وعد، لو خيروك)
# ═══════════════════════════════════════════════
wa3ed_list = [
    "اشرب جايك لا يبرد حبيبي ",
    "مالي خلكك ",
    "شتريد يا حياتي ؟ ❤️",
    "نعم يا احلا صوت بالقروب  🎤",
    "عيونها السود والبيض "
]

khayrok_list = [
    "لو خيروك: تسافر عبر الزمن للمستقبل لو للماضي؟ ⏳",
    "لو خيروك: تاكل بيتزا طول عمرك لو بركر طول عمرك؟ 🍕🍔",
    "لو خيروك: تصير غني بس بدون أصدقاء، لو فقير وعندك أصدقاء يحبوك؟ 💰",
    "لو خيروك: تكدر تقرأ أفكار الناس لو تكدر تطير؟ 🦅"
]

# ═══════════════════════════════════════════════
#  تهيئة الفايربيس
# ═══════════════════════════════════════════════
try:
    cred = credentials.Certificate('firebase.json')
    firebase_url = os.environ.get('DATABASE_URL', 'https://mytelegrambotdb-default-rtdb.europe-west1.firebasedatabase.app/')
    firebase_admin.initialize_app(cred, {'DATABASE_URL': firebase_url})
    logger.info("✅ تم الاتصال بقاعدة بيانات Firebase بنجاح!")
except Exception as e:
    logger.error(f"❌ فشل الاتصال بـ Firebase: {e}")

def db_get(path, default):
    try:
        val = db.reference(path).get()
        return val if val is not None else default
    except: return default

def db_set(path, data):
    try: db.reference(path).set(data)
    except Exception as e: logger.error(f"DB Error: {e}")

def get_settings(chat_id):
    key = str(chat_id)
    s = db_get(f"settings/{key}", {"welcome": True, "banned_words": [], "locked": False, "links_protection": False, "edit_notify": True, "ai_mode": False})
    return s

def save_settings(chat_id, s): db_set(f"settings/{str(chat_id)}", s)

ROLE_OWNER = "owner"; ROLE_MANAGER = "manager"; ROLE_VIP = "vip"
ROLE_RANK = {ROLE_OWNER: 3, ROLE_MANAGER: 2, ROLE_VIP: 1}
def get_role(chat_id, user_id): return db_get(f"roles/{chat_id}/{user_id}", None)

async def is_tg_owner(update, context):
    admins = await context.bot.get_chat_administrators(update.effective_chat.id)
    return any(a.user.id == update.effective_user.id and a.status == "creator" for a in admins)

async def is_privileged(update, context, min_role=ROLE_OWNER):
    role = get_role(update.effective_chat.id, update.effective_user.id)
    return bool(role and ROLE_RANK.get(role, 0) >= ROLE_RANK.get(min_role, 99)) or await is_tg_owner(update, context)

# ═══════════════════════════════════════════════
#  الذكاء الاصطناعي DeepSeek
# ═══════════════════════════════════════════════
async def ask_deepseek(prompt):
    api_key = "sk-f5149facf1164e6db0af5fd276c8fbfe"
    url = "https://api.deepseek.com/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    data = {
        "model": "deepseek-chat",
        "messages": [{"role": "system", "content": "أنت مساعد ذكي ولطيف تتحدث باللهجة العراقية أحياناً واسمك بوت الإدارة."},
                     {"role": "user", "content": prompt}],
        "max_tokens": 1000
    }
    try:
        res = requests.post(url, headers=headers, json=data, timeout=20)
        return res.json()["choices"][0]["message"]["content"]
    except: return "اعذرني، السيرفر مالتي مشغول حالياً 😅"

# ═══════════════════════════════════════════════
#  دوال التحميل (تيك توك ويوتيوب وتويتر)
# ═══════════════════════════════════════════════
def download_tiktok(url):
    api = f'https://www.tikwm.com/api/?url={url}&hd=1'
    try:
        res = requests.get(api, timeout=15).json()
        if res.get('code') == 0 and 'data' in res:
            d = res['data']
            author = d.get('author', {}).get('unique_id', 'مجهول')
            music = d.get('music', '')
            if isinstance(music, dict): music = music.get('play', '')
            
            if 'images' in d and d['images']:
                return {'type': 'images', 'data': d['images'], 'author': author, 'music': music}
            return {'type': 'video', 'data': d.get('hdplay') or d.get('play'), 'author': author, 'music': music}
    except: pass
    return None

active_downloads = {}
def my_yt_hook(d, msg_id):
    if d['status'] == 'downloading':
        p = d.get('_percent_str', '0%').strip()
        active_downloads[msg_id] = re.sub(r'\x1b\[[0-9;]*m', '', p)

async def update_progress_msg(context, chat_id, msg_id, status_msg_id):
    last_p = ""
    while msg_id in active_downloads:
        p = active_downloads[msg_id]
        if p and p != last_p:
            try:
                await context.bot.edit_message_text(f"⏳ جاري التحميل: {p}", chat_id=chat_id, message_id=status_msg_id)
                last_p = p
            except: pass
        await asyncio.sleep(2.5)

async def download_media_ytdlp(url, media_type, quality, msg_id, chat_id, context, status_msg_id):
    tmp = tempfile.mkdtemp()
    ydl_opts = {
        'outtmpl': os.path.join(tmp, '%(title)s.%(ext)s'),
        'quiet': True, 'noplaylist': True,
        'progress_hooks': [lambda d: my_yt_hook(d, msg_id)],
        'nocheckcertificate': True,
        'geo_bypass': True,
        'extractor_retries': 3
    }
    
    if media_type == "audio":
        ydl_opts['format'] = 'bestaudio/best'
        ydl_opts['postprocessors'] = [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3', 'preferredquality': '192'}]
    else:
        if quality == "1080": ydl_opts['format'] = 'bestvideo[height<=1080]+bestaudio/best'
        elif quality == "720": ydl_opts['format'] = 'bestvideo[height<=720]+bestaudio/best'
        elif quality == "360": ydl_opts['format'] = 'bestvideo[height<=360]+bestaudio/best'
        else: ydl_opts['format'] = 'best'
        ydl_opts['merge_output_format'] = 'mp4'

    active_downloads[msg_id] = "0%"
    progress_task = asyncio.create_task(update_progress_msg(context, chat_id, msg_id, status_msg_id))

    def run_dl():
        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            for f in os.listdir(tmp):
                if f.endswith('.mp3') or f.endswith('.mp4'):
                    return os.path.join(tmp, f), info.get('title', 'media')
        return None, None

    loop = asyncio.get_running_loop()
    try:
        filepath, title = await loop.run_in_executor(None, run_dl)
        active_downloads.pop(msg_id, None)
        progress_task.cancel()
        return filepath, title
    except Exception as e:
        logger.error(f"DL Error: {e}")
        active_downloads.pop(msg_id, None)
        progress_task.cancel()
        return None, None

# ═══════════════════════════════════════════════
#  أوامر التسلية والإضافات القديمة
# ═══════════════════════════════════════════════
async def fun_commands_handler(update, context, text, msg):
    # نسبة الحب
    if text == "نسبة الحب" and msg.reply_to_message:
        perc = random.randint(0, 100)
        u1 = msg.from_user.first_name
        u2 = msg.reply_to_message.from_user.first_name
        return await msg.reply_text(f"💘 نسبة الحب بين {u1} و {u2} هي: {perc}%")
    
    # وعد
    if text == "وعد": return await msg.reply_text(random.choice(wa3ed_list))
    
    # لو خيروك
    if text == "لو خيروك": return await msg.reply_text(random.choice(khayrok_list))
    
    # افتار (جلب صورة البروفايل)
    if text == "افتار":
        target = msg.reply_to_message.from_user if msg.reply_to_message else msg.from_user
        photos = await target.get_profile_photos()
        if photos:
            return await msg.reply_photo(photos[0].file_id, caption=f"🖼 افتار {target.first_name}")
        else: return await msg.reply_text("هذا العضو ما حاط صورة بروفايل!")

    # ايدي
    if text == "ايدي":
        target = msg.reply_to_message.from_user if msg.reply_to_message else msg.from_user
        return await msg.reply_text(f"🆔 ايدي العضو: `{target.id}`", parse_mode="Markdown")

    return False

# ═══════════════════════════════════════════════
#  الهاندلرات
# ═══════════════════════════════════════════════
async def inline_button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    
    if data.startswith("dl_"):
        await query.answer()
        parts = data.split('_')
        action, uid, url_hash = parts[1], parts[2], parts[3]
        
        if str(query.from_user.id) != uid:
            return await query.answer("هذه الأزرار لطلب شخص آخر!", show_alert=True)
            
        url = context.bot_data.get(url_hash)
        if not url: return await query.edit_message_text("❌ الرابط منتهي الصلاحية، أعد إرساله.")

        if action == "opts":
            k = InlineKeyboardMarkup([
                [InlineKeyboardButton("🎥 360p", callback_data=f"dl_vid360_{uid}_{url_hash}"), InlineKeyboardButton("🎥 720p", callback_data=f"dl_vid720_{uid}_{url_hash}")],
                [InlineKeyboardButton("🎥 1080p", callback_data=f"dl_vid1080_{uid}_{url_hash}")],
            ])
            await query.edit_message_reply_markup(k)
        
        elif action.startswith("vid") or action == "audio":
            await query.edit_message_text("⏳ جاري تحضير الملف...")
            m_type = "audio" if action == "audio" else "video"
            qual = action.replace("vid", "") if "vid" in action else None
            
            filepath, title = await download_media_ytdlp(url, m_type, qual, query.message.message_id, query.message.chat_id, context, query.message.message_id)
            if filepath and os.path.exists(filepath):
                await query.edit_message_text("📤 جاري الرفع للتيليجرام...")
                with open(filepath, 'rb') as file:
                    if m_type == "audio": await context.bot.send_audio(query.message.chat_id, file, title=title)
                    else: await context.bot.send_video(query.message.chat_id, file, caption=title)
                try: os.remove(filepath)
                except: pass
                await query.message.delete()
            else: await query.edit_message_text("❌ فشل التحميل. قد يكون المقطع محمي أو غير متوفر بتلك الجودة.")

async def handle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message: return
    msg = update.message
    text = (msg.text or "").strip()
    
    # تعريف المتغيرات الأساسية المفقودة
    chat_id = msg.chat_id
    user_id = msg.from_user.id
    s = get_settings(chat_id)
    is_owner = await is_tg_owner(update, context)  # أو يمكن استخدام is_privileged حسب الحاجة
    
    # معالجة أوامر التسلية أولاً
    fun_res = await fun_commands_handler(update, context, text, msg)
    if fun_res: return  # إذا تم تنفيذ أمر تسلية، نوقف التنفيذ
    
    # وضع الذكاء الاصطناعي
    if s.get("ai_mode", False) and text and not text.startswith(('رفع', 'تنزيل', 'طرد', 'حظر', 'كتم', 'ايقاف سيك', 'تشغيل سيك')):
        await context.bot.send_chat_action(chat_id, 'typing')
        reply = await ask_deepseek(text)
        return await msg.reply_text(reply)

    # تشغيل وإيقاف الذكاء الاصطناعي (للمالك فقط)
    if text == "تشغيل سيك" and is_owner:
        s["ai_mode"] = True
        save_settings(chat_id, s)
        return await msg.reply_text("🤖 تم تفعيل الذكاء الاصطناعي!")
    if text == "ايقاف سيك" and is_owner:
        s["ai_mode"] = False
        save_settings(chat_id, s)
        return await msg.reply_text("😴 تم إيقاف الذكاء الاصطناعي.")

    # ── يوتيوب ──
    if re.search(r'youtube\.com|youtu\.be', text, re.I):
        url = re.search(r'https?://[^\s]+', text).group()
        wait = await msg.reply_text("🔍 جاري جلب المعلومات من يوتيوب...")
        try:
            with YoutubeDL({'quiet': True, 'noplaylist': True, 'nocheckcertificate': True}) as ydl:
                info = ydl.extract_info(url, download=False)
            url_hash = str(random.randint(1000, 9999))
            context.bot_data[url_hash] = url
            k = InlineKeyboardMarkup([
                [InlineKeyboardButton("🎬 تحميل فيديو", callback_data=f"dl_opts_{user_id}_{url_hash}")],
                [InlineKeyboardButton("🎵 تحميل صوت", callback_data=f"dl_audio_{user_id}_{url_hash}")]
            ])
            if info.get('thumbnail'):
                await msg.reply_photo(info['thumbnail'], caption=info.get('title', 'اختر الصيغة:'), reply_markup=k)
            else:
                await msg.reply_text(info.get('title', 'اختر الصيغة:'), reply_markup=k)
            await wait.delete()
        except Exception as e:
            await wait.edit_text("❌ لم أتمكن من جلب بيانات هذا الرابط، قد يكون محمي أو البوت محظور مؤقتاً.")
        return

    # ── تويتر (X) ──
    if re.search(r'x\.com|twitter\.com', text, re.I):
        url = re.search(r'https?://[^\s]+', text).group()
        wait = await msg.reply_text("⏳ جاري تحميل المقطع من تويتر مباشرة...")
        filepath, title = await download_media_ytdlp(url, "video", "best", msg.message_id, chat_id, context, wait.message_id)
        if filepath and os.path.exists(filepath):
            await wait.edit_text("📤 جاري الرفع للتيليجرام...")
            with open(filepath, 'rb') as file:
                await context.bot.send_video(chat_id, file, caption="✅ تم التحميل من منصة X")
            os.remove(filepath)
            await wait.delete()
        else:
            await wait.edit_text("❌ فشل التحميل من تويتر.")
        return

    # ── تيك توك ──
    if 'tiktok.com' in text:
        url = re.search(r'https?://[^\s]+', text).group()
        wait = await msg.reply_text("⏳ جاري المعالجة...")
        res = download_tiktok(url)
        if res:
            caption = f"👤 <b>الحساب:</b> @{res['author']}"
            try:
                if res['type'] == 'images':
                    media = [InputMediaPhoto(img) for img in res['data']]
                    await context.bot.send_media_group(chat_id, media, reply_to_message_id=msg.message_id)
                    if res.get('music'):
                        await context.bot.send_audio(chat_id, res['music'], caption=caption, parse_mode="HTML")
                else:
                    await context.bot.send_video(chat_id, res['data'], caption=caption, parse_mode="HTML", reply_to_message_id=msg.message_id)
                await wait.delete()
            except Exception as e:
                await wait.edit_text("❌ حدث خطأ بالإرسال.")
        else:
            await wait.edit_text("❌ فشل التحميل.")
        return

def main():
    token = os.environ.get("BOT_TOKEN", "8159446452:AAHvUE5aEvuTmGfwAYAV7EqfshKD9Nv-B5o")
    app = Application.builder().token(token).build()
    app.add_handler(CallbackQueryHandler(inline_button_callback, pattern=r"^dl_"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle))
    app.run_polling()

if __name__ == "__main__":
    main()
