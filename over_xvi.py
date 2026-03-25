import discord
from discord.ext import commands
from discord import ui
from pymongo import MongoClient
import datetime, asyncio, re, io, threading, os, csv

# ================= CONFIG =================
TOKEN = 'MTQ4NjE1MTQ4NzUxOTQ1NzM2MA.GerHXg.UA69z1BlBK0aGtY63FEZo1dU9iSHn-TgtHl0i8'
MONGO_URL = "mongodb+srv://time-attack1:01010101@cluster0.smztndb.mongodb.net/?appName=Cluster0"

bot = commands.Bot(command_prefix="!", intents=discord.Intents.all(), help_command=None)
db = MongoClient(MONGO_URL)["over_xvi_db"]
col = db["timeattack"]
history = db["history"]

user_cooldowns = {}

# ================= HELPER =================
def parse_time(t):
    if not re.match(r'^\d{2}:\d{2}\.\d{3}$', t): return None
    try:
        m, s_ms = t.split(":"); s, ms = s_ms.split(".")
        return int(m)*60 + int(s) + float(f"0.{ms}")
    except: return None

def is_on_cooldown(user_id, seconds=10):
    now = datetime.datetime.now()
    if user_id in user_cooldowns:
        diff = (now - user_cooldowns[user_id]).total_seconds()
        if diff < seconds: return True, int(seconds - diff)
    user_cooldowns[user_id] = now
    return False, 0

# ================= ADMIN MODALS =================

class DeletePlayerModal(ui.Modal, title="Hapus Data Player"):
    target = ui.TextInput(label="IGN atau User ID", placeholder="Masukkan IGN atau ID Discord player...")

    async def on_submit(self, i: discord.Interaction):
        target_val = self.target.value
        query = {"$or": [{"ign": target_val}, {"user_id": int(target_val) if target_val.isdigit() else 0}]}
        result = col.delete_many(query)
        await i.response.send_message(f"✅ Berhasil menghapus {result.deleted_count} data untuk: **{target_val}**", ephemeral=True)

# ================= VIEWS =================

class AdminMenuView(ui.View):
    def __init__(self, event_name):
        super().__init__(timeout=60)
        self.event_name = event_name

    @ui.button(label="📥 Download Spreadsheet", style=discord.ButtonStyle.green)
    async def download_sheet(self, i: discord.Interaction, b: ui.Button):
        data = list(col.find({"event": self.event_name}).sort("waktu_raw", 1))
        if not data: return await i.response.send_message("❌ Tidak ada data.", ephemeral=True)
        
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["RANK", "IGN", "GAME ID", "CLUB", "TIME", "SUBMITTER", "DATE"])
        for idx, d in enumerate(data):
            writer.writerow([idx+1, d['ign'], f"'{d.get('game_id','-')}", d.get('club','-'), d['waktu'], d.get('submitter','-'), d.get('last_submit','-')])
        
        output.seek(0)
        file = discord.File(io.BytesIO(output.getvalue().encode()), filename=f"Admin_Report_{self.event_name}.csv")
        await i.response.send_message(f"📊 Laporan spreadsheet untuk **#{self.event_name}**:", file=file, ephemeral=True)

    @ui.button(label="👤 Hapus Player", style=discord.ButtonStyle.grey)
    async def del_player(self, i: discord.Interaction, b: ui.Button):
        await i.response.send_modal(DeletePlayerModal())

    @ui.button(label="🗑️ Reset Event Ini", style=discord.ButtonStyle.danger)
    async def reset_event(self, i: discord.Interaction, b: ui.Button):
        # Konfirmasi penghapusan seluruh data channel
        col.delete_many({"event": self.event_name})
        await i.response.send_message(f"⚠️ Seluruh data rekor di channel **#{self.event_name}** telah dihapus!", ephemeral=True)

    @ui.button(label="⬅️ Kembali", style=discord.ButtonStyle.secondary)
    async def back(self, i: discord.Interaction, b: ui.Button):
        await i.response.edit_message(content="🏎️ **PANEL UTAMA**", embed=None, view=MainView())

class LeaderboardView(ui.View):
    def __init__(self, data, event_name, page=0):
        super().__init__(timeout=60)
        self.data, self.event_name, self.page = data, event_name, page
        self.per_page = 10

    def create_embed(self):
        start = self.page * self.per_page
        current_data = self.data[start:start+self.per_page]
        desc = ""
        medals = ["🥇", "🥈", "🥉"]
        for idx, d in enumerate(current_data):
            pos = start + idx
            rank = medals[pos] if pos < 3 else f"{pos+1}."
            desc += f"{rank} **{d['ign']}** - `{d['waktu']}`\n"
        embed = discord.Embed(title=f"🏆 LEADERBOARD: #{self.event_name}", description=desc or "Kosong", color=0xf1c40f)
        total_p = (len(self.data)-1)//self.per_page + 1 if self.data else 1
        embed.set_footer(text=f"Halaman {self.page+1}/{total_p}")
        return embed

    @ui.button(label="⬅️ Prev", style=discord.ButtonStyle.grey)
    async def prev(self, i: discord.Interaction, b: ui.Button):
        if self.page > 0:
            self.page -= 1
            await i.response.edit_message(embed=self.create_embed(), view=self)
        else: await i.response.defer(ephemeral=True)

    @ui.button(label="Next ➡️", style=discord.ButtonStyle.grey)
    async def next(self, i: discord.Interaction, b: ui.Button):
        if (self.page + 1) * self.per_page < len(self.data):
            self.page += 1
            await i.response.edit_message(embed=self.create_embed(), view=self)
        else: await i.response.defer(ephemeral=True)

    @ui.button(label="Menu Awal", style=discord.ButtonStyle.red)
    async def back(self, i: discord.Interaction, b: ui.Button):
        await i.response.edit_message(content="🏎️ **PANEL UTAMA**", embed=None, view=MainView())

# ================= SUBMIT MODAL =================
class SubmitModal(ui.Modal, title="Submit Time"):
    ign = ui.TextInput(label="IGN", placeholder="Nickname game")
    game_id = ui.TextInput(label="ID Game", placeholder="Contoh: 666666666")
    club = ui.TextInput(label="Club", placeholder="Nama Club")
    time_val = ui.TextInput(label="Time (MM:SS.ms)", placeholder="00:46.000")

    async def on_submit(self, i: discord.Interaction):
        sec = parse_time(self.time_val.value)
        if sec is None or sec < 10:
            return await i.response.send_message("❌ Format salah!", ephemeral=True)

        event_name = i.channel.name
        await i.response.send_message("📸 Kirim screenshot hasil balapan.", ephemeral=True)

        def check(m): return m.author.id == i.user.id and m.attachments
        try:
            msg = await bot.wait_for("message", timeout=60, check=check)
            img = await msg.attachments[0].read()
            try: await msg.delete()
            except: pass

            data = {"user_id": i.user.id, "event": event_name, "ign": self.ign.value, "club": self.club.value, "game_id": self.game_id.value, "waktu": self.time_val.value, "waktu_raw": sec, "submitter": i.user.display_name, "last_submit": datetime.datetime.now()}
            col.update_one({"user_id": i.user.id, "event": event_name}, {"$set": data}, upsert=True)

            embed = discord.Embed(title="🌟 REKOR BARU TERCATAT", color=0x2ecc71)
            embed.add_field(name="👤 Peserta", value=self.ign.value, inline=True)
            embed.add_field(name="🛡️ Club", value=self.club.value, inline=True)
            embed.add_field(name="⏱️ Waktu", value=f"`{self.time_val.value}`", inline=False)
            embed.set_image(url="attachment://res.png")
            await i.channel.send(file=discord.File(io.BytesIO(img), "res.png"), embed=embed)
        except: pass

# ================= MAIN UI =================
class MainView(ui.View):
    def __init__(self): super().__init__(timeout=None)

    @ui.button(label="Submit Time", style=discord.ButtonStyle.green, custom_id="btn_sub")
    async def sub(self, i: discord.Interaction, b: ui.Button):
        on_cd, rem = is_on_cooldown(i.user.id, 10)
        if on_cd: return await i.response.send_message(f"⏳ Tunggu {rem} detik.", ephemeral=True)
        await i.response.send_modal(SubmitModal())

    @ui.button(label="Leaderboard", style=discord.ButtonStyle.blurple, custom_id="btn_lb")
    async def lb(self, i: discord.Interaction, b: ui.Button):
        data = list(col.find({"event": i.channel.name}).sort("waktu_raw", 1))
        await i.response.edit_message(content=None, embed=LeaderboardView(data, i.channel.name).create_embed(), view=LeaderboardView(data, i.channel.name))

    @ui.button(label="🛠️ Admin Menu", style=discord.ButtonStyle.grey, custom_id="btn_admin")
    async def admin(self, i: discord.Interaction, b: ui.Button):
        # PROTEKSI: Hanya admin server yang bisa masuk
        if not i.user.guild_permissions.administrator:
            return await i.response.send_message("🚫 Akses Ditolak! Hanya Admin yang boleh masuk.", ephemeral=True)
        
        embed = discord.Embed(title="🛠️ PANEL KONTROL ADMIN", description=f"Manajemen data untuk channel: **#{i.channel.name}**", color=0x34495e)
        await i.response.edit_message(content=None, embed=embed, view=AdminMenuView(i.channel.name))

# ================= COMMANDS =================
@bot.command()
async def ta(ctx): await ctx.send("🏎️ **PANEL UTAMA**", view=MainView())

@bot.event
async def on_ready():
    bot.add_view(MainView())
    print(f"ONLINE: {bot.user}")

bot.run(TOKEN)
