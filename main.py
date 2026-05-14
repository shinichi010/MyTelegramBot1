import telebot
from telebot.types import Message
import time

# التوكن الجديد مالتك
TOKEN = '8159446452:AAGrkJbtEFoKgXab19l7tX36SDTowRvPxB4'
bot = telebot.TeleBot(TOKEN)

groups_data = {}

def get_group_data(chat_id):
    if chat_id not in groups_data:
        groups_data[chat_id] = {
            'locked': False, 'welcome': True, 'admins': [], 'vips': []
        }
    return groups_data[chat_id]

def is_owner(chat_id, user_id):
    try:
        member = bot.get_chat_member(chat_id, user_id)
        return member.status == 'creator'
    except: return False

def is_admin(chat_id, user_id):
    if is_owner(chat_id, user_id): return True
    return user_id in get_group_data(chat_id)['admins']

# --- ميزة كشف تعديل الرسائل ---
@bot.edited_message_handler(func=lambda m: True)
def handle_edited_message(message: Message):
    if message.chat.type in ['group', 'supergroup']:
        bot.reply_to(message, f"كشفته! القفاص {message.from_user.first_name} عدل رسالته 🕵️‍♂️")

# --- الردود التفاعلية ---
@bot.message_handler(func=lambda m: True, content_types=['text'])
def handle_text(message: Message):
    text = message.text
    chat_id = message.chat.id
    user_id = message.from_user.id
    data = get_group_data(chat_id)

    # 1. ردود السلام والتحية
    greetings = {
        "السلام عليكم": "وعليكم السلام ورحمة الله وبركاته، نورتنا! ❤️",
        "شلونك": "بخير إذا أنت بخير، أسأل عليك يا طيب! ✨",
        "هلا": "هلا بيك وبجيتك، نورت الكروب 🌹",
        "شلونكم": "بخير وعافية، أنت شلونك؟",
        "منو المالك": "المالك هو تاج راسي منشئ الكروب 👑"
    }
    
    if text in greetings:
        bot.reply_to(message, greetings[text])
        return

    # 2. أوامر الإدارة والقفل
    if text == "قفل الشات":
        if is_admin(chat_id, user_id):
            data['locked'] = True
            bot.reply_to(message, "🔒 تم قفل الشات بنجاح.")
        return
    
    if text == "فتح الشات":
        if is_admin(chat_id, user_id):
            data['locked'] = False
            bot.reply_to(message, "🔓 تم فتح الشات، انطلقوا.")
        return

    # 3. أمر المسح
    if text.startswith("مسح "):
        if is_admin(chat_id, user_id):
            try:
                num = int(text.split()[1])
                for i in range(num + 1):
                    bot.delete_message(chat_id, message.message_id - i)
            except: pass
        return

    # 4. حماية الشات المقفول
    if data['locked'] and not is_admin(chat_id, user_id):
        if user_id not in data['vips']:
            bot.delete_message(chat_id, message.message_id)

# --- الترحيب بالاعضاء الجدد ---
@bot.message_handler(content_types=['new_chat_members'])
def welcome(message: Message):
    if get_group_data(message.chat.id)['welcome']:
        for member in message.new_chat_members:
            bot.send_message(message.chat.id, f"يا هلا بـ {member.first_name} نورت كروبنا الجديد! 🌟")

# تشغيل البوت مع ضمان الاستمرارية
print("البوت شغال حالياً...")
while True:
    try:
        bot.polling(none_stop=True, interval=0, timeout=20)
    except Exception as e:
        print(f"حدث خطأ: {e}")
        time.sleep(5)
