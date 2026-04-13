import discord
from discord.ext import commands
from discord import ui
from pymongo import MongoClient
import datetime, asyncio, re, io, threading, os
from flask import Flask, jsonify
import pytesseract
from PIL import Image, ImageOps, ImageEnhance
import pandas as pd

# ================= KONFIGURASI SISTEM =================
TOKEN = os.getenv('TOKEN') 
MONGO_URL = os.getenv('MONGO_URL')

bot = commands.Bot(
    command_prefix="!",
    intents=discord.Intents.all(),
    help_command=None
)

# Database Setup
db = MongoClient(MONGO_URL, maxPoolSize=50)["over_xvi_db"]
col = db["timeattack"]
events = db["events"]

# ================= MULTI-LANGUAGE DICTIONARY =================
TRANSLATIONS = {
    "id": {
        "modal_title": "Submit Waktu",
        "ign": "IGN (Nickname)",
        "club": "Nama Club",
        "id_game": "Game ID",
        "time": "Waktu (MM:SS.ms)",
        "invalid_time": "❌ Format Salah! Gunakan **MM:SS.ms**",
        "upload_msg": "📸 Silakan upload screenshot bukti sekarang...",
        "timeout": "❌ Waktu habis! Anda tidak mengupload gambar.",
        "cooldown": "⏳ **COOLDOWN AKTIF!**\nSilakan tunggu **{}m {}s**.",
        "pb_title": "⏱️ Rekor Pribadi Anda",
        "pb_not_found": "❌ Anda belum memiliki rekor yang disetujui di event ini.",
        "pb_rank": "Peringkat",
        "pb_footer": "Terakhir diperbarui: {}"
    },
    "en": {
        "modal_title": "Submit Time",
        "ign": "IGN (Nickname)",
        "club": "Club Name",
        "id_game": "Game ID",
        "time": "Time (MM:SS.ms)",
        "invalid_time": "❌ Invalid Format! Use **MM:SS.ms**",
        "upload_msg": "📸 Please upload screenshot evidence now...",
        "timeout": "❌ Timeout! No image uploaded.",
        "cooldown": "⏳ **COOLDOWN ACTIVE!**\nPlease wait **{}m {}s**.",
        "pb_title": "⏱️ Your Personal Best",
        "pb_not_found": "❌ You don't have an approved record in this event yet.",
        "pb_rank": "Rank",
        "pb_footer": "Last updated: {}"
    },
    "th": {
        "modal_title": "ส่งเวลา",
        "ign": "ชื่อในเกม (IGN)",
        "club": "ชื่อคลับ",
        "id_game": "ไอดีเกม",
        "time": "เวลา (นาที:วินาที.มิลลิวินาที)",
        "invalid_time": "❌ รูปแบบไม่ถูกต้อง! ใช้ **MM:SS.ms**",
        "upload_msg": "📸 กรุณาอัปโหลดภาพหน้าจอหลักฐานตอนนี้...",
        "timeout": "❌ หมดเวลา! ไม่มีการอัปโหลดภาพ",
        "cooldown": "⏳ **คูลดาวน์ทำงาน!**\nกรุณารอ **{}น {}ว**.",
        "pb_title": "⏱️ สถิติส่วนตัวของคุณ",
        "pb_not_found": "❌ คุณยังไม่มีบันทึกที่ได้รับการอนุมัติในกิจกรรมนี้",
        "pb_rank": "อันดับ",
        "pb_footer": "อัปเดตล่าสุด: {}"
    },
    "ph": {
        "modal_title": "I-submit ang Oras",
        "ign": "IGN (Nickname)",
        "club": "Pangalan ng Club",
        "id_game": "Game ID",
        "time": "Oras (MM:SS.ms)",
        "invalid_time": "❌ Maling Format! Gamitin ang **MM:SS.ms**",
        "upload_msg": "📸 Mangyaring i-upload ang screenshot ngayon...",
        "timeout": "❌ Ubos na ang oras! Walang na-upload na larawan.",
        "cooldown": "⏳ **COOLDOWN AKTIBO!**\nMaghintay ng **{}m {}s**.",
        "pb_title": "⏱️ Iyong Personal Best",
        "pb_not_found": "❌ Wala ka pang aprubadong record sa event na ito.",
        "pb_rank": "Ranggo",
        "pb_footer": "Huling na-update: {}"
    },
    "ms": {
        "modal_title": "Hantar Masa",
        "ign": "IGN (Nickname)",
        "club": "Nama Kelab",
        "id_game": "ID Permainan",
        "time": "Masa (MM:SS.ms)",
        "invalid_time": "❌ Format Salah! Gunakan **MM:SS.ms**",
        "upload_msg": "📸 Sila muat naik tangkapan skrin sekarang...",
        "timeout": "❌ Masa tamat! Tiada gambar dimuat naik.",
        "cooldown": "⏳ **COOLDOWN AKTIF!**\nSila tunggu **{}m {}s**.",
        "pb_title": "⏱️ Rekod Peribadi Anda",
        "pb_not_found": "❌ Anda belum mempunyai rekod yang diluluskan dalam acara ini.",
        "pb_rank": "Kedudukan",
        "pb_footer": "Kemaskini terakhir: {}"
    }
}

# ================= WEB SERVER (DASHBOARD) =================
app = Flask(__name__)

@app.route("/")
def home(): 
    return jsonify({
        "bot_status": "Online",
        "total_players": col.count_documents({}),
        "active_events": events.count_documents({}),
        "engine": "Gemini-Powered OCR System"
    })

def run_web():
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)

# ================= UTILS & OCR ENGINE =================
def parse_time(t):
    if not re.match(r'^\d{2}:\d{2}\.\d{3}$', t): 
        return None
    try:
        m, s_ms = t.split(":")
        s, ms = s_ms.split(".")
        return int(m)*60 + int(s) + float(f"0.{ms}")
    except: 
        return None

def scan_time(image_bytes):
    try:
        img = Image.open(io.BytesIO(image_bytes))
        width, height = img.size
        # Crop 50% kiri atas
        img_cropped = img.crop((0, 0, width * 0.50, height * 0.50))
        img_cropped = img_cropped.convert('L')
        img_cropped = ImageEnhance.Contrast(img_cropped).enhance(3.5)
        img_cropped = ImageEnhance.Sharpness(img_cropped).enhance(2.0)
        
        # Invert hanya jika perlu, Tesseract bekerja baik pada teks hitam background putih
        img_cropped = ImageOps.invert(img_cropped) 
        
        custom_config = r'--psm 7 -c tessedit_char_whitelist=0123456789:.'
        text = pytesseract.image_to_string(img_cropped, config=custom_config)
        text = text.replace(" ", "").strip()
        
        match = re.search(r'\d{2}:\d{2}\.\d{3}', text)
        return match.group(0) if match else None
    except Exception as e:
        print(f"DEBUG OCR ERROR: {e}")
        return None

async def update_live_leaderboard(event_name):
    channel = discord.utils.get(bot.get_all_channels(), name=event_name)
    if not channel: return
    data = list(col.find({"event": event_name, "approved": True}).sort("waktu_raw", 1).limit(10))
    
    description = ""
    for idx, d in enumerate(data):
        medal = "🥇" if idx == 0 else "🥈" if idx == 1 else "🥉" if idx == 2 else f"**{idx+1}.**"
        description += f"{medal} {d['ign']} [{d.get('club', 'RFF')}] - `{d['waktu']}`\n"

    emb = discord.Embed(
        title=f"🏆 LIVE LEADERBOARD: {event_name.upper()}",
        description=description or "Belum ada rekor tercatat.",
        color=0xf1c40f,
        timestamp=datetime.datetime.now()
    )
    async for message in channel.history(limit=50):
        if message.author == bot.user and message.embeds:
            if "LIVE LEADERBOARD" in message.embeds[0].title:
                await message.edit(embed=emb)
                return
                
# ================= MODAL DIALOGS =================
class SubmitModal(ui.Modal):
    def __init__(self, event_name, lang_code="en"):
        self.lang = TRANSLATIONS.get(lang_code, TRANSLATIONS["en"])
        super().__init__(title=f"{self.lang['modal_title']}")
        self.event_name = event_name
        self.ign = ui.TextInput(label=self.lang["ign"], min_length=2)
        self.club = ui.TextInput(label=self.lang["club"], default="RFF", required=False)
        self.game_id = ui.TextInput(label=self.lang["id_game"])
        self.time_val = ui.TextInput(label=self.lang["time"], placeholder="00:00.000")
        for item in [self.ign, self.club, self.game_id, self.time_val]: self.add_item(item)

    async def on_submit(self, i: discord.Interaction):
        sec = parse_time(self.time_val.value)
        if not sec:
            return await i.response.send_message(self.lang["invalid_time"], ephemeral=True)
        
        # Langkah 1: Beri instruksi upload
        await i.response.send_message(self.lang["upload_msg"], ephemeral=True)

        try:
            # Langkah 2: Tunggu Gambar
            msg = await bot.wait_for(
                "message", 
                timeout=120, 
                check=lambda m: m.author.id == i.user.id and m.attachments
            )
            
            img_bytes = await msg.attachments[0].read()
            # Langkah 3: Jalankan OCR (pindahkan ke loop executor agar tidak freeze)
            loop = asyncio.get_event_loop()
            detected = await loop.run_in_executor(None, scan_time, img_bytes)

            is_match = (detected == self.time_val.value)
            
            entry = {
                "user_id": i.user.id, "discord_name": str(i.user),
                "event": self.event_name, "ign": self.ign.value,
                "club": self.club.value, "game_id": self.game_id.value,
                "waktu": self.time_val.value, "waktu_raw": sec,
                "evidence_url": msg.attachments[0].url, "approved": is_match,
                "timestamp": datetime.datetime.now()
            }
            
            col.update_one({"user_id": i.user.id, "event": self.event_name}, {"$set": entry}, upsert=True)
            doc = col.find_one({"user_id": i.user.id, "event": self.event_name})

            # Langkah 4: Kirim Hasil ke Channel
            if is_match:
                emb = discord.Embed(title="✅ AUTO APPROVED", color=0x2ecc71)
                emb.add_field(name="Driver", value=self.ign.value)
                emb.add_field(name="Time", value=self.time_val.value)
                emb.set_image(url=msg.attachments[0].url)
                await i.channel.send(embed=emb)
                await update_live_leaderboard(self.event_name)
            else:
                emb = discord.Embed(title="📩 PENDING APPROVAL", color=0xf1c40f)
                emb.add_field(name="Input", value=self.time_val.value)
                emb.add_field(name="AI Scan", value=detected or "Gagal Baca")
                emb.set_image(url=msg.attachments[0].url)
                # ApprovalView akan didefinisikan di bagian selanjutnya
                await i.channel.send(embed=emb, view=ApprovalView(doc['_id']))
            
            await msg.delete()

        except asyncio.TimeoutError:
            await i.followup.send(self.lang["timeout"], ephemeral=True)
            
# ================= INTERACTIVE VIEWS =================
class ApprovalView(ui.View):
    def __init__(self, entry_id):
        super().__init__(timeout=None)
        self.entry_id = entry_id
        
    async def interaction_check(self, i: discord.Interaction):
        if i.user.guild_permissions.administrator: return True
        await i.response.send_message("❌ Akses khusus Administrator!", ephemeral=True)
        return False

    @ui.button(label="✅ Approve", style=discord.ButtonStyle.green)
    async def approve(self, i: discord.Interaction, b: ui.Button):
        approver = i.user.display_name
        old_data = col.find_one({"_id": self.entry_id})
        
        if not old_data:
            return await i.response.send_message("Data tidak ditemukan!", ephemeral=True)

        pb_data = col.find_one({
            "user_id": old_data["user_id"], 
            "event": old_data["event"], 
            "approved": True,
            "_id": {"$ne": self.entry_id}
        })

        diff_msg = ""
        if pb_data:
            diff = pb_data['waktu_raw'] - old_data['waktu_raw']
            if diff > 0:
                diff_msg = f"\n🔥 **NEW PERSONAL BEST!** Improved by `-{diff:.3f}s`"
            elif diff < 0:
                diff_msg = f"\n⚠️ *Note: Time is slower than current PB (+{abs(diff):.3f}s)*"

        col.update_one({"_id": self.entry_id}, {"$set": {"approved": True, "approved_by": approver}})
        
        emb = discord.Embed(title="🌟 NEW RECORD RECORDED", description=diff_msg, color=0x2ecc71)
        emb.add_field(name="👤 Driver", value=f"**{old_data['ign']}**", inline=True)
        emb.add_field(name="⏱️ Time", value=f"`{old_data['waktu']}`", inline=True)
        emb.add_field(name="⚖️ Approved by", value=approver, inline=True)
        
        if "evidence_url" in old_data:
            emb.set_image(url=old_data["evidence_url"])
            
        await i.response.edit_message(content=None, embed=emb, view=None)
        await update_live_leaderboard(old_data["event"])
        
        # Kirim Log Audit
        await send_audit_log(
            event_name=old_data["event"],
            action="MANUAL APPROVAL",
            admin_name=i.user.display_name,
            details=f"Pembalap: **{old_data['ign']}**\nWaktu: `{old_data['waktu']}`",
            color=0x2ecc71
        )
        
    @ui.button(label="❌ Reject", style=discord.ButtonStyle.red)
    async def reject(self, i: discord.Interaction, b: ui.Button):
        data = col.find_one({"_id": self.entry_id})
        if data:
            col.delete_one({"_id": self.entry_id})
            emb_reject = discord.Embed(
                title="❌ SUBMISSION REJECTED",
                description=f"Submit dari **{data['ign']}** telah ditolak oleh Admin.",
                color=0xe74c3c
            )
            emb_reject.add_field(name="Admin", value=i.user.display_name)
            await i.response.edit_message(content=None, embed=emb_reject, view=None)
        else:
            await i.response.send_message("Data tidak ditemukan.", ephemeral=True)

# Catatan: LeaderboardView dan AdminMenuView memerlukan MainView. 
# Pastikan MainView didefinisikan sebelum kelas-kelas ini atau gunakan late-binding.

# ================= NEW: LANGUAGE SELECT VIEW =================
class LanguageSelectView(ui.View):
    """View awal untuk memilih bahasa sebelum masuk ke menu utama"""
    def __init__(self, event_name):
        super().__init__(timeout=60)
        self.event_name = event_name

    @ui.select(
        placeholder="Choose your language / Pilih bahasa anda...",
        options=[
            discord.SelectOption(label="Indonesia", value="id", emoji="🇮🇩"),
            discord.SelectOption(label="English", value="en", emoji="🇬🇧"),
            discord.SelectOption(label="Thailand", value="th", emoji="🇹🇭"),
            discord.SelectOption(label="Philippines", value="ph", emoji="🇵🇭"),
            discord.SelectOption(label="Malaysia", value="ms", emoji="🇲🇾"),
        ]
    )
    async def select_lang(self, i: discord.Interaction, select: ui.Select):
        lang_code = select.values[0]
        emb = discord.Embed(title=f"🏎️ EVENT: {self.event_name.upper()}", color=0x3498db)
        # Teruskan kode bahasa ke MainView
        await i.response.edit_message(embed=emb, view=MainView(self.event_name, lang_code))

class MainView(ui.View):
    def __init__(self, event_name, lang_code="en"):
        super().__init__(timeout=None)
        self.event_name = event_name
        self.lang_code = lang_code
        
    @ui.button(label="Guide / Panduan", style=discord.ButtonStyle.grey, custom_id="btn_guide_v5")
    async def guide_btn(self, i: discord.Interaction, b: ui.Button):
        emb = discord.Embed(
            title="📖 HOW TO USE / CARA PENGGUNAAN", 
            description="Please follow these steps / Silakan ikuti langkah-langkah berikut:",
            color=0x95a5a6
        )
        
        # 🇮🇩 INDONESIA
        id_msg = "1. Klik **Submit Time**\n2. Isi Nickname, ID, & Waktu (MM:SS.ms)\n3. Kirim foto bukti screenshot\n4. Tunggu verifikasi."
        # 🇬🇧 ENGLISH
        en_msg = "1. Click **Submit Time**\n2. Fill IGN, ID, & Time (MM:SS.ms)\n3. Upload screenshot evidence\n4. Wait for verification."
        # 🇹🇭 THAILAND
        th_msg = "1. คลิกที่ **Submit Time**\n2. กรอกชื่อในเกม, ID และเวลา (นาที:วินาที.มิลลิวินาที)\n3. อัปโหลดภาพถ่ายหน้าจอหลักฐาน\n4. รอการตรวจสอบ"
        # 🇵🇭 PHILIPPINES (Tagalog)
        ph_msg = "1. I-click ang **Submit Time**\n2. Ilagay ang IGN, ID, at Oras (MM:SS.ms)\n3. I-upload ang screenshot\n4. Maghintay para sa beripikasyon."
        # 🇲🇾 MALAYSIA
        ms_msg = "1. Klik **Submit Time**\n2. Isi Nickname, ID, & Masa (MM:SS.ms)\n3. Muat naik bukti tangkapan skrin\n4. Tunggu pengesahan."

        emb.add_field(name="🇮🇩 Indonesia", value=id_msg, inline=False)
        emb.add_field(name="🇬🇧 English", value=en_msg, inline=False)
        emb.add_field(name="🇹🇭 ภาษาไทย", value=th_msg, inline=False)
        emb.add_field(name="🇵🇭 Tagalog", value=ph_msg, inline=False)
        emb.add_field(name="🇲🇾 Bahasa Melayu", value=ms_msg, inline=False)
        
        await i.response.send_message("Menampilkan panduan...", ephemeral=True)
        
    @ui.button(label="Submit Time", style=discord.ButtonStyle.green, custom_id="btn_sub_v5")
    async def submit_btn(self, i: discord.Interaction, b: ui.Button):
        user_id = i.user.id
        now = datetime.datetime.now()
        cooldown_seconds = 600
        lang = TRANSLATIONS.get(self.lang_code, TRANSLATIONS["en"])

        # Ambil data terakhir user untuk event ini
        last_entry = col.find_one({"user_id": user_id, "event": self.event_name})
        
        if last_entry and "timestamp" in last_entry and not i.user.guild_permissions.administrator:
            # CEK STATUS APPROVAL
            # Jika status 'approved' adalah True, baru terapkan cooldown.
            # Jika False (ditolak/pending), izinkan submit ulang tanpa tunggu.
            is_approved = last_entry.get("approved", False)
            
            if is_approved:
                last_submit = last_entry["timestamp"]
                elapsed = (now - last_submit).total_seconds()

                if elapsed < cooldown_seconds:
                    rem_m = int((cooldown_seconds - elapsed) // 60)
                    rem_s = int((cooldown_seconds - elapsed) % 60)
                    return await i.response.send_message(
                        lang["cooldown"].format(rem_m, rem_s), 
                        ephemeral=True
                    )
        
        # Mengirim modal dengan bahasa yang dipilih
        # Kirim modal jika lolos pengecekan (atau jika data sebelumnya ditolak)
        await i.response.send_modal(SubmitModal(self.event_name, self.lang_code))

    @ui.button(label="Leaderboard", style=discord.ButtonStyle.blurple, custom_id="btn_lb_v5")
    async def lb_btn(self, i, b):
        v = LeaderboardView(self.event_name)
        d, p = await v.get_stats()
        await i.response.edit_message(embed=v.create_embed(d, p), view=v)

    @ui.button(label="Check My PB", style=discord.ButtonStyle.secondary, custom_id="btn_mypb_v5")
    async def my_pb_btn(self, i: discord.Interaction, b: ui.Button):
        lang = TRANSLATIONS.get(self.lang_code, TRANSLATIONS["en"])
        data = col.find_one({"user_id": i.user.id, "event": self.event_name, "approved": True})
        
        if data:
            # Hitung Ranking
            rank = col.count_documents({
                "event": self.event_name, 
                "approved": True, 
                "waktu_raw": {"$lt": data['waktu_raw']}
            }) + 1
            
            emb = discord.Embed(title=f"{lang['pb_title']}: {self.event_name.upper()}", color=0x9b59b6)
            emb.add_field(name="👤 IGN", value=f"`{data['ign']}`", inline=True)
            emb.add_field(name=f"🏆 {lang['pb_rank']}", value=f"**#{rank}**", inline=True)
            emb.add_field(name="⏱️ Time", value=f"`{data['waktu']}`", inline=True)
            
            time_str = data['timestamp'].strftime('%Y-%m-%d %H:%M')
            emb.set_footer(text=lang['pb_footer'].format(time_str))
            
            if "evidence_url" in data:
                emb.set_thumbnail(url=data["evidence_url"])
                
            await i.response.send_message(embed=emb, ephemeral=True)
        else:
            await i.response.send_message(lang["pb_not_found"], ephemeral=True)

    # ... (Tombol Guide, Submit, Leaderboard, dan Admin tetap ada dengan custom_id) ...
        
    @ui.button(label="Admin Panel", style=discord.ButtonStyle.red, custom_id="btn_adm_v5")
    async def admin_btn(self, i, b):
        if not i.user.guild_permissions.administrator: 
            return await i.response.send_message("🚫 Khusus Admin!", ephemeral=True)
        await i.response.edit_message(embed=discord.Embed(title="🛠️ Admin Control Panel", color=0x2c3e50), view=AdminMenuView(self.event_name))

# ================= COMMANDS =================
@bot.command()
async def ta(ctx):
    if not events.find_one({"name": ctx.channel.name}): 
        return await ctx.send("❌ Event tidak ditemukan di channel ini.")
    
    emb = discord.Embed(
        title="🌐 SELECT LANGUAGE", 
        description="Please select your language first to continue.\nSilakan pilih bahasa terlebih dahulu.",
        color=0x3498db
    )
    await ctx.send(embed=emb, view=LanguageSelectView(ctx.channel.name))

@bot.command()
@commands.has_permissions(administrator=True)
async def create_event(ctx):
    guild = ctx.guild
    event_name = ctx.channel.name

    category = discord.utils.get(guild.categories, name="RACE FOR FUN OFFICIAL LOGS")
    if not category:
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            guild.me: discord.PermissionOverwrite(read_messages=True)
        }
        category = await guild.create_category("RACE FOR FUN OFFICIAL LOGS", overwrites=overwrites)

    log_channel_name = f"log-{event_name}"
    log_channel = discord.utils.get(category.channels, name=log_channel_name)
    
    if not log_channel:
        log_channel = await guild.create_text_channel(log_channel_name, category=category)

    events.update_one(
        {"name": event_name}, 
        {"$set": {
            "name": event_name,
            "log_channel_id": log_channel.id,
            "created_at": datetime.datetime.now()
        }}, 
        upsert=True
    )

    await ctx.send(f"✅ Event **#{event_name}** aktif!\n🛡️ Log Admin: {log_channel.mention}")

@bot.command()
@commands.has_permissions(administrator=True)
async def setup_lb(ctx):
    emb = discord.Embed(title=f"🏆 LIVE LEADERBOARD: {ctx.channel.name.upper()}", description="Menunggu data...", color=0xf1c40f)
    await ctx.send(embed=emb)
    await ctx.message.delete()

@bot.event
async def on_ready():
    try:
        active_events = list(events.find())
        for ev in active_events:
            name = ev.get('name')
            if name:
                bot.add_view(MainView(event_name=name))
        
        print(f">>> OVER-XVI SYSTEM ONLINE <<<")
        print(f"Logged in as: {bot.user.name}")
        print(f"Loaded {len(active_events)} active events.")
    except Exception as e:
        print(f"Error loading persistent views: {e}")

    if not any(t.name == "FlaskThread" for t in threading.enumerate()):
        threading.Thread(target=run_web, name="FlaskThread", daemon=True).start()

bot.run(TOKEN)
