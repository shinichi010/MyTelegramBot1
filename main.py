import telebot
import requests
import time
import random

TOKEN = '8159446452:AAGrkJbtEFoKgXab19l7tX36SDTowRvPxB4'
bot = telebot.TeleBot(TOKEN)
OWNER_ID = 5489814144 # ايدي حسابك

groups_data = {}

def get_data(cid):
    if cid not in groups_data:
        groups_data[cid] = {'locked': False, 'admins': [], 'vips': [], 'warns': {}, 'anti_link': True}
    return groups_data[cid]

def is_admin(m):
    try:
        if m.from_user.id == OWNER_ID: return True
        status = bot.get_chat_member(m.chat.id, m.from_user.id).status
        if status in ['creator', 'administrator'] or m.from_user.id in get_data(m.chat.id)['admins']:
            return True
    except: return False

# حذف رسائل النظام
@bot.message_handler(content_types=['new_chat_members', 'left_chat_member'])
def clean_system(m):
    try: bot.delete_message(m.chat.id, m.message_id)
    except: pass

@bot.message_handler(func=lambda m: True)
def handle_all(m):
    text = m.text
    if not text: return
    cid = m.chat.id
    uid = m.from_user.id
    data = get_data(cid)

    # 1. أول خطوة: حماية الشات المقفول (حتى لا يرد على الكلمات)
    if data['locked'] and not is_admin(m) and uid not in data['vips']:
        try:
            bot.delete_message(cid, m.message_id)
            return # توقف هنا ولا تعالج بقية الأوامر
        except: pass

    # 2. منع الروابط للأعضاء
    if data['anti_link'] and ("http" in text or "t.me" in text) and not is_admin(m):
        try:
            bot.delete_message(cid, m.message_id)
            return
        except: pass

    # 3. الردود العشوائية لـ "وعد"
    if text == "وعد":
        waad_responses = ["عيون وعد", "مالي خلقك", "توكل لان ضايجة", "ها شتريد؟", "كول اسمعك"]
        bot.reply_to(m, random.choice(waad_responses))

    # 4. ردود سريعة
    if text == "السلام عليكم": bot.reply_to(m, "وعليكم السلام")
    elif text == "شلونك": bot.reply_to(m, "بخير")
    elif text == "ايدي":
        status = "ادمن" if is_admin(m) else "عضو"
        bot.reply_to(m, f"اسمه: {m.from_user.first_name}\nايديه: {uid}\nرتبته: {status}")

    # 5. نظام الرتب والتحذير (بالرد)
    if m.reply_to_message:
        target_id = m.reply_to_message.from_user.id
        target_name = m.reply_to_message.from_user.first_name
        
        if text == "تحذير" and is_admin(m):
            data['warns'][target_id] = data['warns'].get(target_id, 0) + 1
            count = data['warns'][target_id]
            if count >= 3:
                bot.kick_chat_member(cid, target_id)
                bot.reply_to(m, f"تم طرد {target_name} لتجاوزه 3 تحذيرات")
                data['warns'][target_id] = 0
            else:
                bot.reply_to(m, f"تم تحذير {target_name}. عدد تحذيراته: {count}/3")
        
        elif text == "رفع مدير" and is_admin(m):
            if target_id not in data['admins']: data['admins'].append(target_id)
            bot.reply_to(m, "تم الرفع مدير")
        elif text == "تنزيل مدير" and is_admin(m):
            if target_id in data['admins']: data['admins'].remove(target_id)
            bot.reply_to(m, "تم التنزيل")

    # 6. المسح والقفل
    if text.startswith("مسح ") and is_admin(m):
        try:
            num = int(text.split()[1])
            for i in range(num + 1):
                try: bot.delete_message(cid, m.message_id - i)
                except: pass
        except: pass

    if text == "قفل الشات" and is_admin(m):
        data['locked'] = True
        bot.reply_to(m, "تم القفل")
    elif text == "فتح الشات" and is_admin(m):
        data['locked'] = False
        bot.reply_to(m, "تم الفتح")

    # 7. تحميل تيك توك (تحديث الـ API)
    if "tiktok.com" in text:
        try:
            wait = bot.reply_to(m, "جاري جلب الفيديو... ⏳")
            # API جديد أكثر استقراراً
            res = requests.get(f"https://api.tiklydown.eu.org/api/download?url={text}").json()
            bot.send_video(cid, res['video']['noWatermark'], reply_to_message_id=m.message_id)
            bot.delete_message(cid, wait.message_id)
        except:
            bot.edit_message_text("حدث خطأ، تأكد من الرابط", cid, wait.message_id)

bot.infinity_polling()
