import telebot
import requests
import time
from telebot.types import Message

TOKEN = '8159446452:AAGrkJbtEFoKgXab19l7tX36SDTowRvPxB4'
bot = telebot.TeleBot(TOKEN)

groups_data = {}

def get_data(cid):
    if cid not in groups_data:
        groups_data[cid] = {'locked': False, 'admins': [], 'vips': []}
    return groups_data[cid]

def is_admin(m):
    try:
        status = bot.get_chat_member(m.chat.id, m.from_user.id).status
        if status in ['creator', 'administrator'] or m.from_user.id in get_data(m.chat.id)['admins']:
            return True
    except: pass
    return False

# 1. حذف رسائل النظام (دخول وخروج)
@bot.message_handler(content_types=['new_chat_members', 'left_chat_member'])
def clean_system_messages(m):
    try:
        bot.delete_message(m.chat.id, m.message_id)
    except: pass

# 2. كشف التعديل
@bot.edited_message_handler(func=lambda m: True)
def handle_edit(m):
    bot.reply_to(m, f"عدل رسالته القفاص {m.from_user.first_name} 🕵️")

# 3. معالج الرسائل والأوامر
@bot.message_handler(func=lambda m: True)
def handle_all(m):
    text = m.text
    cid = m.chat.id
    uid = m.from_user.id
    data = get_data(cid)

    # ردود تفاعلية (بدون فوارز)
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

    # نظام المسح
    if text.startswith("مسح ") and is_admin(m):
        try:
            num = int(text.split()[1])
            # حذف الرسائل دفعة واحدة
            for i in range(num + 1):
                try: bot.delete_message(cid, m.message_id - i)
                except: pass
        except: pass

    # قفل وفتح الشات
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

    # --- ميزة التحميل من تيك توك ---
    if "tiktok.com" in text:
        msg = bot.reply_to(m, "جاري تحميل الفيديو... ⏳")
        try:
            # استخدام API مجاني للتحميل
            api_url = f"https://api.tiklydown.eu.org/api/download?url={text}"
            res = requests.get(api_url).json()
            video_url = res['video']['noWatermark']
            bot.send_video(cid, video_url, reply_to_message_id=m.message_id)
            bot.delete_message(cid, msg.message_id)
        except:
            bot.edit_message_text("عذراً، حدث خطأ أثناء التحميل. تأكد من الرابط.", cid, msg.message_id)

# تشغيل البوت
print("البوت شغال...")
while True:
    try:
        bot.polling(none_stop=True)
    except:
        time.sleep(5)
