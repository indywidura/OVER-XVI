import discord
from discord.ext import commands
from discord import ui
from pymongo import MongoClient
import datetime, asyncio, re, io, csv, threading, os
from flask import Flask, jsonify
import pytesseract
from PIL import Image

# ================= CONFIG =================
TOKEN = os.getenv('TOKEN') 
MONGO_URL = os.getenv('MONGO_URL')

# Integrasi Nixpacks/Tesseract
# Jika di Windows lokal, arahkan path ke tesseract.exe Anda
# pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

bot = commands.Bot(
    command_prefix="!",
    intents=discord.Intents.all(),
    help_command=None
)

# Database MongoDB untuk Skala Besar (1000+ Player)
db = MongoClient(MONGO_URL)["over_xvi_db"]
col = db["timeattack"]
events = db["events"]

user_cooldowns = {}

# ================= WEB SERVER (Flask) =================
app = Flask(__name__)

@app.route("/")
def home(): 
    total_entries = col.count_documents({})
    active_events = events.count_documents({})
    return jsonify({
        "status": "Online",
        "total_players_recorded": total_entries,
        "active_events": active_events,
        "bot_name": str(bot.user) if bot.user else "Starting..."
    })

def run_web():
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)

# ================= HELPER & OCR ENGINE =================
def parse_time(t):
    if not re.match(r'^\d{2}:\d{2}\.\d{3}$', t): return None
    try:
        m, s_ms = t.split(":")
        s, ms = s_ms.split(".")
        return int(m)*60 + int(s) + float(f"0.{ms}")
    except: return None

def scan_time(image_bytes):
    """Fungsi Mata AI untuk membaca screenshot"""
    try:
        img = Image.open(io.BytesIO(image_bytes))
        img = img.convert('L') # Pre-processing: Grayscale
        text = pytesseract.image_to_string(img)
        match = re.search(r'\d{2}:\d{2}\.\d{3}', text)
        return match.group(0) if match else None
    except Exception as e:
        print(f"OCR Error: {e}")
        return None

def is_on_cooldown(member, seconds=30):
    if member.guild_permissions.administrator: return False, 0
    now = datetime.datetime.now()
    if member.id in user_cooldowns:
        diff = (now - user_cooldowns[member.id]).total_seconds()
        if diff < seconds: return True, int(seconds - diff)
    return False, 0

# ================= MODALS =================
class SearchPlayerModal(ui.Modal):
    def __init__(self, event_name):
        super().__init__(title="Pencarian Global Driver")
        self.event_name = event_name
        self.target = ui.TextInput(label="IGN atau ID Game", placeholder="Cari driver di database...")
        self.add_item(self.target)

    async def on_submit(self, i: discord.Interaction):
        search_val = self.target.value.lower()
        query = {
            "event": self.event_name, 
            "approved": True,
            "$or": [{"ign": {"$regex": search_val, "$options": "i"}}, {"game_id": search_val}]
        }
        found_data = list(col.find(query).sort("waktu_raw", 1).limit(1))
        
        if found_data:
            d = found_data[0]
            # Kalkulasi Rank matematis untuk skala 1000+
            rank = col.count_documents({"event": self.event_name, "approved": True, "waktu_raw": {"$lt": d['waktu_raw']}}) + 1
            emb = discord.Embed(title="🔍 HASIL PENCARIAN", color=0x3498db)
            emb.add_field(name="👤 Driver", value=f"**{d['ign']}** (ID: {d.get('game_id','-')})", inline=False)
            emb.add_field(name="🏆 Peringkat", value=f"**#{rank}**", inline=True)
            emb.add_field(name="⏱️ Waktu Terbaik", value=f"`{d['waktu']}`", inline=True)
            await i.response.send_message(embed=emb, ephemeral=True)
        else:
            await i.response.send_message(f"❌ Data **{self.target.value}** tidak ditemukan atau belum disetujui.", ephemeral=True)

class SubmitModal(ui.Modal):
    def __init__(self, event_name):
        super().__init__(title=f"Submit: {event_name}")
        self.event_name = event_name
        self.ign = ui.TextInput(label="IGN (Nickname)", min_length=2, max_length=20)
        self.game_id = ui.TextInput(label="ID Game", placeholder="Contoh: 889922")
        self.time_val = ui.TextInput(label="Waktu (MM:SS.ms)", placeholder="00:55.123")
        for item in [self.ign, self.game_id, self.time_val]: self.add_item(item)

    async def on_submit(self, i: discord.Interaction):
        sec = parse_time(self.time_val.value)
        if not sec: return await i.response.send_message("❌ Format salah! Gunakan `00:00.000`", ephemeral=True)

        await i.response.send_message("📸 Kirim Screenshot bukti balapan ke sini...", ephemeral=True)
        
        try:
            msg = await bot.wait_for("message", timeout=60, check=lambda m: m.author.id == i.user.id and m.attachments)
            img_bytes = await msg.attachments[0].read()
            
            # PROSES KOMPARASI OCR
            detected = scan_time(img_bytes)
            is_match = (detected == self.time_val.value)
            
            entry = {
                "user_id": i.user.id, "event": self.event_name,
                "ign": self.ign.value, "game_id": self.game_id.value,
                "waktu": self.time_val.value, "waktu_raw": sec,
                "approved": is_match, "timestamp": datetime.datetime.now()
            }
            # Upsert untuk Personal Best
            col.update_one({"user_id": i.user.id, "event": self.event_name}, {"$set": entry}, upsert=True)
            
            if is_match:
                emb = discord.Embed(title="✅ AUTO-VERIFIED", color=0x2ecc71)
                emb.description = f"Rekor **{self.ign.value}** otomatis masuk Leaderboard."
                emb.set_image(url=msg.attachments[0].url)
                await i.channel.send(embed=emb)
            else:
                # Masuk antrean pending jika OCR gagal/beda
                admin_emb = discord.Embed(title="⚠️ PENDING REVIEW (OCR BERBEDA)", color=0xf1c40f)
                admin_emb.add_field(name="Input User", value=self.time_val.value)
                admin_emb.add_field(name="Hasil Scan AI", value=str(detected) or "Tidak Terdeteksi")
                admin_emb.set_image(url=msg.attachments[0].url)
                doc = col.find_one({"user_id": i.user.id, "event": self.event_name})
                await i.channel.send(content="🔔 **LAPORAN UNTUK ADMIN:**", embed=admin_emb, view=ApprovalView(doc['_id']))
            
            try: await msg.delete()
            except: pass
        except:
            await i.followup.send("❌ Gagal upload atau sesi berakhir.", ephemeral=True)

# ================= VIEWS (Admin & Leaderboard) =================
class ApprovalView(ui.View):
    def __init__(self, entry_id):
        super().__init__(timeout=None)
        self.entry_id = entry_id

    @ui.button(label="Approve ✅", style=discord.ButtonStyle.green)
    async def approve(self, i, b):
        col.update_one({"_id": self.entry_id}, {"$set": {"approved": True}})
        await i.response.edit_message(content="✅ Data disetujui Admin!", embed=None, view=None)

    @ui.button(label="Reject ❌", style=discord.ButtonStyle.danger)
    async def reject(self, i, b):
        col.delete_one({"_id": self.entry_id})
        await i.response.edit_message(content="❌ Data ditolak Admin.", embed=None, view=None)

class LeaderboardView(ui.View):
    def __init__(self, event_name, page=0):
        super().__init__(timeout=60)
        self.event_name = event_name
        self.page = page

    async def get_page(self):
        skip = self.page * 10
        data = list(col.find({"event": self.event_name, "approved": True}).sort("waktu_raw", 1).skip(skip).limit(10))
        total = col.count_documents({"event": self.event_name, "approved": True})
        pages = (total - 1) // 10 + 1 if total else 1
        return data, pages

    def make_emb(self, data, pages):
        desc = ""
        for idx, d in enumerate(data):
            rank = (self.page * 10) + idx + 1
            desc += f"**{rank}.** {d['ign']} - `{d['waktu']}`\n"
        emb = discord.Embed(title=f"🏆 LEADERBOARD: {self.event_name}", description=desc or "Belum ada data terverifikasi.", color=0xf1c40f)
        emb.set_footer(text=f"Halaman {self.page+1} dari {pages}")
        return emb

    @ui.button(label="⬅️", style=discord.ButtonStyle.grey)
    async def prev(self, i, b):
        if self.page > 0:
            self.page -= 1
            data, pages = await self.get_page()
            await i.response.edit_message(embed=self.make_emb(data, pages), view=self)
        else: await i.response.defer()

    @ui.button(label="➡️", style=discord.ButtonStyle.grey)
    async def next(self, i, b):
        data, pages = await self.get_page()
        if self.page < pages - 1:
            self.page += 1
            data, pages = await self.get_page()
            await i.response.edit_message(embed=self.make_emb(data, pages), view=self)
        else: await i.response.defer()

    @ui.button(label="🔍 Cari", style=discord.ButtonStyle.blurple)
    async def srch(self, i, b): await i.response.send_modal(SearchPlayerModal(self.event_name))

class AdminMenuView(ui.View):
    def __init__(self, event_name):
        super().__init__(timeout=60)
        self.event_name = event_name

    @ui.button(label="📥 Download CSV", style=discord.ButtonStyle.green)
    async def csv_dl(self, i, b):
        data = list(col.find({"event": self.event_name}).sort("waktu_raw", 1))
        out = io.StringIO()
        writer = csv.writer(out)
        writer.writerow(["RANK", "IGN", "ID GAME", "TIME", "STATUS"])
        for idx, d in enumerate(data):
            writer.writerow([idx+1, d['ign'], d.get('game_id','-'), d['waktu'], "Approved" if d.get('approved') else "Pending"])
        
        mem_file = io.BytesIO(out.getvalue().encode())
        await i.response.send_message(content=f"📊 Data Event: {self.event_name}", file=discord.File(mem_file, f"{self.event_name}.csv"), ephemeral=True)

    @ui.button(label="🗑️ Reset Leaderboard", style=discord.ButtonStyle.danger)
    async def reset(self, i, b):
        col.delete_many({"event": self.event_name})
        await i.response.send_message("🚨 Leaderboard telah dikosongkan!", ephemeral=True)

class MainView(ui.View):
    def __init__(self, event_name):
        super().__init__(timeout=None)
        self.event_name = event_name

    @ui.button(label="Submit Time", style=discord.ButtonStyle.green, custom_id="main_sub")
    async def sub(self, i, b):
        cd, r = is_on_cooldown(i.user)
        if cd: return await i.response.send_message(f"⏳ Tunggu {r} detik.", ephemeral=True)
        await i.response.send_modal(SubmitModal(self.event_name))

    @ui.button(label="Leaderboard", style=discord.ButtonStyle.blurple, custom_id="main_lb")
    async def lb(self, i, b):
        v = LeaderboardView(self.event_name)
        data, pages = await v.get_page()
        await i.response.edit_message(embed=v.make_emb(data, pages), view=v)

    @ui.button(label="Admin Panel", style=discord.ButtonStyle.grey, custom_id="main_adm")
    async def adm(self, i, b):
        if not i.user.guild_permissions.administrator: return await i.response.send_message("❌ Akses Ditolak.", ephemeral=True)
        await i.response.edit_message(embed=discord.Embed(title="🛠️ Admin Control Panel", color=0x2c3e50), view=AdminMenuView(self.event_name))

# ================= COMMANDS & EVENTS =================
@bot.command()
async def ta(ctx):
    ev = events.find_one({"name": ctx.channel.name})
    if not ev: return await ctx.send("❌ Channel ini belum aktif. Gunakan `!create_event`")
    desc = "**SISTEM VERIFIKASI AI (OCR) AKTIF**\nSilakan klik Submit dan upload bukti screenshot balapan Anda."
    emb = discord.Embed(title=f"🏎️ EVENT: {ctx.channel.name.upper()}", description=desc, color=0x3498db)
    await ctx.send(embed=emb, view=MainView(ctx.channel.name))

@bot.command()
@commands.has_permissions(administrator=True)
async def create_event(ctx):
    events.update_one({"name": ctx.channel.name}, {"$set": {"name": ctx.channel.name}}, upsert=True)
    await ctx.send(f"✅ Channel **#{ctx.channel.name}** telah didaftarkan untuk event!")

@bot.event
async def on_ready():
    bot.add_view(MainView("")) # Persisten view
    print(f">>> OVER-XVI BOT SYSTEM ONLINE <<<")
    print(f"Logged in as: {bot.user}")
    threading.Thread(target=run_web, daemon=True).start()

bot.run(TOKEN)
