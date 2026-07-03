import os
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)
from motor.motor_asyncio import AsyncIOMotorClient

# --- المتغيرات البيئية ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
MONGO_URI = os.getenv("MONGO_URI")

# يوزرات الإدارة
OWNER_USERNAME = "snh_1" 
FIXED_ADMIN_USERNAME = "x_mzer"

# 🔴 الآيدي مال قناتك الخاصة
TARGET_CHANNEL_ID = -1004451735544  

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# --- إعداد قاعدة البيانات (MongoDB) ---
client = AsyncIOMotorClient(MONGO_URI)
db = client.graduation_bot

# دوال مساعدة لقاعدة البيانات
async def get_config():
    conf = await db.config.find_one({"_id": "main_config"})
    if not conf:
        conf = {"_id": "main_config", "maintenance_mode": False, "total_received": 0}
        await db.config.insert_one(conf)
    return conf

async def update_config(key, value):
    await db.config.update_one({"_id": "main_config"}, {"$set": {key: value}}, upsert=True)

async def inc_received():
    await db.config.update_one({"_id": "main_config"}, {"$inc": {"total_received": 1}}, upsert=True)

# تسجيل المشرفين الأساسيين تلقائياً في قاعدة البيانات ليتمكنوا من استلام الرسائل
async def register_admin_if_needed(user):
    if user and user.username in [OWNER_USERNAME, FIXED_ADMIN_USERNAME]:
        await db.admins.update_one({"user_id": user.id}, {"$set": {"user_id": user.id}}, upsert=True)

async def is_admin(user):
    if user.username in [OWNER_USERNAME, FIXED_ADMIN_USERNAME]:
        return True
    doc = await db.admins.find_one({"user_id": user.id})
    return bool(doc)

async def is_banned(user_id):
    doc = await db.banned.find_one({"user_id": user_id})
    return bool(doc)

# --- الأوامر الأساسية ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    
    # تحقق من الحظر
    if await is_banned(user.id):
        return

    await register_admin_if_needed(user)
    
    if user.username == OWNER_USERNAME:
        await update.message.reply_text(f"أهلاً بك يا مطور @{OWNER_USERNAME}! تم تفعيل صلاحياتك الإدارية.\nإرسل /admin لفتح لوحة التحكم.")
        return

    if user.username == FIXED_ADMIN_USERNAME:
        await update.message.reply_text(f"أهلاً بك @{FIXED_ADMIN_USERNAME}! أنت مشرف ثابت في هذا البوت.\nستصلك تصاميم وملفات الطلاب هنا تلقائياً.")
        return

    conf = await get_config()
    if conf.get("maintenance_mode", False) and not await is_admin(user):
        await update.message.reply_text("عذراً، تم إيقاف استقبال الملفات والرسائل حالياً.")
        return

    await update.message.reply_text("اهلا بك ارسل ملفك وراح يوصل للمشرفين.\n(للمساعدة ارسل /help)")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if await is_banned(user.id): return

    help_text = (
        "في حال واجهت أي مشكلة أثناء إرسال ملف التصميم أو كان لديك استفسار، "
        "يرجى التواصل مع فريق الدعم:\n\n"
        f"👨‍💻 المطور: @{OWNER_USERNAME}\n"
        f"👨‍💼 المشرف: @{FIXED_ADMIN_USERNAME}"
    )
    await update.message.reply_text(help_text)

# --- نظام الحظر (للمالك فقط) ---
async def ban_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.username != OWNER_USERNAME: return
    if not context.args:
        await update.message.reply_text("يرجى إرسال آيدي المستخدم. مثال:\n`/ban 123456789`", parse_mode="Markdown")
        return
    try:
        target_id = int(context.args[0])
        await db.banned.update_one({"user_id": target_id}, {"$set": {"user_id": target_id}}, upsert=True)
        await update.message.reply_text(f"🚫 تم حظر المستخدم ذو الآيدي {target_id} بنجاح ولن يتمكن من استخدام البوت.")
    except ValueError:
        await update.message.reply_text("❌ الآيدي غير صحيح.")

async def unban_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.username != OWNER_USERNAME: return
    if not context.args:
        await update.message.reply_text("يرجى إرسال آيدي المستخدم. مثال:\n`/unban 123456789`", parse_mode="Markdown")
        return
    try:
        target_id = int(context.args[0])
        await db.banned.delete_one({"user_id": target_id})
        await update.message.reply_text(f"✅ تم رفع الحظر عن المستخدم ذو الآيدي {target_id} بنجاح.")
    except ValueError:
        await update.message.reply_text("❌ الآيدي غير صحيح.")

# --- لوحة الإدارة ---
async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not await is_admin(user):
        await update.message.reply_text("عذراً، هذا الأمر مخصص للمشرفين فقط.")
        return

    conf = await get_config()
    status_text = "🔴 متوقف (لا يستقبل ملفات)" if conf.get("maintenance_mode") else "🟢 يعمل ويستقبل الملفات"
    total_received = conf.get("total_received", 0)
    
    # حساب حجم قاعدة البيانات
    stats = await db.command("dbstats")
    data_size_kb = stats.get("dataSize", 0) / 1024
    size_str = f"{data_size_kb / 1024:.2f} MB" if data_size_kb > 1024 else f"{data_size_kb:.2f} KB"
    
    admins_count = await db.admins.count_documents({})
    banned_count = await db.banned.count_documents({})

    text = (
        f"📊 **لوحة تحكم الإدارة**\n\n"
        f"🔹 حالة البوت: {status_text}\n"
        f"🔹 إجمالي الطلبات المستلمة: {total_received} طلب 📈\n"
        f"🔹 عدد المشرفين الإضافيين: {admins_count}\n"
        f"🔹 عدد المحظورين: {banned_count}\n"
        f"💾 حجم قاعدة البيانات المستهلك: {size_str} من أصل 512 MB\n\n"
        "استخدم الأزرار أدناه للتحكم:"
    )
    
    keyboard = [
        [
            InlineKeyboardButton("⏸ إيقاف الاستقبال", callback_data="m_on"),
            InlineKeyboardButton("▶️ تشغيل الاستقبال", callback_data="m_off")
        ]
    ]
    
    if update.effective_user.username == OWNER_USERNAME:
        text += "\n\n👑 *صلاحيات المطور:*\n- لإضافة مشرف: `/add_admin ID`\n- لحذف مشرف: `/rem_admin ID`\n- لحظر طالب مزعج: `/ban ID`\n- لفك الحظر: `/unban ID`"
        
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(text, reply_markup=reply_markup, parse_mode="Markdown")

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if not await is_admin(query.from_user):
        await query.edit_message_text("لا تملك صلاحية استخدام هذه الأزرار.")
        return

    data = query.data

    if data == "m_on":
        await update_config("maintenance_mode", True)
        await query.edit_message_text("⚙️ تم إيقاف استقبال الملفات. البوت الآن لا يستقبل أي شيء من الطلاب.")
    elif data == "m_off":
        await update_config("maintenance_mode", False)
        await query.edit_message_text("🟢 تم تشغيل الاستقبال. البوت يعمل الآن بشكل طبيعي ويستقبل الملفات.")
    
    elif data.startswith("forward_"):
        try:
            await context.bot.copy_message(
                chat_id=TARGET_CHANNEL_ID,
                from_chat_id=query.message.chat_id,
                message_id=query.message.message_id
            )
            await query.edit_message_reply_markup(reply_markup=None)
            await context.bot.send_message(chat_id=query.message.chat_id, text="✅ تم نشر الطلب بنجاح في القناة.")
        except Exception as e:
            await context.bot.send_message(chat_id=query.message.chat_id, text=f"❌ حدث خطأ أثناء النشر للقناة.\nتفاصيل الخطأ: {e}")

async def add_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.username != OWNER_USERNAME: return
    if not context.args:
        await update.message.reply_text("يرجى كتابة الآيدي بعد الأمر. مثال:\n`/add_admin 12345678`", parse_mode="Markdown")
        return
    try:
        admin_id = int(context.args[0])
        await db.admins.update_one({"user_id": admin_id}, {"$set": {"user_id": admin_id}}, upsert=True)
        await update.message.reply_text(f"✅ تم إضافة العضو ذو الآيدي {admin_id} كمشرف بنجاح.")
    except ValueError:
        await update.message.reply_text("❌ يرجى إدخال آيدي رقمي صحيح.")

async def rem_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.username != OWNER_USERNAME: return
    if not context.args:
        await update.message.reply_text("يرجى كتابة الآيدي بعد الأمر. مثال:\n`/rem_admin 12345678`", parse_mode="Markdown")
        return
    try:
        admin_id = int(context.args[0])
        await db.admins.delete_one({"user_id": admin_id})
        await update.message.reply_text(f"✅ تم إزالة العضو ذو الآيدي {admin_id} من المشرفين.")
    except ValueError:
        await update.message.reply_text("❌ يرجى إدخال آيدي رقمي صحيح.")

# --- استقبال ومعالجة الرسائل ---
async def handle_incoming_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat_id = update.effective_chat.id

    if await is_banned(user.id):
        return

    if await is_admin(user):
        if update.message.reply_to_message:
            # استرجاع آيدي المرسل الأصلي من قاعدة البيانات
            doc = await db.messages.find_one({"_id": update.message.reply_to_message.message_id})
            if doc:
                target_user_id = doc["user_id"]
                try:
                    await context.bot.copy_message(
                        chat_id=target_user_id,
                        from_chat_id=chat_id,
                        message_id=update.message.message_id
                    )
                    await update.message.reply_text("✅ تم إرسال ردك إلى المستخدم بنجاح.")
                except Exception as e:
                    await update.message.reply_text(f"❌ فشل إرسال الرد للمستخدم: {e}")
            return
        return

    conf = await get_config()
    if conf.get("maintenance_mode", False):
        await update.message.reply_text("⚠️ نعتذر، استلام الملفات متوقف حالياً من قبل الإدارة.")
        return

    await inc_received()

    content_type = "نص 📝"
    is_auto_forwarded = False

    if update.message.document:
        content_type = "ملف 📄"
    elif update.message.photo:
        content_type = "صورة 🖼"
    elif update.message.video:
        content_type = "فيديو 🎥"

    # التحويل التلقائي للقناة
    if update.message.document or update.message.photo:
        try:
            await context.bot.copy_message(
                chat_id=TARGET_CHANNEL_ID,
                from_chat_id=chat_id,
                message_id=update.message.message_id,
                caption=f"👤 المرسل: {user.full_name}"
            )
            is_auto_forwarded = True
        except Exception as e:
            logger.error(f"فشل التحويل التلقائي للقناة: {e}")

    username_str = f"@{user.username}" if user.username else "لا يوجد"
    info_text = f"📬 **طلب تصميم جديد**\n" \
                f"👤 المرسل: {user.full_name}\n" \
                f"🆔 الآيدي: `{user.id}`\n" \
                f"🔗 اليوزر: {username_str}\n" \
                f"نوع المرفق: {content_type}\n"

    if is_auto_forwarded:
        info_text += "✅ حالة التحويل: (تم النشر في القناة تلقائياً)\n--- الطلب بالأسفل ---"
    else:
        info_text += "⚠️ حالة التحويل: (يحتاج تحويل يدوي للقناة)\n--- الطلب بالأسفل ---"

    # جلب جميع المشرفين من قاعدة البيانات
    all_admins = [doc["user_id"] async for doc in db.admins.find()]
    
    for admin_id in all_admins:
        try:
            await context.bot.send_message(chat_id=admin_id, text=info_text, parse_mode="Markdown")
            
            reply_markup = None
            if not is_auto_forwarded:
                keyboard = [[InlineKeyboardButton("📢 تحويل فوري للقناة", callback_data=f"forward_{update.message.message_id}")]]
                reply_markup = InlineKeyboardMarkup(keyboard)
            
            sent_msg = await context.bot.copy_message(
                chat_id=admin_id,
                from_chat_id=chat_id,
                message_id=update.message.message_id,
                reply_markup=reply_markup
            )
            
            # حفظ رسالة البوت لربطها بالطالب من أجل ميزة الرد المباشر
            await db.messages.insert_one({"_id": sent_msg.message_id, "user_id": user.id})

        except Exception as e:
            logger.error(f"فشل إرسال الرسالة للمشرف {admin_id}: {e}")

    await update.message.reply_text("تم الاستلام بنجاح")

def main():
    if not BOT_TOKEN or not MONGO_URI:
        print("❌ خطأ: تأكد من إضافة BOT_TOKEN و MONGO_URI في متغيرات البيئة.")
        return

    application = Application.builder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("admin", admin_panel))
    application.add_handler(CommandHandler("add_admin", add_admin))
    application.add_handler(CommandHandler("rem_admin", rem_admin))
    application.add_handler(CommandHandler("ban", ban_user))
    application.add_handler(CommandHandler("unban", unban_user))
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, handle_incoming_messages))

    print("🤖 البوت يعمل الآن بقاعدة بيانات سحابية ويراقب الطلبات...")
    application.run_polling()

if __name__ == "__main__":
    main()
