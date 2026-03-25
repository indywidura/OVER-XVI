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
history = db["history"]
events = db["events"]

user_cooldowns = {}

# ================= WEB SERVER (PORT 5000) =================
app = Flask(__name__)

@app.route("/")
def home():
    return jsonify(list(events.find({}, {"_id":0})))

@app.route("/event/<name>")
def event_lb(name):
    data = list(col.find({"event": name}).sort("waktu_raw",1))
    return jsonify([
        {
            "rank": i+1,
            "ign": d.get("ign"),
            "time": d.get("waktu"),
            "club": d.get("club","-")
        } for i,d in enumerate(data)
    ])

def run_web():
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)

# ================= HELPER FUNCTIONS =================
def parse_time(t):
    if not re.match(r'^\d{2}:\d{2}\.\d{3}$', t): 
        return None
    try:
        m, s_ms = t.split(":")
        s, ms = s_ms.split(".")
        return int(m)*60 + int(s) + float(f"0.{ms}")
    except:
        return None

def is_on_cooldown(member, seconds=30):
    if member.guild_permissions.administrator:
        return False, 0
    now = datetime.datetime.now()
    if member.id in user_cooldowns:
        diff = (now - user_cooldowns[member.id]).total_seconds()
        if diff < seconds: return True, int(seconds - diff)
    return False, 0

# ================= AUTO ROLE CHAMPION =================
async def update_role(guild, event_name):
    data = list(col.find({"event": event_name}).sort("waktu_raw", 1))
    if not data: return

    top_user_id = data[0]["user_id"]
    role_name = f"Champion {event_name}"

    role = discord.utils.get(guild.roles, name=role_name)
    if not role:
        try:
            role = await guild.create_role(name=role_name, color=0xf1c40f, reason="Auto Champion")
        except: return

    for m in guild.members:
        if role in m.roles and m.id != top_user_id:
            await m.remove_roles(role)

    winner = guild.get_member(top_user_id)
    if winner and role not in winner.roles:
        await winner.add_roles(role)

# ================= MODALS =================
class SubmitModal(ui.Modal):
    def __init__(self, event_name):
        super().__init__(title=f"Submit: {event_name}")
        self.event_name = event_name
        self.ign = ui.TextInput(label="IGN", placeholder="Nickname anda", min_length=2)
        self.club = ui.TextInput(label="Club", default="ENDGAME")
        self.game_id = ui.TextInput(label="ID Game", placeholder="Contoh: 12345678")
        self.time_val = ui.TextInput(label="Waktu (MM:SS.ms)", placeholder="00:45.000")
        
        self.add_item(self.ign)
        self.add_item(self.club)
        self.add_item(self.game_id)
        self.add_item(self.time_val)

    async def on_submit(self, i: discord.Interaction):
        sec = parse_time(self.time_val.value)
        if not sec:
            return await i.response.send_message("❌ Format waktu salah (MM:SS.ms)!", ephemeral=True)

        await i.response.send_message("📸 Kirim screenshot bukti balapan sekarang.", ephemeral=True)

        def check(m): return m.author.id == i.user.id and m.attachments
        try:
            msg = await bot.wait_for("message", timeout=60, check=check)
            img_data = await msg.attachments[0].read()
            try: await msg.delete()
            except: pass

            entry = {
                "user_id": i.user.id, "event": self.event_name,
                "ign": self.ign.value, "club": self.club.value,
                "game_id": self.game_id.value, "waktu": self.time_val.value,
                "waktu_raw": sec, "submitter": i.user.display_name,
                "last_submit": datetime.datetime.now()
            }
            col.update_one({"user_id": i.user.id, "event": self.event_name}, {"$set": entry}, upsert=True)
            user_cooldowns[i.user.id] = datetime.datetime.now()

            embed = discord.Embed(title="🏁 REKOR BARU!", color=0x2ecc71)
            embed.add_field(name="👤 Driver", value=self.ign.value, inline=True)
            embed.add_field(name="⏱️ Time", value=f"`{self.time_val.value}`", inline=True)
            
            file = discord.File(io.BytesIO(img_data), filename="proof.png")
            embed.set_image(url="attachment://proof.png")

            await i.channel.send(file=file, embed=embed)
            await update_role(i.guild, self.event_name)
        except asyncio.TimeoutError:
            await i.followup.send("❌ Waktu habis!", ephemeral=True)

class DeletePlayerModal(ui.Modal):
    def __init__(self, event_name):
        super().__init__(title="Hapus Peserta")
        self.event_name = event_name
        self.target = ui.TextInput(label="IGN atau User ID", placeholder="Ketik nama/ID yang ingin dihapus...")
        self.add_item(self.target)

    async def on_submit(self, i: discord.Interaction):
        val = self.target.value
        query = {"event": self.event_name, "$or": [{"ign": val}, {"user_id": int(val) if val.isdigit() else 0}]}
        res = col.delete_one(query)
        
        if res.deleted_count:
            await i.response.send_message(f"✅ **{val}** dihapus dari {self.event_name}.", ephemeral=True)
            await update_role(i.guild, self.event_name)
        else:
            await i.response.send_message("❌ Data tidak ditemukan.", ephemeral=True)

# ================= VIEWS =================
class AdminMenuView(ui.View):
    def __init__(self, event_name):
        super().__init__(timeout=60)
        self.event_name = event_name

    @ui.button(label="📥 Download CSV", style=discord.ButtonStyle.green)
    async def download(self, i, b):
        data = list(col.find({"event": self.event_name}).sort("waktu_raw", 1))
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["RANK", "IGN", "ID", "CLUB", "TIME"])
        for idx, d in enumerate(data):
            writer.writerow([idx+1, d['ign'], f"'{d.get('game_id')}", d.get('club'), d['waktu']])
        
        file = discord.File(io.BytesIO(output.getvalue().encode()), filename=f"{self.event_name}.csv")
        await i.response.send_message(f"Data {self.event_name}:", file=file, ephemeral=True)

    @ui.button(label="👤 Hapus Pemain", style=discord.ButtonStyle.secondary)
    async def del_p(self, i, b):
        await i.response.send_modal(DeletePlayerModal(self.event_name))

    @ui.button(label="🗑️ Reset Leaderboard", style=discord.ButtonStyle.danger)
    async def reset(self, i, b):
        col.delete_many({"event": self.event_name})
        await i.response.send_message(f"✅ Data di #{self.event_name} dibersihkan!", ephemeral=True)

class MainView(ui.View):
    def __init__(self, event_name):
        super().__init__(timeout=None)
        self.event_name = event_name

    @ui.button(label="Submit Time", style=discord.ButtonStyle.green, custom_id="sub_v3")
    async def sub(self, i, b):
        on_cd, rem = is_on_cooldown(i.user)
        if on_cd: return await i.response.send_message(f"⏳ Tunggu {rem} detik.", ephemeral=True)
        await i.response.send_modal(SubmitModal(self.event_name))

    @ui.button(label="Leaderboard", style=discord.ButtonStyle.blurple, custom_id="lb_v3")
    async def lb(self, i, b):
        data = list(col.find({"event": self.event_name}).sort("waktu_raw", 1))
        desc = "".join([f"{'🥇' if idx==0 else '🥈' if idx==1 else '🥉' if idx==2 else f'**{idx+1}.**'} {d['ign']} - `{d['waktu']}`\n" for idx, d in enumerate(data[:10])])
        embed = discord.Embed(title=f"🏆 TOP 10: {self.event_name.upper()}", description=desc or "Belum ada data.", color=0xf1c40f)
        await i.response.send_message(embed=embed, ephemeral=True)

    @ui.button(label="Admin Menu", style=discord.ButtonStyle.grey, custom_id="adm_v3")
    async def adm(self, i, b):
        if not i.user.guild_permissions.administrator:
            return await i.response.send_message("🚫 Khusus Admin!", ephemeral=True)
        await i.response.send_message(f"🛠️ Menu Admin: **#{self.event_name}**", view=AdminMenuView(self.event_name), ephemeral=True)

# ================= BOT COMMANDS =================
@bot.command()
async def ta(ctx):
    if not events.find_one({"name": ctx.channel.name}):
        return await ctx.send("❌ Channel ini belum aktif. Ketik `!create_event` dulu.")

    embed = discord.Embed(
        title=f"🏎️ EVENT: {ctx.channel.name.upper()}",
        description=(
            "**Instruksi Submit:**\n"
            "1. Klik **Submit Time** & isi formulir.\n"
            "2. Gunakan format waktu `00:45.123`.\n"
            "3. **Upload Screenshot** bukti setelah klik submit.\n"
            "4. Pesan asli kamu akan otomatis dihapus bot."
        ), color=0x3498db
    )
    await ctx.send(embed=embed, view=MainView(ctx.channel.name))

@bot.command()
@commands.has_permissions(administrator=True)
async def create_event(ctx):
    events.update_one({"name": ctx.channel.name}, {"$set": {"name": ctx.channel.name}}, upsert=True)
    await ctx.send(f"✅ Event **#{ctx.channel.name}** Aktif! Ketik `!ta`.")

@bot.command()
@commands.has_permissions(administrator=True)
async def delete_event(ctx):
    events.delete_one({"name": ctx.channel.name})
    col.delete_many({"event": ctx.channel.name})
    await ctx.send(f"🗑️ Event **#{ctx.channel.name}** dihapus.")

@bot.event
async def on_ready():
    bot.add_view(MainView("")) 
    print(f"BOT READY: {bot.user}")
    threading.Thread(target=run_web, daemon=True).start()

bot.run(TOKEN)
