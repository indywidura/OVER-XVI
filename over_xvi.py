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
events = db["events"]

# ================= WEB =================
app = Flask(__name__)

@app.route("/")
def home():
    return jsonify(list(events.find({}, {"_id":0})))

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

def clean(x): return x if x else "N/A"

def help_embed():
    embed = discord.Embed(
        title="📖 PANDUAN PERINTAH BOT",
        description="Gunakan tombol di bawah atau command berikut:",
        color=0x3498db
    )
    embed.add_field(name="🏎️ Player Commands", value="`!ta` - Membuka Panel Utama\n`!help` - Menampilkan panduan ini", inline=False)
    embed.add_field(name="🛠️ Admin Commands", value="`!create_event <nama>` - Buat event baru\n`!delete_event <nama>` - Hapus event\n`!del_player <IGN/ID>` - Hapus data player", inline=False)
    embed.add_field(name="📝 Format Waktu", value="Wajib menggunakan format `MM:SS.ms`.\nContoh: `00:46.000`", inline=False)
    embed.set_footer(text="OVER-XVI System • v2.0")
    return embed

# ================= SUBMIT MODAL =================
class SubmitModal(ui.Modal, title="Submit Time"):
    ign = ui.TextInput(label="IGN (In-Game Name)", placeholder="Nama di dalam game")
    game_id = ui.TextInput(label="ID Game", placeholder="Contoh: 666666666")
    club = ui.TextInput(label="Club", placeholder="Nama Club")
    time_val = ui.TextInput(label="Time MM:SS.ms", placeholder="Contoh: 00:46.000")

    def __init__(self, event_target):
        super().__init__()
        self.event_target = event_target # Mengunci event dari pilihan dropdown

    async def on_submit(self, i: discord.Interaction):
        sec = parse_time(self.time_val.value)
        if sec is None:
            return await i.response.send_message("❌ Format salah! Gunakan `MM:SS.ms` (Contoh: 00:46.000)", ephemeral=True)

        await i.response.send_message("📸 Upload screenshot hasil balapan kamu di channel ini.", ephemeral=True)

        def check(m): return m.author.id == i.user.id and m.attachments

        try:
            msg = await bot.wait_for("message", timeout=60, check=check)
            img = await msg.attachments[0].read()

            data = {
                "user_id": i.user.id,
                "event": self.event_target,
                "ign": self.ign.value,
                "club": self.club.value,
                "game_id": self.game_id.value,
                "waktu": self.time_val.value,
                "waktu_raw": sec,
                "submitter": str(i.user),
                "last_submit": datetime.datetime.now()
            }
            
            col.update_one(
                {"user_id": i.user.id, "event": self.event_target},
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
            await i.followup.send("❌ Timeout: Kamu tidak mengunggah gambar tepat waktu.", ephemeral=True)

# ================= UI COMPONENTS =================
class SelectionView(ui.View):
    """View untuk memilih event sebelum Submit atau melihat Leaderboard"""
    def __init__(self, mode="lb"):
        super().__init__(timeout=60)
        self.mode = mode # 'lb' untuk Leaderboard, 'sub' untuk Submit
        
        options = [discord.SelectOption(label=e["name"]) for e in events.find()]
        if not options:
            options = [discord.SelectOption(label="Tidak ada event aktif", value="none")]
        
        self.select = ui.Select(placeholder="Pilih Nama Event...", options=options)
        self.select.callback = self.select_callback
        self.add_item(self.select)

    async def select_callback(self, i: discord.Interaction):
        if self.select.values[0] == "none": return
        event = self.select.values[0]

        if self.mode == "sub":
            await i.response.send_modal(SubmitModal(event_target=event))
        else:
            # Tampilkan Leaderboard
            data = list(col.find({"event": event}).sort("waktu_raw", 1))
            desc = ""
            medals = ["🥇", "🥈", "🥉"]
            for idx, d in enumerate(data[:10]):
                rank = medals[idx] if idx < 3 else f"{idx+1}."
                desc += f"{rank} **{d['ign']}** - `{d['waktu']}`\n"

            embed = discord.Embed(title=f"🏆 LEADERBOARD: {event}", description=desc or "Belum ada rekor.", color=0xf1c40f)
            
            # Tombol Back
            back_view = ui.View()
            btn_back = ui.Button(label="Kembali ke Menu", style=discord.ButtonStyle.red)
            async def back_cb(interaction):
                await interaction.response.edit_message(content="🏎️ PANEL UTAMA", embed=None, view=MainView())
            btn_back.callback = back_cb
            back_view.add_item(btn_back)

            await i.response.edit_message(content=None, embed=embed, view=back_view)

    @ui.button(label="Batal", style=discord.ButtonStyle.grey)
    async def cancel(self, i: discord.Interaction, b: ui.Button):
        await i.response.edit_message(content="🏎️ PANEL UTAMA", view=MainView())

class HelpView(ui.View):
    def __init__(self):
        super().__init__(timeout=60)

    @ui.button(label="Kembali ke Menu", style=discord.ButtonStyle.red)
    async def back(self, i: discord.Interaction, b: ui.Button):
        await i.response.edit_message(content="🏎️ PANEL UTAMA", embed=None, view=MainView())

class MainView(ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @ui.button(label="Submit Time", style=discord.ButtonStyle.green, custom_id="btn_submit")
    async def sub(self, i: discord.Interaction, b: ui.Button):
        await i.response.send_message("Pilih event yang ingin kamu ikuti:", view=SelectionView(mode="sub"), ephemeral=True)

    @ui.button(label="Leaderboard", style=discord.ButtonStyle.blurple, custom_id="btn_lb")
    async def lb(self, i: discord.Interaction, b: ui.Button):
        await i.response.edit_message(content="Pilih event untuk melihat Leaderboard:", view=SelectionView(mode="lb"))

    @ui.button(label="📖 Help", style=discord.ButtonStyle.grey, custom_id="btn_help")
    async def help_btn(self, i: discord.Interaction, b: ui.Button):
        await i.response.edit_message(content=None, embed=help_embed(), view=HelpView())

# ================= COMMANDS =================
@bot.command()
async def ta(ctx):
    await ctx.send("🏎️ PANEL UTAMA", view=MainView())

@bot.command()
async def help(ctx):
    await ctx.send(embed=help_embed())

@bot.command()
@commands.has_permissions(administrator=True)
async def create_event(ctx, name):
    events.update_one({"name": name}, {"$set": {"name": name}}, upsert=True)
    await ctx.send(f"✅ Event **{name}** telah diaktifkan.")

@bot.event
async def on_ready():
    bot.add_view(MainView())
    print(f"BOT ONLINE: {bot.user}")
    threading.Thread(target=run_web, daemon=True).start()

bot.run(TOKEN)
