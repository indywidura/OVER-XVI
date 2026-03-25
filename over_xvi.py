import discord
from discord.ext import commands
from discord import ui
from pymongo import MongoClient
import datetime, asyncio, re, io, csv, threading, os
from flask import Flask, jsonify

# ================= CONFIG =================
TOKEN = 'MTQ4NjE1MTQ4NzUxOTQ1NzM2MA.GerHXg.UA69z1BlBK0aGtY63FEZo1dU9iSHn-TgtHl0i8'
MONGO_URL = "mongodb+srv://time-attack1:01010101@cluster0.smztndb.mongodb.net/?appName=Cluster0"

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

# ================= WEB =================
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

# ================= HELPER =================
def parse_time(t):
    if not re.match(r'^\d{2}:\d{2}\.\d{3}$', t): # Update format ke MM:SS.ms
        return None
    try:
        m, s_ms = t.split(":")
        s, ms = s_ms.split(".")
        return int(m)*60 + int(s) + float(f"0.{ms}")
    except:
        return None

def clean(x): return x if x else "N/A"

def is_on_cooldown(member, seconds=30):
    """Cek cooldown, abaikan jika user adalah Admin"""
    if member.guild_permissions.administrator:
        return False, 0
    now = datetime.datetime.now()
    if member.id in user_cooldowns:
        diff = (now - user_cooldowns[member.id]).total_seconds()
        if diff < seconds: return True, int(seconds - diff)
    return False, 0

# ================= HELP =================
def help_embed():
    return discord.Embed(
        title="📖 COMMAND LIST",
        description="""
🏎️ **User**
!ta → Panel utama

🛠️ **Admin**
!create_event <nama>
!delete_event <nama>
!del_player <IGN/ID>

🌐 **Web**
/event/<nama>
        """,
        color=0x3498db
    )

# ================= AUTO ROLE =================
async def update_role(guild, event):
    data = list(col.find({"event": event}).sort("waktu_raw",1))
    if not data: return

    top = data[0]["user_id"]
    role_name = f"Champion {event}"

    role = discord.utils.get(guild.roles, name=role_name)
    if not role:
        role = await guild.create_role(name=role_name, color=0xf1c40f)

    for m in guild.members:
        if role in m.roles and m.id != top:
            await m.remove_roles(role)

    member = guild.get_member(top)
    if member:
        await member.add_roles(role)

# ================= ADMIN MENU COMPONENTS =================
class AdminMenuView(ui.View):
    def __init__(self, event_name):
        super().__init__(timeout=60)
        self.event_name = event_name

    @ui.button(label="📥 Download Spreadsheet", style=discord.ButtonStyle.green)
    async def download_sheet(self, i, b):
        data = list(col.find({"event": self.event_name}).sort("waktu_raw", 1))
        if not data: return await i.response.send_message("❌ Data kosong.", ephemeral=True)
        
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["RANK", "IGN", "GAME ID", "CLUB", "TIME", "SUBMITTER", "DATE"])
        for idx, d in enumerate(data):
            writer.writerow([idx+1, d['ign'], f"'{d.get('game_id','-')}", d.get('club','-'), d['waktu'], d.get('submitter','-'), d.get('last_submit','-')])
        
        file = discord.File(io.BytesIO(output.getvalue().encode()), filename=f"Report_{self.event_name}.csv")
        await i.response.send_message(f"✅ Data channel **#{self.event_name}**:", file=file, ephemeral=True)

    @ui.button(label="🗑️ Reset Event", style=discord.ButtonStyle.danger)
    async def reset_event(self, i, b):
        col.delete_many({"event": self.event_name})
        await i.response.send_message(f"⚠️ Data rekor di **#{self.event_name}** telah dihapus!", ephemeral=True)

# ================= SUBMIT MODAL =================
class SubmitModal(ui.Modal):
    def __init__(self, event_name):
        super().__init__(title=f"Submit Time: {event_name}")
        self.event_name = event_name
        self.ign = ui.TextInput(label="IGN", placeholder="Nickname game")
        self.club = ui.TextInput(label="Club", placeholder="Nama Club", default="ENDGAME")
        self.game_id = ui.TextInput(label="ID Game", placeholder="Contoh: 666666666")
        self.time_val = ui.TextInput(label="Time MM:SS.ms", placeholder="00:46.000")
        
        self.add_item(self.ign)
        self.add_item(self.club)
        self.add_item(self.game_id)
        self.add_item(self.time_val)

    async def on_submit(self, i: discord.Interaction):
        sec = parse_time(self.time_val.value)
        # Jika salah isi data, peserta tidak kena cooldown
        if not sec or sec < 10:
            return await i.response.send_message("❌ Format salah! Gunakan MM:SS.ms (Contoh 00:46.000). Silahkan coba lagi.", ephemeral=True)

        await i.response.send_message("📸 Kirim screenshot hasil balapan.", ephemeral=True)

        def check(m): return m.author.id == i.user.id and m.attachments

        try:
            msg = await bot.wait_for("message", timeout=60, check=check)
            img = await msg.attachments[0].read()
            try: await msg.delete()
            except: pass

            # Simpan Data ke MongoDB
            data_entry = {
                "user_id": i.user.id,
                "event": self.event_name,
                "ign": self.ign.value,
                "club": self.club.value,
                "game_id": self.game_id.value,
                "waktu": self.time_val.value,
                "waktu_raw": sec,
                "submitter": i.user.display_name,
                "last_submit": datetime.datetime.now()
            }
            col.update_one(
                {"user_id": i.user.id, "event": self.event_name},
                {"$set": data_entry},
                upsert=True
            )

            # Catat ke History
            history.insert_one({
                "user_id": i.user.id,
                "event": self.event_name,
                "time": self.time_val.value,
                "raw": sec,
                "date": datetime.datetime.now()
            })

            # Aktifkan cooldown HANYA SETELAH DATA BERHASIL
            user_cooldowns[i.user.id] = datetime.datetime.now()

            # Embed Output Sesuai Gambar 1
            embed = discord.Embed(title="🌟 REKOR BARU TERCATAT", color=0x2ecc71)
            embed.add_field(name="👤 Peserta", value=self.ign.value, inline=False)
            embed.add_field(name="🛡️ Club", value=self.club.value, inline=False)
            embed.add_field(name="🆔 ID Game", value=self.game_id.value, inline=False)
            embed.add_field(name="⏱️ Waktu", value=self.time_val.value, inline=False)
            embed.set_footer(text=f"Submitter: {i.user.display_name}")

            file = discord.File(io.BytesIO(img), filename="res.png")
            embed.set_image(url="attachment://res.png")

            await i.channel.send(file=file, embed=embed)
            await update_role(i.guild, self.event_name)

        except asyncio.TimeoutError:
            await i.followup.send("❌ Waktu upload habis. Silahkan ulangi.", ephemeral=True)

# ================= DROPDOWN LOGIC =================
class EventDropdown(ui.Select):
    def __init__(self, mode):
        self.mode = mode # 'submit', 'leaderboard', atau 'admin'
        event_list = list(events.find())
        options = [discord.SelectOption(label=e["name"]) for e in event_list]
        if not options:
            options = [discord.SelectOption(label="Tidak ada event aktif")]
        super().__init__(placeholder="Pilih Nama Event...", options=options)

    async def callback(self, i: discord.Interaction):
        if self.values[0] == "Tidak ada event aktif":
            return await i.response.send_message("Buat event dulu dengan `!create_event`", ephemeral=True)
            
        if self.mode == 'submit':
            await i.response.send_modal(SubmitModal(self.values[0]))
        elif self.mode == 'admin':
            emb = discord.Embed(title="🛠️ ADMIN MENU", description=f"Manajemen data: **{self.values[0]}**", color=0x2c3e50)
            await i.response.send_message(embed=emb, view=AdminMenuView(self.values[0]), ephemeral=True)
        else:
            # Tampilkan Leaderboard
            data = list(col.find({"event": self.values[0]}).sort("waktu_raw", 1))
            medals = ["🥇","🥈","🥉"]
            desc = ""
            for idx, d in enumerate(data[:10]):
                icon = medals[idx] if idx < 3 else f"{idx+1}."
                desc += f"{icon} {clean(d['ign'])} - `{d['waktu']}`\n"
            
            embed = discord.Embed(title=f"🏆 LEADERBOARD: {self.values[0]}", description=desc or "Belum ada rekor", color=0xf1c40f)
            await i.response.send_message(embed=embed, ephemeral=True)

# ================= MAIN UI =================
class MainView(ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @ui.button(label="Submit Time", style=discord.ButtonStyle.green, custom_id="btn_sub")
    async def sub(self, i, b):
        on_cd, rem = is_on_cooldown(i.user)
        if on_cd: return await i.response.send_message(f"⏳ Kamu sudah submit! Tunggu {rem} detik untuk update data.", ephemeral=True)
        
        v = ui.View(); v.add_item(EventDropdown('submit'))
        await i.response.send_message("Pilih event yang ingin kamu ikuti:", view=v, ephemeral=True)

    @ui.button(label="Leaderboard", style=discord.ButtonStyle.blurple, custom_id="btn_lb")
    async def lb(self, i, b):
        v = ui.View(); v.add_item(EventDropdown('leaderboard'))
        await i.response.send_message("Pilih event untuk melihat leaderboard:", view=v, ephemeral=True)

    @ui.button(label="🛠️ Admin Menu", style=discord.ButtonStyle.grey, custom_id="btn_admin")
    async def admin_btn(self, i, b):
        if not i.user.guild_permissions.administrator:
            return await i.response.send_message("🚫 Khusus Admin!", ephemeral=True)
        v = ui.View(); v.add_item(EventDropdown('admin'))
        await i.response.send_message("Pilih event yang ingin dikelola:", view=v, ephemeral=True)

# ================= COMMANDS =================
@bot.command()
async def ta(ctx):
    await ctx.send("🏎️ **PANEL UTAMA**", view=MainView())

@bot.command()
async def help(ctx):
    await ctx.send(embed=help_embed())

@bot.command()
@commands.has_permissions(administrator=True)
async def create_event(ctx, name):
    events.insert_one({"name": name})
    await ctx.send(f"✅ Event **{name}** dibuat")

@bot.command()
@commands.has_permissions(administrator=True)
async def delete_event(ctx, name):
    events.delete_one({"name": name})
    await ctx.send(f"🗑️ Event **{name}** dihapus")

@bot.command()
@commands.has_permissions(administrator=True)
async def del_player(ctx, *, target: str):
    query = {"$or": [{"ign": target}, {"user_id": int(target) if target.isdigit() else 0}]}
    result = col.delete_one(query)
    if result.deleted_count: await ctx.send(f"🗑️ {target} dihapus")
    else: await ctx.send("❌ Tidak ditemukan")

# ================= RUN =================
@bot.event
async def on_ready():
    bot.add_view(MainView())
    print(f"BOT READY: {bot.user}")
    t = threading.Thread(target=run_web)
    t.daemon = True
    t.start()

bot.run(TOKEN)
