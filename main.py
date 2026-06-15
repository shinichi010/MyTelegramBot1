import logging, os, asyncio, random, re, hashlib, requests
import tempfile, shutil, subprocess, sqlite3, json, threading, math
from telegram import Update, ChatPermissions, InlineKeyboardMarkup, InlineKeyboardButton, InputMediaPhoto
from telegram.ext import Application, MessageHandler, CallbackQueryHandler, CommandHandler, filters, ContextTypes
from yt_dlp import YoutubeDL
import imageio_ffmpeg

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()

# ═══════════════════════════════════════════════════════════════════
# دالة ذكية لضغط الفيديوهات الكبيرة حتى لا تتخطى حد تليجرام (50 ميجا)
# ═══════════════════════════════════════════════════════════════════
def ensure_tg_size_limit(fp):
    if not fp or not os.path.exists(fp): return fp
    max_size = 49 * 1024 * 1024  # 49 ميجابايت للأمان
    if os.path.getsize(fp) > max_size:
        logger.info(f"⚠️ حجم الملف ({os.path.getsize(fp)}0) يعبر الـ 49 ميجا. جاري الضغط التلقائي...")
        tmp_out = fp.rsplit('.', 1)[0] + "_compressed.mp4"
        try:
            subprocess.run([
                FFMPEG, "-i", fp, 
                "-vcodec", "libx264", "-crf", "30", 
                "-acodec", "aac", "-b:a", "128k",
                "-fs", "48M", "-y", tmp_out
            ], capture_output=True, timeout=300)
            if os.path.exists(tmp_out) and os.path.getsize(tmp_out) > 0:
                os.remove(fp)
                logger.info(f"✅ تم ضغط الملف بنجاح.")
                return tmp_out
        except Exception as e:
            logger.error(f"❌ فشل ضغط الملف: {e}")
    return fp

# ═══════════════════════════════════════════════════════════════════
# 1. القوائم والمحتوى
# ═══════════════════════════════════════════════════════════════════
WA3ED_LIST = ["عيونها السود والبيض 👀", " هلا بالحلو \ ة 🌸", "مالي خلقك 😏", "اتسرسح منا وليدي 😤", "انا هسة مشغولة 😅"]
KHAYROK_LIST = ["لو خيروك: تسافر للمستقبل لو للماضي? ⏳", "لو خيروك: تاكل بيتزا طول عمرك لو بركر? 🍕🍔", "لو خيروك: ما تنام أبد لو ما تأكل أبد? 😴"]
JOKES_LIST = ["شلون النملة تعدّ حياتها؟ — تحسب سنين! 🐜😂", "ليش الكمبيوتر بارد؟ — لأن عنده ويندوز! 🪟"]
LANG_FLAG = {'ar':'🇸🇦','en':'🇬🇧','tr':'🇹🇷','fa':'🇮🇷','ru':'🇷🇺'}

TEXT_MAIN = "📋 <b>لوحة أوامر البوت</b>\n\nاختر القسم 👇"
TEXT_ADMIN = (
    "👑 <b>أوامر الإدارة:</b>\n"
    "• <code>رفع مالك | مدير | مميز</code> / <code>تنزيل رتبة</code>\n"
    "• <code>طرد | حظر | فك حظر | كتم | الغاء كتم</code>\n"
    "• <code>تثبيت | الغاء تثبيت</code>\n"
    "• <code>قفل الشات | فتح الشات</code>\n"
    "• <code>تحذير | الغاء تحذير | تحذيراتي</code>\n"
    "• <code>منع كلمة X | حذف كلمة X | الكلمات</code>\n"
    "• <code>مسح X</code> — حذف X رسالة"
)
TEXT_FUN = (
    "🎮 <b>أوامر التسلية:</b>\n"
    "• <code>همسة</code> — همسة سرية (بالرد)\n"
    "• <code>ايدي</code> / <code>افتار</code>\n"
    "• <code>زواج | طلاق | شريكي | نسبة الحب</code>\n"
    "• <code>تحويل</code> — رد على فيديو لتحويله لصوت\n"
    "• <code>لو خيروك | ري | نكتة | نرد | عملة</code>\n"
    "• <code>اكس او</code> — لعبة إكس أو 🎮\n"
    "• <code>ترجمة [نص]</code> — ترجمة أي نص للعربي\n"
    "• <code>حساب [عملية]</code> — حاسبة رياضية"
)
TEXT_DL = (
    "📥 <b>التحميل — المواقع المدعومة:</b>\n\n"
    "🎬 يوتيوب — مقاطع وصوت\n"
    "🐦 تويتر/X — مقاطع وريلز\n"
    "🎵 تيك توك + 🇨🇳 دوين — فيديو وصور\n"
    "📘 فيس بوك — مقاطع ريلز\n"
    "📸 انستغرام — ريلز وبوستات\n"
    "📌 بينترست — فيديو وصور\n"
    "🎵 ساوند كلاود — تحميل موسيقى MP3\n"
    "🎵 يوتيوب ميوزك — تحميل MP3\n\n"
    "💡 أرسل الرابط مباشرة!"
)

def mk_main(): return InlineKeyboardMarkup([[InlineKeyboardButton("🛡️ الإدارة", callback_data="cmd_admin"), InlineKeyboardButton("🎮 التسلية", callback_data="cmd_fun")], [InlineKeyboardButton("📥 التحميل", callback_data="cmd_dl")]])
def mk_back(): return InlineKeyboardMarkup([[InlineKeyboardButton("🔙 القائمة", callback_data="cmd_main")]])

# ═══════════════════════════════════════════════════════════════════
# 2. قاعدة البيانات SQLite و الكوكيز
# ═══════════════════════════════════════════════════════════════════
DB_PATH = os.environ.get('DB_PATH', 'bot_data.db')
_db_lock = threading.Lock()

def _init_db():
    with sqlite3.connect(DB_PATH) as c:
        c.execute('CREATE TABLE IF NOT EXISTS kv (path TEXT PRIMARY KEY, value TEXT)')
        c.commit()
_init_db()

def _load_cookies():
    import base64
    data = os.environ.get('COOKIES_DATA', '').strip()
    if not data: return
    success = False
    try:
        clean = ''.join(data.split())
        content = base64.b64decode(clean + '==').decode('utf-8')
        if '\t' in content:
            with open('cookies.txt', 'w', encoding='utf-8') as f: f.write(content)
            success = True
    except: pass
    if not success:
        try:
            if '\t' in data:
                with open('cookies.txt', 'w', encoding='utf-8') as f: f.write(data)
                success = True
        except: pass
_load_cookies()

def db_get(path: str, default=None):
    with _db_lock:
        try:
            with sqlite3.connect(DB_PATH) as c:
                row = c.execute('SELECT value FROM kv WHERE path=?', (path,)).fetchone()
                return json.loads(row[0]) if row else default
        except: return default

def db_set(path: str, value):
    with _db_lock:
        try:
            with sqlite3.connect(DB_PATH) as c:
                if value is None: c.execute('DELETE FROM kv WHERE path=?', (path,))
                else: c.execute('INSERT OR REPLACE INTO kv (path,value) VALUES (?,?)', (path, json.dumps(value, ensure_ascii=False)))
                c.commit()
        except: pass

def get_settings(cid): return db_get(f"settings/{cid}", {"welcome":True,"banned_words":[],"locked":False,"edit_notify":True,"ai_mode":False})
def save_settings(cid, s): db_set(f"settings/{cid}", s)

def make_key(text): return "k"+hashlib.md5(text.strip().lower().encode()).hexdigest()[:16]
def store_reply(cid, trigger, reply):
    d = db_get(f"replies/{cid}", {})
    d[make_key(trigger)] = {"t": trigger.strip(), "r": reply.strip()}
    db_set(f"replies/{cid}", d)
def delete_reply(cid, trigger):
    d = db_get(f"replies/{cid}", {})
    d.pop(make_key(trigger), None)
    db_set(f"replies/{cid}", d)
def get_replies(cid):
    d = db_get(f"replies/{cid}", {})
    return [(v["t"], v["r"]) for v in d.values() if isinstance(v, dict) and v.get("t") and v.get("r")]

# ═══════════════════════════════════════════════════════════════════
# 2.5 دوال لعبة إكس أو (XO)
# ═══════════════════════════════════════════════════════════════════
def ttt_kb(board, gid):
    inline_board = []
    for i in range(0, 9, 3):
        row = []
        for j in range(3):
            idx = i + j
            val = board[idx]
            cb_data = f"ttt_{gid}_{idx}" if val == '' else "ttt_noop"
            row.append(InlineKeyboardButton(val if val != '' else ' ', callback_data=cb_data))
        inline_board.append(row)
    inline_board.append([InlineKeyboardButton("🔄 إعادة", callback_data=f"ttt_reset_{gid}"), InlineKeyboardButton("❌ إلغاء", callback_data="convert_cancel")])
    return InlineKeyboardMarkup(inline_board)

def ttt_winner(b):
    win_coords = [(0,1,2), (3,4,5), (6,7,8), (0,3,6), (1,4,7), (2,5,8), (0,4,8), (2,4,6)]
    for r in win_coords:
        if b[r[0]] == b[r[1]] == b[r[2]] != '': return b[r[0]]
    return None

def ttt_bot(b):
    empty_cells = [i for i, x in enumerate(b) if x == '']
    return random.choice(empty_cells) if empty_cells else None

# ═══════════════════════════════════════════════════════════════════
# 3. الصلاحيات
# ═══════════════════════════════════════════════════════════════════
ROLE_OWNER, ROLE_MGR, ROLE_VIP = "owner","manager","vip"
ROLE_RANK = {ROLE_OWNER:3, ROLE_MGR:2, ROLE_VIP:1}
ROLE_LABEL = {ROLE_OWNER:"👑 مالك", ROLE_MGR:"🛡 مدير", ROLE_VIP:"⭐ مميز"}

def get_role(cid, uid): return db_get(f"roles/{cid}/{uid}")
def set_role(cid, uid, r): db_set(f"roles/{cid}/{uid}", r)
def rm_role(cid, uid): db_set(f"roles/{cid}/{uid}", None)

async def is_tg_owner(upd, ctx):
    try:
        admins = await ctx.bot.get_chat_administrators(upd.effective_chat.id)
        return any(a.user.id == upd.effective_user.id and a.status == "creator" for a in admins)
    except: return False

async def is_priv(upd, ctx, min_role=ROLE_OWNER):
    r = get_role(upd.effective_chat.id, upd.effective_user.id)
    return (bool(r and ROLE_RANK.get(r,0) >= ROLE_RANK.get(min_role,99))) or await is_tg_owner(upd, ctx)

async def get_target(upd, ctx):
    m = upd.message
    if m.reply_to_message: return m.reply_to_message.from_user
    if m.entities:
        for e in m.entities:
            if e.type == "text_mention" and e.user: return e.user
    return None

# ═══════════════════════════════════════════════════════════════════
# 4. الذكاء الاصطناعي
# ═══════════════════════════════════════════════════════════════════
async def ask_ai(prompt: str) -> str:
    api_key = os.environ.get("GEMINI_KEY", "")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={api_key}"
    payload = {
        "systemInstruction": {"parts": [{"text": "أنت مساعد ذكي اسمك سيك، تتحدث باللهجة العراقية أحياناً وتبقى لطيف وخفيف. كن مختصراً ومفيداً."}]},
        "contents": [{"role": "user", "parts": [{"text": prompt}]}]
    }
    def _call():
        try:
            r = requests.post(url, json=payload, timeout=30)
            if r.status_code == 200: return r.json()["candidates"][0]["content"]["parts"][0]["text"]
            return "⚠️ Gemini مشغول الحين (free tier limit)."
        except: return "⏱ Gemini ما رد. حاول ثاني."
    return await asyncio.get_running_loop().run_in_executor(None, _call)

# ═══════════════════════════════════════════════════════════════════
# 5. نظام التحميل الأساسي
# ═══════════════════════════════════════════════════════════════════
active_dl = {}

def _progress(d, mid):
    if d['status'] == 'downloading':
        pct = re.sub(r'\x1b\[[0-9;]*m','', d.get('_percent_str','0%').strip())
        active_dl[mid] = pct

async def _progress_updater(ctx, cid, mid, smid, is_photo=False):
    last = ""
    while mid in active_dl:
        cur = active_dl.get(mid,"")
        if cur and cur != last:
            try:
                t = f"⏳ جاري التحميل: {cur}"
                if is_photo: await ctx.bot.edit_message_caption(chat_id=cid, message_id=smid, caption=t)
                else: await ctx.bot.edit_message_text(t, chat_id=cid, message_id=smid)
                last = cur
            except: pass
        await asyncio.sleep(2.5)

def _base_opts(mid):
    opts = {
        'outtmpl': os.path.join(tempfile.mkdtemp(), '%(title)s.%(ext)s'),
        'quiet': True, 'noplaylist': True, 'nocheckcertificate': True,
        'geo_bypass': True, 'extractor_retries': 2, 'retries': 2,
        'ffmpeg_location': FFMPEG,
        'progress_hooks': [lambda d: _progress(d, mid)],
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0.0.0 Safari/537.36',
        },
    }
    if os.path.exists('cookies.txt'): opts['cookiefile'] = 'cookies.txt'
    return opts

def build_quality_kb(format_map, uid, uhash, emoji="🎬"):
    standard = [2160,1440,1080,720,480,360,240,144]
    avail = sorted([h for h in format_map if h], reverse=True) if isinstance(format_map, dict) else [720,480,360]
    avail = [q for q in standard if any(abs(a-q)<=q*0.15 for a in avail)][:6] or [720,480,360]
    rows, row = [], []
    for q in avail:
        row.append(InlineKeyboardButton(f"{emoji} {q}p", callback_data=f"dl_v{q}_{uid}_{uhash}"))
        if len(row)==2: rows.append(row); row=[]
    if row: rows.append(row)
    rows.append([InlineKeyboardButton("🎵 صوت MP3", callback_data=f"dl_audio_{uid}_{uhash}")])
    return InlineKeyboardMarkup(rows)

async def do_download(url, media_type, quality, mid, cid, ctx, smid, is_photo=False):
    opts = _base_opts(mid)
    opts['outtmpl'] = opts['outtmpl'].replace('%(title)s', '%(id)s')
    tmp = os.path.dirname(opts['outtmpl'])

    if bool(re.search(r'(youtube\.com|youtu\.be)', url)):
        opts['extractor_args'] = {'youtube': {'player_client': ['ios', 'android']}}

    if media_type == "audio":
        opts['format'] = 'bestaudio[ext=m4a]/bestaudio/best'
        opts['writethumbnail'] = True
        opts['postprocessors'] = [{'key':'FFmpegExtractAudio','preferredcodec':'mp3','preferredquality':'320'}, {'key':'FFmpegMetadata','add_metadata':True}, {'key':'EmbedThumbnail'}]
    else:
        h = int(quality) if quality and str(quality).isdigit() else 720
        opts['format'] = f'bestvideo[height<={h}]+bestaudio/best[height<={h}]/best'
        opts['merge_output_format'] = 'mp4'

    active_dl[mid] = "0%"
    task = asyncio.create_task(_progress_updater(ctx, cid, mid, smid, is_photo))

    def run():
        with YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            for f in os.listdir(tmp):
                if f.endswith(('.mp3','.mp4','.m4a','.webm','.mkv')):
                    return os.path.join(tmp, f), info.get('title','media')
        return None, None

    try:
        path, title = await asyncio.get_running_loop().run_in_executor(None, run)
        active_dl.pop(mid, None); task.cancel()
        return path, title, tmp
    except:
        active_dl.pop(mid, None); task.cancel()
        return None, None, tmp

# ═══════════════════════════════════════════════════════════════════
# 6. معالجات المواقع بالتفصيل
# ═══════════════════════════════════════════════════════════════════
async def yt_handler(upd, ctx, url, uid):
    msg = upd.message
    wm = await msg.reply_text("🔍 جاري جلب معلومات الفيديو من يوتيوب...")
    has_yt_c = os.path.exists('cookies.txt')

    def _get_info():
        clients = [['tv_embedded'], ['ios'], ['android'], ['web']]
        for client in clients:
            try:
                opts = {'quiet': True, 'skip_download': True, 'extractor_args': {'youtube': {'player_client': client}}}
                if has_yt_c: opts['cookiefile'] = 'cookies.txt'
                with YoutubeDL(opts) as ydl: return ydl.extract_info(url, download=False)
            except: continue
        return None

    info = await asyncio.get_running_loop().run_in_executor(None, _get_info)
    if not info:
        return await wm.edit_text("❌ <b>فشل جلب بيانات اليوتيوب</b>\nالرابط محمي أو يحتاج تجديد الـ Cookies.", parse_mode="HTML")

    format_map = {f.get('height'): {'id': f['format_id']} for f in info.get('formats', []) if f.get('height') and f.get('vcodec','none') != 'none'}
    uhash = str(random.randint(10000,99999))
    ctx.bot_data[uhash] = url
    kb = build_quality_kb(format_map, uid, uhash, "🎬")
    cap = f"🎬 <b>{info.get('title','')[:60]}</b>"
    
    try:
        if info.get('thumbnail'):
            await ctx.bot.send_photo(msg.chat_id, info['thumbnail'], caption=cap, parse_mode="HTML", reply_markup=kb)
            await wm.delete()
        else: await wm.edit_text(cap, parse_mode="HTML", reply_markup=kb)
    except: await wm.edit_text(cap, parse_mode="HTML", reply_markup=kb)

async def auto_download(upd, ctx, url, cid, platform="🎬", max_height=1080):
    msg = upd.message
    wm = await msg.reply_text(f"{platform} جاري التحميل بأعلى جودة...")
    tmp = tempfile.mkdtemp()
    opts = {**_base_opts(msg.message_id), 'outtmpl': os.path.join(tmp, '%(id)s.%(ext)s')}
    opts['format'] = f'bestvideo[height<={max_height}]+bestaudio/best[height<={max_height}]/best'
    opts['merge_output_format'] = 'mp4'

    active_dl[msg.message_id] = "0%"
    prog_task = asyncio.create_task(_progress_updater(ctx, cid, msg.message_id, wm.message_id))

    def _run():
        with YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            files = [os.path.join(tmp, f) for f in os.listdir(tmp) if f.endswith(('.mp4', '.webm', '.mkv'))]
            return files[0] if files else None, info.get('title', '')

    try:
        fp, title = await asyncio.get_running_loop().run_in_executor(None, _run)
        active_dl.pop(msg.message_id, None); prog_task.cancel()
        if fp and os.path.exists(fp):
            fp = ensure_tg_size_limit(fp) # تطبيق ميزة الضغط
            await wm.edit_text("📤 جاري الرفع لتليجرام...")
            with open(fp, 'rb') as f:
                await ctx.bot.send_video(cid, f, caption=f"{platform} {title[:60]}", supports_streaming=True)
            await wm.delete()
        else: await wm.edit_text("❌ فشل التحميل. تأكد أن الرابط عام.")
    except Exception as e:
        active_dl.pop(msg.message_id, None); prog_task.cancel()
        await wm.edit_text(f"❌ فشل التحميل.")
    finally: shutil.rmtree(tmp, ignore_errors=True)

async def fb_handler(upd, ctx, url, uid): await auto_download(upd, ctx, url, upd.message.chat_id, "📘", 720)
async def x_handler(upd, ctx, url, uid): await auto_download(upd, ctx, url, upd.message.chat_id, "🐦", 1080)
async def pinterest_handler(upd, ctx, url, cid): await auto_download(upd, ctx, url, cid, "📌", 1080)
async def tiktok_handler(upd, ctx, url, cid, reply_id): await auto_download(upd, ctx, url, cid, "🎵", 1080)

async def music_handler(upd, ctx, url, cid, platform="🎵"):
    msg = upd.message
    wm = await msg.reply_text(f"{platform} جاري تحميل الصوت...")
    tmp = tempfile.mkdtemp()
    opts = {**_base_opts(msg.message_id), 'outtmpl': os.path.join(tmp,'%(title)s.%(ext)s'), 'format': 'bestaudio/best'}
    opts['postprocessors'] = [{'key':'FFmpegExtractAudio','preferredcodec':'mp3','preferredquality':'320'}]
    if 'youtube' in url: opts['extractor_args'] = {'youtube': {'player_client': ['tv_embedded', 'ios', 'android']}}
    
    def _dl():
        with YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            files = [os.path.join(tmp, f) for f in os.listdir(tmp) if f.endswith('.mp3')]
            return files[0] if files else None, info.get('title','Audio')
            
    try:
        fp, title = await asyncio.get_running_loop().run_in_executor(None, _dl)
        if fp and os.path.exists(fp):
            await wm.edit_text("📤 جاري الرفع الموسيقى...")
            with open(fp,'rb') as f: await ctx.bot.send_audio(cid, f, title=title[:60])
            await wm.delete()
        else: await wm.edit_text("❌ فشل التحميل. يوتيوب يرفض الاتصال.")
    except Exception as e: await wm.edit_text(f"❌ خطأ: لم يتم العثور على الصوت.")
    finally: shutil.rmtree(tmp, ignore_errors=True)

async def spotify_handler(upd, ctx, url, cid):
    msg = upd.message
    wm = await msg.reply_text("🎧 سبوتيفاي: جاري البحث والتحميل...")
    tmp = tempfile.mkdtemp()
    
    def _dl():
        import sys
        env = os.environ.copy()
        env['PATH'] = os.path.dirname(FFMPEG) + os.pathsep + env.get('PATH', '')
        cmd = [sys.executable, '-m', 'spotdl', url, '--output', tmp, '--format', 'mp3', '--bitrate', '320k', '--threads', '1']
        if os.path.exists('cookies.txt'):
            cmd.extend(['--cookie-file', 'cookies.txt'])
        subprocess.run(cmd, cwd=tmp, capture_output=True, env=env, timeout=180)
        return [os.path.join(tmp, f) for f in os.listdir(tmp) if f.endswith('.mp3')]

    try:
        files = await asyncio.get_running_loop().run_in_executor(None, _dl)
        if not files: return await wm.edit_text("❌ فشل سبوتيفاي. جرب إرسال رابط الأغنية من يوتيوب ميوزك مباشرة. 🎵")
        await wm.edit_text("📤 جاري الرفع المقطع الصوت...")
        for fp in files[:5]:
            with open(fp, 'rb') as f: await ctx.bot.send_audio(cid, f, title=os.path.basename(fp).rsplit('.',1)[0])
        await wm.delete()
    except Exception as e: await wm.edit_text("❌ حدث خطأ في تحميل سبوتيفاي.")
    finally: shutil.rmtree(tmp, ignore_errors=True)

async def insta_handler(upd, ctx, url, cid):
    msg = upd.message
    wm = await msg.reply_text("📸 جاري التحميل من انستغرام...")
    tmp = tempfile.mkdtemp()
    opts = {**_base_opts(msg.message_id), 'outtmpl': os.path.join(tmp, '%(id)s_%(autonumber)03d.%(ext)s'), 'format': 'bestvideo+bestaudio/best'}
    
    def _dl():
        with YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            files = [os.path.join(tmp, f) for f in os.listdir(tmp) if f.endswith(('.mp4','.jpg','.png','.webp'))]
            return files, info.get('title', 'Instagram')

    try:
        files, title = await asyncio.get_running_loop().run_in_executor(None, _dl)
        if not files: return await wm.edit_text("❌ فشل التحميل من انستغرام. الحساب خاص أو تم حظر السيرفر.")
        await wm.edit_text("📤 جاري الرفع...")
        for fp in files[:5]:
            fp = ensure_tg_size_limit(fp)
            if fp.endswith('.mp4'):
                with open(fp,'rb') as f: await ctx.bot.send_video(cid, f, caption=f"📸 {title[:50]}", supports_streaming=True)
            else:
                with open(fp,'rb') as f: await ctx.bot.send_photo(cid, f, caption=f"📸 {title[:50]}")
        await wm.delete()
    except Exception as e: await wm.edit_text("❌ حدث خطأ أو الحساب خاص.")
    finally: shutil.rmtree(tmp, ignore_errors=True)

# ═══════════════════════════════════════════════════════════════════
# 7. الأوامر العامة والأزرار (Callback)
# ═══════════════════════════════════════════════════════════════════
async def cmd_help(upd, ctx): await upd.message.reply_text("❓ أرسل أي رابط وسيتم التحميل تلقائياً! 🚀")
async def cmd_ping(upd, ctx): await upd.message.reply_text("🏓 البوت شغال وبأفضل حال!")
async def cmd_start(upd, ctx): await upd.message.reply_text("👋 أهلاً بك! أرسل أي رابط وسأقوم بالواجب 🚀")

async def btn_cb(upd, ctx):
    q = upd.callback_query; d = q.data; await q.answer()
    if d.startswith("cmd_"):
        m = {"cmd_main":(TEXT_MAIN,mk_main()),"cmd_admin":(TEXT_ADMIN,mk_back()),"cmd_fun":(TEXT_FUN,mk_back()),"cmd_dl":(TEXT_DL,mk_back())}
        if d in m: await q.edit_message_text(m[d][0], parse_mode="HTML", reply_markup=m[d][1])
        return

    if d.startswith("dl_"):
        parts = d.split('_', 3)
        action, uid, uhash = parts[1], parts[2], parts[3]
        if str(q.from_user.id) != uid: return
        url = ctx.bot_data.get(uhash)
        if not url: return await q.edit_message_text("❌ الرابط منتهي الصلاحية.")
        
        await q.edit_message_text("⏳ جاري سحب ومعالجة الملف المتوافق...")
        mt = "audio" if action == "audio" else "video"
        ql = action.replace("v","") if action.startswith("v") else "720"
        
        fp, title, tmp = await do_download(url, mt, ql, q.message.message_id, q.message.chat_id, ctx, q.message.message_id)
        if fp and os.path.exists(fp):
            if mt == "video": fp = ensure_tg_size_limit(fp)
            await q.edit_message_text("📤 جاري الرفع التليجرام الحين...")
            try:
                with open(fp, 'rb') as f:
                    if mt == "audio": await ctx.bot.send_audio(q.message.chat_id, f, title=title)
                    else: await ctx.bot.send_video(q.message.chat_id, f, caption=f"✅ {title[:50]}", supports_streaming=True)
                await q.message.delete()
            except: await q.edit_message_text("❌ حدث خطأ أثناء الرفع الحجمي.")
        else:
            await q.edit_message_text("❌ فشل معالجة يوتيوب، السيرفر محظور حالياً.")
        if tmp: shutil.rmtree(tmp, ignore_errors=True)
    if d == "convert_cancel":
        try: await q.message.delete()
        except: pass

# ═══════════════════════════════════════════════════════════════════
# 10. معالج الرسائل
# ═══════════════════════════════════════════════════════════════════
async def handle_msg(upd, ctx):
    msg = upd.message; text = (msg.text or "").strip(); cid = msg.chat_id; uid = msg.from_user.id
    if not text or text.startswith('/'): return
    if text == "الاوامر": return await msg.reply_text(TEXT_MAIN, parse_mode="HTML", reply_markup=mk_main())

    if re.search(r'music\.youtube\.com', text, re.I) or re.search(r'soundcloud\.com', text, re.I): await music_handler(upd, ctx, text, cid, "🎵")
    elif re.search(r'(youtube\.com|youtu\.be|shorts)', text, re.I): await yt_handler(upd, ctx, text, uid)
    elif re.search(r'(x\.com|twitter\.com)', text, re.I): await x_handler(upd, ctx, text, uid)
    elif re.search(r'(tiktok\.com|vm\.tiktok)', text, re.I): await tiktok_handler(upd, ctx, text, cid, msg.message_id)
    elif re.search(r'(facebook\.com|fb\.watch|fb\.com)', text, re.I): await fb_handler(upd, ctx, text, uid)
    elif re.search(r'instagram\.com', text, re.I): await insta_handler(upd, ctx, text, cid)
    elif re.search(r'spotify\.com', text, re.I): await spotify_handler(upd, ctx, text, cid)
    elif re.search(r'(pinterest\.com|pin\.it)', text, re.I): await pinterest_handler(upd, ctx, text, cid)

# ═══════════════════════════════════════════════════════════════════
# 11. تشغيل وإدارة تطبيق البوت و الـ Keep Alive
# ═══════════════════════════════════════════════════════════════════
async def _keep_alive(app):
    url = os.environ.get('RENDER_EXTERNAL_URL', '').strip()
    if not url: return
    logger.info(f"✅ keep_alive started → {url}")
    while True:
        await asyncio.sleep(600)
        try:
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, lambda: requests.get(url, timeout=15))
        except: pass

def _start_health_server():
    from http.server import HTTPServer, BaseHTTPRequestHandler
    class _H(BaseHTTPRequestHandler):
        def do_GET(self): self.send_response(200); self.end_headers(); self.wfile.write(b"OK - Bot is running!")
        def log_message(self, *a): pass
    port = int(os.environ.get('PORT', 10000))
    try:
        srv = HTTPServer(('0.0.0.0', port), _H)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
    except Exception as e: logger.warning(f"Health server error: {e}")

def main():
    token = os.environ.get("BOT_TOKEN", "")
    if not token: return logger.error("❌ BOT_TOKEN empty!")
    
    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("ping", cmd_ping))
    app.add_handler(CallbackQueryHandler(btn_cb, pattern=r"^(cmd_|dl_|convert_)"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_msg))
    
    _start_health_server()
    
    async def _post_init(app):
        asyncio.create_task(_keep_alive(app))
    app.post_init = _post_init

    logger.info("🚀 البوت انطلق بنجاح!")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
