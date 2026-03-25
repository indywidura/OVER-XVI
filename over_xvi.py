import discord
from discord.ext import commands
from discord import ui
from pymongo import MongoClient
import datetime, asyncio, re, io, csv, threading, os
from flask import Flask, jsonify

# ================= CONFIG =================
TOKEN = os.getenv('TOKEN') 
MONGO_URL = os.getenv('MONGO_URL')

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
def home(): return jsonify(list(events.find({}, {"_id":0})))

def run_web():
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)

# ================= HELPER =================
def parse_time(t):
    if not re.match(r'^\d{2}:\d{2}\.\d{3}$', t): return None
    try:
        m, s_ms = t.split(":")
        s, ms = s_ms.split(".")
        return int(m)*60 + int(s) + float(f"0.{ms}")
    except: return None

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
        self.target = ui.TextInput(
            label="Nickname atau ID Game", 
            placeholder="Masukkan IGN atau ID Game untuk mencari..."
        )
        self.add_item(self.target)

    async def on_submit(self, i: discord.Interaction):
        # Ambil semua data event ini urut waktu tercepat
        data = list(col.find({"event": self.event_name}).sort("waktu_raw", 1))
        search_val = self.target.value.lower()
        
        found = None
        for idx, d in enumerate(data):
            # Cek kecocokan di IGN atau ID Game
            if d.get('ign', '').lower() == search_val or d.get('game_id', '') == search_val:
                found = (idx + 1, d)
                break
        
        if found:
            rank, d = found
            emb = discord.Embed(title="🔍 HASIL PENCARIAN", color=0x3498db)
            emb.add_field(name="👤 Driver", value=f"**{d['ign']}** (ID: {d.get('game_id', '-')})", inline=False)
            emb.add_field(name="🏆 Peringkat", value=f"**#{rank}**", inline=True)
            emb.add_field(name="⏱️ Waktu", value=f"`{d['waktu']}`", inline=True)
            await i.response.send_message(embed=emb, ephemeral=True)
        else:
            await i.response.send_message(f"❌ Data **{self.target.value}** tidak ditemukan.", ephemeral=True)

class SubmitModal(ui.Modal):
    def __init__(self, event_name):
        super().__init__(title=f"Submit: {event_name}")
        self.event_name = event_name
        self.ign = ui.TextInput(label="IGN", min_length=2)
        self.club = ui.TextInput(label="Club", default="ENDGAME")
        self.game_id = ui.TextInput(label="ID Game")
        self.time_val = ui.TextInput(label="Waktu (MM:SS.ms)", placeholder="00:45.000")
        for item in [self.ign, self.club, self.game_id, self.time_val]: self.add_item(item)

    async def on_submit(self, i: discord.Interaction):
        sec = parse_time(self.time_val.value)
        if not sec: return await i.response.send_message("❌ Format waktu salah!", ephemeral=True)
        
        await i.response.send_message("📸 Kirim screenshot bukti balapan.", ephemeral=True)
        def check(m): return m.author.id == i.user.id and m.attachments
        try:
            msg = await bot.wait_for("message", timeout=60, check=check)
            img = await msg.attachments[0].read()
            try: await msg.delete()
            except: pass
            
            entry = {
                "user_id": i.user.id, 
                "event": self.event_name, 
                "ign": self.ign.value, 
                "club": self.club.value, 
                "game_id": self.game_id.value, # Simpan ID Game untuk pencarian
                "waktu": self.time_val.value, 
                "waktu_raw": sec
            }
            col.update_one({"user_id": i.user.id, "event": self.event_name}, {"$set": entry}, upsert=True)
            user_cooldowns[i.user.id] = datetime.datetime.now()
            
            embed = discord.Embed(title="🏁 REKOR TERCATAT!", color=0x2ecc71)
            embed.add_field(name="Driver", value=self.ign.value)
            embed.add_field(name="Time", value=self.time_val.value)
            file = discord.File(io.BytesIO(img), filename="p.png")
            embed.set_image(url="attachment://p.png")
            await i.channel.send(file=file, embed=embed)
        except: await i.followup.send("❌ Gagal upload/Waktu habis.", ephemeral=True)

# ================= VIEWS =================

class LeaderboardView(ui.View):
    def __init__(self, event_name, page=0):
        super().__init__(timeout=60)
        self.event_name = event_name
        self.page = page

    async def get_embed(self):
        data = list(col.find({"event": self.event_name}).sort("waktu_raw", 1))
        items_per_page = 10
        total_pages = (len(data) - 1) // items_per_page + 1 if data else 1
        start = self.page * items_per_page
        end = start + items_per_page
        
        desc = ""
        for idx, d in enumerate(data[start:end]):
            rank = start + idx + 1
            icon = "🥇" if rank==1 else "🥈" if rank==2 else "🥉" if rank==3 else f"**{rank}.**"
            desc += f"{icon} {d['ign']} - `{d['waktu']}`\n"
            
        embed = discord.Embed(title=f"🏆 LEADERBOARD: {self.event_name.upper()}", description=desc or "Belum ada data.", color=0xf1c40f)
        embed.set_footer(text=f"Halaman {self.page + 1} dari {total_pages}")
        return embed, total_pages

    @ui.button(label="⬅️ Prev", style=discord.ButtonStyle.grey)
    async def prev(self, i, b):
        if self.page > 0:
            self.page -= 1
            emb, _ = await self.get_embed()
            await i.response.edit_message(embed=emb, view=self)
        else: await i.response.defer()

    @ui.button(label="Next ➡️", style=discord.ButtonStyle.grey)
    async def next(self, i, b):
        _, total = await self.get_embed()
        if self.page < total - 1:
            self.page += 1
            emb, _ = await self.get_embed()
            await i.response.edit_message(embed=emb, view=self)
        else: await i.response.defer()

    @ui.button(label="🔍 Cari", style=discord.ButtonStyle.blurple)
    async def search(self, i, b):
        await i.response.send_modal(SearchPlayerModal(self.event_name))

    @ui.button(label="🏠 Home", style=discord.ButtonStyle.danger)
    async def home_btn(self, i, b):
        emb = discord.Embed(title=f"🏎️ EVENT: {self.event_name.upper()}", description=MAIN_DESC, color=0x3498db)
        await i.response.edit_message(embed=emb, view=MainView(self.event_name))

class AdminMenuView(ui.View):
    def __init__(self, event_name):
        super().__init__(timeout=60)
        self.event_name = event_name

    @ui.button(label="📥 Download CSV", style=discord.ButtonStyle.green)
    async def dl(self, i, b):
        data = list(col.find({"event": self.event_name}).sort("waktu_raw", 1))
        out = io.StringIO(); w = csv.writer(out); w.writerow(["RANK", "IGN", "GAME ID", "TIME"])
        for idx, d in enumerate(data): w.writerow([idx+1, d['ign'], d.get('game_id','-'), d['waktu']])
        await i.response.send_message(file=discord.File(io.BytesIO(out.getvalue().encode()), f"{self.event_name}.csv"), ephemeral=True)

    @ui.button(label="🏠 Home", style=discord.ButtonStyle.blurple)
    async def home_btn(self, i, b):
        emb = discord.Embed(title=f"🏎️ EVENT: {self.event_name.upper()}", description=MAIN_DESC, color=0x3498db)
        await i.response.edit_message(embed=emb, view=MainView(self.event_name))

MAIN_DESC = (
    "**CARA MENGISI DATA LENGKAP:**\n"
    "1. Klik tombol **Submit Time** di bawah.\n"
    "2. Masukkan **IGN**, **Club**, dan **ID Game** kamu.\n"
    "3. Isi **Waktu** dengan format `00:00.000`.\n"
    "4. Setelah Klik Submit, **Upload Screenshot** bukti balapan.\n"
    "5. Bot akan menghapus pesan asli agar channel tetap rapi."
)

class MainView(ui.View):
    def __init__(self, event_name):
        super().__init__(timeout=None)
        self.event_name = event_name

    @ui.button(label="Submit Time", style=discord.ButtonStyle.green, custom_id="sub_v6")
    async def sub(self, i, b):
        cd, r = is_on_cooldown(i.user)
        if cd: return await i.response.send_message(f"⏳ Tunggu {r} detik.", ephemeral=True)
        await i.response.send_modal(SubmitModal(self.event_name))

    @ui.button(label="Leaderboard", style=discord.ButtonStyle.blurple, custom_id="lb_v6")
    async def lb(self, i, b):
        view = LeaderboardView(self.event_name)
        emb, _ = await view.get_embed()
        await i.response.edit_message(embed=emb, view=view)

    @ui.button(label="Admin Menu", style=discord.ButtonStyle.grey, custom_id="adm_v6")
    async def adm(self, i, b):
        if not i.user.guild_permissions.administrator: return await i.response.send_message("🚫 Khusus Admin!", ephemeral=True)
        emb = discord.Embed(title=f"🛠️ Menu Admin: #{self.event_name}", color=0x2c3e50)
        await i.response.edit_message(embed=emb, view=AdminMenuView(self.event_name))

# ================= COMMANDS =================
@bot.command()
async def ta(ctx):
    if not events.find_one({"name": ctx.channel.name}): return await ctx.send("❌ Aktifkan channel ini: `!create_event`")
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
    print(f"BOT READY: {bot.user}")
    threading.Thread(target=run_web, daemon=True).start()

bot.run(TOKEN)
