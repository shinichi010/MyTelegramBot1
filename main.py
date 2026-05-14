import telebot
import requests
import time
import random
from telebot import types

TOKEN = '8159446452:AAGrkJbtEFoKgXab19l7tX36SDTowRvPxB4'
bot = telebot.TeleBot(TOKEN)
OWNER_ID = 5489814144 # ايديك

# مخزن البيانات
groups_data = {}

def get_data(cid):
    if cid not in groups_data:
        groups_data[cid] = {'locked': False, 'admins': [], 'vips': [], 'warns': {}, 'muted': []}
    return groups_data[cid]

def is_admin(m):
    try:
        if m.from_user.id == OWNER_ID: return True
        status = bot.get_chat_member(m.chat.id, m.from_user.id).status
        if status in ['creator', 'administrator'] or m.from_user.id in get_data(m.chat.id)['admins']:
            return True
    except: return False

# 1. حذف رسائل الدخول والخروج (تنظيف الشات)
@bot.message_handler(content_types=['new_chat_members', 'left_chat_member'])
def clean_logs(m):
    try: bot.delete_message(m.chat.id, m.message_id)
    except: pass

@bot.message_handler(func=lambda m: True)
def handle_all(m):
    text = m.text
    if not text: return
    cid = m.chat.id
    uid = m.from_user.id
    data = get_data(cid)

    # --- حماية الشات المقفول والكتم ---
    if (data['locked'] or uid in data['muted']) and not is_admin(m) and uid not in data['vips']:
        try:
            bot.delete_message(cid, m.message_id)
            return
        except: pass

    # --- ردود "وعد" العشوائية ---
    if text == "وعد":
        responses = ["عيون وعد", "مالي خلقك", "توكل لان ضايجة", "ها شتريد", "كول اسمعك", "وعد مشغولة هسه"]
        bot.reply_to(m, random.choice(responses))

    # --- ميزة التحميل (تيك توك - فيديو وصور) ---
    if "vt.tiktok.com" in text:
        wait = bot.reply_to(m, "انتظر جاري جلب الميديا... ⏳")
        try:
            res = requests.get(f"https://api.tiklydown.eu.org/api/download?url={text}").json()
            # إذا كان ألبوم صور
            if 'images' in res and res['images']:
                for img in res['images']:
                    bot.send_photo(cid, img['url'], reply_to_message_id=m.message_id)
            # إذا كان فيديو
            else:
                video_url = res['video']['noWatermark']
                bot.send_video(cid, video_url, reply_to_message_id=m.message_id)
            bot.delete_message(cid, wait.message_id)
        except:
            bot.edit_message_text("فشل التحميل تأكد من الرابط", cid, wait.message_id)

    # --- أوامر الرتب والإدارة (بالرد) ---
    if m.reply_to_message:
        target_id = m.reply_to_message.from_user.id
        target_name = m.reply_to_message.from_user.first_name
        
        if text == "رفع مدير" and is_admin(m):
            if target_id not in data['admins']: data['admins'].append(target_id)
            bot.reply_to(m, f"تم رفع {target_name} مدير")
        
        elif text == "تنزيل مدير" and is_admin(m):
            if target_id in data['admins']: data['admins'].remove(target_id)
            bot.reply_to(m, f"تم تنزيل {target_name}")

        elif text == "كتم" and is_admin(m):
            if target_id not in data['muted']: data['muted'].append(target_id)
            bot.reply_to(m, f"تم كتم {target_name}")

        elif text == "الغاء الكتم" and is_admin(m):
            if target_id in data['muted']: data['muted'].remove(target_id)
            bot.reply_to(m, f"تم الغاء كتم {target_name}")

        elif text == "طرد" and is_admin(m):
            try:
                bot.kick_chat_member(cid, target_id)
                bot.reply_to(m, f"تم طرد {target_name}")
            except: bot.reply_to(m, "ما اكدر اطرده لازم اكون ادمن")

    # --- أوامر عامة ---
    if text == "ايدي":
        try:
            photos = bot.get_user_profile_photos(uid)
            if photos.total_count > 0:
                bot.send_photo(cid, photos.photos[0][-1].file_id, caption=f"اسمه: {m.from_user.first_name}\nايديه: `{uid}`")
            else:
                bot.reply_to(m, f"اسمه: {m.from_user.first_name}\nايديه: `{uid}`")
        except: pass

    if text.startswith("مسح ") and is_admin(m):
        try:
            num = int(text.split()[1])
            for i in range(num + 1):
                try: bot.delete_message(cid, m.message_id - i)
                except: pass
        except: pass

    if text == "قفل الشات" and is_admin(m):
        data['locked'] = True
        bot.reply_to(m, "قفلته")
    
    elif text == "فتح الشات" and is_admin(m):
        data['locked'] = False
        bot.reply_to(m, "فتحته")

    # --- تسلية ---
    if text == "لو خيروك":
        options = ["تاكل صرصر لو تشرب نفط؟", "تنام بالشارع لو تسبح بمي بارد بالشتا؟", "تترك التلفون اسبوع لو تترك الاكل يوم؟"]
        bot.reply_to(m, random.choice(options))

bot.infinity_polling()
