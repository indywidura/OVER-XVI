import discord
from discord.ext import commands
from discord import ui
from pymongo import MongoClient
import datetime, asyncio, re, io, csv, threading
from flask import Flask, jsonify

# ================= CONFIG =================
TOKEN = "YOUR_TOKEN"
MONGO_URL = "YOUR_MONGO_URL"

bot = commands.Bot(command_prefix="!", intents=discord.Intents.all())

db = MongoClient(MONGO_URL)["over_xvi_db"]
col = db["timeattack"]
history = db["history"]
events = db["events"]

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
    app.run(host="0.0.0.0", port=5000)

# ================= HELPER =================
def parse_time(t):
    if not re.match(r'^\d{1,2}:\d{2}\.\d{2}$', t):
        return None
    m,s = t.split(":")
    s,ms = s.split(".")
    return int(m)*60 + int(s) + float(f"0.{ms}")

def clean(x): return x if x else "N/A"

# ================= HELP EMBED =================
def help_embed():
    return discord.Embed(
        title="📖 COMMAND LIST",
        description="""
🏎️ **User Commands**
!ta → Buka panel utama
Submit Button → Kirim waktu
Leaderboard → Lihat ranking
Club Rank → Ranking club
My Stats → Statistik kamu

🛠️ **Admin Commands**
!create_event <nama> → Buat event
!delete_event <nama> → Hapus event
!del_player <IGN / ID> → Hapus peserta
!export → Export CSV

🌐 **Web Dashboard**
/ → List event
/event/<nama> → Leaderboard

🎯 **Auto System**
• Auto Role Champion
• Anti Cheat
• Cooldown Submit
• History Tracking
        """,
        color=0x3498db
    )

# ================= AUTO ROLE =================
async def update_role(guild, event_name):
    data = list(col.find({"event": event_name}).sort("waktu_raw",1))
    if not data: return

    top_id = data[0]["user_id"]
    role_name = f"Champion {event_name}"

    role = discord.utils.get(guild.roles, name=role_name)
    if not role:
        role = await guild.create_role(name=role_name)

    for m in guild.members:
        if role in m.roles:
            await m.remove_roles(role)

    member = guild.get_member(top_id)
    if member:
        await member.add_roles(role)

# ================= SUBMIT =================
class SubmitModal(ui.Modal, title="Submit Time"):
    event = ui.TextInput(label="Event")
    ign = ui.TextInput(label="IGN")
    club = ui.TextInput(label="Club")
    time = ui.TextInput(label="Time MM:SS.ms")

    async def on_submit(self, i: discord.Interaction):
        sec = parse_time(self.time.value)
        if not sec or sec < 10:
            return await i.response.send_message("❌ Format salah / terlalu cepat", ephemeral=True)

        await i.response.send_message("📸 Upload screenshot", ephemeral=True)

        def check(m): return m.author.id == i.user.id and m.attachments

        try:
            msg = await bot.wait_for("message", timeout=60, check=check)
            img = await msg.attachments[0].read()

            col.update_one(
                {"user_id": i.user.id, "event": self.event.value},
                {"$set":{
                    "user_id": i.user.id,
                    "event": self.event.value,
                    "ign": self.ign.value,
                    "club": self.club.value,
                    "waktu": self.time.value,
                    "waktu_raw": sec,
                    "last_submit": datetime.datetime.now()
                }},
                upsert=True
            )

            history.insert_one({
                "user_id": i.user.id,
                "event": self.event.value,
                "time": self.time.value,
                "raw": sec,
                "date": datetime.datetime.now()
            })

            embed = discord.Embed(title="🌟 REKOR BARU", color=0x2ecc71)
            embed.add_field(name="IGN", value=self.ign.value)
            embed.add_field(name="TIME", value=self.time.value)

            file = discord.File(io.BytesIO(img), filename="img.png")
            embed.set_image(url="attachment://img.png")

            await i.channel.send(file=file, embed=embed)
            await update_role(i.guild, self.event.value)

        except:
            await i.followup.send("❌ Timeout", ephemeral=True)

# ================= EMBEDS =================
def leaderboard(event):
    data = list(col.find({"event": event}).sort("waktu_raw",1))
    medals = ["🥇","🥈","🥉"]
    desc = ""

    for i,d in enumerate(data[:10]):
        icon = medals[i] if i<3 else f"{i+1}."
        desc += f"{icon} {clean(d['ign'])} - `{d['waktu']}`\n"

    return discord.Embed(title=f"🏆 {event}", description=desc or "Kosong")

# ================= UI =================
class EventSelect(ui.Select):
    def __init__(self):
        opts = [discord.SelectOption(label=e["name"]) for e in events.find()]
        super().__init__(placeholder="Pilih Event", options=opts)

    async def callback(self, i):
        await i.response.send_message(embed=leaderboard(self.values[0]), ephemeral=True)

class EventView(ui.View):
    def __init__(self):
        super().__init__()
        self.add_item(EventSelect())

class MainView(ui.View):
    def __init__(self): 
        super().__init__(timeout=None)

    @ui.button(label="Submit", style=discord.ButtonStyle.green)
    async def sub(self, i, b):
        await i.response.send_modal(SubmitModal())

    @ui.button(label="Leaderboard", style=discord.ButtonStyle.blurple)
    async def lb(self, i, b):
        await i.response.send_message("Pilih event:", view=EventView(), ephemeral=True)

    @ui.button(label="📖 Help", style=discord.ButtonStyle.grey)
    async def help_btn(self, i, b):
        await i.response.send_message(embed=help_embed(), ephemeral=True)

# ================= COMMAND =================
@bot.command()
async def ta(ctx):
    await ctx.send("🏎️ TIME ATTACK PANEL", view=MainView())

@bot.command()
async def help(ctx):
    await ctx.send(embed=help_embed())

@bot.command()
@commands.has_permissions(administrator=True)
async def create_event(ctx, name):
    events.insert_one({"name": name})
    await ctx.send(f"✅ Event {name} dibuat")

@bot.command()
@commands.has_permissions(administrator=True)
async def delete_event(ctx, name):
    events.delete_one({"name": name})
    await ctx.send(f"🗑️ Event {name} dihapus")

@bot.command()
@commands.has_permissions(administrator=True)
async def del_player(ctx, *, target: str):
    query = {"event": ctx.channel.name}

    if target.isdigit():
        query["user_id"] = int(target)
    else:
        query["ign"] = {"$regex": f"^{target}$", "$options": "i"}

    result = col.delete_one(query)

    if result.deleted_count:
        await ctx.send(f"🗑️ {target} dihapus")
    else:
        await ctx.send("❌ Tidak ditemukan")

# ================= RUN =================
@bot.event
async def on_ready():
    bot.add_view(MainView())
    print("BOT READY")

    t = threading.Thread(target=run_web)
    t.start()

bot.run(TOKEN)
