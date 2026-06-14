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
            # ضغط الفيديو باستخدام ترميز x264 وتحديد الحجم الأقصى بـ 48 ميجا
            subprocess.run([
                FFMPEG, "-i", fp, 
                "-vcodec", "libx264", "-crf", "30", 
                "-acodec", "aac", "-b:a", "128k",
                "-fs", "48M", "-y", tmp_out
            ], capture_output=True, timeout=300)
            if os.path.exists(tmp_out) and os.path.getsize(tmp_out) > 0:
                os.remove(fp)
                logger.info(f"✅ تم ضغط الملف بنجاح إلى: {os.path.getsize(tmp_out)}0")
                return tmp_out
        except Exception as e:
            logger.error(f"❌ فشل ضغط الملف: {e}")
    return fp

# ═══════════════════════════════════════════════════════════════════
# 1. القوائم والمحتوى
# ═══════════════════════════════════════════════════════════════════
WA3ED_LIST = [
    "عيونها السود والبيض 👀",
    " هلا بالحلو \ ة 🌸",
    "مالي خلقك 😏",
    "اتسرسح منا وليدي 😤",
    "انا هسة مشغولة 😅",
]
KHAYROK_LIST = [
    "لو خيروك: تسافر للمستقبل لو للماضي? ⏳",
    "لو خيروك: تاكل بيتزا طول عمرك لو بركر? 🍕🍔",
    "لو خيروك: غني بلا أصدقاء، لو فقير وعندك أحباء? 💰",
    "لو خيروك: تقرأ أفكار الناس لو تطير? 🦅",
    "لو خيروك: ما تنام أبد لو ما تأكل أبد? 😴",
]
JOKES_LIST = [
    "شلون النملة تعدّ حياتها؟ — تحسب سنين! 🐜😂",
    "شو يقول الصفر للرقم 8؟ — حزامك ظاهر! 😄",
    "ليش الكمبيوتر بارد؟ — لأن عنده ويندوز! 🪟",
    "شو يقول السمكة لما اصطدمت بالحائط؟ — دام! 🐟",
]
LANG_FLAG = {
    'ar':'🇸🇦','en':'🇬🇧','tr':'🇹🇷','fa':'🇮🇷','ru':'🇷🇺',
    'fr':'🇫🇷','de':'🇩🇪','es':'🇪🇸','hi':'🇮🇳','zh':'🇨🇳',
    'ja':'🇯🇵','ko':'🇰🇷','pt':'🇧🇷','it':'🇮🇹','uk':'🇺🇦',
}
TEXT_MAIN = "📋 <b>لوحة أوامر البوت</b>\n\nاختر القسم 👇"
TEXT_ADMIN = (
    "👑 <b>أوامر الإدارة:</b>\n"
    "• <code>رفع مالك | مدير | مميز</code> / <code>تنزيل رتبة</code>\n"
    "• <code>طرد | حظر | فك حظر | كتم | الغاء كتم</code>\n"
    "• <code>تثبيت | الغاء تثبيت</code>\n"
    "• <code>قفل الشات | فتح الشات</code>\n"
    "• <code>تحذير | الغاء تحذير | تحذيراتي</code>\n"
    "• <code>منع كلمة X | حذف كلمة X | الكلمات</code>\n"
    "• <code>منع ملصقات | منع قيف | منع مقاطع | منع صور</code>\n"
    "• <code>تفعيل ملصقات | تفعيل قيف | تفعيل مقاطع | تفعيل صور</code>\n"
    "• <code>اضافة رد X | Y</code> / <code>حذف رد X</code> / <code>قائمة الردود</code>\n"
    "• <code>الترحيب تشغيل/ايقاف</code> / <code>تعديل تشغيل/ايقاف</code>\n"
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
    "🎵 تيك توك + 🇨🇳 دوين — فيديو وصور (بدون حد)\n"
    "📘 فيس بوك — مقاطع ريلز بافضل جودة\n"
    "📸 انستغرام — ريلز وبوستات* \n"
    "📌 بينترست — فيديو وصور\n"
    "🎵 ساوند كلاود — تحميل موسيقى MP3\n"
    "🎵 يوتيوب ميوزك — تحميل MP3 320kbps\n\n"
    "🎵 <b>معلومات تيك توك:</b>\n"
    "• <code>تيك @username</code>\n\n"
    "💡 أرسل الرابط مباشرة!"
)

def mk_main(): return InlineKeyboardMarkup([[
    InlineKeyboardButton("🛡️ الإدارة", callback_data="cmd_admin"),
    InlineKeyboardButton("🎮 التسلية", callback_data="cmd_fun")],
    [InlineKeyboardButton("📥 التحميل", callback_data="cmd_dl")]])
def mk_back(): return InlineKeyboardMarkup([[InlineKeyboardButton("🔙 القائمة", callback_data="cmd_main")]])

# ═══════════════════════════════════════════════════════════════════
# 2. قاعدة البيانات SQLite
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
    if not data:
        logger.info("ℹ️ COOKIES_DATA not set")
        return
    success = False
    try:
        clean = ''.join(data.split())
        content = base64.b64decode(clean + '==').decode('utf-8')
        if '\t' in content:
            with open('cookies.txt', 'w', encoding='utf-8') as f:
                f.write(content)
            lines = [l for l in content.splitlines() if l and not l.startswith('#') and '\t' in l]
            domains = set(l.split('\t')[0].lstrip('.') for l in lines)
            logger.info(f"✅ cookies.txt loaded (base64) — {len(lines)} cookies — {domains}")
            success = True
    except Exception as e:
        logger.warning(f"[cookies] base64 failed: {e}")
    if not success:
        try:
            if '\t' in data:
                with open('cookies.txt', 'w', encoding='utf-8') as f:
                    f.write(data)
                logger.info("✅ cookies.txt loaded (plain text)")
                success = True
        except Exception as e:
            logger.error(f"[cookies] plain text failed: {e}")
    if not success:
        logger.error("❌ Failed to load cookies from COOKIES_DATA")
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
                if value is None:
                    c.execute('DELETE FROM kv WHERE path=?', (path,))
                else:
                    c.execute('INSERT OR REPLACE INTO kv (path,value) VALUES (?,?)',
                              (path, json.dumps(value, ensure_ascii=False)))
                c.commit()
        except Exception as e: logger.error(f"DB error: {e}")

def get_settings(cid):
    return db_get(f"settings/{cid}", {
        "welcome":True,"banned_words":[],"locked":False,
        "edit_notify":True,"ai_mode":False,
        "ban_stickers":False,"ban_gifs":False,"ban_videos":False,"ban_photos":False
    })
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
            text = val if val != '' else ' '
            cb_data = f"ttt_{gid}_{idx}" if val == '' else "ttt_noop"
            row.append(InlineKeyboardButton(text, callback_data=cb_data))
        inline_board.append(row)
    control_row = [
        InlineKeyboardButton("🔄 إعادة", callback_data=f"ttt_reset_{gid}"),
        InlineKeyboardButton("❌ إلغاء", callback_data="convert_cancel")
    ]
    inline_board.append(control_row)
    return InlineKeyboardMarkup(inline_board)

def ttt_winner(b):
    win_coords = [(0,1,2), (3,4,5), (6,7,8), (0,3,6), (1,4,7), (2,5,8), (0,4,8), (2,4,6)]
    for r in win_coords:
        if b[r[0]] == b[r[1]] == b[r[2]] != '':
            return b[r[0]]
    return None

def ttt_bot(b):
    empty_cells = [i for i, x in enumerate(b) if x == '']
    if empty_cells:
        return random.choice(empty_cells)
    return None

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
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {"maxOutputTokens": 1000, "temperature": 0.8}
    }
    def _call():
        try:
            r = requests.post(url, json=payload, timeout=30)
            if not api_key: return "❌ GEMINI_KEY غير مضاف. أضفه كـ environment variable."
            if r.status_code in (401, 403): return "❌ مفتاح Gemini منتهي أو غلط. راجع GEMINI_KEY."
            if r.status_code == 429:
                import time; time.sleep(12)
                r2 = requests.post(url, json=payload, timeout=30)
                if r2.status_code == 200:
                    return r2.json()["candidates"][0]["content"]["parts"][0]["text"]
                return "⚠️ Gemini مشغول الحين (free tier limit). انتظر دقيقة وأعد المحاولة."
            if r.status_code == 400:
                return f"❌ خطأ في الطلب"
            r.raise_for_status()
            return r.json()["candidates"][0]["content"]["parts"][0]["text"]
        except Exception as e: logger.error(f"[AI] {e}"); return f"❌ خطأ: مساعد الذكاء الاصطناعي لم يستجب."
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
        'geo_bypass': True, 'extractor_retries': 5, 'retries': 5,
        'ffmpeg_location': FFMPEG,
        'progress_hooks': [lambda d: _progress(d, mid)],
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept': 'text/html,application/xhtml+xml,*/*;q=0.8',
        },
    }
    if os.path.exists('cookies.txt'): opts['cookiefile'] = 'cookies.txt'
    return opts

def get_qualities(url: str):
    is_yt = bool(re.search(r'(youtube\.com|youtu\.be)', url))
    try:
        opts = {**_base_opts(0), 'skip_download': True}
        opts.pop('progress_hooks')
        if is_yt:
            opts['extractor_args'] = {'youtube': {'player_client': ['android', 'ios', 'web']}}
        with YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
            format_map = {}
            for f in info.get('formats', []):
                h = f.get('height')
                vcodec = f.get('vcodec','none')
                if not h or vcodec == 'none': continue
                tbr = f.get('tbr') or f.get('vbr') or 0
                if h not in format_map or tbr > format_map[h]['tbr']:
                    format_map[h] = {'id': f['format_id'], 'tbr': tbr, 'ext': f.get('ext','mp4')}
            return format_map, info
    except Exception as e:
        logger.error(f"[qualities] {e}")
        return {}, None

def build_quality_kb(format_map, uid, uhash, emoji="🎬"):
    standard = [2160,1440,1080,720,480,360,240,144]
    if isinstance(format_map, dict):
        avail = sorted([h for h in format_map if h], reverse=True)
        avail = [q for q in standard if any(abs(a-q)<=q*0.15 for a in avail)]
    else:
        avail = [q for q in standard if any(h >= q*0.85 for h in (format_map or []))]
    avail = avail[:6] if avail else [720,480,360]
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
    is_yt = bool(re.search(r'(youtube\.com|youtu\.be|music\.youtube)', url))
    
    if is_yt:
        opts['extractor_args'] = {'youtube': {'player_client': ['android', 'ios']}}

    if media_type == "audio":
        opts['format'] = 'bestaudio[ext=m4a]/bestaudio/best'
        opts['writethumbnail'] = True
        opts['postprocessors'] = [
            {'key':'FFmpegExtractAudio','preferredcodec':'mp3','preferredquality':'320'},
            {'key':'FFmpegMetadata','add_metadata':True},
            {'key':'EmbedThumbnail'},
        ]
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
    except Exception as e:
        logger.error(f"[download] {e}")
        active_dl.pop(mid, None); task.cancel()
        return None, None, tmp

def tiktok_api(url: str):
    encoded = requests.utils.quote(url, safe='')
    api_urls = [
        f'https://www.tikwm.com/api/?url={encoded}&hd=1',
        f'https://tikwm.com/api/?url={encoded}&hd=1',
    ]
    headers = {'User-Agent': 'Mozilla/5.0'}
    for api_url in api_urls:
        try:
            r = requests.get(api_url, timeout=20, headers=headers)
            if r.status_code != 200: continue
            j = r.json()
            if j.get('code') == 0 and 'data' in j:
                d = j['data']
                author = d.get('author', {}).get('unique_id','مجهول') if isinstance(d.get('author'), dict) else 'مجهول'
                music = d.get('music_info', {}).get('play','') if isinstance(d.get('music_info'), dict) else d.get('music','')
                if d.get('images'): return {'type':'images','data':d['images'],'author':author,'music':music}
                vid = d.get('hdplay') or d.get('play')
                if vid: return {'type':'video','data':vid,'author':author,'music':music}
        except: pass
    return None

# ═══════════════════════════════════════════════════════════════════
# 6. معالجات منصات ومواقع التواصل
# ═══════════════════════════════════════════════════════════════════
async def yt_handler(upd, ctx, url, uid):
    msg = upd.message
    wm = await msg.reply_text("🔍 جاري جلب معلومات الفيديو من يوتيوب...")
    has_cookies = os.path.exists('cookies.txt')

    def _get_info():
        clients = [['android'], ['ios'], ['web']]
        for client in clients:
            try:
                opts = {
                    'quiet': True, 'noplaylist': True, 'nocheckcertificate': True,
                    'skip_download': True, 'geo_bypass': True,
                    'extractor_args': {'youtube': {'player_client': client}},
                }
                if has_cookies: opts['cookiefile'] = 'cookies.txt'
                with YoutubeDL(opts) as ydl:
                    return ydl.extract_info(url, download=False)
            except Exception as e: logger.warning(f"YT client {client} failed: {e}")
        return None

    info = await asyncio.get_running_loop().run_in_executor(None, _get_info)
    if not info:
        hint = "\n\n🍪 <b>ملاحظة:</b> سيرفرات ريندر تحتاج كوكيز حديثة جداً لتخطي حظر بوتات يوتيوب. يرجى تجديد COOKIES_DATA."
        return await wm.edit_text("❌ <b>فشل جلب بيانات اليوتيوب بسبب حظر المنصة (Bot Block)</b>" + hint, parse_mode="HTML")

    format_map = {}
    for f in info.get('formats', []):
        h = f.get('height')
        if h and f.get('vcodec','none') != 'none': format_map[h] = {'id': f['format_id']}

    uhash = str(random.randint(10000,99999))
    ctx.bot_data[uhash] = url
    kb = build_quality_kb(format_map, uid, uhash, "🎬")
    cap = f"🎬 <b>{info.get('title','')[:60]}</b>"
    
    try:
        if info.get('thumbnail'): await ctx.bot.send_photo(msg.chat_id, info['thumbnail'], caption=cap, parse_mode="HTML", reply_markup=kb); await wm.delete()
        else: await wm.edit_text(cap, parse_mode="HTML", reply_markup=kb)
    except: await wm.edit_text(cap, parse_mode="HTML", reply_markup=kb)

async def auto_download(upd, ctx, url, cid, platform="🎬", max_height=720):
    msg = upd.message
    wm = await msg.reply_text(f"{platform} جاري التحميل تلقائياً...")
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
            # فحص وضغط الحجم تلقائياً لتفادي أخطاء الرفع
            fp = ensure_tg_size_limit(fp)
            await wm.edit_text("📤 جاري الرفع لتليجرام...")
            with open(fp, 'rb') as f:
                await ctx.bot.send_video(cid, f, caption=f"{platform} {title[:60]}", supports_streaming=True)
            await wm.delete()
        else:
            await wm.edit_text("❌ فشل تحميل الملف. تأكد أن الرابط عام وصحيح.")
    except Exception as e:
        active_dl.pop(msg.message_id, None); prog_task.cancel()
        await wm.edit_text(f"❌ حدث خطأ أثناء المعالجة أو الرفع.")
    finally: shutil.rmtree(tmp, ignore_errors=True)

async def fb_handler(upd, ctx, url, uid): await auto_download(upd, ctx, url, upd.message.chat_id, "📘", 720)
async def x_handler(upd, ctx, url, uid): await auto_download(upd, ctx, url, upd.message.chat_id, "🐦", 720)

async def tiktok_handler(upd, ctx, url, cid, reply_id):
    msg = upd.message; wm = await msg.reply_text("⏳ جاري التحميل من تيك توك...")
    data = await asyncio.get_running_loop().run_in_executor(None, lambda: tiktok_api(url))
    if data:
        try:
            if data['type'] == 'images':
                media = [InputMediaPhoto(img) for img in data['data'][:10]]
                await ctx.bot.send_media_group(cid, media, reply_to_message_id=reply_id)
            else:
                await ctx.bot.send_video(cid, data['data'], caption=f"👤 @{data['author']}", reply_to_message_id=reply_id, supports_streaming=True)
            return await wm.delete()
        except: pass
    await wm.delete(); await auto_download(upd, ctx, url, cid, "🎵", 720)

async def _insta_download_and_send(ctx, cid, url, wm, username="", download_all=False, is_story=False):
    tmp = tempfile.mkdtemp()
    opts = {**_base_opts(1), 'outtmpl': os.path.join(tmp, '%(id)s.%(ext)s'), 'format': 'bestvideo[height<=720]+bestaudio/best'}
    
    def _dl():
        with YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            files = [os.path.join(tmp, f) for f in os.listdir(tmp) if f.endswith(('.mp4','.jpg','.png','.jpeg'))]
            return files, info.get('title', 'Instagram')

    try:
        files, title = await asyncio.get_running_loop().run_in_executor(None, _dl)
        if not files: return await wm.edit_text("❌ لم يتم العثور على ميديا عامة للتحميل.")
        await wm.edit_text("📤 جاري الرفع...")
        for fp in files:
            fp = ensure_tg_size_limit(fp)
            if fp.endswith('.mp4'):
                with open(fp,'rb') as f: await ctx.bot.send_video(cid, f, caption=f"📸 {title[:50]}", supports_streaming=True)
            else:
                with open(fp,'rb') as f: await ctx.bot.send_photo(cid, f, caption=f"📸 {title[:50]}")
        await wm.delete()
    except Exception as e:
        await wm.edit_text("❌ حدث خطأ أو الحساب خاص/محمي.")
    finally: shutil.rmtree(tmp, ignore_errors=True)

async def insta_handler(upd, ctx, url, cid):
    wm = await upd.message.reply_text("📸 جاري التحميل من انستغرام...")
    await _insta_download_and_send(ctx, cid, url, wm)

async def insta_stories_handler(upd, ctx, username, cid):
    username = username.lstrip('@').strip()
    await upd.message.reply_text("💡 جرب إرسال رابط الستوري المباشر ليتم تحميله.")

async def pinterest_handler(upd, ctx, url, cid): await auto_download(upd, ctx, url, cid, "📌", 720)

async def music_handler(upd, ctx, url, cid, platform="🎵"):
    msg = upd.message; wm = await msg.reply_text(f"{platform} جاري معالجة وتحميل الصوت الحين...")
    tmp = tempfile.mkdtemp()
    opts = {
        **_base_opts(msg.message_id), 'outtmpl': os.path.join(tmp,'%(title)s.%(ext)s'),
        'format': 'bestaudio/best', 'writethumbnail': True,
        'postprocessors': [{'key':'FFmpegExtractAudio','preferredcodec':'mp3','preferredquality':'320'},
                           {'key':'FFmpegMetadata','add_metadata':True}, {'key':'EmbedThumbnail'}]
    }
    if 'youtube' in url: opts['extractor_args'] = {'youtube': {'player_client': ['android','ios']}}
    
    def _dl():
        with YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            files = [os.path.join(tmp, f) for f in os.listdir(tmp) if f.endswith('.mp3')]
            return files[0] if files else None, info.get('title','Audio')
            
    try:
        fp, title = await asyncio.get_running_loop().run_in_executor(None, _dl)
        if fp and os.path.exists(fp):
            await wm.edit_text("📤 جاري الرفع الموسيقى...")
            with open(fp,'rb') as f: await ctx.bot.send_audio(cid, f, title=title)
            await wm.delete()
        else: await wm.edit_text("❌ فشل استخراج الصوت.")
    except Exception as e: await wm.edit_text("❌ فشل التحميل. يوتيوب يفرض قيوداً على السيرفر.")
    finally: shutil.rmtree(tmp, ignore_errors=True)

async def spotify_handler(upd, ctx, url, cid):
    msg = upd.message; wm = await msg.reply_text("🎧 سبوتيفاي: جاري البحث والتحميل...")
    tmp = tempfile.mkdtemp()
    
    def _dl():
        # استخدام تطبيق الاستدعاء لـ spotdl وتوفير بيئة مسار الـ ffmpeg
        import sys
        env = os.environ.copy()
        env['PATH'] = os.path.dirname(FFMPEG) + os.pathsep + env.get('PATH', '')
        cmd = [sys.executable, '-m', 'spotdl', url, '--output', tmp, '--format', 'mp3', '--bitrate', '320k', '--threads', '1']
        subprocess.run(cmd, cwd=tmp, capture_output=True, env=env, timeout=180)
        return [os.path.join(tmp, f) for f in os.listdir(tmp) if f.endswith('.mp3')]

    try:
        files = await asyncio.get_running_loop().run_in_executor(None, _dl)
        if not files:
            # رسالة مساعدة ذكية للمستخدم عند فشل السيرفر
            return await wm.edit_text("❌ فشل التحميل التلقائي من سبوتيفاي بسبب حظر آيبي الاستضافة.\n\n💡 <b>البديل الأسهل:</b> انسخ رابط الأغنية من تطبيق يوتيوب ميوزك (music.youtube.com) وأرسله هنا مباشرة وسأقوم بتحميله لك فوراً! 🎵", parse_mode="HTML")
        await wm.edit_text("📤 جاري الرفع المقطع الصوت...")
        for fp in files[:5]:
            with open(fp, 'rb') as f: await ctx.bot.send_audio(cid, f, title=os.path.basename(fp).rsplit('.',1)[0])
        await wm.delete()
    except Exception as e: await wm.edit_text("❌ فشل تحميل سبوتيفاي.")
    finally: shutil.rmtree(tmp, ignore_errors=True)

async def tiktok_user_info(upd, ctx, username, cid):
    await upd.message.reply_text("🔍 ميزة معلومات الحساب قيد الصيانة المؤقتة.")

# ═══════════════════════════════════════════════════════════════════
# 7. الأوامر العامة والـ Helpers
# ═══════════════════════════════════════════════════════════════════
async def cmd_help(upd, ctx):
    await upd.message.reply_text("❓ أرسل أي رابط من (يوتيوب، انستا، فيس، تيك توك، ساوند كلاود) مباشرة وسيتم تحميله تلقائياً! 🚀")

async def cmd_ping(upd, ctx):
    await upd.message.reply_text("🏓 <b>البوت شغال وبأفضل حال!</b>", parse_mode="HTML")

async def cmd_id(upd, ctx):
    t = upd.message.reply_to_message.from_user if upd.message.reply_to_message else upd.message.from_user
    await upd.message.reply_text(f"🆔 ID: <code>{t.id}</code>", parse_mode="HTML")

async def cmd_start(upd, ctx):
    await upd.message.reply_text("👋 أهلاً بك في بوت التحميل الذكي الحجم السريع! أرسل أي رابط وسأقوم بالواجب 🚀")

# ═══════════════════════════════════════════════════════════════════
# 9. معالج الأزرار التفاعلية Callback
# ═══════════════════════════════════════════════════════════════════
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
        if not url: return await q.edit_message_text("❌ الرابط منتهي الصلاحية، يرجى إرساله مجدداً.")
        
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
# 10. معالجات الأحداث والرسائل والمجموعات
# ═══════════════════════════════════════════════════════════════════
async def welcome_handler(upd, ctx): pass
async def edit_handler(upd, ctx): pass
async def media_filter(upd, ctx): pass
async def track_msg(upd, ctx): pass

async def handle_msg(upd, ctx):
    msg = upd.message; text = (msg.text or "").strip(); cid = msg.chat_id; uid = msg.from_user.id
    if not text or text.startswith('/'): return

    if text == "الاوامر": return await msg.reply_text(TEXT_MAIN, parse_mode="HTML", reply_markup=mk_main())

    # فحص الروابط بشكل مرن وتلقائي
    if re.search(r'music\.youtube\.com', text, re.I) or re.search(r'soundcloud\.com', text, re.I):
        await music_handler(upd, ctx, text, cid, "🎵")
    elif re.search(r'(youtube\.com|youtu\.be|shorts)', text, re.I):
        await yt_handler(upd, ctx, text, uid)
    elif re.search(r'(x\.com|twitter\.com)', text, re.I):
        await x_handler(upd, ctx, text, uid)
    elif re.search(r'(tiktok\.com|vm\.tiktok)', text, re.I):
        await tiktok_handler(upd, ctx, text, cid, msg.message_id)
    elif re.search(r'(facebook\.com|fb\.watch|fb\.com)', text, re.I):
        await fb_handler(upd, ctx, text, uid)
    elif re.search(r'instagram\.com', text, re.I):
        await insta_handler(upd, ctx, text, cid)
    elif re.search(r'spotify\.com', text, re.I):
        await spotify_handler(upd, ctx, text, cid)
    elif re.search(r'(pinterest\.com|pin\.it)', text, re.I):
        await pinterest_handler(upd, ctx, text, cid)

# ═══════════════════════════════════════════════════════════════════
# 11. تشغيل وإدارة تطبيق البوت
# ═══════════════════════════════════════════════════════════════════
def _start_health_server():
    from http.server import HTTPServer, BaseHTTPRequestHandler
    class _H(BaseHTTPRequestHandler):
        def do_GET(self): self.send_response(200); self.end_headers(); self.wfile.write(b"OK")
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
    app.add_handler(CommandHandler("id", cmd_id))
    app.add_handler(CallbackQueryHandler(btn_cb, pattern=r"^(cmd_|dl_|convert_)"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_msg))
    
    _start_health_server()
    logger.info("🚀 البوت انطلق بنجاح!")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
