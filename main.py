import logging
import json
import os
import asyncio
import random
import re
import requests
import tempfile
import firebase_admin
from firebase_admin import credentials, db
from telegram import Update, ChatPermissions, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    Application, MessageHandler, CallbackQueryHandler, CommandHandler,
    filters, ContextTypes,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════
#  تهيئة الفايربيس (Firebase Initialization)
# ═══════════════════════════════════════════════
try:
    cred = credentials.Certificate('firebase.json')
    firebase_admin.initialize_app(cred, {
        'databaseURL': 'https://mytelegrambotdb-default-rtdb.firebaseio.com/'  # تأكد من مطابقة الرابط الخاص بك
    })
    logger.info("✅ تم الاتصال بقاعدة بيانات Firebase بنجاح!")
except Exception as e:
    logger.error(f"❌ فشل الاتصال بـ Firebase: {e}")

# ═══════════════════════════════════════════════
#  دوال التعامل مع Firebase بدلاً من الـ Local JSON
# ═══════════════════════════════════════════════
def db_get(path, default):
    try:
        ref = db.reference(path)
        val = ref.get()
        return val if val is not None else default
    except Exception as e:
        logger.error(f"Error reading from Firebase: {e}")
        return default

def db_set(path, data):
    try:
        ref = db.reference(path)
        ref.set(data)
    except Exception as e:
        logger.error(f"Error writing to Firebase: {e}")

# ═══ إعدادات ═══
def get_settings(chat_id):
    key = str(chat_id)
    s = db_get(f"settings/{key}", {})
    default_structure = {
        "welcome": True, "banned_words": [], "locked": False,
        "links_protection": False, "edit_notify": True,
    }
    changed = False
    for k, v in default_structure.items():
        if k not in s:
            s[k] = v
            changed = True
    if changed or not s:
        db_set(f"settings/{key}", s)
    return s

def save_settings(chat_id, s):
    db_set(f"settings/{str(chat_id)}", s)

# ═══ تحذيرات ═══
def get_warns(chat_id, user_id):
    return db_get(f"warns/{chat_id}/{user_id}", 0)

def set_warns(chat_id, user_id, count):
    db_set(f"warns/{chat_id}/{user_id}", count)

# ═══ رتب ═══
ROLE_OWNER   = "owner"
ROLE_MANAGER = "manager"
ROLE_VIP     = "vip"
ROLE_RANK    = {ROLE_OWNER: 3, ROLE_MANAGER: 2, ROLE_VIP: 1}
ROLE_LABEL   = {ROLE_OWNER: "👑 مالك", ROLE_MANAGER: "🛡 مدير", ROLE_VIP: "⭐ مميز"}

def get_role(chat_id, user_id):
    return db_get(f"roles/{chat_id}/{user_id}", None)

def set_role(chat_id, user_id, role):
    db_set(f"roles/{chat_id}/{user_id}", role)

def remove_role(chat_id, user_id):
    db_set(f"roles/{chat_id}/{user_id}", None)

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
    if msg.reply_to_message:
        return msg.reply_to_message.from_user
    if msg.entities:
        for ent in msg.entities:
            if ent.type == "mention":
                username = msg.text[ent.offset+1:ent.offset+ent.length]
                try:
                    chat = await context.bot.get_chat(f"@{username}")
                    return chat
                except: pass
            elif ent.type == "text_mention" and ent.user:
                return ent.user
    return None

# ═══ تحميل يوتيوب وتيكتوك (نفس دوالك السابقة) ═══
async def download_youtube(url):
    try:
        from yt_dlp import YoutubeDL
        tmp = tempfile.mkdtemp()
        ydl_opts = {
            'format': 'bestaudio/best',
            'outtmpl': os.path.join(tmp, '%(title)s.%(ext)s'),
            'quiet': True,
            'noplaylist': True,
            'postprocessors': [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3', 'preferredquality': '192'}],
        }
        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            title = info.get('title', 'audio')
            for f in os.listdir(tmp):
                if f.endswith('.mp3'):
                    return os.path.join(tmp, f), title
        return None, None
    except: return None, None

def download_tiktok(url):
    apis = [
        f'https://www.tikwm.com/api/?url={url}&hd=1',
        f'https://api.tiklydown.eu.org/api/download?url={url}',
    ]
    for api in apis:
        try:
            res = requests.get(api, timeout=15).json()
            if res.get('code') == 0 and 'data' in res:
                d = res['data']
                return d.get('hdplay') or d.get('play')
            if 'video' in res:
                return res['video'].get('noWatermark') or res['video'].get('watermark')
        except: continue
    return None

lo_kh = [
    'تاكل صرصر لو تشرب نفط؟ 😂', 'تترك التلفون شهر لو الاكل يومين؟ 😭',
    'تنام بالشارع لو تبقى بدون نت؟ 😵', 'تحب شخص يكرهك لو تكره شخص يحبك؟ 🤔',
    'تكون غني وحيد لو فقير ومحاط بالأهل؟ 💸', 'تعيش بدون موسيقى لو بدون أفلام؟ 🎵',
    'تصير مشهور ويكرهونك لو عادي ومحبوب؟ 🌟', 'تنام 12 ساعة كل يوم لو ما تنام بالنهار؟ 😴',
    'تكذب وتنجح لو تصدق وتفشل؟ 🤥', 'تفقد ذاكرتك لو تفقد حاستك؟ 😱',
]

waad_replies = [
    'ها شتريد 😒', 'كول بسرعة 🙄', 'وعد موجودة 😌',
    'لتزعجني هسه 😂', 'سمعك 👀', 'ايه؟ 😑',
]

# ═══════════════════════════════════════════════
#  ميزة الهمسة السرية الـ Inline والـ Start Command
# ═══════════════════════════════════════════════
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if msg.chat.type == 'private' and msg.text.startswith('/start w_'):
        try:
            parts = msg.text.replace('/start w_', '').split('_')
            sender_id = int(parts[0])
            target_id = int(parts[1])
            chat_id = int(parts[2].replace('m', '-'))
            
            if msg.from_user.id != sender_id:
                await msg.reply_text("عذراً، هذا الرابط ليس لك! ❌")
                return
            
            context.user_data['whisper_target'] = target_id
            context.user_data['whisper_chat'] = chat_id
            
            await msg.reply_text("🔒 *أرسل همستك الآن هنا بالخاص:* \n(سيتم إرسالها مشفرة للكروب تلقائياً)")
        except Exception as e:
            await msg.reply_text("حدث خطأ في رابط الهمسة.")
    else:
        await msg.reply_text("أهلاً بك في بوت إدارة الكروبات المتطور المتصل بـ Firebase! 🚀")

async def handle_private_whisper(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if msg.chat.type != 'private' or not msg.text:
        return
    
    target_id = context.user_data.get('whisper_target')
    chat_id = context.user_data.get('whisper_chat')
    
    if not target_id or not chat_id:
        return

    w_id = str(random.randint(100000, 999999))
    
    # حفظ الهمسة بالفايربيس حتى ما تضيع أبداً
    db_set(f"whispers/{w_id}", {
        'text': msg.text,
        'sender': msg.from_user.id,
        'target': target_id
    })
    
    # تنظيف الـ user_data
    context.user_data.pop('whisper_target', None)
    context.user_data.pop('whisper_chat', None)
    
    markup = InlineKeyboardMarkup([[InlineKeyboardButton("🔒 قراءة الهمسة", callback_data=f"show_w_{w_id}")]])
    
    try:
        target_member = await context.bot.get_chat_member(chat_id, target_id)
        target_name = target_member.user.first_name
    except:
        target_name = "العضو المستهدف"
        
    await context.bot.send_message(
        chat_id=chat_id,
        text=f"🤫 *همسة سرية جديدة!*\nمن: {msg.from_user.first_name}\nإلى: {target_name}\n\nفقط المستهدف يمكنه القراءة 👇",
        reply_markup=markup,
        parse_mode="Markdown"
    )
    await msg.reply_text("✅ تم تشفير همستك وإرسالها للكروب بنجاح!")

async def whisper_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    w_id = query.data.replace('show_w_', '')
    w = db_get(f"whispers/{w_id}", None)
    
    if w:
        if query.from_user.id == w['target'] or query.from_user.id == w['sender']:
            await query.answer(text=f"💬 الهمسة السرية:\n{w['text']}", show_alert=True)
        else:
            await query.answer(text="الهمسة مو إلك عيني، لا تتباوع! ❌👀", show_alert=True)
    else:
        await query.answer(text="عذراً، هذه الهمسة قديمة أو غير موجودة.", show_alert=True)

# ═══════════════════════════════════════════════
#  المعالج الرئيسي للمجموعات
# ═══════════════════════════════════════════════
async def handle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message: return
    msg  = update.message
    text = (msg.text or "").strip()
    chat_id = msg.chat.id
    user_id = msg.from_user.id
    s = get_settings(chat_id)

    # إذا كانت الرسالة بالخاص وجاري كتابة همسة
    if msg.chat.type == 'private':
        if 'whisper_target' in context.user_data:
            await handle_private_whisper(update, context)
        return

    # ══ قفل الشات ══
    if s.get("locked", False):
        role = get_role(chat_id, user_id)
        tg_own = False
        try:
            admins = await context.bot.get_chat_administrators(chat_id)
            tg_own = any(a.user.id == user_id and a.status == "creator" for a in admins)
        except: pass
        if not role and not tg_own:
            try: await msg.delete()
            except: pass
            return

    if not text: return

    # ══ حماية الروابط ══
    if s.get("links_protection", False) and not get_role(chat_id, user_id):
        if re.search(r'https?://|t\.me/|\.com|\.net|\.org', text, re.I):
            try: await msg.delete()
            except: pass
            return

    # ══ كلمات محظورة ══
    for word in s.get("banned_words", []):
        if word in text.lower():
            if not get_role(chat_id, user_id):
                try:
                    await msg.delete()
                    await context.bot.send_message(chat_id, f"⚠️ {msg.from_user.first_name}، رسالتك تحتوي على كلمة محظورة.")
                except: pass
            return

    priv_owner   = await is_privileged(update, context, ROLE_OWNER)
    priv_manager = await is_privileged(update, context, ROLE_MANAGER)
    any_role     = bool(get_role(chat_id, user_id)) or await is_tg_owner(update, context)

    # ══ تفعيل أمر همسة بالرد ══
    if text == "همسة" and msg.reply_to_message:
        target = msg.reply_to_message.from_user
        if target.is_bot:
            await msg.reply_text("ما تكدر تهمس لبوت يا ذكي! 😂")
            return
        clean_cid = str(chat_id).replace('-', 'm')
        bot_username = context.bot.username
        markup = InlineKeyboardMarkup([[InlineKeyboardButton("🔒 اضغط هنا واكتب الهمسة", url=f"t.me/{bot_username}?start=w_{user_id}_{target.id}_{clean_cid}")]])
        await msg.reply_text(f"يا {msg.from_user.first_name}، اضغط على الزر بالأسفل واكتب همستك بالخاص 🤫", reply_markup=markup)
        return

    # ══ بقية الأوامر السابقة ══
    if text == "الاوامر":
        t = (
            "📋 *قائمة الأوامر مدمجة*\n\n"
            "👑 *مالك فقط:*\n"
            "`رفع مالك` — تعيين مالك (رد/منشن)\n"
            "`رفع مدير` — تعيين مدير\n"
            "`رفع مميز` — تعيين مميز\n"
            "`تنزيل رتبة` — إزالة رتبة\n"
            "`الرتب` — عرض الرتب\n"
            "`طرد` — طرد عضو\n"
            "`تحذير` / `الغاء تحذير` — تحذير / إلغاء\n"
            "`منع كلمة X` — إضافة كلمة محظورة\n"
            "`حذف كلمة X` — حذف كلمة محظورة\n"
            "`الكلمات` — عرض الكلمات المحظورة\n"
            "`الترحيب تشغيل` / `الترحيب ايقاف`\n"
            "`تعديل تشغيل` / `تعديل ايقاف` — إشعار تعديل الرسائل\n"
            "`روابط تشغيل` / `روابط ايقاف` — حماية الروابط\n"
            "`فحص بوتات` — كشف البوتات\n"
            "`اضافة منشن اسم @يوزر` — ربط اسم بمنشن\n"
            "`حذف منشن اسم` — حذف ربط\n"
            "`المنشنات` — عرض المنشنات\n\n"
            "🛡 *مدير + مالك:*\n"
            "`حظر` / `فك حظر` — بالرد أو المنشن\n"
            "`كتم` / `الغاء كتم`\n"
            "`قفل الشات` / `فتح الشات`\n"
            "`استفتاء سؤال | خيار1 | خيار2`\n"
            "`منشن الكل`\n\n"
            "⭐ *كل الرتب:*\n"
            "`مسح X` — حذف X رسالة\n\n"
            "👥 *للجميع:*\n"
            "`همسة` — بالرد على العضو لإرسال همسة سرية 🤫\n"
            "`تحذيراتي` — عدد تحذيراتك\n"
            "`ايدي` — معلوماتك أو معلومات عضو (رد/منشن)\n"
            "`افتار` — عرض أفاتار\n"
            "`زواج` — زواج (رد/منشن)\n"
            "`طلاق` — طلاق\n"
            "`شريكي` — عرض شريكك\n"
            "`انطقي نص` — البوت يكرر النص\n"
            "`لو خيروك` — سؤال عشوائي\n"
            "`وعد` — رد عشوائي\n\n"
            "📥 *تحميل:*\n"
            "أرسل رابط يوتيوب ← صوت MP3\n"
            "أرسل رابط تيكتوك ← فيديو\n"
        )
        await msg.reply_text(t, parse_mode="Markdown")
        return

    if text in ("رفع مالك", "رفع مدير", "رفع مميز") and priv_owner:
        role_map = {"رفع مالك": ROLE_OWNER, "رفع مدير": ROLE_MANAGER, "رفع مميز": ROLE_VIP}
        target = await get_target_user(update, context)
        if not target: return await msg.reply_text("رد على رسالة العضو أو اذكره.")
        set_role(chat_id, target.id, role_map[text])
        await msg.reply_text(f"✅ تم تعيين {target.first_name} كـ {ROLE_LABEL[role_map[text]]}.")
        return

    if text == "تنزيل رتبة" and priv_owner:
        target = await get_target_user(update, context)
        if not target: return await msg.reply_text("رد على رسالة العضو أو اذكره.")
        remove_role(chat_id, target.id)
        await msg.reply_text(f"✅ تمت إزالة رتبة {target.first_name}.")
        return

    if text == "الرتب":
        chat_roles = db_get(f"roles/{chat_id}", {})
        if not chat_roles: return await msg.reply_text("لا توجد رتب معينة.")
        lines = []
        for uid, role in chat_roles.items():
            if not role: continue
            try:
                member = await context.bot.get_chat_member(chat_id, int(uid))
                name = member.user.first_name
            except: name = f"ID:{uid}"
            lines.append(f"{ROLE_LABEL[role]} — {name}")
        await msg.reply_text("📋 *الرتب من الفايربيس:*\n" + "\n".join(lines), parse_mode="Markdown")
        return

    if text == "طرد" and priv_owner:
        target = await get_target_user(update, context)
        if not target: return await msg.reply_text("رد على رسالة العضو أو اذكره.")
        await context.bot.ban_chat_member(chat_id, target.id)
        await context.bot.unban_chat_member(chat_id, target.id)
        await msg.reply_text(f"👢 تم طرد {target.first_name}.")
        return

    if text == "حظر" and priv_manager:
        target = await get_target_user(update, context)
        if not target: return await msg.reply_text("رد على رسالة العضو أو اذكره.")
        await context.bot.ban_chat_member(chat_id, target.id)
        await msg.reply_text(f"🚫 تم حظر {target.first_name}.")
        return

    if text == "فك حظر" and priv_manager:
        target = await get_target_user(update, context)
        if not target: return await msg.reply_text("رد على رسالة العضو أو اذكره.")
        await context.bot.unban_chat_member(chat_id, target.id)
        await msg.reply_text(f"✅ رفع الحظر عن {target.first_name}.")
        return

    if text == "كتم" and priv_manager:
        target = await get_target_user(update, context)
        if not target: return await msg.reply_text("رد على رسالة العضو أو اذكره.")
        await context.bot.restrict_chat_member(chat_id, target.id, ChatPermissions(can_send_messages=False))
        await msg.reply_text(f"🔇 تم كتم {target.first_name}.")
        return

    if text == "الغاء كتم" and priv_manager:
        target = await get_target_user(update, context)
        if not target: return await msg.reply_text("رد على رسالة العضو أو اذكره.")
        await context.bot.restrict_chat_member(chat_id, target.id, ChatPermissions(
            can_send_messages=True, can_send_media_messages=True,
            can_send_other_messages=True, can_add_web_page_previews=True
        ))
        await msg.reply_text(f"🔊 رفع الكتم عن {target.first_name}.")
        return

    if text == "تحذير" and priv_owner:
        target = await get_target_user(update, context)
        if not target: return await msg.reply_text("رد على رسالة العضو أو اذكره.")
        count = get_warns(chat_id, target.id) + 1
        set_warns(chat_id, target.id, count)
        if count >= 3:
            await context.bot.ban_chat_member(chat_id, target.id)
            set_warns(chat_id, target.id, 0)
            await msg.reply_text(f"🚫 {target.first_name} وصل 3 تحذيرات — تم حظره.")
        else:
            await msg.reply_text(f"⚠️ تحذير {count}/3 لـ {target.first_name}.")
        return

    if text == "الغاء تحذير" and priv_owner:
        target = await get_target_user(update, context)
        if not target: return await msg.reply_text("رد على رسالة العضو أو اذكره.")
        set_warns(chat_id, target.id, 0)
        await msg.reply_text(f"✅ مسح تحذيرات {target.first_name}.")
        return

    if text == "تحذيراتي":
        count = get_warns(chat_id, user_id)
        await msg.reply_text(f"تحذيراتك: {count}/3")
        return

    if text == "قفل الشات" and priv_manager:
        s["locked"] = True; save_settings(chat_id, s)
        await msg.reply_text("🔒 الشات مقفول.")
        return

    if text == "فتح الشات" and priv_manager:
        s["locked"] = False; save_settings(chat_id, s)
        await msg.reply_text("🔓 الشات مفتوح.")
        return

    if text.startswith("منع كلمة ") and priv_owner:
        word = text[9:].strip().lower()
        if word and word not in s["banned_words"]:
            s["banned_words"].append(word)
            save_settings(chat_id, s)
        await msg.reply_text(f"✅ تمت إضافة: {word}")
        return

    if text.startswith("حذف كلمة ") and priv_owner:
        word = text[9:].strip().lower()
        if word in s["banned_words"]:
            s["banned_words"].remove(word)
            save_settings(chat_id, s)
            await msg.reply_text(f"✅ تمت إزالة: {word}")
        else: await msg.reply_text("الكلمة مو موجودة.")
        return

    if text == "الكلمات" and priv_owner:
        if not s["banned_words"]: await msg.reply_text("لا توجد كلمات محظورة.")
        else: await msg.reply_text("🚫 الكلمات المحظورة:\n" + "\n".join(s["banned_words"]))
        return

    if text == "الترحيب تشغيل" and priv_owner:
        s["welcome"] = True; save_settings(chat_id, s)
        await msg.reply_text("✅ الترحيب مفعّل.")
        return

    if text == "الترحيب ايقاف" and priv_owner:
        s["welcome"] = False; save_settings(chat_id, s)
        await msg.reply_text("🔕 الترحيب موقوف.")
        return

    if text == "تعديل تشغيل" and priv_owner:
        s["edit_notify"] = True; save_settings(chat_id, s)
        await msg.reply_text("✅ إشعار التعديل مفعّل.")
        return

    if text == "تعديل ايقاف" and priv_owner:
        s["edit_notify"] = False; save_settings(chat_id, s)
        await msg.reply_text("❌ إشعار التعديل موقوف.")
        return

    if text == "روابط تشغيل" and priv_owner:
        s["links_protection"] = True; save_settings(chat_id, s)
        await msg.reply_text("✅ حماية الروابط مفعّلة.")
        return

    if text == "روابط ايقاف" and priv_owner:
        s["links_protection"] = False; save_settings(chat_id, s)
        await msg.reply_text("❌ حماية الروابط موقوفة.")
        return

    if text == "فحص بوتات" and priv_owner:
        wait_msg = await msg.reply_text("🔍 جاري الفحص...")
        try:
            admins = await context.bot.get_chat_administrators(chat_id)
            bot_list = [a for a in admins if a.user.is_bot and a.user.id != context.bot.id]
            if not bot_list: await wait_msg.edit_text("✅ ما في بوتات ثانية.")
            else:
                lines = "\n".join([f"• @{b.user.username or b.user.first_name}" for b in bot_list])
                await wait_msg.edit_text(f"🤖 *البوتات:*\n{lines}", parse_mode="Markdown")
        except: await wait_msg.edit_text("❌ ما قدرت أفحص.")
        return

    if text.startswith("اضافة منشن ") and priv_owner:
        parts = text[11:].strip().split()
        if len(parts) < 2: return await msg.reply_text("مثال: اضافة منشن أحمد @username")
        name = parts[0]
        username = parts[1].lstrip("@")
        db_set(f"mentions/{chat_id}/{name}", username)
        await msg.reply_text(f"✅ تم ربط '{name}' بـ @{username}")
        return

    if text.startswith("حذف منشن ") and priv_owner:
        name = text[9:].strip()
        db_set(f"mentions/{chat_id}/{name}", None)
        await msg.reply_text(f"✅ تم حذف منشن '{name}'")
        return

    if text == "المنشنات":
        m = db_get(f"mentions/{chat_id}", {})
        if not m: return await msg.reply_text("لا توجد منشنات.")
        lines = [f"• {n} → @{u}" for n, u in m.items() if u]
        await msg.reply_text("📋 *المنشنات:*\n" + "\n".join(lines), parse_mode="Markdown")
        return

    if text == "منشن الكل" and priv_manager:
        try:
            admins = await context.bot.get_chat_administrators(chat_id)
            mentions = " ".join([f'<a href="tg://user?id={a.user.id}">{a.user.first_name}</a>' for a in admins if not a.user.is_bot])
            await msg.reply_text(f"📢 {mentions}", parse_mode="HTML")
        except: await msg.reply_text("❌ ما قدرت.")
        return

    if text.startswith("مسح ") and any_role:
        parts = text.split()
        if len(parts) == 2 and parts[1].isdigit():
            count = int(parts[1])
            if 1 <= count <= 200:
                msg_id = msg.message_id
                deleted = 0
                for mid in range(msg_id - count, msg_id + 1):
                    try:
                        await context.bot.delete_message(chat_id, mid)
                        deleted += 1
                    except: pass
                notice = await context.bot.send_message(chat_id, f"🗑 تم حذف {deleted} رسالة.")
                await asyncio.sleep(3)
                try: await notice.delete()
                except: pass
        return

    if text.startswith("استفتاء ") and priv_manager:
        parts = [p.strip() for p in text[8:].split("|")]
        if len(parts) < 3: return await msg.reply_text("مثال: استفتاء سؤالك | خيار1 | خيار2")
        try: await context.bot.send_poll(chat_id, question=parts[0], options=parts[1:], is_anonymous=False)
        except Exception as e: await msg.reply_text(f"❌ خطأ: {e}")
        return

    if text == "ايدي":
        target = await get_target_user(update, context)
        user = target if target else msg.from_user
        uid = user.id
        username = f"@{user.username}" if user.username else "—"
        role = get_role(chat_id, uid)
        role_text = ROLE_LABEL.get(role, "—") if role else "—"
        caption = f"👤 <b>الاسم:</b> {user.first_name}\n🆔 <b>الآيدي:</b> <code>{uid}</code>\n📌 <b>اليوزر:</b> {username}\n🏅 <b>الرتبة:</b> {role_text}"
        try:
            photos = await context.bot.get_user_profile_photos(uid, limit=1)
            if photos.total_count > 0: await context.bot.send_photo(chat_id, photos.photos[0][-1].file_id, caption=caption, parse_mode="HTML")
            else: await msg.reply_text(caption, parse_mode="HTML")
        except: await msg.reply_text(caption, parse_mode="HTML")
        return

    if text == "افتار":
        target = await get_target_user(update, context)
        user = target if target else msg.from_user
        try:
            photos = await context.bot.get_user_profile_photos(user.id, limit=1)
            if photos.total_count > 0: await context.bot.send_photo(chat_id, photos.photos[0][-1].file_id, caption=f"🖼 أفاتار {user.first_name}")
            else: await msg.reply_text("ما عنده صورة بروفايل.")
        except: await msg.reply_text("ما قدرت أجيب الصورة.")
        return

    if text == "زواج":
        target = await get_target_user(update, context)
        if not target: return await msg.reply_text("رد على رسالة الشخص أو اذكره.")
        if str(target.id) == str(user_id): return await msg.reply_text("ما تقدر تتزوج نفسك 😂")
        
        if db_get(f"marriages/{chat_id}/{user_id}", None):
            return await msg.reply_text("أنت متزوج خلاص! اطلق أول.")
            
        db_set(f"marriages/{chat_id}/{user_id}", str(target.id))
        db_set(f"marriages/{chat_id}/{target.id}", str(user_id))
        u1 = f'<a href="tg://user?id={user_id}">{msg.from_user.first_name}</a>'
        u2 = f'<a href="tg://user?id={target.id}">{target.first_name}</a>'
        await msg.reply_text(f"💍 تهانينا! {u1} و {u2} صاروا متزوجين! 🎉", parse_mode="HTML")
        return

    if text == "طلاق":
        partner_id = db_get(f"marriages/{chat_id}/{user_id}", None)
        if not partner_id: return await msg.reply_text("أنت مو متزوج أصلاً.")
        db_set(f"marriages/{chat_id}/{user_id}", None)
        db_set(f"marriages/{chat_id}/{partner_id}", None)
        await msg.reply_text("💔 تم الطلاق.")
        return

    if text == "شريكي":
        partner_id = db_get(f"marriages/{chat_id}/{user_id}", None)
        if not partner_id: return await msg.reply_text("أنت مو متزوج.")
        try:
            member = await context.bot.get_chat_member(chat_id, int(partner_id))
            p = member.user
            await msg.reply_text(f'💑 شريكك: <a href="tg://user?id={p.id}">{p.first_name}</a>', parse_mode="HTML")
        except: await msg.reply_text("ما قدرت أجيب معلومات شريكك.")
        return

    if text.startswith("انطقي "):
        speech = text[6:].strip()
        if speech: await msg.reply_text(speech)
        return

    if text == "لو خيروك":
        await msg.reply_text(random.choice(lo_kh))
        return

    if text == "وعد":
        await msg.reply_text(random.choice(waad_replies))
        return

    # منشن تلقائي بالاسم
    chat_mentions = db_get(f"mentions/{chat_id}", {})
    for name, username in chat_mentions.items():
        if username and name in text:
            await msg.reply_text(f"📣 تم منادة {name}! بانتظار رده 👉 @{username}")

    # يوتيوب وتيكتوك ميديا
    if re.search(r'youtube\.com|youtu\.be', text):
        url = re.search(r'https?://\S+', text)
        if url:
            wait = await msg.reply_text("🎧 جاري تحميل الصوت...")
            try:
                filepath, title = await download_youtube(url.group())
                if filepath and os.path.exists(filepath):
                    with open(filepath, 'rb') as audio:
                        await context.bot.send_audio(chat_id, audio, title=title, reply_to_message_id=msg.message_id)
                    try: os.remove(filepath)
                    except: pass
                    await wait.delete()
                else: await wait.edit_text("❌ فشل تحميل الصوت.")
            except: await wait.edit_text("❌ فشل تحميل الصوت.")
        return

    if 'tiktok.com' in text:
        url = re.search(r'https?://\S+', text)
        if url:
            wait = await msg.reply_text("⏳ جاري تحميل التيكتوك...")
            try:
                video_url = download_tiktok(url.group())
                if video_url:
                    await context.bot.send_video(chat_id, video_url, reply_to_message_id=msg.message_id)
                    await wait.delete()
                else: await wait.edit_text("❌ فشل تحميل الفيديو.")
            except: await wait.edit_text("❌ صار خطأ.")
        return

# ═══ ترحيب أعضاء جدد ═══
async def welcome_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    for member in update.message.new_chat_members:
        if member.is_bot: continue
        s = get_settings(update.message.chat.id)
        if s.get("welcome", True):
            name = f'<a href="tg://user?id={member.id}">{member.first_name}</a>'
            try:
                photos = await context.bot.get_user_profile_photos(member.id, limit=1)
                if photos.total_count > 0:
                    await context.bot.send_photo(update.message.chat.id, photos.photos[0][-1].file_id, caption=f"👋 أهلاً {name} في المجموعة! 🎉", parse_mode="HTML")
                else: await update.message.reply_text(f"👋 أهلاً {name} في المجموعة! 🎉", parse_mode="HTML")
            except: await update.message.reply_text(f"👋 أهلاً {name} في المجموعة! 🎉", parse_mode="HTML")

# ═══ إشعار تعديل الرسائل ═══
async def edited_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.edited_message: return
    chat_id = update.edited_message.chat.id
    s = get_settings(chat_id)
    if not s.get("edit_notify", True): return
    msg = update.edited_message
    user = msg.from_user
    new_text = msg.text or "[ميديا]"
    name = f'<a href="tg://user?id={user.id}">{user.first_name}</a>'
    await context.bot.send_message(chat_id, f"✏️ {name} عدّل رسالته:\n\n{new_text}", parse_mode="HTML")

# ═══ Main ═══
def main():
    token = os.environ.get("BOT_TOKEN", "8159446452:AAGrkJbtEFoKgXab19l7tX36SDTowRvPxB4")
    app = Application.builder().token(token).build()
    
    # الهاندلرات
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CallbackQueryHandler(whisper_callback, pattern=r"^show_w_"))
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, welcome_member))
    app.add_handler(MessageHandler(filters.UpdateType.EDITED_MESSAGE & filters.TEXT, edited_message_handler))
    
    # هذا الهاندلر يستقبل الخاص والكروبات معاً
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle))
    
    print("✅ البوت شغال ومتصل بـ Firebase...")
    app.run_polling()

if __name__ == "__main__":
    main()
