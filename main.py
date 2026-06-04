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
from telegram import Update, ChatPermissions, InlineKeyboardMarkup, InlineKeyboardButton, InputMediaPhoto
from telegram.ext import (
    Application, MessageHandler, CallbackQueryHandler, CommandHandler,
    filters, ContextTypes,
)
from yt_dlp import YoutubeDL
import imageio_ffmpeg

# إعداد التسجيل
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════
# 1. مصفوفات التسلية والقوائم
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
    "لو خيروك: تاكل بيتزا طول عمرك لو بركر طول عمرك? 🍕🍔",
    "لو خيروك: تصير غني بس بدون أصدقاء، لو فقير وعندك أصدقاء يحبوك؟ 💰",
    "لو خيروك: تكدر تقرأ أفكار الناس لو تكدر تطير؟ 🦅"
]

TEXT_MAIN_MENU = "📋 <b>أهلاً بك في لوحة أوامر البوت المتكاملة</b>\n\nالرجاء اختيار القسم الذي تود تصفحه من الأزرار بالأسفل 👇"
TEXT_ADMIN_CMDS = (
    "👑 <b>أوامر المالك والمدراء:</b>\n"
    "• <code>رفع مالك | مدير | مميز</code> / <code>تنزيل رتبة</code>\n"
    "• <code>طرد | حظر | فك حظر</code> / <code>تثبيت | الغاء تثبيت</code>\n"
    "• <code>كتم | الغاء كتم</code> / <code>قفل الشات | فتح الشات</code>\n"
    "• <code>تحذير | الغاء تحذير | تحذيراتي</code>\n"
    "• <code>منع كلمة X | حذف كلمة X | الكلمات</code>\n"
    "• <code>الترحيب تشغيل | الترحيب ايقاف</code>\n"
    "• <code>تعديل تشغيل | تعديل ايقاف</code>\n"
    "• <code>تشغيل سيك | ايقاف سيك</code> — للذكاء الاصطناعي\n"
    "• <code>مسح X</code> — لحذف عدد من الرسائل"
)
TEXT_FUN_CMDS = (
    "👥 <b>أوامر التسلية والخدمات العامة:</b>\n"
    "• <code>همسة</code> — همسة سرية (بالرد)\n"
    "• <code>ايدي</code> / <code>افتار</code>\n"
    "• <code>زواج | طلاق | شريكي | نسبة الحب</code>\n"
    "• <code>تحويل</code> — بالرد على فيديو لتحويله لصوت\n"
    "• <code>لو خيروك | وعد</code>"
)
TEXT_DOWNLOAD_CMDS = (
    "📥 <b>قسم التحميل المتطور:</b>\n"
    "• أرسل رابط يوتيوب (أو شورت) وسيعرض لك البوت أزرار لاختيار الجودة والصيغة.\n"
    "• أرسل رابط تويتر (X) وسيحمله كفيديو فوراً.\n"
    "• أرسل رابط تيك توك وسيحمله كفيديو أو ألبوم صور مباشر بدون علامة مائية."
)

def get_main_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🛡️ أوامر الإدارة", callback_data="cmd_admin"), InlineKeyboardButton("🎮 التسلية", callback_data="cmd_fun")],
        [InlineKeyboardButton("📥 قسم التحميل", callback_data="cmd_dl")]
    ])

def get_back_keyboard():
    return InlineKeyboardMarkup([[InlineKeyboardButton("🔙 العودة للقائمة", callback_data="cmd_main")]])

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
    except: return default

def db_set(path, data):
    try: db.reference(path).set(data)
    except Exception as e: logger.error(f"DB set error: {e}")

def get_settings(chat_id):
    return db_get(f"settings/{str(chat_id)}", {"welcome": True, "banned_words": [], "locked": False, "links_protection": False, "edit_notify": True, "ai_mode": False})

def save_settings(chat_id, settings):
    db_set(f"settings/{str(chat_id)}", settings)

# ═══════════════════════════════════════════════════════════════════
# 3. الصلاحيات
# ═══════════════════════════════════════════════════════════════════
ROLE_OWNER = "owner"; ROLE_MANAGER = "manager"; ROLE_VIP = "vip"
ROLE_RANK = {ROLE_OWNER: 3, ROLE_MANAGER: 2, ROLE_VIP: 1}
ROLE_LABEL = {ROLE_OWNER: "👑 مالك", ROLE_MANAGER: "🛡 مدير", ROLE_VIP: "⭐ مميز"}

def get_role(chat_id, user_id): return db_get(f"roles/{chat_id}/{user_id}", None)
def set_role(chat_id, user_id, role): db_set(f"roles/{chat_id}/{user_id}", role)
def remove_role(chat_id, user_id): db_set(f"roles/{chat_id}/{user_id}", None)

async def is_tg_owner(update: Update, context: ContextTypes.DEFAULT_TYPE):
    admins = await context.bot.get_chat_administrators(update.effective_chat.id)
    return any(a.user.id == update.effective_user.id and a.status == "creator" for a in admins)

async def is_privileged(update: Update, context: ContextTypes.DEFAULT_TYPE, min_role=ROLE_OWNER):
    role = get_role(update.effective_chat.id, update.effective_user.id)
    return bool(role and ROLE_RANK.get(role, 0) >= ROLE_RANK.get(min_role, 99)) or await is_tg_owner(update, context)

async def get_target_user(update, context):
    msg = update.message
    if msg.reply_to_message: return msg.reply_to_message.from_user
    if msg.entities:
        for ent in msg.entities:
            if ent.type == "text_mention" and ent.user: return ent.user
    return None

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
            {"role": "system", "content": "أنت مساعد ذكي ولطيف تتحدث باللهجة العراقية أحياناً واسمك بوت الإدارة."},
            {"role": "user", "content": prompt}
        ],
        "max_tokens": 1000
    }
    try:
        res = requests.post(url, headers=headers, json=data, timeout=20)
        return res.json()["choices"][0]["message"]["content"]
    except: return "اعذرني، السيرفر مشغول حالياً 😅"

# ═══════════════════════════════════════════════════════════════════
# 5. دوال التحميل والتحديث للتقدم
# ═══════════════════════════════════════════════════════════════════
active_downloads = {}

def progress_hook(d, msg_id):
    if d['status'] == 'downloading':
        percent = d.get('_percent_str', '0%').strip()
        percent = re.sub(r'\x1b\[[0-9;]*m', '', percent)
        active_downloads[msg_id] = percent

async def update_progress(context, chat_id, msg_id, status_msg_id, is_photo=False):
    last = ""
    while msg_id in active_downloads:
        current = active_downloads.get(msg_id, "")
        if current and current != last:
            try:
                if is_photo:
                    await context.bot.edit_message_caption(chat_id=chat_id, message_id=status_msg_id, caption=f"⏳ جاري التحميل: {current}")
                else:
                    await context.bot.edit_message_text(f"⏳ جاري التحميل: {current}", chat_id=chat_id, message_id=status_msg_id)
                last = current
            except: pass
        await asyncio.sleep(2.5)

async def download_media(url, media_type, quality, msg_id, chat_id, context, status_msg_id, is_photo=False):
    tmp = tempfile.mkdtemp()
    ydl_opts = {
        'outtmpl': os.path.join(tmp, '%(title)s.%(ext)s'),
        'quiet': True,
        'noplaylist': True,
        'progress_hooks': [lambda d: progress_hook(d, msg_id)],
        'nocheckcertificate': True,
        'geo_bypass': True,
        'extractor_retries': 3,
        'ffmpeg_location': imageio_ffmpeg.get_ffmpeg_exe(),
        'http_headers': {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36'}
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
    progress_task = asyncio.create_task(update_progress(context, chat_id, msg_id, status_msg_id, is_photo))

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
        return path, title, tmp
    except Exception as e:
        logger.error(f"Download error: {e}")
        active_downloads.pop(msg_id, None)
        progress_task.cancel()
        shutil.rmtree(tmp, ignore_errors=True)
        return None, None, None

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

# ═══════════════════════════════════════════════════════════════════
# 6. الدوال الفرعية الموحدة لمعالجة الروابط
# ═══════════════════════════════════════════════════════════════════
async def handle_youtube_link(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str, user_id: int):
    msg = update.message
    url = re.search(r'https?://[^\s]+', text).group()
    wait_msg = await msg.reply_text("🔍 جاري جلب المعلومات من يوتيوب...")
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
        await wait_msg.edit_text("❌ فشل جلب بيانات الرابط.")

async def handle_twitter_link(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str, chat_id: int):
    msg = update.message
    url = re.search(r'https?://[^\s]+', text).group()
    wait_msg = await msg.reply_text("⏳ جاري تحميل المقطع من تويتر...")
    filepath, title, tmp_dir = await download_media(url, "video", "best", msg.message_id, chat_id, context, wait_msg.message_id, is_photo=False)
    if filepath and os.path.exists(filepath):
        await wait_msg.edit_text("📤 جاري الرفع...")
        with open(filepath, 'rb') as f: await context.bot.send_video(chat_id, f, caption="✅ تم التحميل من X")
        await wait_msg.delete()
    else: await wait_msg.edit_text("❌ فشل التحميل من تويتر.")
    if tmp_dir: shutil.rmtree(tmp_dir, ignore_errors=True)

async def handle_tiktok_link(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str, chat_id: int, reply_to_id: int):
    url = re.search(r'https?://[^\s]+', text).group()
    wait_msg = await update.message.reply_text("⏳ جاري تحميل التيك توك...")
    data = download_tiktok(url)
    if data:
        caption = f"👤 <b>الحساب:</b> @{data['author']}"
        try:
            if data['type'] == 'images':
                media = [InputMediaPhoto(img) for img in data['data']]
                await context.bot.send_media_group(chat_id, media, reply_to_message_id=reply_to_id)
                if data.get('music'): await context.bot.send_audio(chat_id, data['music'], caption=caption, parse_mode="HTML")
            else: 
                await context.bot.send_video(chat_id, data['data'], caption=caption, parse_mode="HTML", reply_to_message_id=reply_to_id)
            await wait_msg.delete()
        except Exception as e: await wait_msg.edit_text("❌ حدث خطأ أثناء الإرسال.")
    else: await wait_msg.edit_text("❌ فشل التحميل من تيك توك.")

# ═══════════════════════════════════════════════════════════════════
# 7. الهاندلرات (بداية، همسة، كولباك، مسار الرسائل)
# ═══════════════════════════════════════════════════════════════════
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if msg.chat.type == 'private' and msg.text.startswith('/start w_'):
        try:
            parts = msg.text.replace('/start w_', '').split('_')
            sender_id, target_id, chat_id = int(parts[0]), int(parts[1]), int(parts[2].replace('m', '-'))
            if msg.from_user.id != sender_id: return await msg.reply_text("عذراً، هذا الرابط ليس لك! ❌")
            context.user_data['whisper_target'] = target_id
            context.user_data['whisper_chat'] = chat_id
            await msg.reply_text("🔒 *أرسل همستك الآن هنا بالخاص:* \n(سيتم إرسالها مشفرة للكروب تلقائياً)", parse_mode="Markdown")
        except: await msg.reply_text("حدث خطأ في رابط الهمسة.")
    else: await msg.reply_text("أهلاً بك! أنا بوت الإدارة والتحميل الذكي 🚀\nأرسل أي رابط هنا (يوتيوب، تيك توك، تويتر) لتحميله فوراً، أو تحدث معي مباشرة لأرد عليك بالذكاء الاصطناعي!")

async def handle_private_whisper(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg.text: return
    target_id = context.user_data.get('whisper_target')
    chat_id = context.user_data.get('whisper_chat')
    if not target_id or not chat_id: return

    w_id = str(random.randint(100000, 999999))
    db_set(f"whispers/{w_id}", {'text': msg.text, 'sender': msg.from_user.id, 'target': target_id})
    context.user_data.pop('whisper_target', None)
    context.user_data.pop('whisper_chat', None)
    
    markup = InlineKeyboardMarkup([[InlineKeyboardButton("🔒 قراءة الهمسة", callback_data=f"show_w_{w_id}")]])
    try:
        member = await context.bot.get_chat_member(chat_id, target_id)
        target_name = member.user.first_name
    except: target_name = "العضو المستهدف"
        
    await context.bot.send_message(chat_id, f"🤫 *همسة سرية جديدة!*\nمن: {msg.from_user.first_name}\nإلى: {target_name}\n\nفقط المستهدف يمكنه القراءة 👇", reply_markup=markup, parse_mode="Markdown")
    await msg.reply_text("✅ تم تشفير همستك وإرسالها للكروب بنجاح!")

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data

    # ── حل مشكلة الهمسة السرية ──
    if data.startswith('show_w_'):
        w = db_get(f"whispers/{data.replace('show_w_', '')}", None)
        if w:
            if query.from_user.id in [w['target'], w['sender']]: 
                await query.answer(text=f"💬 الهمسة:\n{w['text']}", show_alert=True)
            else: 
                await query.answer(text="الهمسة مو إلك عيني! ❌👀", show_alert=True)
        else: 
            await query.answer(text="هذه الهمسة قديمة أو غير موجودة.", show_alert=True)
        return

    # ── قوائم الأوامر ──
    if data.startswith("cmd_"):
        await query.answer()
        if data == "cmd_main": await query.edit_message_text(TEXT_MAIN_MENU, parse_mode="HTML", reply_markup=get_main_keyboard())
        elif data == "cmd_admin": await query.edit_message_text(TEXT_ADMIN_CMDS, parse_mode="HTML", reply_markup=get_back_keyboard())
        elif data == "cmd_fun": await query.edit_message_text(TEXT_FUN_CMDS, parse_mode="HTML", reply_markup=get_back_keyboard())
        elif data == "cmd_dl": await query.edit_message_text(TEXT_DOWNLOAD_CMDS, parse_mode="HTML", reply_markup=get_back_keyboard())
        return

    # ── حل مشكلة أزرار جودة التحميل ──
    if data.startswith("dl_"):
        parts = data.split('_')
        action, uid, url_hash = parts[1], parts[2], parts[3]

        if str(query.from_user.id) != uid: 
            return await query.answer("هذه الأزرار لطلب شخص آخر!", show_alert=True)
            
        await query.answer()
        url = context.bot_data.get(url_hash)
        
        is_photo = bool(query.message.photo) # فحص نوع الرسالة إذا كانت ميديا أو نص لتجنب الكراش

        if not url: 
            if is_photo: await query.edit_message_caption("❌ الرابط منتهي الصلاحية، أعد إرساله.")
            else: await query.edit_message_text("❌ الرابط منتهي الصلاحية، أعد إرساله.")
            return

        if action == "opts":
            k = InlineKeyboardMarkup([
                [InlineKeyboardButton("🎥 360p", callback_data=f"dl_vid360_{uid}_{url_hash}"), InlineKeyboardButton("🎥 720p", callback_data=f"dl_vid720_{uid}_{url_hash}")],
                [InlineKeyboardButton("🎥 1080p", callback_data=f"dl_vid1080_{uid}_{url_hash}")]
            ])
            return await query.edit_message_reply_markup(k)

        if is_photo: await query.edit_message_caption("⏳ جاري تحضير الملف...")
        else: await query.edit_message_text("⏳ جاري تحضير الملف...")
        
        media_type = "audio" if action == "audio" else "video"
        quality = action.replace("vid", "") if "vid" in action else None

        filepath, title, tmp_dir = await download_media(url, media_type, quality, query.message.message_id, query.message.chat_id, context, query.message.message_id, is_photo=is_photo)
        if filepath and os.path.exists(filepath):
            try:
                if is_photo: await query.edit_message_caption("📤 جاري الرفع...")
                else: await query.edit_message_text("📤 جاري الرفع...")
            except: pass
            with open(filepath, 'rb') as f:
                if media_type == "audio": await context.bot.send_audio(query.message.chat_id, f, title=title)
                else: await context.bot.send_video(query.message.chat_id, f, caption=title)
            await query.message.delete()
        else:
            try:
                if is_photo: await query.edit_message_caption("❌ فشل التحميل. حاول مرة أخرى.")
                else: await query.edit_message_text("❌ فشل التحميل. حاول مرة أخرى.")
            except: pass
        
        if tmp_dir: shutil.rmtree(tmp_dir, ignore_errors=True)

async def track_messages_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text or update.message.text.startswith('/'): return
    db_set(f"messages/{update.message.chat.id}/{update.message.message_id}", {"text": update.message.text})

async def edited_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.edited_message: return
    chat_id, msg_id = update.edited_message.chat.id, update.edited_message.message_id
    if not get_settings(chat_id).get("edit_notify", True): return
    new_text = update.edited_message.text or "[ميديا/ملف]"
    old_text = db_get(f"messages/{chat_id}/{msg_id}/text", "[غير متوفر]")
    db_set(f"messages/{chat_id}/{msg_id}", {"text": new_text})
    t = f"✏️ <b>إشعار تعديل</b>\n👤 <b>من:</b> {update.edited_message.from_user.first_name}\n❌ <b>قديم:</b> <code>{old_text}</code>\n✅ <b>جديد:</b> <code>{new_text}</code>"
    await context.bot.send_message(chat_id, t, parse_mode="HTML")

async def welcome_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    for member in update.message.new_chat_members:
        if member.is_bot: continue
        s = get_settings(update.message.chat.id)
        if s.get("welcome", True):
            name = f'<a href="tg://user?id={member.id}">{member.first_name}</a>'
            try:
                photos = await context.bot.get_user_profile_photos(member.id, limit=1)
                if photos.total_count > 0: await context.bot.send_photo(update.message.chat.id, photos.photos[0][-1].file_id, caption=f"👋 أهلاً {name} في المجموعة! 🎉", parse_mode="HTML")
                else: await update.message.reply_text(f"👋 أهلاً {name} في المجموعة! 🎉", parse_mode="HTML")
            except: await update.message.reply_text(f"👋 أهلاً {name} في المجموعة! 🎉", parse_mode="HTML")

# ═══════════════════════════════════════════════════════════════════
# 8. المعالج الرئيسي للرسائل (كروبات + خاص مطور)
# ═══════════════════════════════════════════════════════════════════
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message: return
    msg = update.message
    text = (msg.text or "").strip()
    chat_id = msg.chat_id
    user_id = msg.from_user.id

    if not text: return

    # 📥 [أولاً] تفعيل ميزات الخاص الكاملة (تحميل + ذكاء اصطناعي حر)
    if msg.chat.type == 'private':
        if 'whisper_target' in context.user_data: 
            await handle_private_whisper(update, context)
            return
        if re.search(r'(youtube\.com|youtu\.be|shorts)', text, re.I):
            await handle_youtube_link(update, context, text, user_id)
            return
        if re.search(r'(x\.com|twitter\.com)', text, re.I):
            await handle_twitter_link(update, context, text, chat_id)
            return
        if 'tiktok.com' in text:
            await handle_tiktok_link(update, context, text, chat_id, msg.message_id)
            return
        if not text.startswith('/'):
            await context.bot.send_chat_action(chat_id, 'typing')
            reply = await ask_deepseek(text)
            await msg.reply_text(reply)
            return
        return

    # 👥 [ثانياً] التعامل مع المجموعات (الكروبات)
    settings = get_settings(chat_id)
    priv_owner = await is_privileged(update, context, ROLE_OWNER)
    priv_manager = await is_privileged(update, context, ROLE_MANAGER)

    if text == "الاوامر": return await msg.reply_text(TEXT_MAIN_MENU, parse_mode="HTML", reply_markup=get_main_keyboard())
    if text == "نسبة الحب" and msg.reply_to_message:
        return await msg.reply_text(f"💘 نسبة الحب بين {msg.from_user.first_name} و {msg.reply_to_message.from_user.first_name} هي: {random.randint(0, 100)}%")
    if text == "وعد": return await msg.reply_text(random.choice(WA3ED_LIST))
    if text == "لو خيروك": return await msg.reply_text(random.choice(KHAYROK_LIST))
    if text == "افتار":
        target = msg.reply_to_message.from_user if msg.reply_to_message else msg.from_user
        photos = await target.get_profile_photos(limit=1)
        if photos and photos.total_count > 0: return await msg.reply_photo(photos.photos[0][-1].file_id, caption=f"🖼 افتار {target.first_name}")
        return await msg.reply_text("هذا العضو ما حاط صورة بروفايل!")
    if text == "ايدي":
        target = msg.reply_to_message.from_user if msg.reply_to_message else msg.from_user
        return await msg.reply_text(f"🆔 ايدي العضو: `{target.id}`", parse_mode="Markdown")

    if text == "همسة" and msg.reply_to_message:
        target = msg.reply_to_message.from_user
        if target.is_bot: return await msg.reply_text("ما تكدر تهمس لبوت يا ذكي! 😂")
        markup = InlineKeyboardMarkup([[InlineKeyboardButton("🔒 اضغط هنا واكتب الهمسة", url=f"t.me/{context.bot.username}?start=w_{user_id}_{target.id}_{str(chat_id).replace('-','m')}")]])
        return await msg.reply_text(f"يا {msg.from_user.first_name}، اضغط جوا واكتب همستك بالخاص 🤫", reply_markup=markup)

    if text == "تحويل" and msg.reply_to_message and msg.reply_to_message.video:
        wait = await msg.reply_text("🔄 جاري استخراج الصوت...")
        try:
            ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
            file = await msg.reply_to_message.video.get_file()
            in_p = f"tmp_v_{msg.message_id}.mp4"
            out_p = f"tmp_a_{msg.message_id}.mp3"
            await file.download_to_drive(custom_path=in_p)
            result = subprocess.run([ffmpeg_exe, "-i", in_p, "-q:a", "0", "-map", "a", out_p, "-y"], capture_output=True, text=True)
            if os.path.exists(out_p):
                with open(out_p, 'rb') as audio: await msg.reply_audio(audio)
                await wait.delete()
            else:
                raise Exception(result.stderr if result.stderr else "فشل استخراج الصوت.")
            if os.path.exists(in_p): os.remove(in_p)
            if os.path.exists(out_p): os.remove(out_p)
        except Exception as e:
            logger.error(f"Conversion error: {e}")
            await wait.edit_text(f"❌ <b>فشل التحويل!</b>\n\n<code>{str(e)[:300]}</code>", parse_mode="HTML")
        return

    # الأوامر الإدارية
    if text in ("رفع مالك", "رفع مدير", "رفع مميز") and priv_owner:
        r_map = {"رفع مالك": ROLE_OWNER, "رفع مدير": ROLE_MANAGER, "رفع مميز": ROLE_VIP}
        tgt = await get_target_user(update, context)
        if tgt: set_role(chat_id, tgt.id, r_map[text]); await msg.reply_text(f"✅ صار {tgt.first_name} {ROLE_LABEL[r_map[text]]}.")
        return
    if text == "تنزيل رتبة" and priv_owner:
        tgt = await get_target_user(update, context)
        if tgt: remove_role(chat_id, tgt.id); await msg.reply_text(f"✅ تمت إزالة رتبة {tgt.first_name}.")
        return
    if text == "طرد" and priv_manager:
        tgt = await get_target_user(update, context)
        if tgt: await context.bot.ban_chat_member(chat_id, tgt.id); await context.bot.unban_chat_member(chat_id, tgt.id); await msg.reply_text(f"👢 تم طرد {tgt.first_name}.")
        return
    if text == "حظر" and priv_manager:
        tgt = await get_target_user(update, context)
        if tgt: await context.bot.ban_chat_member(chat_id, tgt.id); await msg.reply_text(f"🚫 تم حظر {tgt.first_name}.")
        return
    if text == "فك حظر" and priv_manager:
        tgt = await get_target_user(update, context)
        if tgt: await context.bot.unban_chat_member(chat_id, tgt.id, only_if_banned=True); await msg.reply_text(f"✅ تم رفع الحظر عن {tgt.first_name}.")
        return
    if text == "كتم" and priv_manager:
        tgt = await get_target_user(update, context)
        if tgt: await context.bot.restrict_chat_member(chat_id, tgt.id, ChatPermissions(can_send_messages=False)); await msg.reply_text(f"🔇 تم كتم {tgt.first_name}.")
        return
    if text == "الغاء كتم" and priv_manager:
        tgt = await get_target_user(update, context)
        if tgt:
            perms = ChatPermissions(can_send_messages=True, can_send_audios=True, can_send_documents=True, can_send_photos=True, can_send_videos=True, can_send_video_notes=True, can_send_voice_notes=True, can_send_polls=True, can_send_other_messages=True, can_add_web_page_previews=True)
            await context.bot.restrict_chat_member(chat_id, tgt.id, permissions=perms); await msg.reply_text(f"🔊 تم رفع الكتم عن {tgt.first_name}.")
        return
    if text.startswith("تثبيت") and priv_manager:
        if msg.reply_to_message: await context.bot.pin_chat_message(chat_id, msg.reply_to_message.message_id)
        return
    if text.startswith("الغاء تثبيت") and priv_manager:
        if msg.reply_to_message: await context.bot.unpin_chat_message(chat_id, msg.reply_to_message.message_id)
        return

    # التحكم بالذكاء الاصطناعي في الكروب
    if text == "تشغيل سيك" and priv_owner:
        settings["ai_mode"] = True; save_settings(chat_id, settings); return await msg.reply_text("🤖 تم تفعيل الذكاء الاصطناعي في الكروب!")
    if text == "ايقاف سيك" and priv_owner:
        settings["ai_mode"] = False; save_settings(chat_id, settings); return await msg.reply_text("😴 تم إيقاف الذكاء الاصطناعي في الكروب.")

    # فحص الروابط بالكروبات
    if re.search(r'(youtube\.com|youtu\.be|shorts)', text, re.I):
        await handle_youtube_link(update, context, text, user_id)
        return
    if re.search(r'(x\.com|twitter\.com)', text, re.I):
        await handle_twitter_link(update, context, text, chat_id)
        return
    if 'tiktok.com' in text:
        await handle_tiktok_link(update, context, text, chat_id, msg.message_id)
        return

    # الرد بالذكاء الاصطناعي بالكروب إذا تم تفعيله
    if settings.get("ai_mode", False) and not text.startswith(('رفع', 'تنزيل', 'طرد', 'حظر', 'كتم', 'قفل', 'فتح')):
        await context.bot.send_chat_action(chat_id, 'typing')
        reply = await ask_deepseek(text)
        return await msg.reply_text(reply)

# ═══════════════════════════════════════════════════════════════════
# 9. تشغيل البوت
# ═══════════════════════════════════════════════════════════════════
def main():
    token = os.environ.get("BOT_TOKEN", "8159446452:AAHvUE5aEvuTmGfwAYAV7EqfshKD9Nv-B5o")
    app = Application.builder().token(token).build()
    
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CallbackQueryHandler(button_callback, pattern=r"^(show_w_|cmd_|dl_)"))
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, welcome_member))
    app.add_handler(MessageHandler(filters.UpdateType.EDITED_MESSAGE & filters.TEXT, edited_message_handler))
    app.add_handler(MessageHandler(filters.ChatType.GROUPS & filters.TEXT & ~filters.COMMAND, track_messages_handler), group=1)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message), group=2)
    
    app.run_polling()

if __name__ == "__main__":
    main()
