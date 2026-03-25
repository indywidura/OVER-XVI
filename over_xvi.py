import discord
from discord.ext import commands
from discord import ui
from pymongo import MongoClient
import datetime, asyncio, re, io, threading, os
from flask import Flask, jsonify

# ================= CONFIG =================
TOKEN = 'MTQ4NjE1MTQ4NzUxOTQ1NzM2MA.GerHXg.UA69z1BlBK0aGtY63FEZo1dU9iSHn-TgtHl0i8'
MONGO_URL = "mongodb+srv://time-attack1:01010101@cluster0.smztndb.mongodb.net/?appName=Cluster0"

bot = commands.Bot(command_prefix="!", intents=discord.Intents.all(), help_command=None)
db = MongoClient(MONGO_URL)["over_xvi_db"]
col = db["timeattack"]
history = db["history"]

# ================= WEB =================
app = Flask(__name__)
@app.route("/")
def home(): return jsonify(col.distinct("event"))

def run_web():
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)

# ================= HELPER =================
def parse_time(t):
    if not re.match(r'^\d{2}:\d{2}\.\d{3}$', t): return None
    try:
        m, s_ms = t.split(":"); s, ms = s_ms.split(".")
        return int(m)*60 + int(s) + float(f"0.{ms}")
    except: return None

# ================= VIEWS & PAGINATION =================

class LeaderboardView(ui.View):
    def __init__(self, data, event_name, page=0):
        super().__init__(timeout=60)
        self.data = data
        self.event_name = event_name
        self.page = page
        self.per_page = 10 # Tampilkan 10 data per halaman

    def create_embed(self):
        start = self.page * self.per_page
        end = start + self.per_page
        current_data = self.data[start:end]
        
        desc = ""
        medals = ["🥇", "🥈", "🥉"]
        for idx, d in enumerate(current_data):
            pos = start + idx
            rank = medals[pos] if pos < 3 else f"{pos+1}."
            desc += f"{rank} **{d['ign']}** - `{d['waktu']}`\n"
        
        embed = discord.Embed(title=f"🏆 LEADERBOARD: #{self.event_name}", 
                              description=desc or "Tidak ada data.", color=0xf1c40f)
        embed.set_footer(text=f"Halaman {self.page + 1} dari {(len(self.data)-1)//self.per_page + 1}")
        return embed

    @ui.button(label="⬅️ Prev", style=discord.ButtonStyle.grey)
    async def prev(self, i: discord.Interaction, b: ui.Button):
        if self.page > 0:
            self.page -= 1
            await i.response.edit_message(embed=self.create_embed(), view=self)
        else:
            await i.response.defer(ephemeral=True)

    @ui.button(label="Next ➡️", style=discord.ButtonStyle.grey)
    async def next(self, i: discord.Interaction, b: ui.Button):
        if (self.page + 1) * self.per_page < len(self.data):
            self.page += 1
            await i.response.edit_message(embed=self.create_embed(), view=self)
        else:
            await i.response.defer(ephemeral=True)

    @ui.button(label="Menu Awal", style=discord.ButtonStyle.red)
    async def back(self, i: discord.Interaction, b: ui.Button):
        await i.response.edit_message(content="🏎️ **PANEL UTAMA**", embed=None, view=MainView())

class HelpView(ui.View):
    def __init__(self):
        super().__init__(timeout=60)

    @ui.button(label="Kembali ke Menu", style=discord.ButtonStyle.red)
    async def back(self, i: discord.Interaction, b: ui.Button):
        await i.response.edit_message(content="🏎️ **PANEL UTAMA**", embed=None, view=MainView())

# ================= SUBMIT MODAL =================
class SubmitModal(ui.Modal, title="Submit Time"):
    ign = ui.TextInput(label="IGN", placeholder="Nama di dalam game")
    game_id = ui.TextInput(label="ID Game", placeholder="Contoh: 666666666")
    club = ui.TextInput(label="Club", placeholder="Nama Club")
    time_val = ui.TextInput(label="Time MM:SS.ms", placeholder="Contoh: 00:46.000")

    async def on_submit(self, i: discord.Interaction):
        sec = parse_time(self.time_val.value)
        if sec is None or sec < 10:
            return await i.response.send_message("❌ Format salah!", ephemeral=True)

        event_name = i.channel.name
        await i.response.send_message("📸 Upload screenshot sekarang.", ephemeral=True)

        def check(m): return m.author.id == i.user.id and m.attachments
        try:
            msg = await bot.wait_for("message", timeout=60, check=check)
            img = await msg.attachments[0].read()
            
            # FITUR: Hapus gambar asli peserta agar chat bersih
            try: await msg.delete()
            except: pass

            data = {
                "user_id": i.user.id, "event": event_name, "ign": self.ign.value,
                "club": self.club.value, "game_id": self.game_id.value,
                "waktu": self.time_val.value, "waktu_raw": sec,
                "submitter": i.user.display_name, "last_submit": datetime.datetime.now()
            }
            col.update_one({"user_id": i.user.id, "event": event_name}, {"$set": data}, upsert=True)
            history.insert_one({"user_id": i.user.id, "event": event_name, "time": self.time_val.value, "raw": sec, "date": datetime.datetime.now()})

            # Embed Hasil Sesuai Gambar 2
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
            await i.followup.send("❌ Waktu habis.", ephemeral=True)

# ================= MAIN UI =================
class MainView(ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @ui.button(label="Submit Time", style=discord.ButtonStyle.green, custom_id="btn_submit")
    async def sub(self, i: discord.Interaction, b: ui.Button):
        await i.response.send_modal(SubmitModal())

    @ui.button(label="Leaderboard", style=discord.ButtonStyle.blurple, custom_id="btn_lb")
    async def lb(self, i: discord.Interaction, b: ui.Button):
        event_name = i.channel.name
        data = list(col.find({"event": event_name}).sort("waktu_raw", 1))
        
        view = LeaderboardView(data, event_name)
        await i.response.edit_message(content=None, embed=view.create_embed(), view=view)

    @ui.button(label="📖 Help", style=discord.ButtonStyle.grey, custom_id="btn_help")
    async def help_btn(self, i: discord.Interaction, b: ui.Button):
        embed = discord.Embed(title="📖 HELP MENU", color=0x3498db)
        embed.add_field(name="Format", value="Wajib `MM:SS.ms` (Contoh: `00:46.000`)", inline=False)
        embed.add_field(name="Channel", value="Bot merekam data berdasarkan nama channel otomatis.", inline=False)
        await i.response.edit_message(content=None, embed=embed, view=HelpView())

# ================= COMMANDS =================
@bot.command()
async def ta(ctx):
    await ctx.send("🏎️ **PANEL UTAMA**", view=MainView())

@bot.event
async def on_ready():
    bot.add_view(MainView())
    print(f"BOT ONLINE: {bot.user}")
    threading.Thread(target=run_web, daemon=True).start()

bot.run(TOKEN)
