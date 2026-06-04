import logging
import os
import asyncio
import random
import re
import requests
import tempfile
import shutil
import subprocess
import firebase_admin
from firebase_admin import credentials, db
from telegram import Update, ChatPermissions, InlineKeyboardMarkup, InlineKeyboardButton, InputMediaPhoto
from telegram.ext import (
    Application, MessageHandler, CallbackQueryHandler, CommandHandler,
    filters, ContextTypes,
)
from yt_dlp import YoutubeDL
import imageio_ffmpeg

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════
# 1. القوائم والمحتوى الثابت
# ═══════════════════════════════════════════════════════════════════
WA3ED_LIST = [
    "وعد: تعزم أول شخص يرد عليك على شاورما 🌯",
    "وعد: تخلي صورتك بالبروفايل صورة طفل لمدة يوم 👶",
    "وعد: تكتب بالكروب 'أنا أحبكم كلكم' وتثبتها دقيقة ❤️",
    "وعد: تدز بصمة صوتية تغني بيها للكروب 🎤",
    "وعد: تعترف بأكثر موقف محرج صار وياك 🫣",
    "وعد: تغير اسمك للكروب على اسم شخص تختاره لمدة ساعة 😂",
]

KHAYROK_LIST = [
    "لو خيروك: تسافر عبر الزمن للمستقبل لو للماضي؟ ⏳",
    "لو خيروك: تاكل بيتزا طول عمرك لو بركر طول عمرك؟ 🍕🍔",
    "لو خيروك: تصير غني بس بدون أصدقاء، لو فقير وعندك أصدقاء يحبوك؟ 💰",
    "لو خيروك: تكدر تقرأ أفكار الناس لو تكدر تطير؟ 🦅",
    "لو خيروك: ما تنام أبد لو ما تأكل أبد؟ 😴🍽️",
    "لو خيروك: تعرف تاريخ وفاتك لو مو تعرف؟ 💀",
]

JOKES_LIST = [
    "شلون النملة تعدّ حياتها؟ — تحسب سنين! 🐜😂",
    "شو يقول الصفر للرقم 8؟ — حزامك ظاهر! 😄",
    "ليش الكمبيوتر بارد؟ — لأن عنده ويندوز! 🪟",
    "شو تقول السمكة لما اصطدمت بالحائط؟ — دام! 🐟",
    "ليش العلماء لا يثقون بالذرة؟ — لأنها تشكّل كلشي! ⚛️",
]

LANG_TO_FLAG = {
    'ar': '🇸🇦 عربي', 'en': '🇬🇧 انجليزي', 'tr': '🇹🇷 تركي',
    'fa': '🇮🇷 فارسي', 'ru': '🇷🇺 روسي', 'fr': '🇫🇷 فرنسي',
    'de': '🇩🇪 ألماني', 'es': '🇪🇸 اسباني', 'it': '🇮🇹 ايطالي',
    'hi': '🇮🇳 هندي', 'zh': '🇨🇳 صيني', 'ja': '🇯🇵 ياباني',
    'ko': '🇰🇷 كوري', 'pt': '🇧🇷 برتغالي', 'nl': '🇳🇱 هولندي',
    'pl': '🇵🇱 بولندي', 'uk': '🇺🇦 أوكراني', 'uz': '🇺🇿 أوزبكي',
    'kk': '🇰🇿 كازاخي', 'ky': '🇰🇬 قرغيزي',
}

TEXT_MAIN_MENU = "📋 <b>أهلاً بك في لوحة أوامر البوت المتكاملة</b>\n\nالرجاء اختيار القسم الذي تود تصفحه من الأزرار بالأسفل 👇"

TEXT_ADMIN_CMDS = (
    "👑 <b>أوامر المالك والمدراء:</b>\n"
    "• <code>رفع مالك | مدير | مميز</code> / <code>تنزيل رتبة</code>\n"
    "• <code>طرد | حظر | فك حظر</code>\n"
    "• <code>تثبيت | الغاء تثبيت</code>\n"
    "• <code>كتم | الغاء كتم</code>\n"
    "• <code>قفل الشات | فتح الشات</code>\n"
    "• <code>تحذير | الغاء تحذير | تحذيراتي</code>\n"
    "• <code>منع كلمة X | حذف كلمة X | الكلمات</code>\n"
    "• <code>منع ملصقات | منع قيف | منع مقاطع | منع صور</code>\n"
    "• <code>تفعيل ملصقات | تفعيل قيف | تفعيل مقاطع | تفعيل صور</code>\n"
    "• <code>اضافة رد X | Y</code> — رد تلقائي عند كتابة X\n"
    "• <code>حذف رد X</code> / <code>قائمة الردود</code>\n"
    "• <code>الترحيب تشغيل | الترحيب ايقاف</code>\n"
    "• <code>تعديل تشغيل | تعديل ايقاف</code>\n"
    "• <code>تشغيل سيك | ايقاف سيك</code> — الذكاء الاصطناعي\n"
    "• <code>مسح X</code> — حذف X رسالة (رد على الأولى)"
)

TEXT_FUN_CMDS = (
    "🎮 <b>أوامر التسلية والخدمات العامة:</b>\n"
    "• <code>همسة</code> — همسة سرية (بالرد)\n"
    "• <code>ايدي</code> — معلومات المستخدم\n"
    "• <code>افتار</code> — صورة البروفايل\n"
    "• <code>زواج | طلاق | شريكي</code>\n"
    "• <code>نسبة الحب</code> — بالرد على شخص\n"
    "• <code>تحويل</code> — رد على مقطع لتحويله لصوت\n"
    "• <code>لو خيروك | وعد | نكتة</code>\n"
    "• <code>اكس او</code> — لعبة إكس أو 🎮"
)

TEXT_DOWNLOAD_CMDS = (
    "📥 <b>قسم التحميل — المواقع المدعومة:</b>\n\n"
    "🎬 <b>يوتيوب</b> — اختيار الجودة (144p → 4K) + صوت MP3\n"
    "🐦 <b>تويتر/X</b> — اختيار الجودة\n"
    "🎵 <b>تيك توك</b> — فيديو بدون علامة مائية + ألبوم صور\n"
    "🇨🇳 <b>دوين (Douyin)</b> — تيك توك الصيني\n"
    "📘 <b>فيس بوك</b> — تحميل مقاطع الفيس بوك\n"
    "📸 <b>انستغرام</b> — فيديو وصور (ريلز، بوستات)\n\n"
    "💡 فقط أرسل الرابط مباشرة!"
)


def get_main_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🛡️ أوامر الإدارة", callback_data="cmd_admin"),
         InlineKeyboardButton("🎮 التسلية", callback_data="cmd_fun")],
        [InlineKeyboardButton("📥 قسم التحميل", callback_data="cmd_dl")]
    ])


def get_back_keyboard():
    return InlineKeyboardMarkup([[InlineKeyboardButton("🔙 العودة للقائمة", callback_data="cmd_main")]])


# ═══════════════════════════════════════════════════════════════════
# 2. قاعدة البيانات (Firebase)
# ═══════════════════════════════════════════════════════════════════
try:
    cred = credentials.Certificate('firebase.json')
    firebase_url = os.environ.get('DATABASE_URL', 'https://mytelegrambotdb-default-rtdb.europe-west1.firebasedatabase.app/')
    firebase_admin.initialize_app(cred, {'DATABASE_URL': firebase_url})
    logger.info("✅ Firebase connected")
except Exception as e:
    logger.error(f"❌ Firebase error: {e}")


def db_get(path, default):
    try:
        val = db.reference(path).get()
        return val if val is not None else default
    except:
        return default


def db_set(path, data):
    try:
        db.reference(path).set(data)
    except Exception as e:
        logger.error(f"DB set error: {e}")


def get_settings(chat_id):
    return db_get(f"settings/{str(chat_id)}", {
        "welcome": True, "banned_words": [], "locked": False,
        "edit_notify": True, "ai_mode": False,
        "ban_stickers": False, "ban_gifs": False,
        "ban_videos": False, "ban_photos": False
    })


def save_settings(chat_id, settings):
    db_set(f"settings/{str(chat_id)}", settings)


# ═══════════════════════════════════════════════════════════════════
# 3. الصلاحيات
# ═══════════════════════════════════════════════════════════════════
ROLE_OWNER = "owner"
ROLE_MANAGER = "manager"
ROLE_VIP = "vip"
ROLE_RANK = {ROLE_OWNER: 3, ROLE_MANAGER: 2, ROLE_VIP: 1}
ROLE_LABEL = {ROLE_OWNER: "👑 مالك", ROLE_MANAGER: "🛡 مدير", ROLE_VIP: "⭐ مميز"}


def get_role(chat_id, user_id):
    return db_get(f"roles/{chat_id}/{user_id}", None)


def set_role(chat_id, user_id, role):
    db_set(f"roles/{chat_id}/{user_id}", role)


def remove_role(chat_id, user_id):
    db_set(f"roles/{chat_id}/{user_id}", None)


async def is_tg_owner(update, context):
    try:
        admins = await context.bot.get_chat_administrators(update.effective_chat.id)
        return any(a.user.id == update.effective_user.id and a.status == "creator" for a in admins)
    except:
        return False


async def is_privileged(update, context, min_role=ROLE_OWNER):
    role = get_role(update.effective_chat.id, update.effective_user.id)
    return (bool(role and ROLE_RANK.get(role, 0) >= ROLE_RANK.get(min_role, 99))
            or await is_tg_owner(update, context))


async def get_target_user(update, context):
    msg = update.message
    if msg.reply_to_message:
        return msg.reply_to_message.from_user
    if msg.entities:
        for ent in msg.entities:
            if ent.type == "text_mention" and ent.user:
                return ent.user
    return None


# ═══════════════════════════════════════════════════════════════════
# 4. الذكاء الاصطناعي DeepSeek (async-safe)
# ═══════════════════════════════════════════════════════════════════
async def ask_deepseek(prompt: str) -> str:
    api_key = "sk-f5149facf1164e6db0af5fd276c8fbfe"
    url = "https://api.deepseek.com/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    data = {
        "model": "deepseek-chat",
        "messages": [
            {"role": "system", "content": (
                "أنت مساعد ذكي اسمك سيك، تتحدث باللهجة العراقية أحياناً. "
                "كن ودوداً وخفيف الظل ومفيداً. ردودك مختصرة وواضحة."
            )},
            {"role": "user", "content": prompt}
        ],
        "max_tokens": 1000
    }

    def _call():
        try:
            res = requests.post(url, headers=headers, json=data, timeout=25)
            res.raise_for_status()
            return res.json()["choices"][0]["message"]["content"]
        except requests.exceptions.Timeout:
            return "اعذرني، السيرفر ما رد. حاول ثاني 😅"
        except Exception as e:
            logger.error(f"DeepSeek error: {e}")
            return "صار خطأ بالذكاء الاصطناعي، حاول لاحقاً 🙁"

    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _call)


# ═══════════════════════════════════════════════════════════════════
# 5. نظام التحميل
# ═══════════════════════════════════════════════════════════════════
active_downloads = {}


def progress_hook(d, msg_id):
    if d['status'] == 'downloading':
        percent = re.sub(r'\x1b\[[0-9;]*m', '', d.get('_percent_str', '0%').strip())
        active_downloads[msg_id] = percent


async def update_progress(context, chat_id, msg_id, status_msg_id, is_photo=False):
    last = ""
    while msg_id in active_downloads:
        current = active_downloads.get(msg_id, "")
        if current and current != last:
            try:
                txt = f"⏳ جاري التحميل: {current}"
                if is_photo:
                    await context.bot.edit_message_caption(chat_id=chat_id, message_id=status_msg_id, caption=txt)
                else:
                    await context.bot.edit_message_text(txt, chat_id=chat_id, message_id=status_msg_id)
                last = current
            except:
                pass
        await asyncio.sleep(2.5)


def get_available_qualities(url):
    """جلب الجودات المتاحة للفيديو"""
    try:
        opts = {
            'quiet': True, 'noplaylist': True, 'nocheckcertificate': True,
            'http_headers': {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0'}
        }
        with YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
            heights = set()
            for f in info.get('formats', []):
                h = f.get('height')
                if h and f.get('vcodec') != 'none':
                    heights.add(h)
            return sorted(heights, reverse=True), info
    except Exception as e:
        logger.error(f"Quality fetch error: {e}")
        return [], None


async def download_media(url, media_type, quality, msg_id, chat_id, context, status_msg_id, is_photo=False):
    tmp = tempfile.mkdtemp()
    ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
    ydl_opts = {
        'outtmpl': os.path.join(tmp, '%(title)s.%(ext)s'),
        'quiet': True,
        'noplaylist': True,
        'progress_hooks': [lambda d: progress_hook(d, msg_id)],
        'nocheckcertificate': True,
        'geo_bypass': True,
        'extractor_retries': 3,
        'ffmpeg_location': ffmpeg_exe,
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36'
        },
    }
    if os.path.exists('cookies.txt'):
        ydl_opts['cookiefile'] = 'cookies.txt'

    if media_type == "audio":
        ydl_opts['format'] = 'bestaudio/best'
        ydl_opts['postprocessors'] = [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192'
        }]
    else:
        h = int(quality) if quality and quality.isdigit() else 720
        ydl_opts['format'] = (
            f'bestvideo[height<={h}][ext=mp4]+bestaudio[ext=m4a]/'
            f'bestvideo[height<={h}]+bestaudio/best[height<={h}]/best'
        )
        ydl_opts['merge_output_format'] = 'mp4'

    active_downloads[msg_id] = "0%"
    progress_task = asyncio.create_task(
        update_progress(context, chat_id, msg_id, status_msg_id, is_photo)
    )

    def run():
        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            for f in os.listdir(tmp):
                if f.endswith(('.mp3', '.mp4', '.m4a', '.webm', '.mkv')):
                    return os.path.join(tmp, f), info.get('title', 'media')
        return None, None

    loop = asyncio.get_running_loop()
    try:
        path, title = await loop.run_in_executor(None, run)
        active_downloads.pop(msg_id, None)
        progress_task.cancel()
        return path, title, tmp
    except Exception as e:
        logger.error(f"Download error: {e}")
        active_downloads.pop(msg_id, None)
        progress_task.cancel()
        shutil.rmtree(tmp, ignore_errors=True)
        return None, None, None


def download_tiktok_api(url):
    """تحميل تيك توك / دوين عبر API"""
    api = f'https://www.tikwm.com/api/?url={url}&hd=1'
    try:
        res = requests.get(api, timeout=20).json()
        if res.get('code') == 0 and 'data' in res:
            d = res['data']
            author = d.get('author', {}).get('unique_id', 'مجهول')
            music = d.get('music', '')
            if isinstance(music, dict):
                music = music.get('play', '')
            if 'images' in d and d['images']:
                return {'type': 'images', 'data': d['images'], 'author': author, 'music': music}
            return {'type': 'video', 'data': d.get('hdplay') or d.get('play'), 'author': author, 'music': music}
    except Exception as e:
        logger.error(f"TikTok API error: {e}")
    return None


def build_quality_keyboard(heights, user_id, url_hash, platform_emoji="🎬"):
    """بناء أزرار الجودة"""
    standard = [2160, 1440, 1080, 720, 480, 360, 240, 144]
    available = []
    if heights:
        for q in standard:
            if any(h >= q * 0.85 for h in heights):
                available.append(q)
    if not available:
        available = [720, 480, 360]
    available = available[:6]

    rows = []
    row = []
    for q in available:
        row.append(InlineKeyboardButton(f"{platform_emoji} {q}p", callback_data=f"dl_vid{q}_{user_id}_{url_hash}"))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([InlineKeyboardButton("🎵 صوت MP3 عالي الجودة", callback_data=f"dl_audio_{user_id}_{url_hash}")])
    return InlineKeyboardMarkup(rows)


# ═══════════════════════════════════════════════════════════════════
# 6. معالجات الروابط
# ═══════════════════════════════════════════════════════════════════
async def handle_youtube_link(update, context, text, user_id):
    msg = update.message
    url_match = re.search(r'https?://\S+', text)
    if not url_match:
        return
    url = url_match.group()
    wait_msg = await msg.reply_text("🔍 جاري جلب معلومات الفيديو من يوتيوب...")

    loop = asyncio.get_running_loop()
    heights, info = await loop.run_in_executor(None, lambda: get_available_qualities(url))

    if not info:
        await wait_msg.edit_text(
            "❌ فشل جلب بيانات الرابط.\n"
            "• تأكد أن الفيديو عام وغير مقيد\n"
            "• جرب نسخ الرابط مباشرة من يوتيوب"
        )
        return

    url_hash = str(random.randint(10000, 99999))
    context.bot_data[url_hash] = url

    keyboard = build_quality_keyboard(heights, user_id, url_hash, "🎬")
    title = info.get('title', 'فيديو يوتيوب')[:60]
    duration = info.get('duration', 0)
    dur_str = f"{duration // 60}:{duration % 60:02d}" if duration else "غير معروف"
    views = info.get('view_count', 0)
    views_str = f"{views:,}" if views else "—"

    caption = (
        f"🎬 <b>{title}</b>\n"
        f"⏱ المدة: <code>{dur_str}</code>\n"
        f"👁 المشاهدات: <code>{views_str}</code>\n\n"
        f"👇 اختر الجودة:"
    )

    try:
        if info.get('thumbnail'):
            await context.bot.send_photo(msg.chat_id, info['thumbnail'],
                                         caption=caption, parse_mode="HTML", reply_markup=keyboard)
        else:
            await msg.reply_text(caption, parse_mode="HTML", reply_markup=keyboard)
        await wait_msg.delete()
    except Exception as e:
        await wait_msg.edit_text(f"❌ خطأ أثناء إرسال الأزرار: {str(e)[:100]}")


async def handle_twitter_link(update, context, text, chat_id):
    msg = update.message
    url_match = re.search(r'https?://\S+', text)
    if not url_match:
        return
    url = url_match.group()
    user_id = str(msg.from_user.id)
    wait_msg = await msg.reply_text("🔍 جاري جلب معلومات المقطع من X...")

    loop = asyncio.get_running_loop()
    heights, info = await loop.run_in_executor(None, lambda: get_available_qualities(url))

    if not info:
        # محاولة تحميل مباشر كبديل
        await wait_msg.edit_text("⏳ جاري التحميل المباشر من X...")
        filepath, title, tmp_dir = await download_media(
            url, "video", "720", msg.message_id, chat_id, context, wait_msg.message_id
        )
        if filepath and os.path.exists(filepath):
            await wait_msg.edit_text("📤 جاري الرفع...")
            with open(filepath, 'rb') as f:
                await context.bot.send_video(chat_id, f, caption="✅ تم التحميل من X 🐦")
            await wait_msg.delete()
        else:
            await wait_msg.edit_text("❌ فشل التحميل من X. قد يكون المقطع خاص أو محذوف.")
        if tmp_dir:
            shutil.rmtree(tmp_dir, ignore_errors=True)
        return

    url_hash = str(random.randint(10000, 99999))
    context.bot_data[url_hash] = url

    keyboard = build_quality_keyboard(heights, user_id, url_hash, "🐦")
    title = info.get('title', 'مقطع X')[:60]
    caption = f"🐦 <b>{title}</b>\n\n👇 اختر الجودة:"

    try:
        if info.get('thumbnail'):
            await context.bot.send_photo(msg.chat_id, info['thumbnail'],
                                         caption=caption, parse_mode="HTML", reply_markup=keyboard)
        else:
            await msg.reply_text(caption, parse_mode="HTML", reply_markup=keyboard)
        await wait_msg.delete()
    except Exception as e:
        await wait_msg.edit_text(f"❌ خطأ: {str(e)[:100]}")


async def handle_facebook_link(update, context, text, chat_id):
    msg = update.message
    url_match = re.search(r'https?://\S+', text)
    if not url_match:
        return
    url = url_match.group()
    user_id = str(msg.from_user.id)
    wait_msg = await msg.reply_text("🔍 جاري جلب معلومات الفيديو من فيس بوك...")

    loop = asyncio.get_running_loop()
    heights, info = await loop.run_in_executor(None, lambda: get_available_qualities(url))

    if not info:
        await wait_msg.edit_text(
            "❌ فشل جلب بيانات الفيس بوك.\n"
            "• تأكد أن الفيديو عام وليس خاصاً\n"
            "• جرب نسخ الرابط الكامل"
        )
        return

    url_hash = str(random.randint(10000, 99999))
    context.bot_data[url_hash] = url

    keyboard = build_quality_keyboard(heights, user_id, url_hash, "📘")
    title = info.get('title', 'فيديو فيس بوك')[:60]
    caption = f"📘 <b>{title}</b>\n\n👇 اختر الجودة:"

    try:
        if info.get('thumbnail'):
            await context.bot.send_photo(msg.chat_id, info['thumbnail'],
                                         caption=caption, parse_mode="HTML", reply_markup=keyboard)
        else:
            await msg.reply_text(caption, parse_mode="HTML", reply_markup=keyboard)
        await wait_msg.delete()
    except Exception as e:
        await wait_msg.edit_text(f"❌ خطأ: {str(e)[:100]}")


async def handle_instagram_link(update, context, text, chat_id):
    msg = update.message
    url_match = re.search(r'https?://\S+', text)
    if not url_match:
        return
    url = url_match.group()
    wait_msg = await msg.reply_text("📸 جاري تحميل المحتوى من انستغرام...")

    tmp = tempfile.mkdtemp()
    ydl_opts = {
        'outtmpl': os.path.join(tmp, '%(id)s.%(ext)s'),
        'quiet': True,
        'noplaylist': False,
        'nocheckcertificate': True,
        'ffmpeg_location': imageio_ffmpeg.get_ffmpeg_exe(),
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15'
        },
    }
    if os.path.exists('cookies.txt'):
        ydl_opts['cookiefile'] = 'cookies.txt'

    def _download():
        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            files = [os.path.join(tmp, f) for f in os.listdir(tmp)
                     if f.endswith(('.mp4', '.jpg', '.png', '.webp', '.jpeg'))]
            return files, info.get('title', 'انستغرام')

    loop = asyncio.get_running_loop()
    try:
        files, title = await loop.run_in_executor(None, _download)
        if not files:
            await wait_msg.edit_text("❌ لم يتم العثور على محتوى للتحميل.")
            return

        await wait_msg.edit_text("📤 جاري الرفع...")
        videos = [f for f in files if f.endswith('.mp4')]
        images = [f for f in files if not f.endswith('.mp4')]

        if videos:
            for v in videos[:3]:
                with open(v, 'rb') as f:
                    await context.bot.send_video(chat_id, f,
                                                 caption=f"📸 {title[:60]}", supports_streaming=True)
        if images:
            media_group = []
            handles = []
            for img in images[:10]:
                fh = open(img, 'rb')
                handles.append(fh)
                media_group.append(InputMediaPhoto(fh))
            try:
                await context.bot.send_media_group(chat_id, media_group)
            finally:
                for fh in handles:
                    fh.close()
        await wait_msg.delete()
    except Exception as e:
        logger.error(f"Instagram error: {e}")
        await wait_msg.edit_text(
            "❌ فشل التحميل من انستغرام.\n"
            "قد يتطلب تسجيل دخول أو الحساب خاص."
        )
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


async def handle_tiktok_link(update, context, text, chat_id, reply_to_id):
    url_match = re.search(r'https?://\S+', text)
    if not url_match:
        return
    url = url_match.group()
    wait_msg = await update.message.reply_text("⏳ جاري تحميل المحتوى...")

    # محاولة أولى عبر API
    data = download_tiktok_api(url)
    if data:
        caption = f"👤 <b>الحساب:</b> @{data['author']}"
        try:
            if data['type'] == 'images':
                media_items = [InputMediaPhoto(img) for img in data['data'][:10]]
                await context.bot.send_media_group(chat_id, media_items,
                                                   reply_to_message_id=reply_to_id)
                if data.get('music'):
                    await context.bot.send_audio(chat_id, data['music'],
                                                 caption=caption, parse_mode="HTML")
            else:
                await context.bot.send_video(chat_id, data['data'],
                                             caption=caption, parse_mode="HTML",
                                             reply_to_message_id=reply_to_id,
                                             supports_streaming=True)
            await wait_msg.delete()
            return
        except Exception as e:
            logger.error(f"TikTok send error: {e}")

    # محاولة بديلة عبر yt-dlp
    await wait_msg.edit_text("⏳ محاولة تحميل بديلة...")
    filepath, title, tmp_dir = await download_media(
        url, "video", "720", update.message.message_id, chat_id, context, wait_msg.message_id
    )
    if filepath and os.path.exists(filepath):
        with open(filepath, 'rb') as f:
            await context.bot.send_video(chat_id, f,
                                         caption="✅ تيك توك 🎵",
                                         reply_to_message_id=reply_to_id)
        await wait_msg.delete()
    else:
        await wait_msg.edit_text("❌ فشل التحميل. قد يكون الرابط منتهياً أو الحساب خاص.")
    if tmp_dir:
        shutil.rmtree(tmp_dir, ignore_errors=True)


# ═══════════════════════════════════════════════════════════════════
# 7. لعبة إكس أو (Tic-Tac-Toe)
# ═══════════════════════════════════════════════════════════════════
def ttt_render_board(board, game_id):
    symbols = {'': '⬜', 'X': '❌', 'O': '⭕'}
    rows = []
    for i in range(0, 9, 3):
        row = []
        for j in range(3):
            idx = i + j
            cb = f"ttt_{game_id}_{idx}" if board[idx] == '' else "ttt_noop"
            row.append(InlineKeyboardButton(symbols[board[idx]], callback_data=cb))
        rows.append(row)
    rows.append([InlineKeyboardButton("🔄 لعبة جديدة", callback_data=f"ttt_reset_{game_id}")])
    return InlineKeyboardMarkup(rows)


def check_ttt_winner(board):
    lines = [(0, 1, 2), (3, 4, 5), (6, 7, 8),
             (0, 3, 6), (1, 4, 7), (2, 5, 8),
             (0, 4, 8), (2, 4, 6)]
    for a, b, c in lines:
        if board[a] and board[a] == board[b] == board[c]:
            return board[a]
    return None


def ttt_bot_move(board):
    """ذكاء البوت: فوز > حجب > وسط > زاوية > جانب"""
    lines = [(0, 1, 2), (3, 4, 5), (6, 7, 8),
             (0, 3, 6), (1, 4, 7), (2, 5, 8),
             (0, 4, 8), (2, 4, 6)]
    for sym in ['O', 'X']:
        for a, b, c in lines:
            vals = [board[a], board[b], board[c]]
            if vals.count(sym) == 2 and vals.count('') == 1:
                return [a, b, c][vals.index('')]
    for i in [4, 0, 2, 6, 8, 1, 3, 5, 7]:
        if board[i] == '':
            return i
    return None


# ═══════════════════════════════════════════════════════════════════
# 8. الهاندلرات الأساسية
# ═══════════════════════════════════════════════════════════════════
async def start_command(update, context):
    msg = update.message
    if msg.chat.type == 'private' and msg.text.startswith('/start w_'):
        try:
            parts = msg.text.replace('/start w_', '').split('_')
            sender_id = int(parts[0])
            target_id = int(parts[1])
            chat_id = int(parts[2].replace('m', '-'))
            if msg.from_user.id != sender_id:
                return await msg.reply_text("عذراً، هذا الرابط مو إلك! ❌")
            context.user_data['whisper_target'] = target_id
            context.user_data['whisper_chat'] = chat_id
            await msg.reply_text(
                "🔒 *أرسل همستك الآن هنا بالخاص:*\n"
                "_سيتم إرسالها للكروب تلقائياً بشكل مشفر_ 🤫",
                parse_mode="Markdown"
            )
        except:
            await msg.reply_text("حدث خطأ في رابط الهمسة.")
    else:
        await msg.reply_text(
            "أهلاً وسهلاً! 🎉 أنا بوت متكامل للإدارة والتحميل والتسلية!\n\n"
            "📥 <b>أرسل روابط من:</b>\n"
            "يوتيوب • تيك توك • فيس بوك • X • انستغرام • دوين\n\n"
            "💬 <b>أو تحدث معي</b> بأي موضوع وسأرد عليك بالذكاء الاصطناعي!\n\n"
            "👥 أضفني لمجموعتك كمشرف واكتب <code>الاوامر</code>",
            parse_mode="HTML"
        )


async def handle_private_whisper(update, context):
    msg = update.message
    if not msg.text:
        return
    target_id = context.user_data.get('whisper_target')
    chat_id = context.user_data.get('whisper_chat')
    if not target_id or not chat_id:
        return

    w_id = str(random.randint(100000, 999999))
    db_set(f"whispers/{w_id}", {
        'text': msg.text,
        'sender': msg.from_user.id,
        'target': target_id
    })
    context.user_data.pop('whisper_target', None)
    context.user_data.pop('whisper_chat', None)

    markup = InlineKeyboardMarkup([[
        InlineKeyboardButton("🔒 اضغط لقراءة الهمسة", callback_data=f"show_w_{w_id}")
    ]])
    try:
        member = await context.bot.get_chat_member(chat_id, target_id)
        target_name = member.user.first_name
    except:
        target_name = "العضو المستهدف"

    await context.bot.send_message(
        chat_id,
        f"🤫 *همسة سرية جديدة!*\n"
        f"👤 من: {msg.from_user.first_name}\n"
        f"📨 إلى: {target_name}\n\n"
        f"_فقط المستهدف يقدر يقرأها_ 👇",
        reply_markup=markup, parse_mode="Markdown"
    )
    await msg.reply_text("✅ تم إرسال همستك للكروب بنجاح! 🎉")


# ═══════════════════════════════════════════════════════════════════
# 9. معالج الأزرار الكبير
# ═══════════════════════════════════════════════════════════════════
async def button_callback(update, context):
    query = update.callback_query
    data = query.data

    # ── همسة سرية ──
    if data.startswith('show_w_'):
        w = db_get(f"whispers/{data[7:]}", None)
        if w:
            if query.from_user.id in [w['target'], w['sender']]:
                await query.answer(text=f"💬 الهمسة:\n\n{w['text']}", show_alert=True)
            else:
                await query.answer(text="الهمسة مو إلك عيني! ❌👀", show_alert=True)
        else:
            await query.answer(text="هذه الهمسة قديمة أو غير موجودة.", show_alert=True)
        return

    # ── قوائم الأوامر ──
    if data.startswith("cmd_"):
        await query.answer()
        if data == "cmd_main":
            await query.edit_message_text(TEXT_MAIN_MENU, parse_mode="HTML",
                                          reply_markup=get_main_keyboard())
        elif data == "cmd_admin":
            await query.edit_message_text(TEXT_ADMIN_CMDS, parse_mode="HTML",
                                          reply_markup=get_back_keyboard())
        elif data == "cmd_fun":
            await query.edit_message_text(TEXT_FUN_CMDS, parse_mode="HTML",
                                          reply_markup=get_back_keyboard())
        elif data == "cmd_dl":
            await query.edit_message_text(TEXT_DOWNLOAD_CMDS, parse_mode="HTML",
                                          reply_markup=get_back_keyboard())
        return

    # ── أزرار التحميل ──
    if data.startswith("dl_"):
        parts = data.split('_', 3)
        if len(parts) < 4:
            return await query.answer()
        action = parts[1]
        uid = parts[2]
        url_hash = parts[3]

        if str(query.from_user.id) != uid:
            return await query.answer("هذه الأزرار لطلب شخص ثاني! 🚫", show_alert=True)

        await query.answer()
        url = context.bot_data.get(url_hash)
        is_photo = bool(query.message.photo)

        async def edit_msg(text):
            try:
                if is_photo:
                    await query.edit_message_caption(text)
                else:
                    await query.edit_message_text(text)
            except:
                pass

        if not url:
            await edit_msg("❌ الرابط منتهي الصلاحية، أعد إرساله.")
            return

        await edit_msg("⏳ جاري تحضير الملف...")

        media_type = "audio" if action == "audio" else "video"
        quality = action.replace("vid", "") if action.startswith("vid") else "720"

        filepath, title, tmp_dir = await download_media(
            url, media_type, quality,
            query.message.message_id, query.message.chat_id,
            context, query.message.message_id, is_photo=is_photo
        )

        if filepath and os.path.exists(filepath):
            await edit_msg("📤 جاري الرفع...")
            try:
                with open(filepath, 'rb') as f:
                    if media_type == "audio":
                        await context.bot.send_audio(
                            query.message.chat_id, f,
                            title=title or "audio"
                        )
                    else:
                        await context.bot.send_video(
                            query.message.chat_id, f,
                            caption=f"✅ {(title or '')[:200]}",
                            supports_streaming=True
                        )
                await query.message.delete()
            except Exception as e:
                await edit_msg(f"❌ فشل الرفع: {str(e)[:100]}")
        else:
            await edit_msg(
                "❌ فشل التحميل.\n"
                "• الفيديو قد يكون محمياً بحقوق النشر\n"
                "• جرب جودة أقل أو أعد إرسال الرابط"
            )

        if tmp_dir:
            shutil.rmtree(tmp_dir, ignore_errors=True)
        return

    # ── لعبة إكس أو ──
    if data.startswith("ttt_"):
        parts = data.split('_')

        if parts[1] == 'noop':
            return await query.answer("هذه الخلية مشغولة! ❌")

        if parts[1] == 'reset' and len(parts) >= 3:
            game_id = parts[2]
            context.bot_data[f'ttt_{game_id}'] = {
                'board': [''] * 9, 'turn': 'X',
                'players': {'X': None, 'O': None}, 'mode': 'bot'
            }
            kb = ttt_render_board([''] * 9, game_id)
            await query.answer("لعبة جديدة! 🎮")
            await query.edit_message_text(
                "🎮 <b>إكس أو — لعبة جديدة!</b>\n\nاضغط أي خلية للبدء ❌",
                parse_mode="HTML", reply_markup=kb
            )
            return

        if len(parts) < 3:
            return await query.answer()

        game_id = parts[1]
        try:
            cell = int(parts[2])
        except:
            return await query.answer()

        game = context.bot_data.get(f'ttt_{game_id}')
        if not game:
            return await query.answer("اللعبة انتهت، ابدأ لعبة جديدة! 🎮", show_alert=True)

        player_id = query.from_user.id
        # تعيين اللاعب الأول
        if game['players']['X'] is None:
            game['players']['X'] = player_id

        current_sym = game['turn']
        if game['players'].get(current_sym) != player_id:
            sym_txt = '❌' if current_sym == 'X' else '⭕'
            return await query.answer(f"مو دورك! دور {sym_txt}", show_alert=True)

        if game['board'][cell] != '':
            return await query.answer("هذه الخلية مشغولة!", show_alert=True)

        game['board'][cell] = current_sym
        winner = check_ttt_winner(game['board'])

        if winner:
            kb = ttt_render_board(game['board'], game_id)
            sym = '❌' if winner == 'X' else '⭕'
            name = query.from_user.first_name
            await query.answer(f"🏆 {sym} فاز!", show_alert=False)
            await query.edit_message_text(
                f"🎮 <b>إكس أو</b>\n\n🏆 فاز {sym} <b>{name}</b>! مبروك!",
                parse_mode="HTML", reply_markup=kb
            )
            context.bot_data.pop(f'ttt_{game_id}', None)
            return

        if '' not in game['board']:
            kb = ttt_render_board(game['board'], game_id)
            await query.answer("تعادل! 🤝")
            await query.edit_message_text(
                "🎮 <b>إكس أو</b>\n\n🤝 تعادل! ما فاز أحد.",
                parse_mode="HTML", reply_markup=kb
            )
            context.bot_data.pop(f'ttt_{game_id}', None)
            return

        game['turn'] = 'O' if current_sym == 'X' else 'X'

        # دور البوت (O)
        if game.get('mode') == 'bot' and game['turn'] == 'O':
            await asyncio.sleep(0.5)
            move = ttt_bot_move(game['board'])
            if move is not None:
                game['board'][move] = 'O'
                winner = check_ttt_winner(game['board'])
                if winner:
                    kb = ttt_render_board(game['board'], game_id)
                    await query.answer("البوت فاز! 🤖")
                    await query.edit_message_text(
                        "🎮 <b>إكس أو</b>\n\n🤖 البوت فاز! ⭕ حاول مرة ثانية!",
                        parse_mode="HTML", reply_markup=kb
                    )
                    context.bot_data.pop(f'ttt_{game_id}', None)
                    return
                if '' not in game['board']:
                    kb = ttt_render_board(game['board'], game_id)
                    await query.answer("تعادل! 🤝")
                    await query.edit_message_text(
                        "🎮 <b>إكس أو</b>\n\n🤝 تعادل!",
                        parse_mode="HTML", reply_markup=kb
                    )
                    context.bot_data.pop(f'ttt_{game_id}', None)
                    return
            game['turn'] = 'X'

        kb = ttt_render_board(game['board'], game_id)
        await query.answer()
        try:
            await query.edit_message_reply_markup(kb)
        except:
            pass
        return


# ═══════════════════════════════════════════════════════════════════
# 10. معالجات متنوعة
# ═══════════════════════════════════════════════════════════════════
async def track_messages_handler(update, context):
    if not update.message or not update.message.text or update.message.text.startswith('/'):
        return
    db_set(f"messages/{update.message.chat.id}/{update.message.message_id}",
           {"text": update.message.text})


async def edited_message_handler(update, context):
    if not update.edited_message:
        return
    chat_id = update.edited_message.chat.id
    msg_id = update.edited_message.message_id
    if not get_settings(chat_id).get("edit_notify", True):
        return
    new_text = update.edited_message.text or "[ميديا/ملف]"
    old_text = db_get(f"messages/{chat_id}/{msg_id}/text", "[غير متوفر]")
    db_set(f"messages/{chat_id}/{msg_id}", {"text": new_text})
    t = (
        f"✏️ <b>إشعار تعديل رسالة</b>\n"
        f"👤 <b>من:</b> {update.edited_message.from_user.first_name}\n"
        f"❌ <b>قديم:</b> <code>{old_text[:200]}</code>\n"
        f"✅ <b>جديد:</b> <code>{new_text[:200]}</code>"
    )
    await context.bot.send_message(chat_id, t, parse_mode="HTML")


async def welcome_member(update, context):
    for member in update.message.new_chat_members:
        if member.is_bot:
            continue
        s = get_settings(update.message.chat.id)
        if not s.get("welcome", True):
            continue
        name = f'<a href="tg://user?id={member.id}">{member.first_name}</a>'
        text = (
            f"👋 أهلاً وسهلاً {name} في المجموعة! 🎉\n"
            f"نتمنى لك وقتاً ممتعاً معنا 😊"
        )
        try:
            photos = await context.bot.get_user_profile_photos(member.id, limit=1)
            if photos.total_count > 0:
                await context.bot.send_photo(update.message.chat.id,
                                             photos.photos[0][-1].file_id,
                                             caption=text, parse_mode="HTML")
            else:
                await update.message.reply_text(text, parse_mode="HTML")
        except:
            await update.message.reply_text(text, parse_mode="HTML")


async def media_filter_handler(update, context):
    """منع أنواع الميديا المحظورة"""
    msg = update.message
    if not msg:
        return
    chat_id = msg.chat_id
    settings = get_settings(chat_id)

    should_delete = (
        (msg.sticker and settings.get("ban_stickers")) or
        (msg.animation and settings.get("ban_gifs")) or
        (msg.video and settings.get("ban_videos")) or
        (msg.photo and settings.get("ban_photos"))
    )

    if should_delete:
        type_names = []
        if msg.sticker and settings.get("ban_stickers"):
            type_names.append("الملصقات")
        if msg.animation and settings.get("ban_gifs"):
            type_names.append("الـ GIF")
        if msg.video and settings.get("ban_videos"):
            type_names.append("المقاطع")
        if msg.photo and settings.get("ban_photos"):
            type_names.append("الصور")

        try:
            await msg.delete()
            nm = await context.bot.send_message(
                chat_id,
                f"🚫 {msg.from_user.first_name}، إرسال {' و'.join(type_names)} ممنوع هنا!"
            )
            await asyncio.sleep(4)
            await nm.delete()
        except:
            pass


# ═══════════════════════════════════════════════════════════════════
# 11. المعالج الرئيسي للرسائل
# ═══════════════════════════════════════════════════════════════════
async def handle_message(update, context):
    if not update.message:
        return
    msg = update.message
    text = (msg.text or "").strip()
    chat_id = msg.chat_id
    user_id = msg.from_user.id

    if not text:
        return

    # ══ الخاص ══
    if msg.chat.type == 'private':
        if 'whisper_target' in context.user_data:
            await handle_private_whisper(update, context)
            return
        # روابط التحميل
        if re.search(r'(youtube\.com|youtu\.be|shorts)', text, re.I):
            await handle_youtube_link(update, context, text, user_id)
            return
        if re.search(r'(x\.com|twitter\.com)', text, re.I):
            await handle_twitter_link(update, context, text, chat_id)
            return
        if re.search(r'(tiktok\.com|vm\.tiktok\.com|douyin\.com)', text, re.I):
            await handle_tiktok_link(update, context, text, chat_id, msg.message_id)
            return
        if re.search(r'(facebook\.com|fb\.watch|fb\.com)', text, re.I):
            await handle_facebook_link(update, context, text, chat_id)
            return
        if re.search(r'instagram\.com', text, re.I):
            await handle_instagram_link(update, context, text, chat_id)
            return
        # ذكاء اصطناعي حر
        if not text.startswith('/'):
            await context.bot.send_chat_action(chat_id, 'typing')
            reply = await ask_deepseek(text)
            await msg.reply_text(reply)
        return

    # ══ الكروبات ══
    settings = get_settings(chat_id)
    priv_owner = await is_privileged(update, context, ROLE_OWNER)
    priv_manager = await is_privileged(update, context, ROLE_MANAGER)

    # ── الردود التلقائية ──
    auto_replies = db_get(f"auto_replies/{chat_id}", {})
    if auto_replies and isinstance(auto_replies, dict):
        for trigger, reply_text in auto_replies.items():
            if trigger and reply_text and trigger.lower() in text.lower():
                await msg.reply_text(reply_text)
                return

    # ── الكلمات الممنوعة ──
    banned_words = settings.get("banned_words", [])
    if banned_words:
        for word in banned_words:
            if word and word.lower() in text.lower():
                try:
                    await msg.delete()
                except:
                    pass
                try:
                    nm = await context.bot.send_message(
                        chat_id,
                        f"⚠️ {msg.from_user.first_name}، رسالتك تحتوي على كلمة ممنوعة وتم حذفها."
                    )
                    await asyncio.sleep(4)
                    await nm.delete()
                except:
                    pass
                return

    # ══════════════════════════════
    # الأوامر العامة
    # ══════════════════════════════
    if text == "الاوامر":
        return await msg.reply_text(TEXT_MAIN_MENU, parse_mode="HTML",
                                    reply_markup=get_main_keyboard())

    if text == "نسبة الحب" and msg.reply_to_message:
        pct = random.randint(0, 100)
        bar = "💖" * (pct // 20) + "🤍" * (5 - pct // 20)
        return await msg.reply_text(
            f"💘 نسبة الحب بين\n"
            f"<b>{msg.from_user.first_name}</b> و <b>{msg.reply_to_message.from_user.first_name}</b>:\n\n"
            f"{bar}\n"
            f"<b>{pct}%</b>",
            parse_mode="HTML"
        )

    if text == "وعد":
        return await msg.reply_text(random.choice(WA3ED_LIST))

    if text == "لو خيروك":
        return await msg.reply_text(random.choice(KHAYROK_LIST))

    if text == "نكتة":
        return await msg.reply_text(random.choice(JOKES_LIST))

    if text == "افتار":
        target = msg.reply_to_message.from_user if msg.reply_to_message else msg.from_user
        photos = await target.get_profile_photos(limit=1)
        if photos and photos.total_count > 0:
            return await msg.reply_photo(photos.photos[0][-1].file_id,
                                         caption=f"🖼 افتار {target.first_name}")
        return await msg.reply_text("هذا العضو ما حاط صورة بروفايل! 😅")

    if text == "ايدي":
        target = msg.reply_to_message.from_user if msg.reply_to_message else msg.from_user
        lang = target.language_code or 'unknown'
        lang_display = LANG_TO_FLAG.get(lang, f'🌐 {lang}')
        username = f"@{target.username}" if target.username else "لا يوجد"
        full_name = f"{target.first_name} {target.last_name or ''}".strip()
        premium = "💎 نعم" if getattr(target, 'is_premium', False) else "❌ لا"
        account_type = "🤖 بوت" if target.is_bot else "👤 مستخدم"
        return await msg.reply_text(
            f"📋 <b>معلومات العضو</b>\n\n"
            f"👤 <b>الاسم:</b> {full_name}\n"
            f"🆔 <b>الآيدي:</b> <code>{target.id}</code>\n"
            f"📛 <b>اليوزرنيم:</b> {username}\n"
            f"🌐 <b>اللغة:</b> {lang_display}\n"
            f"💎 <b>بريميوم:</b> {premium}\n"
            f"🔖 <b>النوع:</b> {account_type}",
            parse_mode="HTML"
        )

    if text == "همسة" and msg.reply_to_message:
        target = msg.reply_to_message.from_user
        if target.is_bot:
            return await msg.reply_text("ما تكدر تهمس لبوت يا ذكي! 😂")
        bot_username = context.bot.username
        deep_link = f"t.me/{bot_username}?start=w_{user_id}_{target.id}_{str(chat_id).replace('-', 'm')}"
        markup = InlineKeyboardMarkup([[
            InlineKeyboardButton("🔒 اضغط هنا واكتب الهمسة", url=deep_link)
        ]])
        return await msg.reply_text(
            f"يا {msg.from_user.first_name}، اضغط الزر واكتب همستك بالخاص 🤫",
            reply_markup=markup
        )

    if text == "تحويل":
        target_msg = msg.reply_to_message
        if not target_msg:
            return await msg.reply_text("❗ رد على مقطع فيديو أو ملف لتحويله لصوت.")
        media = target_msg.video or target_msg.document
        if not media:
            return await msg.reply_text("❗ رد على مقطع فيديو أو ملف صالح.")
        wait = await msg.reply_text("🔄 جاري استخراج الصوت...")
        try:
            ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
            tg_file = await media.get_file()
            in_p = f"/tmp/vin_{msg.message_id}.mp4"
            out_p = f"/tmp/aout_{msg.message_id}.mp3"
            await tg_file.download_to_drive(custom_path=in_p)
            subprocess.run(
                [ffmpeg_exe, "-i", in_p, "-q:a", "0", "-map", "a", out_p, "-y"],
                capture_output=True, timeout=180
            )
            if os.path.exists(out_p):
                file_name = getattr(media, 'file_name', None) or f"audio_{msg.message_id}"
                title = file_name.rsplit('.', 1)[0] if '.' in file_name else file_name
                with open(out_p, 'rb') as audio:
                    await msg.reply_audio(audio, title=title, performer="Bot 🎵")
                await wait.delete()
            else:
                await wait.edit_text("❌ فشل استخراج الصوت. تأكد أن الملف يحتوي على مقطع صوتي.")
        except subprocess.TimeoutExpired:
            await wait.edit_text("❌ الملف كبير جداً، تجاوز الوقت المسموح.")
        except Exception as e:
            logger.error(f"Conversion error: {e}")
            await wait.edit_text(f"❌ <b>فشل التحويل!</b>\n<code>{str(e)[:200]}</code>",
                                 parse_mode="HTML")
        finally:
            for p in [in_p, out_p]:
                if os.path.exists(p):
                    try:
                        os.remove(p)
                    except:
                        pass
        return

    # لعبة إكس أو
    if text in ("اكس او", "اكسو", "لعبة", "إكس أو"):
        game_id = str(random.randint(10000, 99999))
        context.bot_data[f'ttt_{game_id}'] = {
            'board': [''] * 9,
            'turn': 'X',
            'players': {'X': user_id, 'O': None},
            'mode': 'bot',
        }
        kb = ttt_render_board([''] * 9, game_id)
        return await msg.reply_text(
            f"🎮 <b>إكس أو</b>\n"
            f"👤 {msg.from_user.first_name} vs 🤖 البوت\n\n"
            f"دورك ❌ اضغط أي خلية!",
            parse_mode="HTML", reply_markup=kb
        )

    # نظام الزواج
    if text == "زواج" and msg.reply_to_message:
        target = msg.reply_to_message.from_user
        if target.is_bot or target.id == user_id:
            return await msg.reply_text("ما ينفع هذا الاختيار! 😅")
        existing = db_get(f"marriages/{chat_id}/{user_id}", None)
        if existing:
            return await msg.reply_text("أنت بالفعل متزوج! اكتب 'طلاق' أولاً. 💍")
        db_set(f"marriages/{chat_id}/{user_id}", target.id)
        db_set(f"marriages/{chat_id}/{target.id}", user_id)
        return await msg.reply_text(
            f"💍 تم الزواج بين <b>{msg.from_user.first_name}</b> و <b>{target.first_name}</b>!\n"
            f"مبروك عليكم! 🎊🎉",
            parse_mode="HTML"
        )

    if text == "طلاق":
        partner_id = db_get(f"marriages/{chat_id}/{user_id}", None)
        if not partner_id:
            return await msg.reply_text("أنت مو متزوج أصلاً! 😅")
        db_set(f"marriages/{chat_id}/{user_id}", None)
        db_set(f"marriages/{chat_id}/{partner_id}", None)
        return await msg.reply_text(
            f"💔 تم الطلاق. {msg.from_user.first_name} أصبح حراً.\n"
            f"الحياة مستمرة! 🌹"
        )

    if text == "شريكي":
        partner_id = db_get(f"marriages/{chat_id}/{user_id}", None)
        if not partner_id:
            return await msg.reply_text("ما عندك شريك/ة حالياً 😢\nاكتب 'زواج' بالرد على شخص!")
        try:
            m = await context.bot.get_chat_member(chat_id, partner_id)
            return await msg.reply_text(
                f"💑 شريكك هو/هي: <b>{m.user.first_name}</b>",
                parse_mode="HTML"
            )
        except:
            return await msg.reply_text("شريكك غادر المجموعة 😔")

    # ══════════════════════════════
    # الأوامر الإدارية (مدير أو أعلى)
    # ══════════════════════════════
    if priv_manager:

        if text == "تحذير" and msg.reply_to_message:
            tgt = msg.reply_to_message.from_user
            warns = db_get(f"warns/{chat_id}/{tgt.id}", 0) + 1
            db_set(f"warns/{chat_id}/{tgt.id}", warns)
            if warns >= 3:
                try:
                    await context.bot.ban_chat_member(chat_id, tgt.id)
                    return await msg.reply_text(
                        f"🚫 <b>{tgt.first_name}</b> وصل للتحذير الثالث وتم حظره تلقائياً!",
                        parse_mode="HTML"
                    )
                except:
                    pass
            return await msg.reply_text(
                f"⚠️ تحذير <b>{warns}/3</b> لـ <b>{tgt.first_name}</b>.",
                parse_mode="HTML"
            )

        if text == "الغاء تحذير" and msg.reply_to_message:
            tgt = msg.reply_to_message.from_user
            warns = max(0, db_get(f"warns/{chat_id}/{tgt.id}", 0) - 1)
            db_set(f"warns/{chat_id}/{tgt.id}", warns)
            return await msg.reply_text(
                f"✅ تم إلغاء تحذير. <b>{tgt.first_name}</b> عنده الآن <b>{warns}/3</b>.",
                parse_mode="HTML"
            )

        if text == "تحذيراتي":
            warns = db_get(f"warns/{chat_id}/{user_id}", 0)
            return await msg.reply_text(f"⚠️ تحذيراتك: <b>{warns}/3</b>", parse_mode="HTML")

        if text == "قفل الشات":
            try:
                await context.bot.set_chat_permissions(chat_id,
                                                       ChatPermissions(can_send_messages=False))
                settings["locked"] = True
                save_settings(chat_id, settings)
                return await msg.reply_text("🔒 تم قفل الشات. لا أحد يقدر يكتب الآن.")
            except Exception as e:
                return await msg.reply_text(f"❌ فشل القفل: {e}")

        if text == "فتح الشات":
            try:
                perms = ChatPermissions(
                    can_send_messages=True, can_send_audios=True,
                    can_send_documents=True, can_send_photos=True,
                    can_send_videos=True, can_send_video_notes=True,
                    can_send_voice_notes=True, can_send_polls=True,
                    can_send_other_messages=True, can_add_web_page_previews=True
                )
                await context.bot.set_chat_permissions(chat_id, perms)
                settings["locked"] = False
                save_settings(chat_id, settings)
                return await msg.reply_text("🔓 تم فتح الشات. الجميع يقدر يكتب!")
            except Exception as e:
                return await msg.reply_text(f"❌ فشل الفتح: {e}")

        # منع/تفعيل أنواع الميديا
        ban_map = {
            "منع ملصقات": "ban_stickers", "منع قيف": "ban_gifs",
            "منع مقاطع": "ban_videos", "منع صور": "ban_photos"
        }
        unban_map = {
            "تفعيل ملصقات": "ban_stickers", "تفعيل قيف": "ban_gifs",
            "تفعيل مقاطع": "ban_videos", "تفعيل صور": "ban_photos"
        }
        names = {"ban_stickers": "الملصقات", "ban_gifs": "الـ GIF",
                 "ban_videos": "المقاطع", "ban_photos": "الصور"}

        if text in ban_map:
            key = ban_map[text]
            settings[key] = True
            save_settings(chat_id, settings)
            return await msg.reply_text(f"🚫 تم تفعيل منع {names[key]}.")

        if text in unban_map:
            key = unban_map[text]
            settings[key] = False
            save_settings(chat_id, settings)
            return await msg.reply_text(f"✅ تم رفع منع {names[key]}.")

        if text == "الترحيب تشغيل":
            settings["welcome"] = True
            save_settings(chat_id, settings)
            return await msg.reply_text("✅ تم تفعيل رسالة الترحيب.")

        if text == "الترحيب ايقاف":
            settings["welcome"] = False
            save_settings(chat_id, settings)
            return await msg.reply_text("✅ تم إيقاف رسالة الترحيب.")

        if text == "تعديل تشغيل":
            settings["edit_notify"] = True
            save_settings(chat_id, settings)
            return await msg.reply_text("✅ تم تفعيل إشعارات تعديل الرسائل.")

        if text == "تعديل ايقاف":
            settings["edit_notify"] = False
            save_settings(chat_id, settings)
            return await msg.reply_text("✅ تم إيقاف إشعارات تعديل الرسائل.")

        if text.startswith("منع كلمة "):
            word = text[9:].strip()
            if word:
                words = settings.get("banned_words", [])
                if word not in words:
                    words.append(word)
                settings["banned_words"] = words
                save_settings(chat_id, settings)
                return await msg.reply_text(
                    f"✅ تمت إضافة الكلمة الممنوعة: <code>{word}</code>",
                    parse_mode="HTML"
                )

        if text.startswith("حذف كلمة "):
            word = text[9:].strip()
            words = settings.get("banned_words", [])
            if word in words:
                words.remove(word)
            settings["banned_words"] = words
            save_settings(chat_id, settings)
            return await msg.reply_text(
                f"✅ تمت إزالة الكلمة: <code>{word}</code>",
                parse_mode="HTML"
            )

        if text == "الكلمات":
            words = settings.get("banned_words", [])
            if words:
                return await msg.reply_text(
                    "📋 <b>الكلمات الممنوعة:</b>\n" +
                    "\n".join(f"• <code>{w}</code>" for w in words),
                    parse_mode="HTML"
                )
            return await msg.reply_text("لا توجد كلمات ممنوعة حالياً.")

        if text.startswith("مسح "):
            try:
                count = min(int(text[4:].strip()), 100)
                start_id = (msg.reply_to_message.message_id
                            if msg.reply_to_message else msg.message_id - 1)
                deleted = 0
                for mid in range(start_id, start_id + count + 1):
                    try:
                        await context.bot.delete_message(chat_id, mid)
                        deleted += 1
                    except:
                        pass
                try:
                    await msg.delete()
                except:
                    pass
                nm = await context.bot.send_message(chat_id, f"🗑 تم حذف {deleted} رسالة.")
                await asyncio.sleep(3)
                await nm.delete()
            except ValueError:
                await msg.reply_text("❗ مثال: <code>مسح 10</code> (مع الرد على أول رسالة)",
                                     parse_mode="HTML")
            return

        # الردود التلقائية
        if text.startswith("اضافة رد ") and "|" in text:
            after = text[9:]
            parts = after.split("|", 1)
            trigger_word = parts[0].strip()
            reply_word = parts[1].strip()
            if trigger_word and reply_word:
                db_set(f"auto_replies/{chat_id}/{trigger_word}", reply_word)
                return await msg.reply_text(
                    f"✅ <b>تم إضافة الرد التلقائي:</b>\n"
                    f"🔑 عند كتابة: <code>{trigger_word}</code>\n"
                    f"💬 البوت يرد: {reply_word}",
                    parse_mode="HTML"
                )
            return await msg.reply_text("❗ مثال: <code>اضافة رد السلام عليكم | وعليكم السلام</code>",
                                        parse_mode="HTML")

        if text.startswith("حذف رد "):
            trigger_word = text[7:].strip()
            db_set(f"auto_replies/{chat_id}/{trigger_word}", None)
            return await msg.reply_text(
                f"✅ تم حذف الرد التلقائي لـ: <code>{trigger_word}</code>",
                parse_mode="HTML"
            )

        if text == "قائمة الردود":
            replies = db_get(f"auto_replies/{chat_id}", {})
            if replies and isinstance(replies, dict):
                lines = [f"• <code>{k}</code> ← {v}"
                         for k, v in replies.items() if k and v]
                if lines:
                    return await msg.reply_text(
                        "📋 <b>الردود التلقائية:</b>\n" + "\n".join(lines),
                        parse_mode="HTML"
                    )
            return await msg.reply_text("لا توجد ردود تلقائية حالياً.")

        if text == "طرد":
            tgt = await get_target_user(update, context)
            if tgt:
                await context.bot.ban_chat_member(chat_id, tgt.id)
                await context.bot.unban_chat_member(chat_id, tgt.id)
                await msg.reply_text(f"👢 تم طرد {tgt.first_name}.")
            return

        if text == "حظر":
            tgt = await get_target_user(update, context)
            if tgt:
                await context.bot.ban_chat_member(chat_id, tgt.id)
                await msg.reply_text(f"🚫 تم حظر {tgt.first_name}.")
            return

        if text == "فك حظر":
            tgt = await get_target_user(update, context)
            if tgt:
                await context.bot.unban_chat_member(chat_id, tgt.id, only_if_banned=True)
                await msg.reply_text(f"✅ تم فك حظر {tgt.first_name}.")
            return

        if text == "كتم":
            tgt = await get_target_user(update, context)
            if tgt:
                await context.bot.restrict_chat_member(chat_id, tgt.id,
                                                       ChatPermissions(can_send_messages=False))
                await msg.reply_text(f"🔇 تم كتم {tgt.first_name}.")
            return

        if text == "الغاء كتم":
            tgt = await get_target_user(update, context)
            if tgt:
                perms = ChatPermissions(
                    can_send_messages=True, can_send_audios=True,
                    can_send_documents=True, can_send_photos=True,
                    can_send_videos=True, can_send_video_notes=True,
                    can_send_voice_notes=True, can_send_polls=True,
                    can_send_other_messages=True, can_add_web_page_previews=True
                )
                await context.bot.restrict_chat_member(chat_id, tgt.id, permissions=perms)
                await msg.reply_text(f"🔊 تم رفع الكتم عن {tgt.first_name}.")
            return

        if text.startswith("تثبيت") and msg.reply_to_message:
            await context.bot.pin_chat_message(chat_id, msg.reply_to_message.message_id)
            return

        if text.startswith("الغاء تثبيت") and msg.reply_to_message:
            await context.bot.unpin_chat_message(chat_id, msg.reply_to_message.message_id)
            return

    # ══ أوامر المالك فقط ══
    if priv_owner:
        r_map = {"رفع مالك": ROLE_OWNER, "رفع مدير": ROLE_MANAGER, "رفع مميز": ROLE_VIP}
        if text in r_map:
            tgt = await get_target_user(update, context)
            if tgt:
                set_role(chat_id, tgt.id, r_map[text])
                await msg.reply_text(
                    f"✅ صار <b>{tgt.first_name}</b> {ROLE_LABEL[r_map[text]]}.",
                    parse_mode="HTML"
                )
            return

        if text == "تنزيل رتبة":
            tgt = await get_target_user(update, context)
            if tgt:
                remove_role(chat_id, tgt.id)
                await msg.reply_text(f"✅ تمت إزالة رتبة {tgt.first_name}.")
            return

        if text == "تشغيل سيك":
            settings["ai_mode"] = True
            save_settings(chat_id, settings)
            return await msg.reply_text("🤖 تم تفعيل الذكاء الاصطناعي في الكروب!")

        if text == "ايقاف سيك":
            settings["ai_mode"] = False
            save_settings(chat_id, settings)
            return await msg.reply_text("😴 تم إيقاف الذكاء الاصطناعي.")

    # ══ روابط الكروب ══
    if re.search(r'(youtube\.com|youtu\.be|shorts)', text, re.I):
        await handle_youtube_link(update, context, text, user_id)
        return
    if re.search(r'(x\.com|twitter\.com)', text, re.I):
        await handle_twitter_link(update, context, text, chat_id)
        return
    if re.search(r'(tiktok\.com|vm\.tiktok\.com|douyin\.com)', text, re.I):
        await handle_tiktok_link(update, context, text, chat_id, msg.message_id)
        return
    if re.search(r'(facebook\.com|fb\.watch|fb\.com)', text, re.I):
        await handle_facebook_link(update, context, text, chat_id)
        return
    if re.search(r'instagram\.com', text, re.I):
        await handle_instagram_link(update, context, text, chat_id)
        return

    # ══ الذكاء الاصطناعي في الكروب ══
    if settings.get("ai_mode", False):
        skip_cmds = ('رفع', 'تنزيل', 'طرد', 'حظر', 'كتم', 'قفل',
                     'فتح', 'منع', 'تفعيل', 'اضافة', 'حذف', 'الكلمات',
                     'مسح', 'تحذير', 'الترحيب', 'تعديل')
        if not any(text.startswith(c) for c in skip_cmds):
            await context.bot.send_chat_action(chat_id, 'typing')
            reply = await ask_deepseek(text)
            return await msg.reply_text(reply)


# ═══════════════════════════════════════════════════════════════════
# 12. تشغيل البوت
# ═══════════════════════════════════════════════════════════════════
def main():
    token = os.environ.get("BOT_TOKEN", "8159446452:AAHvUE5aEvuTmGfwAYAV7EqfshKD9Nv-B5o")
    app = Application.builder().token(token).build()

    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CallbackQueryHandler(
        button_callback,
        pattern=r"^(show_w_|cmd_|dl_|ttt_)"
    ))
    app.add_handler(MessageHandler(
        filters.StatusUpdate.NEW_CHAT_MEMBERS, welcome_member
    ))
    app.add_handler(MessageHandler(
        filters.UpdateType.EDITED_MESSAGE & filters.TEXT, edited_message_handler
    ))
    # فلتر منع الميديا (group=0 → يُشغّل أولاً)
    app.add_handler(MessageHandler(
        filters.ChatType.GROUPS & (
            filters.Sticker.ALL | filters.ANIMATION |
            filters.VIDEO | filters.PHOTO
        ),
        media_filter_handler
    ), group=0)
    # تتبع الرسائل
    app.add_handler(MessageHandler(
        filters.ChatType.GROUPS & filters.TEXT & ~filters.COMMAND,
        track_messages_handler
    ), group=1)
    # المعالج الرئيسي
    app.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND, handle_message
    ), group=2)

    logger.info("🚀 Bot is running!")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
