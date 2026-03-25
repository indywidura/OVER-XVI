import discord
from discord.ext import commands
from discord import ui
from pymongo import MongoClient
import datetime, asyncio, re, io, threading, os
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

# ================= WEB =================
app = Flask(__name__)

@app.route("/")
def home():
    # Mengambil daftar event unik dari database rekor
    events = col.distinct("event")
    return jsonify(events)

def run_web():
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)

# ================= HELPER =================
def parse_time(t):
    if not re.match(r'^\d{2}:\d{2}\.\d{3}$', t):
        return None
    try:
        m, s_ms = t.split(":")
        s, ms = s_ms.split(".")
        return int(m)*60 + int(s) + float(f"0.{ms}")
    except:
        return None

def help_embed():
    embed = discord.Embed(
        title="📖 PANDUAN OVER-XVI",
        description="Bot ini mencatat waktu balapan otomatis berdasarkan channel.",
        color=0x3498db
    )
    embed.add_field(name="🏎️ Cara Submit", value="Klik tombol **Submit Time**, isi form, lalu upload screenshot.", inline=False)
    embed.add_field(name="📝 Format Waktu", value="Wajib `MM:SS.ms` (Contoh: `00:46.000`)", inline=False)
    embed.add_field(name="📊 Leaderboard", value="Klik tombol **Leaderboard** untuk melihat rekor di channel ini.", inline=False)
    return embed

# ================= SUBMIT MODAL =================
class SubmitModal(ui.Modal, title="Submit Time"):
    ign = ui.TextInput(label="IGN (In-Game Name)", placeholder="Nama di dalam game")
    game_id = ui.TextInput(label="ID Game", placeholder="Contoh: 666666666")
    club = ui.TextInput(label="Club", placeholder="Nama Club")
    time_val = ui.TextInput(label="Time MM:SS.ms", placeholder="Contoh: 00:46.000")

    async def on_submit(self, i: discord.Interaction):
        sec = parse_time(self.time_val.value)
        if sec is None:
            return await i.response.send_message("❌ Format salah! Gunakan `00:46.000`", ephemeral=True)

        # Otomatis mengambil nama channel sebagai nama Event
        event_name = i.channel.name

        await i.response.send_message("📸 Upload screenshot hasil balapan kamu.", ephemeral=True)

        def check(m): return m.author.id == i.user.id and m.attachments

        try:
            msg = await bot.wait_for("message", timeout=60, check=check)
            img = await msg.attachments[0].read()

            data = {
                "user_id": i.user.id,
                "event": event_name,
                "ign": self.ign.value,
                "club": self.club.value,
                "game_id": self.game_id.value,
                "waktu": self.time_val.value,
                "waktu_raw": sec,
                "submitter": i.user.display_name,
                "last_submit": datetime.datetime.now()
            }
            
            col.update_one(
                {"user_id": i.user.id, "event": event_name},
                {"$set": data},
                upsert=True
            )

            # Embed Hasil (Sesuai Gambar 2)
            embed = discord.Embed(title="🌟 REKOR BARU TERCATAT", color=0x2ecc71)
            embed.add_field(name="👤 Peserta", value=self.ign.value, inline=False)
            embed.add_field(name="🛡️ Club", value=self.club.value, inline=False)
            embed.add_field(name="🆔 ID Game", value=self.game_id.value, inline=False)
            embed.add_field(name="⏱️ Waktu", value=self.time_val.value, inline=False)
            embed.set_footer(text=f"Submitter: {i.user.display_name}")

            file = discord.File(io.BytesIO(img), filename="result.png")
            embed.set_image(url="attachment://result.png")

            await i.channel.send(file=file, embed=embed)
        except asyncio.TimeoutError:
            await i.followup.send("❌ Waktu upload habis.", ephemeral=True)

# ================= MAIN VIEW =================
class MainView(ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @ui.button(label="Submit Time", style=discord.ButtonStyle.green, custom_id="btn_submit")
    async def sub(self, i: discord.Interaction, b: ui.Button):
        # Langsung munculkan Modal tanpa pilih event
        await i.response.send_modal(SubmitModal())

    @ui.button(label="Leaderboard", style=discord.ButtonStyle.blurple, custom_id="btn_lb")
    async def lb(self, i: discord.Interaction, b: ui.Button):
        event_name = i.channel.name
        data = list(col.find({"event": event_name}).sort("waktu_raw", 1))
        
        desc = ""
        medals = ["🥇", "🥈", "🥉"]
        for idx, d in enumerate(data[:10]):
            rank = medals[idx] if idx < 3 else f"{idx+1}."
            desc += f"{rank} **{d['ign']}** - `{d['waktu']}`\n"

        embed = discord.Embed(
            title=f"🏆 LEADERBOARD: #{event_name}", 
            description=desc or "Belum ada rekor di channel ini.", 
            color=0xf1c40f
        )
        # Kirim sebagai pesan baru yang hanya bisa dilihat user (ephemeral)
        await i.response.send_message(embed=embed, ephemeral=True)

    @ui.button(label="📖 Help", style=discord.ButtonStyle.grey, custom_id="btn_help")
    async def help_btn(self, i: discord.Interaction, b: ui.Button):
        await i.response.send_message(embed=help_embed(), ephemeral=True)

# ================= COMMANDS =================
@bot.command()
async def ta(ctx):
    await ctx.send("🏎️ **PANEL UTAMA**", view=MainView())

@bot.event
async def on_ready():
    bot.add_view(MainView())
    print(f"BOT READY: {bot.user}")
    threading.Thread(target=run_web, daemon=True).start()

bot.run(TOKEN)
