import discord
from discord.ext import commands
from discord import ui
from pymongo import MongoClient
import datetime, asyncio, re, io, csv, threading, os
from flask import Flask, jsonify
import pytesseract
from PIL import Image

# ================= CONFIGURATION =================
TOKEN = os.getenv('TOKEN') 
MONGO_URL = os.getenv('MONGO_URL')

bot = commands.Bot(
    command_prefix="!",
    intents=discord.Intents.all(),
    help_command=None
)

# Database Setup (Optimized for 1000+ Players)
db = MongoClient(MONGO_URL)["over_xvi_db"]
col = db["timeattack"]
events = db["events"]

user_cooldowns = {}

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
    """Mengubah format MM:SS.ms ke total detik untuk sorting"""
    if not re.match(r'^\d{2}:\d{2}\.\d{3}$', t): 
        return None
    try:
        m, s_ms = t.split(":")
        s, ms = s_ms.split(".")
        return int(m)*60 + int(s) + float(f"0.{ms}")
    except: 
        return None

def scan_time(image_bytes):
    """Fungsi AI Tesseract untuk membaca angka di screenshot"""
    try:
        img = Image.open(io.BytesIO(image_bytes)).convert('L') 
        text = pytesseract.image_to_string(img)
        match = re.search(r'\d{2}:\d{2}\.\d{3}', text)
        return match.group(0) if match else None
    except: 
        return None

# ================= MODAL DIALOGS =================
class SearchPlayerModal(ui.Modal):
    def __init__(self, event_name):
        super().__init__(title="🔍 Pencarian Database Driver")
        self.event_name = event_name
        self.target = ui.TextInput(
            label="IGN atau ID Game", 
            placeholder="Masukkan Nickname atau ID untuk mencari..."
        )
        self.add_item(self.target)

    async def on_submit(self, i: discord.Interaction):
        search_val = self.target.value.lower()
        # Query database skala besar
        query = {
            "event": self.event_name, 
            "approved": True, 
            "$or": [
                {"ign": {"$regex": search_val, "$options": "i"}}, 
                {"game_id": search_val}
            ]
        }
        found_data = list(col.find(query).sort("waktu_raw", 1).limit(1))
        
        if found_data:
            d = found_data[0]
            # Menghitung rank secara matematis
            rank = col.count_documents({
                "event": self.event_name, 
                "approved": True, 
                "waktu_raw": {"$lt": d['waktu_raw']}
            }) + 1
            
            emb = discord.Embed(title="🔍 HASIL PENCARIAN", color=0x3498db)
            emb.add_field(name="👤 Driver", value=f"**{d['ign']}**", inline=False)
            emb.add_field(name="🛡️ Club", value=f"{d.get('club', '-')}", inline=True)
            emb.add_field(name="🏆 Rank", value=f"**#{rank}**", inline=True)
            emb.add_field(name="⏱️ Waktu", value=f"`{d['waktu']}`", inline=True)
            await i.response.send_message(embed=emb, ephemeral=True)
        else:
            await i.response.send_message(f"❌ Player **{self.target.value}** tidak ditemukan.", ephemeral=True)

class SubmitModal(ui.Modal):
    def __init__(self, event_name):
        super().__init__(title=f"📝 Submit: {event_name}")
        self.event_name = event_name
        self.ign = ui.TextInput(label="IGN (Nickname)", min_length=2, max_length=25)
        self.club = ui.TextInput(label="Club / Tim", default="ENDGAME", max_length=20)
        self.game_id = ui.TextInput(label="ID Game", placeholder="Contoh: 123456")
        self.time_val = ui.TextInput(label="Waktu (MM:SS.ms)", placeholder="00:45.123")
        
        for item in [self.ign, self.club, self.game_id, self.time_val]: 
            self.add_item(item)

    async def on_submit(self, i: discord.Interaction):
        sec = parse_time(self.time_val.value)
        if not sec: 
            return await i.response.send_message("❌ Format waktu salah! Gunakan MM:SS.ms", ephemeral=True)
        
        await i.response.send_message("📸 Silakan upload screenshot bukti balapan...", ephemeral=True)
        
        try:
            msg = await bot.wait_for("message", timeout=60, check=lambda m: m.author.id == i.user.id and m.attachments)
            img_bytes = await msg.attachments[0].read()
            
            # AI Verifikasi
            detected = scan_time(img_bytes)
            is_match = (detected == self.time_val.value)
            
            # Data untuk database
            entry = {
                "user_id": i.user.id, 
                "event": self.event_name, 
                "ign": self.ign.value, 
                "club": self.club.value, 
                "game_id": self.game_id.value, 
                "waktu": self.time_val.value, 
                "waktu_raw": sec, 
                "approved": is_match, 
                "timestamp": datetime.datetime.now()
            }
            
            col.update_one({"user_id": i.user.id, "event": self.event_name}, {"$set": entry}, upsert=True)
            
            if is_match:
                emb = discord.Embed(title="✅ TERVERIFIKASI OTOMATIS", color=0x2ecc71)
                emb.add_field(name="Driver", value=f"**{self.ign.value}**", inline=True)
                emb.add_field(name="Club", value=f"{self.club.value}", inline=True)
                emb.add_field(name="Waktu", value=f"`{self.time_val.value}`", inline=False)
                emb.set_image(url=msg.attachments[0].url)
                await i.channel.send(embed=emb)
            else:
                # Masuk Review Admin jika OCR beda
                adm_emb = discord.Embed(title="📩 MENUNGGU PERSETUJUAN", color=0xf1c40f)
                adm_emb.add_field(name="Driver", value=f"{self.ign.value} ({self.club.value})")
                adm_emb.add_field(name="Waktu User", value=f"`{self.time_val.value}`", inline=True)
                adm_emb.add_field(name="Scan AI", value=f"`{detected or 'Gagal'}`", inline=True)
                adm_emb.set_image(url=msg.attachments[0].url)
                
                doc = col.find_one({"user_id": i.user.id, "event": self.event_name})
                await i.channel.send(content="🔔 **ANTREAN BARU:**", embed=adm_emb, view=ApprovalView(doc['_id']))
            
            try: await msg.delete()
            except: pass
        except: 
            await i.followup.send("❌ Sesi berakhir atau upload gagal.", ephemeral=True)

# ================= INTERACTIVE VIEWS =================
class ApprovalView(ui.View):
    def __init__(self, entry_id):
        super().__init__(timeout=None)
        self.entry_id = entry_id

    @ui.button(label="✅ Approve", style=discord.ButtonStyle.green)
    async def approve(self, i, b):
        col.update_one({"_id": self.entry_id}, {"$set": {"approved": True}})
        await i.response.edit_message(content="✅ Data Driver telah disetujui!", embed=None, view=None)

    @ui.button(label="❌ Reject", style=discord.ButtonStyle.danger)
    async def reject(self, i, b):
        col.delete_one({"_id": self.entry_id})
        await i.response.edit_message(content="❌ Data Driver ditolak dan dihapus.", embed=None, view=None)

class LeaderboardView(ui.View):
    def __init__(self, event_name, page=0):
        super().__init__(timeout=60)
        self.event_name = event_name
        self.page = page

    async def get_stats(self):
        skip_val = self.page * 10
        data = list(col.find({"event": self.event_name, "approved": True}).sort("waktu_raw", 1).skip(skip_val).limit(10))
        total_data = col.count_documents({"event": self.event_name, "approved": True})
        total_pages = (total_data - 1) // 10 + 1 if total_data else 1
        return data, total_pages

    def create_embed(self, data, pages):
        description = ""
        for idx, d in enumerate(data):
            rank = (self.page * 10) + idx + 1
            description += f"**{rank}.** {d['ign']} [{d.get('club', 'Endgame')}] - `{d['waktu']}`\n"
        
        emb = discord.Embed(
            title=f"🏆 LEADERBOARD: {self.event_name.upper()}", 
            description=description or "Belum ada data driver.", 
            color=0xf1c40f
        )
        emb.set_footer(text=f"Halaman {self.page + 1} dari {pages}")
        return emb

    @ui.button(label="⬅️ Sebelumnya", style=discord.ButtonStyle.grey)
    async def prev(self, i, b):
        if self.page > 0:
            self.page -= 1
            d, p = await self.get_stats()
            await i.response.edit_message(embed=self.create_embed(d, p), view=self)
        else: 
            await i.response.defer()

    @ui.button(label="Selanjutnya ➡️", style=discord.ButtonStyle.grey)
    async def next(self, i, b):
        d, p = await self.get_stats()
        if self.page < p - 1:
            self.page += 1
            d, p = await self.get_stats()
            await i.response.edit_message(embed=self.create_embed(d, p), view=self)
        else: 
            await i.response.defer()

    @ui.button(label="🔍 Cari Player", style=discord.ButtonStyle.blurple)
    async def search(self, i, b): 
        await i.response.send_modal(SearchPlayerModal(self.event_name))

class AdminMenuView(ui.View):
    def __init__(self, event_name):
        super().__init__(timeout=60)
        self.event_name = event_name

    @ui.button(label="📥 Export CSV", style=discord.ButtonStyle.green)
    async def download(self, i, b):
        data = list(col.find({"event": self.event_name}).sort("waktu_raw", 1))
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["RANK", "IGN", "CLUB", "GAME ID", "TIME", "STATUS"])
        
        for idx, d in enumerate(data):
            status = "Approved" if d.get('approved') else "Pending"
            writer.writerow([idx+1, d['ign'], d.get('club','-'), d.get('game_id','-'), d['waktu'], status])
        
        file_data = io.BytesIO(output.getvalue().encode())
        await i.response.send_message(
            content=f"📊 Rekap Data {self.event_name}:", 
            file=discord.File(file_data, f"{self.event_name}.csv"), 
            ephemeral=True
        )

    @ui.button(label="🚨 Reset Semua Data", style=discord.ButtonStyle.danger)
    async def clear(self, i, b):
        col.delete_many({"event": self.event_name})
        await i.response.send_message("❌ Leaderboard telah dikosongkan secara permanen.", ephemeral=True)

class MainView(ui.View):
    def __init__(self, event_name):
        super().__init__(timeout=None)
        self.event_name = event_name

    @ui.button(label="Submit Time", style=discord.ButtonStyle.green, custom_id="btn_submit_v3")
    async def submit_btn(self, i, b):
        await i.response.send_modal(SubmitModal(self.event_name))

    @ui.button(label="Leaderboard", style=discord.ButtonStyle.blurple, custom_id="btn_lb_v3")
    async def lb_btn(self, i, b):
        v = LeaderboardView(self.event_name)
        d, p = await v.get_stats()
        await i.response.edit_message(embed=v.create_embed(d, p), view=v)

    @ui.button(label="Menu Admin", style=discord.ButtonStyle.grey, custom_id="btn_admin_v3")
    async def admin_btn(self, i, b):
        if not i.user.guild_permissions.administrator: 
            return await i.response.send_message("🚫 Khusus Admin!", ephemeral=True)
        await i.response.edit_message(embed=discord.Embed(title="🛠️ Panel Kontrol Admin", color=0x2c3e50), view=AdminMenuView(self.event_name))

# ================= COMMANDS =================
@bot.command()
async def ta(ctx):
    if not events.find_one({"name": ctx.channel.name}): 
        return await ctx.send("❌ Gunakan `!create_event` terlebih dahulu.")
    
    emb = discord.Embed(
        title=f"🏎️ OVER-XVI TIME ATTACK: {ctx.channel.name.upper()}", 
        description="Gunakan tombol di bawah untuk mengisi data dan melihat peringkat.", 
        color=0x3498db
    )
    await ctx.send(embed=emb, view=MainView(ctx.channel.name))

@bot.command()
@commands.has_permissions(administrator=True)
async def create_event(ctx):
    events.update_one({"name": ctx.channel.name}, {"$set": {"name": ctx.channel.name}}, upsert=True)
    await ctx.send(f"✅ Channel **#{ctx.channel.name}** sekarang aktif untuk event!")

@bot.event
async def on_ready():
    bot.add_view(MainView("")) # Persistent View
    print(f">>> OVER-XVI SYSTEM ONLINE <<<")
    threading.Thread(target=run_web, daemon=True).start()

bot.run(TOKEN)
