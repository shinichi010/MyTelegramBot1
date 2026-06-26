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

# --- الإعدادات الأساسية قادمة من متغيرات البيئة (Railway) ---
# سيقوم الكود بقراءة التوكن من الـ Variables في Railway تحت اسم BOT_TOKEN
BOT_TOKEN = os.getenv("BOT_TOKEN")

# يوزر المالك الأساسي بدون @ (يجب أن يكون متطابقاً مع يوزرك بالتليجرام)
OWNER_USERNAME = "snh_1" 

# الآيدي الرقمي الثابت لقناتك (تم استخراجه من رابط القناة الخاص بك)
TARGET_CHANNEL_ID = -1002237077978  

# المتغيرات العامة لحفظ البيانات أثناء تشغيل البوت (في الذاكرة)
maintenance_mode = False
admins = set()       # لحفظ الأي دي (Chat ID) الخاص بالمشرفين
user_messages = {}   # لربط رسالة المشرف بالمرسل الأصلي

# إعداد السجلات (Logging) لمراقبة الأخطاء
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# --- دالة التحقق من الصلاحيات ---
def is_owner(update: Update) -> bool:
    return update.effective_user.username == OWNER_USERNAME

def is_admin(update: Update) -> bool:
    return update.effective_user.id in admins or is_owner(update)

# --- الأوامر الأساسية ---

# أمر /start للمستخدمين والمشرفين
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat_id = update.effective_chat.id

    # إذا كان مالك البوت ودخل لأول مرة، نقوم بتسجيل الأي دي الخاص به تلقائياً
    if user.username == OWNER_USERNAME:
        admins.add(chat_id)
        await update.message.reply_text(
            f"أهلاً بك يا مطور @{OWNER_USERNAME}! تم تفعيل صلاحياتك الإدارية.\n"
            "إرسل /admin لفتح لوحة التحكم."
        )
        return

    # إذا كان البوت في وضع الصيانة
    if maintenance_mode and not is_admin(update):
        await update.message.reply_text("عذراً، البوت متوقف حالياً للصيانة. يرجى المحاولة لاحقاً.")
        return

    # للمستخدمين العاديين
    await update.message.reply_text(
        "أهلاً بك في بوت التواصل! 📝\n"
        "أرسل طلبك أو رسالتك هنا، وسيتم مراجعتها من قبل الإدارة والرد عليك أو نشرها في القناة."
    )

# لوحة التحكم للمشرفين والمالك
async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        await update.message.reply_text("عذراً، هذا الأمر مخصص للمشرفين فقط.")
        return

    status_text = "🔴 متوقف (صيانة)" if maintenance_mode else "🟢 يعمل بشكل طبيعي"
    
    text = (
        f"📊 **لوحة تحكم الإدارة**\n\n"
        f"حالة البوت الحالية: {status_text}\n"
        f"عدد المشرفين المضافين حالياً: {len(admins)}\n\n"
        "استخدم الأزرار أدناه للتحكم:"
    )
    
    # أزرار التحكم
    keyboard = [
        [
            InlineKeyboardButton("🛠 تشغيل وضع الصيانة", callback_data="m_on"),
            InlineKeyboardButton("✅ إيقاف وضع الصيانة", callback_data="m_off")
        ]
    ]
    
    # خيارات إضافية للمالك فقط (إدارة المشرفين)
    if is_owner(update):
        text += "\n\n*👑 صلاحيات المالك:*\nلإضافة مشرف: أرسل `/add_admin ID`\nلحذف مشرف: أرسل `/rem_admin ID`"
        
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(text, reply_markup=reply_markup, parse_mode="Markdown")

# --- معالجة أزرار لوحة التحكم وتحويل الرسائل ---
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if not is_admin(update):
        await query.edit_message_text("لا تملك صلاحية استخدام هذه الأزرار.")
        return

    global maintenance_mode
    data = query.data

    if data == "m_on":
        maintenance_mode = True
        await query.edit_message_text("⚙️ تم تفعيل وضع الصيانة. البوت الآن لا يستقبل رسائل من المستخدمين.")
    elif data == "m_off":
        maintenance_mode = False
        await query.edit_message_text("🟢 تم إيقاف وضع الصيانة. البوت يعمل الآن بشكل طبيعي ويستقبل الرسائل.")
    
    # معالجة زر "تحويل تلقائي للقناة" المرافق لرسائل المستخدمين
    elif data.startswith("forward_"):
        msg_id = int(data.split("_")[1])
        orig_user_id = user_messages.get(query.message.message_id)
        
        # جلب الآيدي الخاص بالرسالة الأصلية المخزنة للتحويل
        if query.message.reply_to_message:
            source_msg_id = query.message.reply_to_message.message_id
        else:
            source_msg_id = msg_id

        try:
            # إرسال الرسالة كـ Copy (مجهولة المصدر تماماً) إلى قناتك المحددة بالأعلى
            await context.bot.copy_message(
                chat_id=TARGET_CHANNEL_ID,
                from_chat_id=query.message.chat_id,
                message_id=source_msg_id
            )
            # تحديث أزرار الرسالة لإلغاء الزر وتأكيد التحويل
            await query.edit_message_reply_markup(reply_markup=None)
            await context.bot.send_message(chat_id=query.message.chat_id, text="✅ تم نشر الرسالة بنجاح في القناة المحددة وبشكل مجهول.")
        except Exception as e:
            await context.bot.send_message(
                chat_id=query.message.chat_id, 
                text=f"❌ حدث خطأ أثناء النشر تلقائياً.\nتأكد أن البوت مضاف كـ Admin (مشرف) داخل القناة ولديه صلاحية النشر.\nتفاصيل الخطأ: {e}"
            )

# --- إدارة المشرفين (للمالك فقط) ---
async def add_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update): return
    if not context.args:
        await update.message.reply_text("يرجى كتابة الآيدي بعد الأمر. مثال:\n`/add_admin 12345678`", parse_mode="Markdown")
        return
    try:
        admin_id = int(context.args[0])
        admins.add(admin_id)
        await update.message.reply_text(f"✅ تم إضافة العضو ذو الآيدي {admin_id} كمشرف بنجاح.")
    except ValueError:
        await update.message.reply_text("❌ يرجى إدخال آيدي رقمي صحيح.")

async def rem_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update): return
    if not context.args:
        await update.message.reply_text("يرجى كتابة الآيدي بعد الأمر. مثال:\n`/rem_admin 12345678`", parse_mode="Markdown")
        return
    try:
        admin_id = int(context.args[0])
        admins.discard(admin_id)
        await update.message.reply_text(f"✅ تم إزالة العضو ذو الآيدي {admin_id} من المشرفين.")
    except ValueError:
        await update.message.reply_text("❌ يرجى إدخال آيدي رقمي صحيح.")

# --- استقبال رسائل المستخدمين وتوجيهها للمشرفين ---
async def handle_incoming_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat_id = update.effective_chat.id

    # إذا كان مشرفاً يرسل رسالة عادية
    if is_admin(update):
        # إذا قام المشرف بالرد (Reply) على رسالة مستخدم موجهة إليه للرد عليه
        if update.message.reply_to_message:
            orig_msg_id = update.message.reply_to_message.message_id
            target_user_id = user_messages.get(orig_msg_id)
            if target_user_id:
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

    # إذا كان وضع الصيانة مفعل للمستخدمين العاديين
    if maintenance_mode:
        await update.message.reply_text("⚠️ البوت في وضع الصيانة حالياً، لا يمكن استقبال رسائل.")
        return

    # توجيه الرسالة ومعلومات المرسل إلى جميع المشرفين المضافين
    info_text = f"📬 **رسالة طلب جديدة**\n" \
                f"👤 المرسل: {user.full_name}\n" \
                f"🆔 الآيدي: `{user.id}`\n" \
                f"🔗 اليوزر: @{user.username if user.username else 'لا يوجد'}\n" \
                f"--- نص الطلب/الرسالة بالأسفل ---"

    for admin_id in admins:
        try:
            # 1. إرسال معلومات الشخص
            await context.bot.send_message(chat_id=admin_id, text=info_text, parse_mode="Markdown")
            
            # 2. إرسال محتوى الرسالة وتحتها زر التحويل الفوري المباشر
            keyboard = [[InlineKeyboardButton("📢 تحويل فوري للقناة (مجهول)", callback_data=f"forward_{update.message.message_id}")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            sent_msg = await context.bot.copy_message(
                chat_id=admin_id,
                from_chat_id=chat_id,
                message_id=update.message.message_id,
                reply_markup=reply_markup
            )
            
            # حفظ رقم رسالة البوت الموجهة لربط الأزرار والردود بها
            user_messages[sent_msg.message_id] = chat_id

        except Exception as e:
            logger.error(f"فشل إرسال الرسالة للمشرف {admin_id}: {e}")

    # تأكيد الاستلام للمستخدم العادي
    await update.message.reply_text("✅ تم إرسال طلبك بنجاح إلى الإدارة. سيتم مراجعة طلبك والنشر قريباً.")

# --- التشغيل الأساسي ---
def main():
    if not BOT_TOKEN:
        print("❌ خطأ: لم يتم العثور على متغير البيئة BOT_TOKEN. يرجى إضافته في إعدادات Railway.")
        return

    # بناء التطبيق
    application = Application.builder().token(BOT_TOKEN).build()

    # إضافة المعالجات
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("admin", admin_panel))
    application.add_handler(CommandHandler("add_admin", add_admin))
    application.add_handler(CommandHandler("rem_admin", rem_admin))
    
    application.add_handler(CallbackQueryHandler(button_handler))
    
    # معالج كافة أنواع الرسائل (نصوص، صور، ملفات، إلخ)
    application.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, handle_incoming_messages))

    # بدء تشغيل البوت
    print("🤖 البوت يعمل الآن ويراقب الطلبات...")
    application.run_polling()

if __name__ == "__main__":
    main()
