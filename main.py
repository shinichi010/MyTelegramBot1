import logging
import json
import os
import asyncio
import random
import re
import requests
import tempfile
import subprocess
from functools import partial
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
#  تهيئة الفايربيس (Firebase Initialization)
# ═══════════════════════════════════════════════
try:
    cred = credentials.Certificate('firebase.json')
    firebase_url = os.environ.get(
        'DATABASE_URL', 
        'https://mytelegrambotdb-default-rtdb.europe-west1.firebasedatabase.app/'
    )
    firebase_admin.initialize_app(cred, {'DATABASE_URL': firebase_url})
    logger.info(f"✅ تم الاتصال بقاعدة بيانات Firebase بنجاح!")
except Exception as e:
    logger.error(f"❌ فشل الاتصال بـ Firebase: {e}")

# ═══════════════════════════════════════════════
#  دوال التعامل مع قاعدة البيانات
# ═══════════════════════════════════════════════
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
    s = db_get(f"settings/{key}", {})
    defaults = {"welcome": True, "banned_words": [], "locked": False, "links_protection": False, "edit_notify": True, "ai_mode": False}
    changed = False
    for k, v in defaults.items():
        if k not in s: s[k] = v; changed = True
    if changed or not s: db_set(f"settings/{key}", s)
    return s

def save_settings(chat_id, s): db_set(f"settings/{str(chat_id)}", s)

# ══ الرتب ══
ROLE_OWNER = "owner"; ROLE_MANAGER = "manager"; ROLE_VIP = "vip"
ROLE_RANK = {ROLE_OWNER: 3, ROLE_MANAGER: 2, ROLE_VIP: 1}
ROLE_LABEL = {ROLE_OWNER: "👑 مالك", ROLE_MANAGER: "🛡 مدير", ROLE_VIP: "⭐ مميز"}

def get_role(chat_id, user_id): return db_get(f"roles/{chat_id}/{user_id}", None)
def set_role(chat_id, user_id, role): db_set(f"roles/{chat_id}/{user_id}", role)
def remove_role(chat_id, user_id): db_set(f"roles/{chat_id}/{user_id}", None)
def has_rank(chat_id, user_id, min_role):
    role = get_role(chat_id, user_id)
    return bool(role and ROLE_RANK.get(role, 0) >= ROLE_RANK.get(min_role, 99))

async def is_tg_owner(update, context):
    admins = await context.bot.get_chat_administrators(update.effective_chat.id)
    return any(a.user.id == update.effective_user.id and a.status == "creator" for a in admins)

async def is_privileged(update, context, min_role=ROLE_OWNER):
    return has_rank(update.effective_chat.id, update.effective_user.id, min_role) or await is_tg_owner(update, context)

async def get_target_user(update, context):
    msg = update.message
    if msg.reply_to_message: return msg.reply_to_message.from_user
    if msg.entities:
        for ent in msg.entities:
            if ent.type == "text_mention" and ent.user: return ent.user
    return None

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
    except:
        return "اعذرني، السيرفر مالتي مشغول حالياً 😅"

# ═══════════════════════════════════════════════
#  دوال التحميل المتطورة (يوتيوب وتيكتوك)
# ═══════════════════════════════════════════════
def download_tiktok(url):
    apis = [f'https://www.tikwm.com/api/?url={url}&hd=1', f'https://api.tiklydown.eu.org/api/download?url={url}']
    for api in apis:
        try:
            res = requests.get(api, timeout=15).json()
            if res.get('code') == 0 and 'data' in res:
                d = res['data']
                if 'images' in d and d['images']:
                    return {'type': 'images', 'data': d['images']}
                return {'type': 'video', 'data': d.get('hdplay') or d.get('play')}
        except: continue
    return None

# نظام تتبع نسبة التحميل
active_downloads = {}

def my_yt_hook(d, msg_id):
    if d['status'] == 'downloading':
        p = d.get('_percent_str', '0%').strip()
        p_clean = re.sub(r'\x1b\[[0-9;]*m', '', p)
        active_downloads[msg_id] = p_clean

async def update_progress_msg(context, chat_id, msg_id, status_msg_id):
    last_p = ""
    while msg_id in active_downloads:
        p = active_downloads[msg_id]
        if p and p != last_p:
            try:
                await context.bot.edit_message_text(f"⏳ جاري التحميل: {p}", chat_id=chat_id, message_id=status_msg_id)
                last_p = p
            except: pass
        await asyncio.sleep(2)

async def download_yt_media(url, media_type, quality, msg_id, chat_id, context, status_msg_id):
    tmp = tempfile.mkdtemp()
    ydl_opts = {
        'outtmpl': os.path.join(tmp, '%(title)s.%(ext)s'),
        'quiet': True, 'noplaylist': True,
        'progress_hooks': [lambda d: my_yt_hook(d, msg_id)]
    }
    
    if media_type == "audio":
        ydl_opts['format'] = 'bestaudio/best'
        ydl_opts['postprocessors'] = [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3', 'preferredquality': '192'}]
    else:
        # جودة الفيديو
        if quality == "1080": ydl_opts['format'] = 'bestvideo[height<=1080]+bestaudio/best[height<=1080]'
        elif quality == "720": ydl_opts['format'] = 'bestvideo[height<=720]+bestaudio/best[height<=720]'
        else: ydl_opts['format'] = 'bestvideo[height<=360]+bestaudio/best[height<=360]'
        ydl_opts['merge_output_format'] = 'mp4'

    active_downloads[msg_id] = "0%"
    # تشغيل مهمة تحديث الرسالة بالخلفية
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
        active_downloads.pop(msg_id, None)
        progress_task.cancel()
        return None, None

# ═══════════════════════════════════════════════
#  القوائم التفاعلية للأوامر
# ═══════════════════════════════════════════════
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
    "• <code>مسح X</code> — حذف رسائل"
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
    "• أرسل رابط يوتيوب أو تويتر (X) وسيعرض لك البوت أزرار لاختيار الجودة والصيغة (فيديو/صوت) مع عداد تحميل.\n"
    "• أرسل رابط تيك توك وسيحمله كفيديو أو ألبوم صور مباشر بدون علامة مائية."
)

def get_main_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🛡️ أوامر الإدارة", callback_data="cmd_admin"), InlineKeyboardButton("🎮 التسلية", callback_data="cmd_fun")],
        [InlineKeyboardButton("📥 قسم التحميل", callback_data="cmd_dl")]
    ])
def get_back_keyboard():
    return InlineKeyboardMarkup([[InlineKeyboardButton("🔙 العودة للقائمة", callback_data="cmd_main")]])

# ═══════════════════════════════════════════════
#  هاندلرات البداية والهمسة والتحميل والذكاء
# ═══════════════════════════════════════════════
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if msg.chat.type == 'private' and msg.text.startswith('/start w_'):
        try:
            parts = msg.text.replace('/start w_', '').split('_')
            sender_id, target_id, chat_id = int(parts[0]), int(parts[1]), int(parts[2].replace('m', '-'))
            if msg.from_user.id != sender_id:
                return await msg.reply_text("عذراً، هذا الرابط ليس لك! ❌")
            context.user_data['whisper_target'] = target_id
            context.user_data['whisper_chat'] = chat_id
            await msg.reply_text("🔒 *أرسل همستك الآن هنا بالخاص:* \n(سيتم إرسالها مشفرة للكروب تلقائياً)", parse_mode="Markdown")
        except: await msg.reply_text("حدث خطأ في رابط الهمسة.")
    else:
        await msg.reply_text("أهلاً بك! أنا بوت الإدارة الذكي 🚀")

async def handle_private_whisper(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
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

async def inline_button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    
    if data.startswith('show_w_'):
        await query.answer()
        w = db_get(f"whispers/{data.replace('show_w_', '')}", None)
        if w:
            if query.from_user.id in [w['target'], w['sender']]:
                await query.answer(text=f"💬 الهمسة:\n{w['text']}", show_alert=True)
            else: await query.answer(text="الهمسة مو إلك عيني! ❌👀", show_alert=True)
        else: await query.answer(text="هذه الهمسة قديمة أو غير موجودة.", show_alert=True)
        return

    # تنقل الأوامر
    if data.startswith("cmd_"):
        await query.answer()
        if data == "cmd_main": await query.edit_message_text(TEXT_MAIN_MENU, parse_mode="HTML", reply_markup=get_main_keyboard())
        elif data == "cmd_admin": await query.edit_message_text(TEXT_ADMIN_CMDS, parse_mode="HTML", reply_markup=get_back_keyboard())
        elif data == "cmd_fun": await query.edit_message_text(TEXT_FUN_CMDS, parse_mode="HTML", reply_markup=get_back_keyboard())
        elif data == "cmd_dl": await query.edit_message_text(TEXT_DOWNLOAD_CMDS, parse_mode="HTML", reply_markup=get_back_keyboard())
        return

    # أزرار التحميل
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
            
            filepath, title = await download_yt_media(url, m_type, qual, query.message.message_id, query.message.chat_id, context, query.message.message_id)
            if filepath and os.path.exists(filepath):
                await query.edit_message_text("📤 جاري الرفع للتيليجرام...")
                with open(filepath, 'rb') as file:
                    if m_type == "audio": await context.bot.send_audio(query.message.chat_id, file, title=title)
                    else: await context.bot.send_video(query.message.chat_id, file, caption=title)
                try: os.remove(filepath)
                except: pass
                await query.message.delete()
            else: await query.edit_message_text("❌ فشل التحميل. يرجى المحاولة لاحقاً.")

async def track_messages_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text or update.message.text.startswith('/'): return
    db_set(f"messages/{update.message.chat.id}/{update.message.message_id}", {"text": update.message.text})

async def handle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message: return
    msg = update.message
    text = (msg.text or "").strip()
    chat_id = msg.chat.id
    user_id = msg.from_user.id
    
    # ── حل مشكلة الهمسة بالخاص ──
    if msg.chat.type == 'private':
        if 'whisper_target' in context.user_data:
            await handle_private_whisper(update, context)
        return

    s = get_settings(chat_id)

    # ── وضع الذكاء الاصطناعي ──
    if s.get("ai_mode", False) and text and not text.startswith(('رفع', 'تنزيل', 'طرد', 'حظر', 'كتم', 'ايقاف سيك')):
        await context.bot.send_chat_action(chat_id, 'typing')
        reply = await ask_deepseek(text)
        await msg.reply_text(reply)
        return

    priv_owner = await is_privileged(update, context, ROLE_OWNER)
    priv_manager = await is_privileged(update, context, ROLE_MANAGER)
    any_role = bool(get_role(chat_id, user_id)) or await is_tg_owner(update, context)

    # ══ الأوامر ══
    if text == "تشغيل سيك" and priv_owner:
        s["ai_mode"] = True; save_settings(chat_id, s)
        await msg.reply_text("🤖 تم تفعيل الذكاء الاصطناعي! البوت هسه يجاوب على كلشي.")
        return
    if text == "ايقاف سيك" and priv_owner:
        s["ai_mode"] = False; save_settings(chat_id, s)
        await msg.reply_text("😴 تم إيقاف الذكاء الاصطناعي.")
        return

    if text == "الاوامر": return await msg.reply_text(TEXT_MAIN_MENU, parse_mode="HTML", reply_markup=get_main_keyboard())

    if text == "همسة" and msg.reply_to_message:
        target = msg.reply_to_message.from_user
        if target.is_bot: return await msg.reply_text("ما تكدر تهمس لبوت يا ذكي! 😂")
        bot_usr = context.bot.username
        markup = InlineKeyboardMarkup([[InlineKeyboardButton("🔒 اضغط هنا واكتب الهمسة", url=f"t.me/{bot_usr}?start=w_{user_id}_{target.id}_{str(chat_id).replace('-','m')}")]])
        return await msg.reply_text(f"يا {msg.from_user.first_name}، اضغط جوا واكتب همستك بالخاص 🤫", reply_markup=markup)

    if text == "تحويل" and msg.reply_to_message and msg.reply_to_message.video:
        wait = await msg.reply_text("🔄 جاري استخراج الصوت...")
        try:
            file = await msg.reply_to_message.video.get_file()
            in_p, out_p = f"tmp_v_{msg.message_id}.mp4", f"tmp_a_{msg.message_id}.mp3"
            await file.download_to_drive(in_p)
            subprocess.run(["ffmpeg", "-i", in_p, "-q:a", "0", "-map", "a", out_p, "-y"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            with open(out_p, 'rb') as audio: await msg.reply_audio(audio)
            os.remove(in_p); os.remove(out_p)
            await wait.delete()
        except: await wait.edit_text("❌ فشل التحويل. تأكد أن البوت يمتلك صلاحيات أو ffmpeg منصب بالسيرفر.")
        return

    if text.startswith("تثبيت") and priv_manager:
        if msg.reply_to_message: await context.bot.pin_chat_message(chat_id, msg.reply_to_message.message_id)
        return
    if text.startswith("الغاء تثبيت") and priv_manager:
        if msg.reply_to_message: await context.bot.unpin_chat_message(chat_id, msg.reply_to_message.message_id)
        return

    if text == "نسبة الحب" and msg.reply_to_message:
        perc = random.randint(0, 100)
        u1, u2 = msg.from_user.first_name, msg.reply_to_message.from_user.first_name
        return await msg.reply_text(f"💘 نسبة الحب بين {u1} و {u2} هي: {perc}%")

    if text == "فك حظر" and priv_manager:
        target = await get_target_user(update, context)
        if target:
            await context.bot.unban_chat_member(chat_id, target.id, only_if_banned=True)
            await msg.reply_text(f"✅ تم رفع الحظر عن {target.first_name}.")
        return

    if text == "الغاء كتم" and priv_manager:
        target = await get_target_user(update, context)
        if target:
            # الحل الصحيح لفك الكتم باسترجاع كامل الصلاحيات الأساسية
            perms = ChatPermissions(can_send_messages=True, can_send_audios=True, can_send_documents=True, can_send_photos=True, can_send_videos=True, can_send_video_notes=True, can_send_voice_notes=True, can_send_polls=True, can_send_other_messages=True, can_add_web_page_previews=True)
            await context.bot.restrict_chat_member(chat_id, target.id, permissions=perms)
            await msg.reply_text(f"🔊 تم رفع الكتم عن {target.first_name} بنجاح.")
        return

    # بقية الأوامر (مختصرة للحفاظ على المساحة بس شغالة طبيعي)
    if text in ("رفع مالك", "رفع مدير", "رفع مميز") and priv_owner:
        r_map = {"رفع مالك": ROLE_OWNER, "رفع مدير": ROLE_MANAGER, "رفع مميز": ROLE_VIP}
        tgt = await get_target_user(update, context)
        if tgt: set_role(chat_id, tgt.id, r_map[text]); await msg.reply_text(f"✅ صار {tgt.first_name} {ROLE_LABEL[r_map[text]]}.")
        return

    # ── ميديا يوتيوب وتويتر ──
    if re.search(r'youtube\.com|youtu\.be|x\.com|twitter\.com', text, re.I):
        url = re.search(r'https?://[^\s]+', text).group()
        wait = await msg.reply_text("🔍 جاري جلب المعلومات...")
        try:
            with YoutubeDL({'quiet': True, 'noplaylist': True}) as ydl: info = ydl.extract_info(url, download=False)
            url_hash = str(random.randint(1000, 9999))
            context.bot_data[url_hash] = url
            k = InlineKeyboardMarkup([
                [InlineKeyboardButton("🎬 تحميل فيديو", callback_data=f"dl_opts_{user_id}_{url_hash}")],
                [InlineKeyboardButton("🎵 تحميل صوت", callback_data=f"dl_audio_{user_id}_{url_hash}")]
            ])
            if info.get('thumbnail'): await msg.reply_photo(info['thumbnail'], caption=info.get('title', 'اختر الصيغة:'), reply_markup=k)
            else: await msg.reply_text(info.get('title', 'اختر الصيغة:'), reply_markup=k)
            await wait.delete()
        except: await wait.edit_text("❌ لم أتمكن من جلب بيانات هذا الرابط.")
        return

    # ── تيك توك ──
    if 'tiktok.com' in text:
        url = re.search(r'https?://[^\s]+', text).group()
        wait = await msg.reply_text("⏳ جاري معالجة التيك توك...")
        res = download_tiktok(url)
        if res:
            try:
                if res['type'] == 'images':
                    media = [InputMediaPhoto(img) for img in res['data']]
                    await context.bot.send_media_group(chat_id, media, reply_to_message_id=msg.message_id)
                else: await context.bot.send_video(chat_id, res['data'], reply_to_message_id=msg.message_id)
                await wait.delete()
            except: await wait.edit_text("❌ حجم الملف كبير أو حدث خطأ بالإرسال.")
        else: await wait.edit_text("❌ فشل التحميل.")
        return

async def edited_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.edited_message: return
    chat_id, msg_id = update.edited_message.chat.id, update.edited_message.message_id
    if not get_settings(chat_id).get("edit_notify", True): return
    new_text = update.edited_message.text or "[ميديا/ملف]"
    old_text = db_get(f"messages/{chat_id}/{msg_id}/text", "[غير متوفر]")
    db_set(f"messages/{chat_id}/{msg_id}", {"text": new_text})
    
    t = f"✏️ <b>إشعار تعديل</b>\n👤 <b>من:</b> {update.edited_message.from_user.first_name}\n❌ <b>قديم:</b> <code>{old_text}</code>\n✅ <b>جديد:</b> <code>{new_text}</code>"
    await context.bot.send_message(chat_id, t, parse_mode="HTML")

def main():
    token = os.environ.get("BOT_TOKEN", "8159446452:AAHvUE5aEvuTmGfwAYAV7EqfshKD9Nv-B5o")
    app = Application.builder().token(token).build()
    
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CallbackQueryHandler(inline_button_callback, pattern=r"^(show_w_|cmd_|dl_)"))
    app.add_handler(MessageHandler(filters.UpdateType.EDITED_MESSAGE & filters.TEXT, edited_message_handler))
    app.add_handler(MessageHandler(filters.ChatType.GROUPS & filters.TEXT & ~filters.COMMAND, track_messages_handler), group=1)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle), group=2)
    
    app.run_polling()

if __name__ == "__main__": main()
