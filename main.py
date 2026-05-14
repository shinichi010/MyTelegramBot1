import telebot
import re
from yt_dlp import YoutubeDLquests
import time
import random
import re
from telebot import types

TOKEN = '8159446452:AAGrkJbtEFoKgXab19l7tX36SDTowRvPxB4'
bot = telebot.TeleBot(TOKEN, parse_mode='HTML')
OWNER_ID = 5489814144

# ---------------- البيانات ----------------
groups_data = {}
user_points = {}
spam_tracker = {}

# ---------------- إنشاء بيانات الكروب ----------------
def get_data(cid):
    if cid not in groups_data:
        groups_data[cid] = {
            'locked': False,
            'admins': [],
            'mods': [],
            'developers': [],
            'vips': [],
            'muted': [],
            'warns': {},
            'points_enabled': True,
            'welcome_enabled': True,
            'links_protection': False,
            'spam_enabled': True,
            'spam_limit': 5,
            'blocked_words': []
        }
    return groups_data[cid]

# ---------------- نقاط ----------------
def get_user_points(cid, uid):
    if cid not in user_points:
        user_points[cid] = {}

    if uid not in user_points[cid]:
        user_points[cid][uid] = {
            'points': 0,
            'level': 1
        }

    return user_points[cid][uid]

# ---------------- صلاحيات ----------------
def is_owner(uid):
    return uid == OWNER_ID


def is_dev(cid, uid):
    data = get_data(cid)
    return uid in data['developers'] or is_owner(uid)


def is_admin_message(m):
    try:
        cid = m.chat.id
        uid = m.from_user.id
        data = get_data(cid)

        if uid == OWNER_ID:
            return True

        member = bot.get_chat_member(cid, uid)

        if member.status in ['creator', 'administrator']:
            return True

        if uid in data['admins']:
            return True

        if uid in data['mods']:
            return True

        return False
    except:
        return False


# ---------------- حذف دخول وخروج ----------------
@bot.message_handler(content_types=['new_chat_members'])
def welcome(m):
    data = get_data(m.chat.id)

    try:
        bot.delete_message(m.chat.id, m.message_id)
    except:
        pass

    if not data['welcome_enabled']:
        return

    for user in m.new_chat_members:
        text = f'''
🎉 أهلاً بيك <a href="tg://user?id={user.id}">{user.first_name}</a>
نورت الكروب ❤️
        '''

        try:
            photos = bot.get_user_profile_photos(user.id)
            if photos.total_count > 0:
                bot.send_photo(
                    m.chat.id,
                    photos.photos[0][-1].file_id,
                    caption=text
                )
            else:
                bot.send_message(m.chat.id, text)
        except:
            bot.send_message(m.chat.id, text)


@bot.message_handler(content_types=['left_chat_member'])
def left_clean(m):
    try:
        bot.delete_message(m.chat.id, m.message_id)
    except:
        pass


# ---------------- سبام ----------------
def check_spam(cid, uid):
    data = get_data(cid)

    if not data['spam_enabled']:
        return False

    current = time.time()

    if uid not in spam_tracker:
        spam_tracker[uid] = []

    spam_tracker[uid] = [t for t in spam_tracker[uid] if current - t < 5]

    spam_tracker[uid].append(current)

    if len(spam_tracker[uid]) > data['spam_limit']:
        return True

    return False


# ---------------- يوتيوب صوت ----------------
def download_audio(url):
    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': '%(title)s.%(ext)s',
        'quiet': True,
        'noplaylist': True
    }

    with YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        filename = ydl.prepare_filename(info)
        return filename


# ---------------- تيكتوك ----------------
def download_tiktok(url):
    apis = [
        f'https://www.tikwm.com/api/?url={url}',
        f'https://api.tiklydown.eu.org/api/download?url={url}',
        f'https://ttdownloader.com/'
    ]

    for api in apis:
        try:
            res = requests.get(api, timeout=10).json()

            if 'data' in res:
                if 'play' in res['data']:
                    return res['data']['play']

            if 'video' in res:
                return res['video']['noWatermark']

        except:
            continue

    return None


# ---------------- الردود ----------------
waad_replies = [
    'ها شتريد 😒',
    'كول بسرعة 🙄',
    'وعد موجودة 😌',
    'لتزعجني هسه 😂',
    'سمعك 👀'
]


# ---------------- معالجة الرسائل ----------------
@bot.message_handler(func=lambda m: True)
def handle_all(m):
    text = m.text

    if not text:
        return

    cid = m.chat.id
    uid = m.from_user.id

    data = get_data(cid)

    # ---------------- نقاط ----------------
    if data['points_enabled']:
        user = get_user_points(cid, uid)
        user['points'] += 1

        new_level = user['points'] // 100 + 1

        if new_level > user['level']:
            user['level'] = new_level

    # ---------------- سبام ----------------
    if check_spam(cid, uid) and not is_admin_message(m):
        if uid not in data['muted']:
            data['muted'].append(uid)

            bot.reply_to(
                m,
                '🚫 تم كتمك مؤقتاً بسبب السبام'
            )

        return

    # ---------------- القفل والكتم ----------------
    if (data['locked'] or uid in data['muted']) and not is_admin_message(m) and uid not in data['vips']:
        try:
            bot.delete_message(cid, m.message_id)
            return
        except:
            pass

    # ---------------- منع روابط ----------------
    if data['links_protection']:
        if 'http' in text or 't.me' in text or '.com' in text:
            if not is_admin_message(m):
                try:
                    bot.delete_message(cid, m.message_id)
                    return
                except:
                    pass

    # ---------------- كلمات ممنوعة ----------------
    for word in data['blocked_words']:
        if word.lower() in text.lower():
            if not is_admin_message(m):
                try:
                    bot.delete_message(cid, m.message_id)
                    return
                except:
                    pass

    # ---------------- ردود ----------------
    if text == 'وعد':
        bot.reply_to(m, random.choice(waad_replies))

    # ---------------- تحميل يوتيوب كصوت ----------------
    if 'youtube.com' in text or 'youtu.be' in text:
        wait = bot.reply_to(m, '🎧 جاري تحميل الصوت...')

        try:
            audio_file = download_audio(text)

            with open(audio_file, 'rb') as audio:
                bot.send_audio(
                    cid,
                    audio,
                    reply_to_message_id=m.message_id
                )

            bot.delete_message(cid, wait.message_id)

        except:
            bot.edit_message_text(
                '❌ فشل تحميل الصوت',
                cid,
                wait.message_id
            )

    # ---------------- تحميل تيكتوك ----------------
    if 'tiktok.com' in text:
        wait = bot.reply_to(m, '⏳ جاري التحميل...')

        try:
            video = download_tiktok(text)

            if video:
                bot.send_video(cid, video, reply_to_message_id=m.message_id)
                bot.delete_message(cid, wait.message_id)
            else:
                bot.edit_message_text(
                    '❌ فشل تحميل الفيديو',
                    cid,
                    wait.message_id
                )

        except:
            bot.edit_message_text(
                '❌ صار خطأ أثناء التحميل',
                cid,
                wait.message_id
            )

    # ---------------- أوامر بالرد ----------------
    if m.reply_to_message:
        target_id = m.reply_to_message.from_user.id
        target_name = m.reply_to_message.from_user.first_name

        # رفع مدير
        if text == 'رفع مدير' and is_admin_message(m):
            if target_id not in data['admins']:
                data['admins'].append(target_id)

            bot.reply_to(m, f'✅ تم رفع {target_name} مدير')

        # تنزيل مدير
        elif text == 'تنزيل مدير' and is_admin_message(m):
            if target_id in data['admins']:
                data['admins'].remove(target_id)

            bot.reply_to(m, f'✅ تم تنزيل {target_name}')

        # رفع ادمن
        elif text == 'رفع ادمن' and is_admin_message(m):
            if target_id not in data['mods']:
                data['mods'].append(target_id)

            bot.reply_to(m, f'✅ تم رفع {target_name} ادمن')

        # تنزيل ادمن
        elif text == 'تنزيل ادمن' and is_admin_message(m):
            if target_id in data['mods']:
                data['mods'].remove(target_id)

            bot.reply_to(m, f'✅ تم تنزيل الادمن')

        # VIP
        elif text == 'رفع vip' and is_admin_message(m):
            if target_id not in data['vips']:
                data['vips'].append(target_id)

            bot.reply_to(m, f'⭐ صار VIP')

        elif text == 'تنزيل vip' and is_admin_message(m):
            if target_id in data['vips']:
                data['vips'].remove(target_id)

            bot.reply_to(m, '❌ انشال من VIP')

        # كتم
        elif text == 'كتم' and is_admin_message(m):
            if target_id not in data['muted']:
                data['muted'].append(target_id)

            bot.reply_to(m, '🔇 تم الكتم')

        # الغاء كتم
        elif text == 'الغاء الكتم' and is_admin_message(m):
            if target_id in data['muted']:
                data['muted'].remove(target_id)

            bot.reply_to(m, '🔊 تم الغاء الكتم')

        # طرد
        elif text == 'طرد' and is_admin_message(m):
            try:
                bot.kick_chat_member(cid, target_id)
                bot.reply_to(m, '✅ تم الطرد')
            except:
                bot.reply_to(m, '❌ ما اكدر اطرده')

    # ---------------- أوامر عامة ----------------

    if text == 'الاوامر' and is_admin_message(m):
        commands = '''
📌 أوامر الإدارة
• رفع مدير
• تنزيل مدير
• رفع ادمن
• تنزيل ادمن
• رفع vip
• تنزيل vip
• كتم
• الغاء الكتم
• طرد
• مسح + عدد

🔒 أوامر الحماية
• قفل الشات
• فتح الشات
• تفعيل الروابط
• تعطيل الروابط
• تفعيل الترحيب
• تعطيل الترحيب
• تشغيل النقاط
• تعطيل النقاط
• تشغيل السبام
• تعطيل السبام
• حد السبام + رقم

⭐ أوامر النقاط
• نقاطي
• لفلي
• توب
• اضافة نقاط
• تنزيل نقاط

🎮 أوامر التسلية
• لو خيروك

📥 التحميل
• فقط ارسل رابط تيكتوك
        '''

        bot.reply_to(m, commands)

    # ---------------- النقاط ----------------
    if text == 'نقاطي':
        user = get_user_points(cid, uid)

        bot.reply_to(
            m,
            f'''⭐ نقاطك: {user['points']}'''
        )

    if text == 'لفلي':
        user = get_user_points(cid, uid)

        bot.reply_to(
            m,
            f'''
🏆 لفلك: {user['level']}
⭐ نقاطك: {user['points']}
            '''
        )

    if text == 'توب':
        if cid not in user_points:
            return

        users = sorted(
            user_points[cid].items(),
            key=lambda x: x[1]['points'],
            reverse=True
        )[:10]

        msg = '🏆 توب 10\n\n'

        count = 1
        for u in users:
            try:
                user_info = bot.get_chat_member(cid, u[0]).user
                msg += f'{count}- {user_info.first_name} | {u[1]["points"]} نقطة\n'
                count += 1
            except:
                pass

        bot.reply_to(m, msg)

    # ---------------- تشغيل وتعطيل ----------------
    if text == 'تشغيل النقاط' and is_admin_message(m):
        data['points_enabled'] = True
        bot.reply_to(m, '✅ تم تشغيل النقاط')

    if text == 'تعطيل النقاط' and is_admin_message(m):
        data['points_enabled'] = False
        bot.reply_to(m, '❌ تم تعطيل النقاط')

    if text == 'تشغيل السبام' and is_admin_message(m):
        data['spam_enabled'] = True
        bot.reply_to(m, '✅ تم تشغيل حماية السبام')

    if text == 'تعطيل السبام' and is_admin_message(m):
        data['spam_enabled'] = False
        bot.reply_to(m, '❌ تم تعطيل حماية السبام')

    if text.startswith('حد السبام') and is_admin_message(m):
        try:
            limit = int(text.split()[2])
            data['spam_limit'] = limit

            bot.reply_to(m, f'✅ صار حد السبام {limit}')
        except:
            bot.reply_to(m, '❌ استخدم: حد السبام 5')

    # ---------------- روابط ----------------
    if text == 'تفعيل الروابط' and is_admin_message(m):
        data['links_protection'] = True
        bot.reply_to(m, '✅ تم تفعيل منع الروابط')

    if text == 'تعطيل الروابط' and is_admin_message(m):
        data['links_protection'] = False
        bot.reply_to(m, '❌ تم تعطيل منع الروابط')

    # ---------------- ترحيب ----------------
    if text == 'تفعيل الترحيب' and is_admin_message(m):
        data['welcome_enabled'] = True
        bot.reply_to(m, '✅ تم تفعيل الترحيب')

    if text == 'تعطيل الترحيب' and is_admin_message(m):
        data['welcome_enabled'] = False
        bot.reply_to(m, '❌ تم تعطيل الترحيب')

    # ---------------- كلمات ممنوعة ----------------
    if text.startswith('منع كلمة') and is_admin_message(m):
        try:
            word = text.replace('منع كلمة ', '')

            if word not in data['blocked_words']:
                data['blocked_words'].append(word)

            bot.reply_to(m, f'✅ تم منع: {word}')
        except:
            pass

    if text.startswith('حذف كلمة') and is_admin_message(m):
        try:
            word = text.replace('حذف كلمة ', '')

            if word in data['blocked_words']:
                data['blocked_words'].remove(word)

            bot.reply_to(m, '✅ تم حذف الكلمة')
        except:
            pass

    if text == 'الكلمات الممنوعة':
        words = data['blocked_words']

        if not words:
            bot.reply_to(m, 'ماكو كلمات ممنوعة')
        else:
            bot.reply_to(m, '\n'.join(words))

    # ---------------- قفل ----------------
    if text == 'قفل الشات' and is_admin_message(m):
        data['locked'] = True
        bot.reply_to(m, '🔒 تم قفل الشات')

    if text == 'فتح الشات' and is_admin_message(m):
        data['locked'] = False
        bot.reply_to(m, '🔓 تم فتح الشات')

    # ---------------- مسح ----------------
    if text.startswith('مسح ') and is_admin_message(m):
        try:
            num = int(text.split()[1])

            for i in range(num + 1):
                try:
                    bot.delete_message(cid, m.message_id - i)
                except:
                    pass
        except:
            pass

    # ---------------- ايدي ----------------
    if text == 'ايدي':
        try:
            photos = bot.get_user_profile_photos(uid)

            caption = f'''
👤 الاسم: {m.from_user.first_name}
🆔 الايدي: <code>{uid}</code>
            '''

            if photos.total_count > 0:
                bot.send_photo(
                    cid,
                    photos.photos[0][-1].file_id,
                    caption=caption
                )
            else:
                bot.reply_to(m, caption)
        except:
            pass

    # ---------------- تسلية ----------------
    if text == 'لو خيروك':
        choices = [
            'تاكل صرصر لو تشرب نفط؟ 😂',
            'تترك التلفون شهر لو الاكل يومين؟ 😭',
            'تنام بالشارع لو تبقى بدون نت؟ 😵'
        ]

        bot.reply_to(m, random.choice(choices))


# ---------------- تشغيل ----------------
print('Bot Is Running...')
bot.infinity_polling(skip_pending=True)

# ---------------- تحميل يوتيوب صوت ----------------
from yt_dlp import YoutubeDL


def download_audio(url):
    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': '%(id)s.%(ext)s',
        'quiet': True,
        'noplaylist': True
    }

    with YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        filename = ydl.prepare_filename(info)
        return filename

# ---------------- يوتيوب صوت ----------------
if 'youtube.com' in text or 'youtu.be' in text:
    wait = bot.reply_to(m, '🎧 جاري تحميل الصوت...')

    try:
        audio = download_audio(text)

        with open(audio, 'rb') as a:
            bot.send_audio(cid, a)

        bot.delete_message(cid, wait.message_id)

    except:
        bot.edit_message_text(
            '❌ فشل تحميل الصوت',
            cid,
            wait.message_id
        )
