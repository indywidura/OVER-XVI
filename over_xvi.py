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

# Aktifkan jika running di Windows Lokal (sesuaikan path)
# pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

bot = commands.Bot(
    command_prefix="!",
    intents=discord.Intents.all(),
    help_command=None
)

db = MongoClient(MONGO_URL)["over_xvi_db"]
col = db["timeattack"]
events = db["events"]

user_cooldowns = {}

# ================= WEB SERVER =================
app = Flask(__name__)
@app.route("/")
def home(): 
    return jsonify(list(events.find({}, {"_id":0})))

def run_web():
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)

# ================= HELPER & OCR =================
def parse_time(t):
    if not re.match(r'^\d{2}:\d{2}\.\d{3}$', t): return None
    try:
        m, s_ms = t.split(":")
        s, ms = s_ms.split(".")
        return int(m)*60 + int(s) + float(f"0.{ms}")
    except: return None

def scan_time(image_bytes):
    try:
        img = Image.open(io.BytesIO(image_bytes))
        img = img.convert('L') # Grayscale untuk akurasi
        text = pytesseract.image_to_string(img)
        match = re.search(r'\d{2}:\d{2}\.\d{3}', text)
        return match.group(0) if match else None
    except Exception as e:
        print(f"Error OCR: {e}")
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
        super().__init__(title="Cari Posisi Driver")
        self.event_name = event_name
        self.target = ui.TextInput(label="Nickname atau ID Game", placeholder="Masukkan IGN atau ID Game...")
        self.add_item(self.target)

    async def on_submit(self, i: discord.Interaction):
        data = list(col.find({"event": self.event_name, "approved": True}).sort("waktu_raw", 1))
        search_val = self.target.value.lower()
        found = None
        for idx, d in enumerate(data):
            if d.get('ign', '').lower() == search_val or d.get('game_id', '') == search_val:
                found = (idx + 1, d)
                break
        
        if found:
            rank, d = found
            emb = discord.Embed(title="🔍 HASIL PENCARIAN", color=0x3498db)
            emb.add_field(name="👤 Driver", value=f"**{d['ign']}**", inline=False)
            emb.add_field(name="🏆 Rank", value=f"**#{rank}**", inline=True)
            emb.add_field(name="⏱️ Time", value=f"`{d['waktu']}`", inline=True)
            await i.response.send_message(embed=emb, ephemeral=True)
        else:
            await i.response.send_message(f"❌ Data **{self.target.value}** tidak ditemukan atau belum di-approve.", ephemeral=True)

class SubmitModal(ui.Modal):
    def __init__(self, event_name):
        super().__init__(title=f"Submit: {event_name}")
        self.event_name = event_name
        self.ign = ui.TextInput(label="IGN", min_length=2)
        self.game_id = ui.TextInput(label="ID Game")
        self.time_val = ui.TextInput(label="Waktu (MM:SS.ms)", placeholder="00:45.000")
        for item in [self.ign, self.game_id, self.time_val]: self.add_item(item)

    async def on_submit(self, i: discord.Interaction):
        sec = parse_time(self.time_val.value)
        if not sec: return await i.response.send_message("❌ Format waktu salah! Gunakan `00:00.000`", ephemeral=True)
        
        await i.response.send_message("📸 Kirim screenshot bukti balapan ke channel ini.", ephemeral=True)
        
        try:
            msg = await bot.wait_for("message", timeout=60, check=lambda m: m.author.id == i.user.id and m.attachments)
            img_bytes = await msg.attachments[0].read()
            try: await msg.delete()
            except: pass
            
            # PROSES OCR
            detected = scan_time(img_bytes)
            is_match = (detected == self.time_val.value)
            
            entry = {
                "user_id": i.user.id, "event": self.event_name,
                "ign": self.ign.value, "game_id": self.game_id.value,
                "waktu": self.time_val.value, "waktu_raw": sec,
                "approved": is_match, "timestamp": datetime.datetime.now()
            }
            res = col.update_one({"user_id": i.user.id, "event": self.event_name}, {"$set": entry}, upsert=True)
            user_cooldowns[i.user.id] = datetime.datetime.now()

            if is_match:
                emb = discord.Embed(title="🏁 REKOR TERCATAT (AUTO-OCR)", color=0x2ecc71)
                emb.add_field(name="Driver", value=self.ign.value)
                emb.add_field(name="Time", value=self.time_val.value)
                file = discord.File(io.BytesIO(img_bytes), filename="p.png")
                emb.set_image(url="attachment://p.png")
                await i.channel.send(file=file, embed=emb)
            else:
                await i.followup.send("⏳ OCR tidak cocok/tidak terbaca. Menunggu validasi Admin.", ephemeral=True)
                # Kirim ke Admin untuk Approval
                admin_emb = discord.Embed(title="📩 PENDING APPROVAL", color=0xf1c40f)
                admin_emb.add_field(name="Driver", value=self.ign.value)
                admin_emb.add_field(name="Input User", value=self.time_val.value)
                admin_emb.add_field(name="Hasil Scan AI", value=str(detected))
                admin_emb.set_image(url=msg.attachments[0].url)
                # Mencari ID Dokumen yang baru diinsert (jika perlu)
                doc = col.find_one({"user_id": i.user.id, "event": self.event_name})
                await i.channel.send(content="🔔 **LAPORAN BARU (CEK ADMIN)**", embed=admin_emb, view=ApprovalView(doc['_id'], i.user.id))
        except:
            await i.followup.send("❌ Gagal upload atau waktu habis.", ephemeral=True)

# ================= VIEWS =================
class ApprovalView(ui.View):
    def __init__(self, entry_id, user_id):
        super().__init__(timeout=None)
        self.entry_id = entry_id
        self.user_id = user_id

    @ui.button(label="✅ Approve", style=discord.ButtonStyle.green)
    async def approve(self, i, b):
        col.update_one({"_id": self.entry_id}, {"$set": {"approved": True}})
        await i.response.edit_message(content="✅ Data Disetujui!", embed=None, view=None)

    @ui.button(label="❌ Reject", style=discord.ButtonStyle.danger)
    async def reject(self, i, b):
        col.delete_one({"_id": self.entry_id})
        await i.response.edit_message(content="❌ Data Ditolak & Dihapus.", embed=None, view=None)

class LeaderboardView(ui.View):
    def __init__(self, event_name, page=0):
        super().__init__(timeout=60)
        self.event_name = event_name
        self.page = page

    async def get_embed(self):
        data = list(col.find({"event": self.event_name, "approved": True}).sort("waktu_raw", 1))
        items_per_page = 10
        total_pages = (len(data) - 1) // items_per_page + 1 if data else 1
        start = self.page * items_per_page
        desc = ""
        for idx, d in enumerate(data[start:start+items_per_page]):
            rank = start + idx + 1
            desc += f"**{rank}.** {d['ign']} - `{d['waktu']}`\n"
        
        embed = discord.Embed(title=f"🏆 LEADERBOARD: {self.event_name.upper()}", description=desc or "Belum ada data.", color=0xf1c40f)
        embed.set_footer(text=f"Halaman {self.page + 1}/{total_pages}")
        return embed, total_pages

    @ui.button(label="⬅️", style=discord.ButtonStyle.grey)
    async def prev(self, i, b):
        if self.page > 0:
            self.page -= 1
            emb, _ = await self.get_embed()
            await i.response.edit_message(embed=emb, view=self)
        else: await i.response.defer()

    @ui.button(label="➡️", style=discord.ButtonStyle.grey)
    async def next(self, i, b):
        _, total = await self.get_embed()
        if self.page < total - 1:
            self.page += 1
            emb, _ = await self.get_embed()
            await i.response.edit_message(embed=emb, view=self)
        else: await i.response.defer()

    @ui.button(label="🔍 Cari", style=discord.ButtonStyle.blurple)
    async def srch(self, i, b): await i.response.send_modal(SearchPlayerModal(self.event_name))

    @ui.button(label="🏠 Home", style=discord.ButtonStyle.danger)
    async def home(self, i, b):
        emb = discord.Embed(title=f"🏎️ EVENT: {self.event_name.upper()}", description=MAIN_DESC, color=0x3498db)
        await i.response.edit_message(embed=emb, view=MainView(self.event_name))

class AdminMenuView(ui.View):
    def __init__(self, event_name):
        super().__init__(timeout=60)
        self.event_name = event_name

    @ui.button(label="📥 Download CSV", style=discord.ButtonStyle.green)
    async def dl(self, i, b):
        data = list(col.find({"event": self.event_name}).sort("waktu_raw", 1))
        out = io.StringIO()
        w = csv.writer(out)
        w.writerow(["RANK", "IGN", "ID", "TIME", "STATUS"])
        for idx, d in enumerate(data):
            w.writerow([idx+1, d['ign'], d.get('game_id','-'), d['waktu'], d.get('approved',False)])
        file = discord.File(io.BytesIO(out.getvalue().encode()), f"{self.event_name}.csv")
        await i.response.send_message(f"✅ Data Exported:", file=file, ephemeral=True)

    @ui.button(label="🗑️ Reset All", style=discord.ButtonStyle.danger)
    async def reset(self, i, b):
        col.delete_many({"event": self.event_name})
        await i.response.send_message("✅ Leaderboard dikosongkan!", ephemeral=True)

    @ui.button(label="🏠 Home", style=discord.ButtonStyle.blurple)
    async def home(self, i, b):
        emb = discord.Embed(title=f"🏎️ EVENT: {self.event_name.upper()}", description=MAIN_DESC, color=0x3498db)
        await i.response.edit_message(embed=emb, view=MainView(self.event_name))

MAIN_DESC = (
    "**SISTEM VERIFIKASI AI AKTIF:**\n"
    "1. Klik **Submit Time** & isi formulir.\n"
    "2. Upload Screenshot hasil balapan.\n"
    "3. AI akan membaca waktu di gambar. Jika sesuai, data otomatis masuk.\n"
    "4. Jika tidak terbaca, data menunggu **Approval Admin**."
)

class MainView(ui.View):
    def __init__(self, event_name):
        super().__init__(timeout=None)
        self.event_name = event_name

    @ui.button(label="Submit Time", style=discord.ButtonStyle.green, custom_id="sub_f")
    async def sub(self, i, b):
        cd, r = is_on_cooldown(i.user)
        if cd: return await i.response.send_message(f"⏳ Tunggu {r} detik.", ephemeral=True)
        await i.response.send_modal(SubmitModal(self.event_name))

    @ui.button(label="Leaderboard", style=discord.ButtonStyle.blurple, custom_id="lb_f")
    async def lb(self, i, b):
        v = LeaderboardView(self.event_name)
        emb, _ = await v.get_embed()
        await i.response.edit_message(embed=emb, view=v)

    @ui.button(label="Admin Menu", style=discord.ButtonStyle.grey, custom_id="adm_f")
    async def adm(self, i, b):
        if not i.user.guild_permissions.administrator: return await i.response.send_message("🚫 Khusus Admin!", ephemeral=True)
        await i.response.edit_message(embed=discord.Embed(title="🛠️ Admin Panel", color=0x2c3e50), view=AdminMenuView(self.event_name))

# ================= COMMANDS =================
@bot.command()
async def ta(ctx):
    ev = events.find_one({"name": ctx.channel.name})
    if not ev: return await ctx.send("❌ Aktifkan channel: `!create_event`")
    emb = discord.Embed(title=f"🏎️ EVENT: {ctx.channel.name.upper()}", description=MAIN_DESC, color=0x3498db)
    await ctx.send(embed=emb, view=MainView(ctx.channel.name))

@bot.command()
@commands.has_permissions(administrator=True)
async def create_event(ctx):
    events.update_one({"name": ctx.channel.name}, {"$set": {"name": ctx.channel.name}}, upsert=True)
    await ctx.send(f"✅ Channel **#{ctx.channel.name}** aktif!")

@bot.event
async def on_ready():
    bot.add_view(MainView(""))
    print(f"OVER-XVI READY: {bot.user}")
    threading.Thread(target=run_web, daemon=True).start()

bot.run(TOKEN)
