import logging
import json
import os
import asyncio
import random
import re
import requests
import tempfile
from telegram import Update, ChatPermissions
from telegram.ext import (
    Application, MessageHandler,
    filters, ContextTypes,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

SETTINGS_FILE  = "settings.json"
WARNS_FILE     = "warns.json"
ROLES_FILE     = "roles.json"
MENTIONS_FILE  = "mentions.json"
MARRIAGES_FILE = "marriages.json"

def load_json(path, default):
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return default

def save_json(path, data):
    with open(path, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

settings     = load_json(SETTINGS_FILE, {})
warns        = load_json(WARNS_FILE, {})
roles        = load_json(ROLES_FILE, {})
mentions_db  = load_json(MENTIONS_FILE, {})
marriages_db = load_json(MARRIAGES_FILE, {})

# ═══ إعدادات ═══
def get_settings(chat_id):
    key = str(chat_id)
    if key not in settings:
        settings[key] = {
            "welcome": True, "banned_words": [], "locked": False,
            "links_protection": False, "edit_notify": True,
        }
        save_json(SETTINGS_FILE, settings)
    for k, v in {"locked": False, "links_protection": False, "edit_notify": True}.items():
        settings[key].setdefault(k, v)
    return settings[key]

# ═══ تحذيرات ═══
def get_warns(chat_id, user_id):
    return warns.get(str(chat_id), {}).get(str(user_id), 0)

def set_warns(chat_id, user_id, count):
    warns.setdefault(str(chat_id), {})[str(user_id)] = count
    save_json(WARNS_FILE, warns)

# ═══ رتب ═══
ROLE_OWNER   = "owner"
ROLE_MANAGER = "manager"
ROLE_VIP     = "vip"
ROLE_RANK    = {ROLE_OWNER: 3, ROLE_MANAGER: 2, ROLE_VIP: 1}
ROLE_LABEL   = {ROLE_OWNER: "👑 مالك", ROLE_MANAGER: "🛡 مدير", ROLE_VIP: "⭐ مميز"}

def get_role(chat_id, user_id):
    return roles.get(str(chat_id), {}).get(str(user_id))

def set_role(chat_id, user_id, role):
    roles.setdefault(str(chat_id), {})[str(user_id)] = role
    save_json(ROLES_FILE, roles)

def remove_role(chat_id, user_id):
    c, u = str(chat_id), str(user_id)
    if c in roles and u in roles[c]:
        del roles[c][u]
        save_json(ROLES_FILE, roles)

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
                except:
                    pass
            elif ent.type == "text_mention" and ent.user:
                return ent.user
    return None

# ═══ تحميل يوتيوب ═══
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
    except:
        return None, None

# ═══ تحميل تيكتوك ═══
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
        except:
            continue
    return None

# ═══ ردود عشوائية ═══
lo_kh = [
    'تاكل صرصر لو تشرب نفط؟ 😂',
    'تترك التلفون شهر لو الاكل يومين؟ 😭',
    'تنام بالشارع لو تبقى بدون نت؟ 😵',
    'تحب شخص يكرهك لو تكره شخص يحبك؟ 🤔',
    'تكون غني وحيد لو فقير ومحاط بالأهل؟ 💸',
    'تعيش بدون موسيقى لو بدون أفلام؟ 🎵',
    'تصير مشهور ويكرهونك لو عادي ومحبوب؟ 🌟',
    'تنام 12 ساعة كل يوم لو ما تنام بالنهار؟ 😴',
    'تكذب وتنجح لو تصدق وتفشل؟ 🤥',
    'تفقد ذاكرتك لو تفقد حاستك؟ 😱',
]

waad_replies = [
    'ها شتريد 😒', 'كول بسرعة 🙄', 'وعد موجودة 😌',
    'لتزعجني هسه 😂', 'سمعك 👀', 'ايه؟ 😑',
]

# ═══════════════════════════════════════════════
#  المعالج الرئيسي
# ═══════════════════════════════════════════════
async def handle(update, context):
    if not update.message:
        return
    msg  = update.message
    text = (msg.text or "").strip()
    chat_id = msg.chat.id
    user_id = msg.from_user.id
    s = get_settings(chat_id)

    # ══ قفل الشات ══
    if s.get("locked", False):
        role = get_role(chat_id, user_id)
        tg_own = False
        try:
            admins = await context.bot.get_chat_administrators(chat_id)
            tg_own = any(a.user.id == user_id and a.status == "creator" for a in admins)
        except:
            pass
        if not role and not tg_own:
            try: await msg.delete()
            except: pass
            return

    if not text:
        return

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

    # ══════════════════════════════
    #  قائمة الأوامر
    # ══════════════════════════════
    if text == "الاوامر":
        t = (
            "📋 *قائمة الأوامر*\n\n"
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

    # ══ رتب ══
    if text in ("رفع مالك", "رفع مدير", "رفع مميز") and priv_owner:
        role_map = {"رفع مالك": ROLE_OWNER, "رفع مدير": ROLE_MANAGER, "رفع مميز": ROLE_VIP}
        target = await get_target_user(update, context)
        if not target:
            return await msg.reply_text("رد على رسالة العضو أو اذكره.")
        set_role(chat_id, target.id, role_map[text])
        await msg.reply_text(f"✅ تم تعيين {target.first_name} كـ {ROLE_LABEL[role_map[text]]}.")
        return

    if text == "تنزيل رتبة" and priv_owner:
        target = await get_target_user(update, context)
        if not target:
            return await msg.reply_text("رد على رسالة العضو أو اذكره.")
        remove_role(chat_id, target.id)
        await msg.reply_text(f"✅ تمت إزالة رتبة {target.first_name}.")
        return

    if text == "الرتب":
        chat_roles = roles.get(str(chat_id), {})
        if not chat_roles:
            return await msg.reply_text("لا توجد رتب معينة.")
        lines = []
        for uid, role in chat_roles.items():
            try:
                member = await context.bot.get_chat_member(chat_id, int(uid))
                name = member.user.first_name
            except:
                name = f"ID:{uid}"
            lines.append(f"{ROLE_LABEL[role]} — {name}")
        await msg.reply_text("📋 *الرتب:*\n" + "\n".join(lines), parse_mode="Markdown")
        return

    # ══ طرد ══
    if text == "طرد" and priv_owner:
        target = await get_target_user(update, context)
        if not target:
            return await msg.reply_text("رد على رسالة العضو أو اذكره.")
        await context.bot.ban_chat_member(chat_id, target.id)
        await context.bot.unban_chat_member(chat_id, target.id)
        await msg.reply_text(f"👢 تم طرد {target.first_name}.")
        return

    # ══ حظر / فك حظر ══
    if text == "حظر" and priv_manager:
        target = await get_target_user(update, context)
        if not target:
            return await msg.reply_text("رد على رسالة العضو أو اذكره.")
        await context.bot.ban_chat_member(chat_id, target.id)
        await msg.reply_text(f"🚫 تم حظر {target.first_name}.")
        return

    if text == "فك حظر" and priv_manager:
        target = await get_target_user(update, context)
        if not target:
            return await msg.reply_text("رد على رسالة العضو أو اذكره.")
        await context.bot.unban_chat_member(chat_id, target.id)
        await msg.reply_text(f"✅ رفع الحظر عن {target.first_name}.")
        return

    # ══ كتم / الغاء كتم ══
    if text == "كتم" and priv_manager:
        target = await get_target_user(update, context)
        if not target:
            return await msg.reply_text("رد على رسالة العضو أو اذكره.")
        await context.bot.restrict_chat_member(chat_id, target.id, ChatPermissions(can_send_messages=False))
        await msg.reply_text(f"🔇 تم كتم {target.first_name}.")
        return

    if text == "الغاء كتم" and priv_manager:
        target = await get_target_user(update, context)
        if not target:
            return await msg.reply_text("رد على رسالة العضو أو اذكره.")
        await context.bot.restrict_chat_member(chat_id, target.id, ChatPermissions(
            can_send_messages=True, can_send_media_messages=True,
            can_send_other_messages=True, can_add_web_page_previews=True
        ))
        await msg.reply_text(f"🔊 رفع الكتم عن {target.first_name}.")
        return

    # ══ تحذير ══
    if text == "تحذير" and priv_owner:
        target = await get_target_user(update, context)
        if not target:
            return await msg.reply_text("رد على رسالة العضو أو اذكره.")
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
        if not target:
            return await msg.reply_text("رد على رسالة العضو أو اذكره.")
        set_warns(chat_id, target.id, 0)
        await msg.reply_text(f"✅ مسح تحذيرات {target.first_name}.")
        return

    if text == "تحذيراتي":
        count = get_warns(chat_id, user_id)
        await msg.reply_text(f"تحذيراتك: {count}/3")
        return

    # ══ قفل / فتح ══
    if text == "قفل الشات" and priv_manager:
        s["locked"] = True; save_json(SETTINGS_FILE, settings)
        await msg.reply_text("🔒 الشات مقفول.")
        return

    if text == "فتح الشات" and priv_manager:
        s["locked"] = False; save_json(SETTINGS_FILE, settings)
        await msg.reply_text("🔓 الشات مفتوح.")
        return

    # ══ كلمات محظورة ══
    if text.startswith("منع كلمة ") and priv_owner:
        word = text[9:].strip().lower()
        if word and word not in s["banned_words"]:
            s["banned_words"].append(word)
            save_json(SETTINGS_FILE, settings)
        await msg.reply_text(f"✅ تمت إضافة: {word}")
        return

    if text.startswith("حذف كلمة ") and priv_owner:
        word = text[9:].strip().lower()
        if word in s["banned_words"]:
            s["banned_words"].remove(word)
            save_json(SETTINGS_FILE, settings)
            await msg.reply_text(f"✅ تمت إزالة: {word}")
        else:
            await msg.reply_text("الكلمة مو موجودة.")
        return

    if text == "الكلمات" and priv_owner:
        if not s["banned_words"]:
            await msg.reply_text("لا توجد كلمات محظورة.")
        else:
            await msg.reply_text("🚫 الكلمات المحظورة:\n" + "\n".join(s["banned_words"]))
        return

    # ══ ترحيب ══
    if text == "الترحيب تشغيل" and priv_owner:
        s["welcome"] = True; save_json(SETTINGS_FILE, settings)
        await msg.reply_text("✅ الترحيب مفعّل.")
        return

    if text == "الترحيب ايقاف" and priv_owner:
        s["welcome"] = False; save_json(SETTINGS_FILE, settings)
        await msg.reply_text("🔕 الترحيب موقوف.")
        return

    # ══ إشعار التعديل ══
    if text == "تعديل تشغيل" and priv_owner:
        s["edit_notify"] = True; save_json(SETTINGS_FILE, settings)
        await msg.reply_text("✅ إشعار التعديل مفعّل.")
        return

    if text == "تعديل ايقاف" and priv_owner:
        s["edit_notify"] = False; save_json(SETTINGS_FILE, settings)
        await msg.reply_text("❌ إشعار التعديل موقوف.")
        return

    # ══ حماية الروابط ══
    if text == "روابط تشغيل" and priv_owner:
        s["links_protection"] = True; save_json(SETTINGS_FILE, settings)
        await msg.reply_text("✅ حماية الروابط مفعّلة.")
        return

    if text == "روابط ايقاف" and priv_owner:
        s["links_protection"] = False; save_json(SETTINGS_FILE, settings)
        await msg.reply_text("❌ حماية الروابط موقوفة.")
        return

    # ══ فحص بوتات ══
    if text == "فحص بوتات" and priv_owner:
        wait_msg = await msg.reply_text("🔍 جاري الفحص...")
        try:
            admins = await context.bot.get_chat_administrators(chat_id)
            bot_list = [a for a in admins if a.user.is_bot and a.user.id != context.bot.id]
            if not bot_list:
                await wait_msg.edit_text("✅ ما في بوتات ثانية.")
            else:
                lines = "\n".join([f"• @{b.user.username or b.user.first_name}" for b in bot_list])
                await wait_msg.edit_text(f"🤖 *البوتات:*\n{lines}", parse_mode="Markdown")
        except:
            await wait_msg.edit_text("❌ ما قدرت أفحص.")
        return

    # ══ منشن بالاسم ══
    if text.startswith("اضافة منشن ") and priv_owner:
        parts = text[11:].strip().split()
        if len(parts) < 2:
            return await msg.reply_text("مثال: اضافة منشن أحمد @username")
        name = parts[0]
        username = parts[1].lstrip("@")
        mentions_db.setdefault(str(chat_id), {})[name] = username
        save_json(MENTIONS_FILE, mentions_db)
        await msg.reply_text(f"✅ تم ربط '{name}' بـ @{username}")
        return

    if text.startswith("حذف منشن ") and priv_owner:
        name = text[9:].strip()
        chat_mentions = mentions_db.get(str(chat_id), {})
        if name in chat_mentions:
            del chat_mentions[name]
            save_json(MENTIONS_FILE, mentions_db)
            await msg.reply_text(f"✅ تم حذف منشن '{name}'")
        else:
            await msg.reply_text("الاسم مو موجود.")
        return

    if text == "المنشنات":
        m = mentions_db.get(str(chat_id), {})
        if not m:
            return await msg.reply_text("لا توجد منشنات.")
        lines = [f"• {n} → @{u}" for n, u in m.items()]
        await msg.reply_text("📋 *المنشنات:*\n" + "\n".join(lines), parse_mode="Markdown")
        return

    # ══ منشن الكل ══
    if text == "منشن الكل" and priv_manager:
        try:
            admins = await context.bot.get_chat_administrators(chat_id)
            mentions = " ".join([
                f'<a href="tg://user?id={a.user.id}">{a.user.first_name}</a>'
                for a in admins if not a.user.is_bot
            ])
            await msg.reply_text(f"📢 {mentions}", parse_mode="HTML")
        except:
            await msg.reply_text("❌ ما قدرت.")
        return

    # ══ مسح ══
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
                    except:
                        pass
                notice = await context.bot.send_message(chat_id, f"🗑 تم حذف {deleted} رسالة.")
                await asyncio.sleep(3)
                try: await notice.delete()
                except: pass
        return

    # ══ استفتاء ══
    if text.startswith("استفتاء ") and priv_manager:
        parts = [p.strip() for p in text[8:].split("|")]
        if len(parts) < 3:
            return await msg.reply_text("مثال: استفتاء سؤالك | خيار1 | خيار2")
        try:
            await context.bot.send_poll(chat_id, question=parts[0], options=parts[1:], is_anonymous=False)
        except Exception as e:
            await msg.reply_text(f"❌ خطأ: {e}")
        return

    # ══ ايدي ══
    if text == "ايدي":
        target = await get_target_user(update, context)
        user = target if target else msg.from_user
        uid = user.id
        username = f"@{user.username}" if user.username else "—"
        role = get_role(chat_id, uid)
        role_text = ROLE_LABEL.get(role, "—") if role else "—"
        caption = (
            f"👤 <b>الاسم:</b> {user.first_name}\n"
            f"🆔 <b>الآيدي:</b> <code>{uid}</code>\n"
            f"📌 <b>اليوزر:</b> {username}\n"
            f"🏅 <b>الرتبة:</b> {role_text}"
        )
        try:
            photos = await context.bot.get_user_profile_photos(uid, limit=1)
            if photos.total_count > 0:
                await context.bot.send_photo(chat_id, photos.photos[0][-1].file_id, caption=caption, parse_mode="HTML")
            else:
                await msg.reply_text(caption, parse_mode="HTML")
        except:
            await msg.reply_text(caption, parse_mode="HTML")
        return

    # ══ افتار ══
    if text == "افتار":
        target = await get_target_user(update, context)
        user = target if target else msg.from_user
        try:
            photos = await context.bot.get_user_profile_photos(user.id, limit=1)
            if photos.total_count > 0:
                await context.bot.send_photo(chat_id, photos.photos[0][-1].file_id, caption=f"🖼 أفاتار {user.first_name}")
            else:
                await msg.reply_text("ما عنده صورة بروفايل.")
        except:
            await msg.reply_text("ما قدرت أجيب الصورة.")
        return

    # ══ زواج وطلاق ══
    if text == "زواج":
        target = await get_target_user(update, context)
        if not target:
            return await msg.reply_text("رد على رسالة الشخص أو اذكره.")
        if str(target.id) == str(user_id):
            return await msg.reply_text("ما تقدر تتزوج نفسك 😂")
        marriages_db.setdefault(str(chat_id), {})
        if str(user_id) in marriages_db[str(chat_id)]:
            return await msg.reply_text("أنت متزوج خلاص! اطلق أول.")
        marriages_db[str(chat_id)][str(user_id)] = str(target.id)
        marriages_db[str(chat_id)][str(target.id)] = str(user_id)
        save_json(MARRIAGES_FILE, marriages_db)
        u1 = f'<a href="tg://user?id={user_id}">{msg.from_user.first_name}</a>'
        u2 = f'<a href="tg://user?id={target.id}">{target.first_name}</a>'
        await msg.reply_text(f"💍 تهانينا! {u1} و {u2} صاروا متزوجين! 🎉", parse_mode="HTML")
        return

    if text == "طلاق":
        marriages_db.setdefault(str(chat_id), {})
        if str(user_id) not in marriages_db[str(chat_id)]:
            return await msg.reply_text("أنت مو متزوج أصلاً.")
        partner_id = marriages_db[str(chat_id)].pop(str(user_id))
        marriages_db[str(chat_id)].pop(partner_id, None)
        save_json(MARRIAGES_FILE, marriages_db)
        await msg.reply_text("💔 تم الطلاق.")
        return

    if text == "شريكي":
        marriages_db.setdefault(str(chat_id), {})
        if str(user_id) not in marriages_db[str(chat_id)]:
            return await msg.reply_text("أنت مو متزوج.")
        partner_id = marriages_db[str(chat_id)][str(user_id)]
        try:
            member = await context.bot.get_chat_member(chat_id, int(partner_id))
            p = member.user
            await msg.reply_text(f'💑 شريكك: <a href="tg://user?id={p.id}">{p.first_name}</a>', parse_mode="HTML")
        except:
            await msg.reply_text("ما قدرت أجيب معلومات شريكك.")
        return

    # ══ انطقي ══
    if text.startswith("انطقي "):
        speech = text[6:].strip()
        if speech:
            await msg.reply_text(speech)
        return

    # ══ لو خيروك ══
    if text == "لو خيروك":
        await msg.reply_text(random.choice(lo_kh))
        return

    # ══ وعد ══
    if text == "وعد":
        await msg.reply_text(random.choice(waad_replies))
        return

    # ══ منشن بالاسم تلقائي ══
    chat_mentions = mentions_db.get(str(chat_id), {})
    for name, username in chat_mentions.items():
        if name in text:
            await msg.reply_text(f"📣 تم منادة {name}! بانتظار رده 👉 @{username}")

    # ══ تحميل يوتيوب ══
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
                else:
                    await wait.edit_text("❌ فشل تحميل الصوت.")
            except:
                await wait.edit_text("❌ فشل تحميل الصوت.")
        return

    # ══ تحميل تيكتوك ══
    if 'tiktok.com' in text:
        url = re.search(r'https?://\S+', text)
        if url:
            wait = await msg.reply_text("⏳ جاري تحميل التيكتوك...")
            try:
                video_url = download_tiktok(url.group())
                if video_url:
                    await context.bot.send_video(chat_id, video_url, reply_to_message_id=msg.message_id)
                    await wait.delete()
                else:
                    await wait.edit_text("❌ فشل تحميل الفيديو.")
            except:
                await wait.edit_text("❌ صار خطأ.")
        return

# ═══ ترحيب أعضاء جدد ═══
async def welcome_member(update, context):
    for member in update.message.new_chat_members:
        if member.is_bot:
            continue
        s = get_settings(update.message.chat.id)
        if s.get("welcome", True):
            name = f'<a href="tg://user?id={member.id}">{member.first_name}</a>'
            try:
                photos = await context.bot.get_user_profile_photos(member.id, limit=1)
                if photos.total_count > 0:
                    await context.bot.send_photo(
                        update.message.chat.id,
                        photos.photos[0][-1].file_id,
                        caption=f"👋 أهلاً {name} في المجموعة! 🎉",
                        parse_mode="HTML"
                    )
                else:
                    await update.message.reply_text(f"👋 أهلاً {name} في المجموعة! 🎉", parse_mode="HTML")
            except:
                await update.message.reply_text(f"👋 أهلاً {name} في المجموعة! 🎉", parse_mode="HTML")

# ═══ إشعار تعديل الرسائل ═══
async def edited_message_handler(update, context):
    if not update.edited_message:
        return
    chat_id = update.edited_message.chat.id
    s = get_settings(chat_id)
    if not s.get("edit_notify", True):
        return
    msg = update.edited_message
    user = msg.from_user
    new_text = msg.text or "[ميديا]"
    name = f'<a href="tg://user?id={user.id}">{user.first_name}</a>'
    await context.bot.send_message(
        chat_id,
        f"✏️ {name} عدّل رسالته:\n\n{new_text}",
        parse_mode="HTML"
    )

# ═══ Main ═══
def main():
    token = os.environ.get("BOT_TOKEN", "8159446452:AAGtFNGAfMxoC2iPwE06Z0gnW0IUUvmAEa0")
    app = Application.builder().token(token).build()
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, welcome_member))
    app.add_handler(MessageHandler(filters.UpdateType.EDITED_MESSAGE & filters.TEXT, edited_message_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle))
    print("✅ البوت شغال...")
    app.run_polling()

if __name__ == "__main__":
    main()
