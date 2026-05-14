import telebot
import requests
import time

# التوكن مالتك
TOKEN = '8159446452:AAGrkJbtEFoKgXab19l7tX36SDTowRvPxB4'
bot = telebot.TeleBot(TOKEN)

# ايدي حسابك التليجرام (حتى تبقى مالك ثابت ما تنحذف رتبتك)
OWNER_ID = 5489814144 # استبدل هذا الرقم بايدي حسابك اذا كان مختلف

groups_data = {}

def get_data(cid):
    if cid not in groups_data:
        groups_data[cid] = {'locked': False, 'admins': [], 'vips': []}
    return groups_data[cid]

def is_admin(m):
    try:
        if m.from_user.id == OWNER_ID: return True
        status = bot.get_chat_member(m.chat.id, m.from_user.id).status
        if status in ['creator', 'administrator'] or m.from_user.id in get_data(m.chat.id)['admins']:
            return True
    except: pass
    return False

# حذف رسائل النظام (انضم وغادر)
@bot.message_handler(content_types=['new_chat_members', 'left_chat_member'])
def clean_system(m):
    try: bot.delete_message(m.chat.id, m.message_id)
    except: pass

# كشف التعديل
@bot.edited_message_handler(func=lambda m: True)
def handle_edit(m):
    try: bot.reply_to(m, f"عدل رسالته القفاص {m.from_user.first_name} 🕵️")
    except: pass

@bot.message_handler(func=lambda m: True)
def handle_all(m):
    text = m.text
    if not text: return
    cid = m.chat.id
    uid = m.from_user.id
    data = get_data(cid)

    # ردود سريعة
    if text == "السلام عليكم": bot.reply_to(m, "وعليكم السلام نورت")
    elif text == "شلونك": bot.reply_to(m, "بخير اسأل عنك")
    elif text == "هلا": bot.reply_to(m, "هلا بيك")

    # نظام الرتب (بالرد)
    if m.reply_to_message:
        target_id = m.reply_to_message.from_user.id
        target_name = m.reply_to_message.from_user.first_name
        
        if text == "رفع مدير" and is_admin(m):
            if target_id not in data['admins']: data['admins'].append(target_id)
            bot.reply_to(m, f"تم رفع {target_name} مدير")
        elif text == "رفع مميز" and is_admin(m):
            if target_id not in data['vips']: data['vips'].append(target_id)
            bot.reply_to(m, f"تم رفع {target_name} مميز")
        elif text == "تنزيل مدير" and is_admin(m):
            if target_id in data['admins']: data['admins'].remove(target_id)
            bot.reply_to(m, f"تم تنزيل {target_name}")
        elif text == "تنزيل مميز" and is_admin(m):
            if target_id in data['vips']: data['vips'].remove(target_id)
            bot.reply_to(m, f"تم تنزيل {target_name}")

    # المسح
    if text.startswith("مسح ") and is_admin(m):
        try:
            num = int(text.split()[1])
            for i in range(num + 1):
                try: bot.delete_message(cid, m.message_id - i)
                except: pass
        except: pass

    # قفل الشات
    if text == "قفل الشات" and is_admin(m):
        data['locked'] = True
        bot.reply_to(m, "تم قفل الشات")
    elif text == "فتح الشات" and is_admin(m):
        data['locked'] = False
        bot.reply_to(m, "تم فتح الشات")

    # حماية الشات المقفول
    if data['locked'] and not is_admin(m) and uid not in data['vips']:
        try: bot.delete_message(cid, m.message_id)
        except: pass

    # تحميل تيك توك
    if "vt.tiktok.com" in text:
        try:
            wait = bot.reply_to(m, "جاري التحميل... ⏳")
            res = requests.get(f"https://api.tiklydown.eu.org/api/download?url={text}").json()
            bot.send_video(cid, res['video']['noWatermark'], reply_to_message_id=m.message_id)
            bot.delete_message(cid, wait.message_id)
        except: pass

# تشغيل
print("Bot is Active...")
bot.infinity_polling(timeout=10, long_polling_timeout=5)
