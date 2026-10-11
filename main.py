import os
import html
import asyncio
import logging
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import httpx
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputMediaPhoto,
    InputMediaDocument,
)
from telegram.error import BadRequest
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)
from motor.motor_asyncio import AsyncIOMotorClient

# ============================================================
# الإعدادات (المتغيرات البيئية)
# ============================================================
BOT_TOKEN = os.getenv("BOT_TOKEN")
MONGO_URI = os.getenv("MONGO_URI")
CHANNEL_ID_RAW = os.getenv("CHANNEL_ID")  # آيدي القناة، مثال: -1001234567890

try:
    CHANNEL_ID = int(CHANNEL_ID_RAW) if CHANNEL_ID_RAW else None
except ValueError:
    CHANNEL_ID = None

OWNER_USERNAME = "snh_1"   # المالك الأساسي (بدون @)
MIN_NAME_WORDS = 2         # أقل عدد كلمات للاسم

PORT = int(os.getenv("PORT", "10000"))  # Render يعطي المنفذ تلقائياً
PING_URL = os.getenv("PING_URL") or os.getenv("RENDER_EXTERNAL_URL")

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ============================================================
# قاعدة البيانات
# ============================================================
client = AsyncIOMotorClient(MONGO_URI)
db = client.graduation_bot
# الكولكشنات:
#   config         -> الإعدادات ورسائل البوت
#   users          -> المستخدمين (بياناتهم + حالة الخطوة)
#   students       -> طلب كل طالب (الاسم + الصورة + رقم منشوره بالقناة)
#   pending_edits  -> طلبات التعديل المعلقة
#   admins         -> المشرفين وصلاحياتهم
#   banned         -> المحظورين

# ============================================================
# الصلاحيات
# ============================================================
PERMS = {
    "stats": "📊 الإحصائيات",
    "broadcast": "📢 الإذاعة",
    "messages": "📝 تعديل رسائل البوت",
    "toggle": "⏯ إيقاف/تشغيل الاستقبال والتعديل",
    "ban": "🚫 الحظر وفك الحظر",
    "edits": "✅ الموافقة على طلبات التعديل",
    "ping": "🏓 التحكم بالبينك",
}

# ============================================================
# رسائل البوت (قابلة للتعديل من لوحة الإدارة)
# ============================================================
DEFAULT_MESSAGES = {
    "start_msg": "هلا بيك 👋\nهذا بوت استلام صور التخرج.\n(للمساعدة ارسل /help)",
    "ask_name_msg": "اكتب اسمك الثلاثي من فضلك ✍️",
    "bad_name_msg": "اكتب اسمك كامل (كلمتين على الأقل) وبنص فقط.",
    "ask_photo_msg": "تمام ✅\nهسه ارسل صورتك.",
    "wrong_type_msg": "ارسل صورة فقط 🖼 (صورة عادية أو ملف بصيغة صورة).",
    "success_msg": "تم استلام اسمك وصورتك بنجاح ✅",
    "edit_note_msg": "إذا تريد تعدل اسمك أو صورتك اكتب: تعديل",
    "already_msg": "تم استلام طلبك مسبقاً ✅",
    "edit_ask_name_msg": "اكتب الاسم الثلاثي الجديد ✍️\n(للإلغاء اكتب: إلغاء)",
    "edit_ask_photo_msg": "هسه ارسل الصورة الجديدة 🖼\n(للإلغاء اكتب: إلغاء)",
    "edit_sent_msg": "تم إرسال طلب التعديل، راح توصلك رسالة بالنتيجة ⏳",
    "edit_pending_msg": "عندك طلب تعديل قيد المراجعة، انتظر النتيجة ⏳",
    "edit_approved_msg": "تمت الموافقة على طلب التعديل ✅",
    "edit_rejected_msg": "تم رفض طلب التعديل ❌",
    "edit_disabled_msg": "التعديل متوقف حالياً.",
    "maintenance_msg": "نعتذر، استلام الطلبات متوقف حالياً.",
    "help_msg": f"إذا واجهتك مشكلة تواصل مع المطور: @{OWNER_USERNAME}",
    "error_msg": "صار خطأ، حاول مرة ثانية بعد شوية.",
}

MSG_LABELS = {
    "start_msg": "👋 الترحيب",
    "ask_name_msg": "✍️ طلب الاسم",
    "bad_name_msg": "⚠️ اسم غير صحيح",
    "ask_photo_msg": "🖼 طلب الصورة",
    "wrong_type_msg": "⚠️ مو صورة",
    "success_msg": "✅ الاستلام",
    "edit_note_msg": "ℹ️ ملاحظة التعديل",
    "already_msg": "🔁 مسجل مسبقاً",
    "edit_ask_name_msg": "✏️ تعديل: الاسم",
    "edit_ask_photo_msg": "✏️ تعديل: الصورة",
    "edit_sent_msg": "📤 تعديل: أُرسل",
    "edit_pending_msg": "⏳ تعديل: قيد المراجعة",
    "edit_approved_msg": "✅ تعديل: القبول",
    "edit_rejected_msg": "❌ تعديل: الرفض",
    "edit_disabled_msg": "🚫 التعديل متوقف",
    "maintenance_msg": "⏸ الاستقبال متوقف",
    "help_msg": "❓ المساعدة",
    "error_msg": "⚠️ رسالة الخطأ",
}

DEFAULT_CONFIG = {
    "maintenance_mode": False,
    "edit_enabled": True,
    "total_received": 0,
    "ping_enabled": True,
    "ping_interval": 10,  # بالدقائق
    **DEFAULT_MESSAGES,
}


# ============================================================
# دوال مساعدة عامة
# ============================================================
def btn(text, data):
    return InlineKeyboardButton(text, callback_data=data)


async def get_config():
    stored = await db.config.find_one({"_id": "main_config"}) or {}
    return {**DEFAULT_CONFIG, **stored}


async def set_config(key, value):
    await db.config.update_one({"_id": "main_config"}, {"$set": {key: value}}, upsert=True)


async def inc_received():
    await db.config.update_one({"_id": "main_config"}, {"$inc": {"total_received": 1}}, upsert=True)


def is_owner(user):
    return bool(user and user.username and user.username.lower() == OWNER_USERNAME.lower())


async def is_admin(user):
    if is_owner(user):
        return True
    return bool(await db.admins.find_one({"user_id": user.id}))


async def perms_of(user):
    """ترجع مجموعة الصلاحيات الفعلية للمستخدم."""
    if is_owner(user):
        return set(PERMS.keys())
    doc = await db.admins.find_one({"user_id": user.id})
    if not doc:
        return set()
    return {k for k, v in doc.get("perms", {}).items() if v}


async def has_perm(user, perm):
    return perm in await perms_of(user)


async def is_banned(user_id):
    return bool(await db.banned.find_one({"user_id": user_id}))


async def set_state(user_id, state, mode=None, tmp_name=None):
    await db.users.update_one(
        {"user_id": user_id},
        {"$set": {"state": state, "mode": mode, "tmp_name": tmp_name}},
        upsert=True,
    )


def with_edit_note(conf, key):
    text = conf[key]
    if conf.get("edit_enabled"):
        text += "\n\n" + conf["edit_note_msg"]
    return text


def extract_image(msg):
    if msg.photo:
        return msg.photo[-1].file_id, "photo"
    d = msg.document
    if d and d.mime_type and d.mime_type.startswith("image/"):
        return d.file_id, "document"
    return None, None


async def safe_edit(query, text, markup=None):
    try:
        await query.edit_message_text(text, reply_markup=markup, parse_mode="HTML")
    except BadRequest as e:
        if "not modified" not in str(e).lower():
            logger.warning(f"safe_edit: {e}")


def who_is(user):
    s = html.escape(user.full_name)
    if user.username:
        s += f" (@{user.username})"
    return s


# ============================================================
# المستخدمين + إشعار المالك عند أول ستارت
# ============================================================
async def notify_owner_new_user(user, context):
    photo_id = None
    try:
        photos = await context.bot.get_user_profile_photos(user.id, limit=1)
        if photos.total_count > 0:
            photo_id = photos.photos[0][-1].file_id
    except Exception as e:
        logger.warning(f"profile photo: {e}")

    if photo_id:
        await db.users.update_one({"user_id": user.id}, {"$set": {"profile_photo": photo_id}})

    conf = await get_config()
    owner_id = conf.get("owner_id")
    if not owner_id:
        return

    username = f"@{user.username}" if user.username else "لا يوجد"
    text = (
        "🆕 <b>مستخدم جديد ضغط ستارت</b>\n"
        f"👤 الاسم: {html.escape(user.full_name)}\n"
        f"🔗 اليوزر: {username}\n"
        f"🆔 الآيدي: <code>{user.id}</code>"
    )
    try:
        if photo_id:
            await context.bot.send_photo(owner_id, photo_id, caption=text, parse_mode="HTML")
        else:
            await context.bot.send_message(owner_id, text + "\n🖼 الصورة: لا توجد/مخفية", parse_mode="HTML")
    except Exception as e:
        logger.error(f"owner notify failed: {e}")


async def touch_user(user, context):
    """يسجل/يحدث المستخدم. إذا أول مرة يدخل يبلغ المالك. ترجع True إذا جديد."""
    now = datetime.now(timezone.utc)
    res = await db.users.update_one(
        {"user_id": user.id},
        {
            "$set": {"full_name": user.full_name, "username": user.username},
            "$setOnInsert": {"joined_at": now},
        },
        upsert=True,
    )
    # تحديث اسم المشرف (إذا كان مشرف) حتى يظهر بالقائمة
    await db.admins.update_one(
        {"user_id": user.id},
        {"$set": {"name": user.full_name, "username": user.username}},
    )
    if is_owner(user):
        await set_config("owner_id", user.id)

    is_new = res.upserted_id is not None
    if is_new and not is_owner(user):
        await notify_owner_new_user(user, context)
    return is_new


async def notify_owner_error(context, text):
    conf = await get_config()
    owner_id = conf.get("owner_id")
    if owner_id:
        try:
            await context.bot.send_message(owner_id, text)
        except Exception:
            pass


# ============================================================
# النشر بالقناة
# ============================================================
def request_keyboard(uid):
    return InlineKeyboardMarkup([
        [btn("✅ قبول", f"ok_{uid}"), btn("❌ رفض", f"no_{uid}")],
    ])


async def send_file(bot, file_id, ftype, caption, markup):
    if ftype == "photo":
        return await bot.send_photo(CHANNEL_ID, file_id, caption=caption, parse_mode="HTML", reply_markup=markup)
    return await bot.send_document(CHANNEL_ID, file_id, caption=caption, parse_mode="HTML", reply_markup=markup)


async def send_post(bot, uid, name, file_id, ftype):
    return await send_file(bot, file_id, ftype, f"👤 {html.escape(name)}", None)


async def send_request(bot, uid, old_name, new_name, file_id, ftype):
    caption = (
        "🔄 <b>طلب تعديل</b>\n"
        f"👤 الاسم القديم: {html.escape(old_name)}\n"
        f"✏️ الاسم الجديد: {html.escape(new_name)}"
    )
    return await send_file(bot, file_id, ftype, caption, request_keyboard(uid))


async def replace_post(bot, uid, student, new_name, file_id, ftype):
    """يعدل منشور الطالب القديم بالقناة. إذا فشل، ينشر جديد ويحذف القديم. يرجع رقم المنشور."""
    caption = f"👤 {html.escape(new_name)}"
    old_id = (student or {}).get("channel_msg_id")
    if old_id:
        if ftype == "photo":
            media = InputMediaPhoto(file_id, caption=caption, parse_mode="HTML")
        else:
            media = InputMediaDocument(file_id, caption=caption, parse_mode="HTML")
        try:
            await bot.edit_message_media(
                chat_id=CHANNEL_ID, message_id=old_id, media=media
            )
            return old_id
        except Exception as e:
            if "not modified" in str(e).lower():
                return old_id
            logger.warning(f"edit_message_media failed, reposting: {e}")

    sent = await send_post(bot, uid, new_name, file_id, ftype)
    if old_id:
        try:
            await bot.delete_message(CHANNEL_ID, old_id)
        except Exception:
            pass
    return sent.message_id


# ============================================================
# الأوامر الأساسية
# ============================================================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    msg = update.message
    if await is_banned(user.id):
        return

    await touch_user(user, context)
    conf = await get_config()
    admin = await is_admin(user)

    if conf["maintenance_mode"] and not admin:
        await msg.reply_text(conf["maintenance_msg"])
        return

    if admin:
        await msg.reply_text("أهلاً بيك 👋\nلوحة التحكم: /admin")

    u = await db.users.find_one({"user_id": user.id}) or {}
    student = await db.students.find_one({"user_id": user.id})
    state = u.get("state")
    mode = u.get("mode") or "new"

    if state == "name":
        await msg.reply_text(conf["edit_ask_name_msg"] if mode == "edit" else conf["ask_name_msg"])
    elif state == "photo":
        await msg.reply_text(conf["edit_ask_photo_msg"] if mode == "edit" else conf["ask_photo_msg"])
    elif student:
        await msg.reply_text(with_edit_note(conf, "already_msg"))
    else:
        await set_state(user.id, "name", "new")
        await msg.reply_text(conf["start_msg"])
        await msg.reply_text(conf["ask_name_msg"])


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if await is_banned(user.id):
        return
    await touch_user(user, context)
    conf = await get_config()
    await update.message.reply_text(conf["help_msg"])


# ============================================================
# الحظر / المشرفين (أوامر)
# ============================================================
async def ban_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await has_perm(update.effective_user, "ban"):
        return
    if not context.args:
        await update.message.reply_text("مثال: /ban 123456789")
        return
    try:
        target = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ الآيدي غير صحيح.")
        return
    if await db.admins.find_one({"user_id": target}):
        await update.message.reply_text("❌ ما يصير تحظر مشرف.")
        return
    await db.banned.update_one({"user_id": target}, {"$set": {"user_id": target}}, upsert=True)
    await update.message.reply_text(f"🚫 تم حظر {target}.")


async def unban_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await has_perm(update.effective_user, "ban"):
        return
    if not context.args:
        await update.message.reply_text("مثال: /unban 123456789")
        return
    try:
        target = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ الآيدي غير صحيح.")
        return
    await db.banned.delete_one({"user_id": target})
    await update.message.reply_text(f"✅ تم فك الحظر عن {target}.")


async def add_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update.effective_user):
        return
    if not context.args:
        await update.message.reply_text("مثال: /add_admin 123456789")
        return
    try:
        admin_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ الآيدي غير صحيح.")
        return
    await db.admins.update_one(
        {"user_id": admin_id},
        {"$setOnInsert": {"perms": {k: False for k in PERMS}}},
        upsert=True,
    )
    await update.message.reply_text(
        f"✅ تمت إضافة {admin_id} كمشرف (بدون صلاحيات حالياً).",
        reply_markup=InlineKeyboardMarkup([[btn("⚙️ ضبط الصلاحيات", f"adm_{admin_id}")]]),
    )


async def rem_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update.effective_user):
        return
    if not context.args:
        await update.message.reply_text("مثال: /rem_admin 123456789")
        return
    try:
        admin_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ الآيدي غير صحيح.")
        return
    await db.admins.delete_one({"user_id": admin_id})
    await update.message.reply_text(f"✅ تمت إزالة {admin_id} من المشرفين.")


# ============================================================
# لوحة الإدارة
# ============================================================
async def build_panel(user):
    conf = await get_config()
    perms = await perms_of(user)
    owner = is_owner(user)

    maint = conf["maintenance_mode"]
    edit_on = conf["edit_enabled"]

    text = (
        "⚙️ <b>لوحة التحكم</b>\n\n"
        f"الاستقبال: {'🔴 متوقف' if maint else '🟢 يعمل'}\n"
        f"التعديل: {'🟢 مفعّل' if edit_on else '🔴 متوقف'}"
    )
    if "ping" in perms:
        if conf["ping_enabled"]:
            text += f"\nالبينك: 🟢 كل {conf['ping_interval']} دقيقة"
        else:
            text += "\nالبينك: 🔴 متوقف"
        if not PING_URL:
            text += "\n⚠️ ما كو رابط للبينك (RENDER_EXTERNAL_URL / PING_URL)"

    rows = []
    if "stats" in perms:
        rows.append([btn("📊 الإحصائيات", "stats")])
    if "broadcast" in perms:
        rows.append([btn("📢 إذاعة للجميع", "bc")])
    if "messages" in perms:
        rows.append([btn("📝 رسائل البوت", "msgs")])
    if "toggle" in perms:
        rows.append([btn("▶️ تشغيل الاستقبال" if maint else "⏸ إيقاف الاستقبال", "tg_maint")])
        rows.append([btn("⏸ إيقاف التعديل" if edit_on else "▶️ تشغيل التعديل", "tg_edit")])
    if "ping" in perms:
        rows.append([btn("⏸ إيقاف البينك" if conf["ping_enabled"] else "▶️ تشغيل البينك", "tg_ping")])
        rows.append([btn("⏱ تغيير مدة البينك", "ping_int")])
    if owner:
        rows.append([btn("👥 المشرفين وصلاحياتهم", "adm_list")])

    if not rows:
        text += "\n\nما عندك صلاحيات حالياً، راجع المطور."
    if "ban" in perms:
        text += "\n\n🚫 الحظر: <code>/ban ID</code> | <code>/unban ID</code>"
    if owner:
        text += "\n👑 <code>/add_admin ID</code> | <code>/rem_admin ID</code>"

    return text, InlineKeyboardMarkup(rows) if rows else None


async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not await is_admin(user):
        await update.message.reply_text("عذراً، هذا الأمر للمشرفين فقط.")
        return
    await touch_user(user, context)
    text, markup = await build_panel(user)
    await update.message.reply_text(text, reply_markup=markup, parse_mode="HTML")


async def render_msgs_menu(query):
    items = list(MSG_LABELS.items())
    rows = []
    for i in range(0, len(items), 2):
        rows.append([btn(label, f"msg_{key}") for key, label in items[i:i + 2]])
    rows.append([btn("⬅️ رجوع", "panel")])
    await safe_edit(query, "📝 <b>رسائل البوت</b>\nاختر الرسالة اللي تريد تعدلها:", InlineKeyboardMarkup(rows))


async def render_admin_list(query):
    docs = [d async for d in db.admins.find()]
    rows = []
    for d in docs:
        label = d.get("name") or str(d["user_id"])
        rows.append([btn(f"👤 {label}", f"adm_{d['user_id']}")])
    rows.append([btn("⬅️ رجوع", "panel")])
    text = "👥 <b>المشرفين</b>\n" + ("اختر مشرف لضبط صلاحياته:" if docs else "ما كو مشرفين. أضف بـ /add_admin ID")
    await safe_edit(query, text, InlineKeyboardMarkup(rows))


async def render_admin_perms(query, uid):
    doc = await db.admins.find_one({"user_id": uid})
    if not doc:
        await safe_edit(query, "المشرف غير موجود.", InlineKeyboardMarkup([[btn("⬅️ رجوع", "adm_list")]]))
        return
    perms = doc.get("perms", {})
    name = html.escape(doc.get("name") or str(uid))
    rows = [
        [btn(("✅ " if perms.get(k) else "❌ ") + label, f"perm_{uid}_{k}")]
        for k, label in PERMS.items()
    ]
    rows.append([btn("🗑 إزالة المشرف", f"adm_rm_{uid}")])
    rows.append([btn("⬅️ رجوع", "adm_list")])
    text = f"👤 <b>{name}</b>\n🆔 <code>{uid}</code>\n\nاضغط على الصلاحية لتشغيلها أو إيقافها:"
    await safe_edit(query, text, InlineKeyboardMarkup(rows))


async def send_stats(query):
    conf = await get_config()
    stats = await db.command("dbstats")
    data_kb = stats.get("dataSize", 0) / 1024
    size_str = f"{data_kb / 1024:.2f} MB" if data_kb > 1024 else f"{data_kb:.2f} KB"

    users_count = await db.users.count_documents({})
    students_count = await db.students.count_documents({})
    pending_count = await db.pending_edits.count_documents({})
    admins_count = await db.admins.count_documents({})
    banned_count = await db.banned.count_documents({})

    text = (
        "📊 <b>الإحصائيات:</b>\n\n"
        f"👥 المستخدمين: {users_count}\n"
        f"🎓 الطلاب المسجلين: {students_count}\n"
        f"📥 الطلبات المستلمة: {conf.get('total_received', 0)}\n"
        f"🔄 طلبات تعديل معلقة: {pending_count}\n"
        f"🛡 المشرفين: {admins_count}\n"
        f"🚫 المحظورين: {banned_count}\n"
        f"💾 القاعدة: {size_str} من 512 MB"
    )
    await query.message.reply_text(text, parse_mode="HTML")


# ============================================================
# أزرار القناة (آيدي / حظر / قبول / رفض)
# ============================================================
async def resolve_edit(query, context, uid, approve):
    admin = query.from_user
    pend = await db.pending_edits.find_one_and_delete({"user_id": uid})
    if not pend:
        await query.answer("تم البت بهذا الطلب مسبقاً.", show_alert=True)
        return

    who = who_is(admin)
    conf = await get_config()

    if approve:
        student = await db.students.find_one({"user_id": uid})
        try:
            new_id = await replace_post(
                context.bot, uid, student, pend["new_name"], pend["file_id"], pend["ftype"]
            )
        except Exception as e:
            logger.error(f"replace_post failed: {e}")
            # نرجع الطلب حتى ما يضيع
            pend.pop("_id", None)
            await db.pending_edits.update_one({"user_id": uid}, {"$set": pend}, upsert=True)
            await query.answer(f"❌ فشل تعديل المنشور: {e}", show_alert=True)
            return
        await db.students.update_one(
            {"user_id": uid},
            {"$set": {
                "name": pend["new_name"],
                "file_id": pend["file_id"],
                "ftype": pend["ftype"],
                "channel_msg_id": new_id,
            }},
            upsert=True,
        )
        status = f"✅ وافق عليها: {who}"
        notify_key = "edit_approved_msg"
    else:
        status = f"❌ رفضها: {who}"
        notify_key = "edit_rejected_msg"

    caption = (
        "🔄 <b>طلب تعديل</b>\n"
        f"👤 الاسم القديم: {html.escape(pend.get('old_name', '-'))}\n"
        f"✏️ الاسم الجديد: {html.escape(pend['new_name'])}\n\n"
        f"{status}"
    )
    try:
        await query.edit_message_caption(caption=caption, parse_mode="HTML", reply_markup=None)
    except Exception as e:
        logger.warning(f"edit request caption: {e}")

    await query.answer("تم ✅")

    try:
        await context.bot.send_message(uid, conf[notify_key])
    except Exception as e:
        logger.warning(f"notify student failed: {e}")


async def channel_buttons(query, context, data):
    user = query.from_user
    action, _, rest = data.partition("_")
    try:
        uid = int(rest)
    except ValueError:
        await query.answer()
        return

    if not await is_admin(user):
        await query.answer("⛔ هذا الزر للمشرفين فقط.", show_alert=True)
        return

    if action in ("ok", "no"):
        if not await has_perm(user, "edits"):
            await query.answer("⛔ ما عندك صلاحية الموافقة على التعديلات.", show_alert=True)
            return
        await resolve_edit(query, context, uid, approve=(action == "ok"))


# ============================================================
# معالج الأزرار الرئيسي
# ============================================================
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    data = query.data or ""

    if data.startswith(("ok_", "no_")):
        await channel_buttons(query, context, data)
        return

    await query.answer()

    if not await is_admin(user):
        await safe_edit(query, "لا تملك صلاحية استخدام هذه الأزرار.")
        return

    perms = await perms_of(user)
    owner = is_owner(user)

    async def deny():
        await query.message.reply_text("⛔ ما عندك صلاحية.")

    if data == "panel":
        text, markup = await build_panel(user)
        await safe_edit(query, text, markup)

    elif data == "stats":
        if "stats" not in perms:
            return await deny()
        await send_stats(query)

    elif data == "bc":
        if "broadcast" not in perms:
            return await deny()
        context.user_data["admin_state"] = "broadcast"
        await query.message.reply_text(
            "📢 <b>وضع الإذاعة</b>\nارسل الرسالة (نص/صورة/ملف) اللي تريد توصل للجميع.\n\n(للإلغاء ارسل: إلغاء)",
            parse_mode="HTML",
        )

    elif data == "msgs":
        if "messages" not in perms:
            return await deny()
        await render_msgs_menu(query)

    elif data.startswith("msg_"):
        if "messages" not in perms:
            return await deny()
        key = data[4:]
        if key not in MSG_LABELS:
            return
        conf = await get_config()
        context.user_data["admin_state"] = f"msg:{key}"
        await query.message.reply_text(
            f"📝 <b>{MSG_LABELS[key]}</b>\n\nالنص الحالي:\n<pre>{html.escape(conf[key])}</pre>\n"
            "ارسل النص الجديد.\n(للإلغاء ارسل: إلغاء)",
            parse_mode="HTML",
        )

    elif data == "tg_maint":
        if "toggle" not in perms:
            return await deny()
        conf = await get_config()
        await set_config("maintenance_mode", not conf["maintenance_mode"])
        text, markup = await build_panel(user)
        await safe_edit(query, text, markup)

    elif data == "tg_edit":
        if "toggle" not in perms:
            return await deny()
        conf = await get_config()
        await set_config("edit_enabled", not conf["edit_enabled"])
        text, markup = await build_panel(user)
        await safe_edit(query, text, markup)

    elif data == "tg_ping":
        if "ping" not in perms:
            return await deny()
        conf = await get_config()
        await set_config("ping_enabled", not conf["ping_enabled"])
        text, markup = await build_panel(user)
        await safe_edit(query, text, markup)

    elif data == "ping_int":
        if "ping" not in perms:
            return await deny()
        context.user_data["admin_state"] = "ping_interval"
        await query.message.reply_text(
            "⏱ ارسل المدة بالدقائق (رقم من 1 إلى 14).\nRender يوقف الخدمة بعد 15 دقيقة بدون زيارة.\n\n(للإلغاء ارسل: إلغاء)"
        )

    elif data == "adm_list":
        if not owner:
            return await deny()
        await render_admin_list(query)

    elif data.startswith("adm_rm_"):
        if not owner:
            return await deny()
        try:
            uid = int(data[7:])
        except ValueError:
            return
        await db.admins.delete_one({"user_id": uid})
        await render_admin_list(query)

    elif data.startswith("adm_"):
        if not owner:
            return await deny()
        try:
            uid = int(data[4:])
        except ValueError:
            return
        await render_admin_perms(query, uid)

    elif data.startswith("perm_"):
        if not owner:
            return await deny()
        try:
            _, uid_s, perm = data.split("_", 2)
            uid = int(uid_s)
        except ValueError:
            return
        if perm not in PERMS:
            return
        doc = await db.admins.find_one({"user_id": uid})
        if not doc:
            return
        new_val = not doc.get("perms", {}).get(perm, False)
        await db.admins.update_one({"user_id": uid}, {"$set": {f"perms.{perm}": new_val}})
        await render_admin_perms(query, uid)


# ============================================================
# معالج الرسائل (خاص فقط)
# ============================================================
async def handle_admin_state(update, context, user, state):
    msg = update.message

    if msg.text and msg.text.strip() == "إلغاء":
        context.user_data["admin_state"] = None
        await msg.reply_text("✅ تم إلغاء العملية.")
        return

    if state == "broadcast":
        if not await has_perm(user, "broadcast"):
            context.user_data["admin_state"] = None
            await msg.reply_text("⛔ ما عندك صلاحية الإذاعة.")
            return
        await msg.reply_text("⏳ جاري الإرسال...")
        banned_ids = {d["user_id"] async for d in db.banned.find()}
        count = 0
        async for u in db.users.find():
            if u["user_id"] in banned_ids:
                continue
            try:
                await context.bot.copy_message(
                    chat_id=u["user_id"],
                    from_chat_id=msg.chat_id,
                    message_id=msg.message_id,
                )
                count += 1
            except Exception:
                pass
            await asyncio.sleep(0.05)
        context.user_data["admin_state"] = None
        await msg.reply_text(f"✅ تمت الإذاعة لـ {count} مستخدم.")

    elif state.startswith("msg:"):
        if not await has_perm(user, "messages"):
            context.user_data["admin_state"] = None
            await msg.reply_text("⛔ ما عندك صلاحية تعديل الرسائل.")
            return
        key = state[4:]
        if key not in MSG_LABELS:
            context.user_data["admin_state"] = None
            return
        if not msg.text:
            await msg.reply_text("❌ ارسل نص فقط.")
            return
        await set_config(key, msg.text)
        context.user_data["admin_state"] = None
        await msg.reply_text("✅ تم تغيير الرسالة، تظهر للطلاب فوراً.")

    elif state == "ping_interval":
        if not await has_perm(user, "ping"):
            context.user_data["admin_state"] = None
            await msg.reply_text("⛔ ما عندك صلاحية.")
            return
        try:
            n = int((msg.text or "").strip())
        except ValueError:
            n = 0
        if not 1 <= n <= 14:
            await msg.reply_text("❌ ارسل رقم من 1 إلى 14.")
            return
        await set_config("ping_interval", n)
        context.user_data["admin_state"] = None
        await msg.reply_text(f"✅ صار البينك كل {n} دقيقة.")


async def submit_new(update, context, user, conf, name, file_id, ftype):
    msg = update.message
    try:
        sent = await send_post(context.bot, user.id, name, file_id, ftype)
    except Exception as e:
        logger.error(f"channel post failed: {e}")
        await notify_owner_error(
            context, f"⚠️ فشل النشر بالقناة: {e}\nتأكد من CHANNEL_ID وأن البوت مشرف بالقناة."
        )
        await msg.reply_text(conf["error_msg"])
        return

    await db.students.update_one(
        {"user_id": user.id},
        {"$set": {
            "name": name,
            "file_id": file_id,
            "ftype": ftype,
            "channel_msg_id": sent.message_id,
            "submitted_at": datetime.now(timezone.utc),
        }},
        upsert=True,
    )
    await set_state(user.id, None)
    await inc_received()
    await msg.reply_text(with_edit_note(conf, "success_msg"))


async def submit_edit(update, context, user, conf, name, file_id, ftype):
    msg = update.message

    if not conf["edit_enabled"]:
        await set_state(user.id, None)
        await msg.reply_text(conf["edit_disabled_msg"])
        return
    if await db.pending_edits.find_one({"user_id": user.id}):
        await set_state(user.id, None)
        await msg.reply_text(conf["edit_pending_msg"])
        return

    student = await db.students.find_one({"user_id": user.id}) or {}
    old_name = student.get("name", "-")

    try:
        req = await send_request(context.bot, user.id, old_name, name, file_id, ftype)
    except Exception as e:
        logger.error(f"edit request failed: {e}")
        await notify_owner_error(context, f"⚠️ فشل إرسال طلب تعديل للقناة: {e}")
        await msg.reply_text(conf["error_msg"])
        return

    await db.pending_edits.update_one(
        {"user_id": user.id},
        {"$set": {
            "user_id": user.id,
            "old_name": old_name,
            "new_name": name,
            "file_id": file_id,
            "ftype": ftype,
            "request_msg_id": req.message_id,
        }},
        upsert=True,
    )
    await set_state(user.id, None)
    await msg.reply_text(conf["edit_sent_msg"])


async def handle_student(update, context, user, conf):
    msg = update.message
    u = await db.users.find_one({"user_id": user.id}) or {}
    state = u.get("state")
    mode = u.get("mode") or "new"
    student = await db.students.find_one({"user_id": user.id})
    text = (msg.text or "").strip()

    # إلغاء التعديل
    if state and mode == "edit" and text == "إلغاء":
        await set_state(user.id, None)
        await msg.reply_text("تم الإلغاء ✅")
        return

    if state == "name":
        if not msg.text or len(text.split()) < MIN_NAME_WORDS or len(text) > 100:
            await msg.reply_text(conf["bad_name_msg"])
            return
        await set_state(user.id, "photo", mode, text)
        await msg.reply_text(conf["edit_ask_photo_msg"] if mode == "edit" else conf["ask_photo_msg"])
        return

    if state == "photo":
        file_id, ftype = extract_image(msg)
        if not file_id:
            await msg.reply_text(conf["wrong_type_msg"])
            return
        name = u.get("tmp_name")
        if not name:
            await set_state(user.id, "name", mode)
            await msg.reply_text(conf["edit_ask_name_msg"] if mode == "edit" else conf["ask_name_msg"])
            return
        if mode == "edit":
            await submit_edit(update, context, user, conf, name, file_id, ftype)
        else:
            await submit_new(update, context, user, conf, name, file_id, ftype)
        return

    # ما كو خطوة نشطة
    if msg.text and text == "تعديل":
        if not conf["edit_enabled"]:
            await msg.reply_text(conf["edit_disabled_msg"])
        elif not student:
            await set_state(user.id, "name", "new")
            await msg.reply_text(conf["ask_name_msg"])
        elif await db.pending_edits.find_one({"user_id": user.id}):
            await msg.reply_text(conf["edit_pending_msg"])
        else:
            await set_state(user.id, "name", "edit")
            await msg.reply_text(conf["edit_ask_name_msg"])
        return

    if student:
        await msg.reply_text(with_edit_note(conf, "already_msg"))
        return

    await set_state(user.id, "name", "new")
    await msg.reply_text(conf["ask_name_msg"])


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    msg = update.message
    if not msg or await is_banned(user.id):
        return

    await touch_user(user, context)

    admin_state = context.user_data.get("admin_state")
    if admin_state and await is_admin(user):
        await handle_admin_state(update, context, user, admin_state)
        return

    conf = await get_config()
    if conf["maintenance_mode"] and not await is_admin(user):
        await msg.reply_text(conf["maintenance_msg"])
        return

    await handle_student(update, context, user, conf)


# ============================================================
# البينك التلقائي (حتى ما ينام البوت على Render) + سيرفر صحة بسيط
# ============================================================
class _Health(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(b"OK")

    def do_HEAD(self):
        self.send_response(200)
        self.end_headers()

    def log_message(self, *args):
        pass


def start_health_server():
    server = ThreadingHTTPServer(("0.0.0.0", PORT), _Health)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    logger.info(f"health server on port {PORT}")


async def ping_loop():
    """يزور رابط الخدمة نفسه حسب الإعدادات المخزنة بالقاعدة (تشغيل/إيقاف + المدة)."""
    last = None
    async with httpx.AsyncClient(timeout=20) as http:
        while True:
            try:
                conf = await get_config()
                interval = max(1, int(conf.get("ping_interval", 10))) * 60
                due = last is None or (time.monotonic() - last) >= interval
                if conf.get("ping_enabled") and PING_URL and due:
                    last = time.monotonic()
                    try:
                        r = await http.get(PING_URL)
                        logger.info(f"ping {PING_URL} -> {r.status_code}")
                    except Exception as e:
                        logger.warning(f"ping failed: {e}")
            except Exception as e:
                logger.warning(f"ping loop error: {e}")
            await asyncio.sleep(20)


async def post_init(application):
    application.bot_data["ping_task"] = asyncio.create_task(ping_loop())


# ============================================================
# التشغيل
# ============================================================
def main():
    if not BOT_TOKEN or not MONGO_URI or CHANNEL_ID is None:
        print("❌ خطأ: تأكد من إضافة المتغيرات BOT_TOKEN و MONGO_URI و CHANNEL_ID (رقم صحيح).")
        return

    start_health_server()
    application = Application.builder().token(BOT_TOKEN).post_init(post_init).build()

    private = filters.ChatType.PRIVATE
    application.add_handler(CommandHandler("start", start, filters=private))
    application.add_handler(CommandHandler("help", help_command, filters=private))
    application.add_handler(CommandHandler("admin", admin_panel, filters=private))
    application.add_handler(CommandHandler("add_admin", add_admin, filters=private))
    application.add_handler(CommandHandler("rem_admin", rem_admin, filters=private))
    application.add_handler(CommandHandler("ban", ban_user, filters=private))
    application.add_handler(CommandHandler("unban", unban_user, filters=private))
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_handler(MessageHandler(private & ~filters.COMMAND, handle_message))

    print("🤖 البوت يعمل...")
    application.run_polling()


if __name__ == "__main__":
    main()
