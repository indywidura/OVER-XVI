import discord
from discord.ext import commands
from discord import ui
from pymongo import MongoClient
import datetime
import math
import io
import csv
import asyncio

# --- KONFIGURASI ---
TOKEN = 'MTQ4NjE1MTQ4NzUxOTQ1NzM2MA.GerHXg.UA69z1BlBK0aGtY63FEZo1dU9iSHn-TgtHl0i8'
MONGO_URL = "mongodb+srv://time-attack1:01010101@cluster0.smztndb.mongodb.net/?appName=Cluster0"

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix='!', intents=intents, help_command=None)

cluster = MongoClient(MONGO_URL)
db = cluster["over_xvi_db"]
collection = db["timeattack"]

# --- HELPER FUNCTIONS ---
def time_to_seconds(time_str):
    """Sortir akurat: Mengonversi format waktu ke angka detik."""
    try:
        parts = time_str.replace(':', '.').split('.')
        if len(parts) == 3: 
            return int(parts[0]) * 60 + int(parts[1]) + float(f"0.{parts[2]}")
        elif len(parts) == 2: 
            return int(parts[0]) + float(f"0.{parts[1]}")
        return float(time_str)
    except:
        return 999999.0

def clean_text(text):
    """Membersihkan karakter khusus agar tidak error di HP."""
    if not text: return "N/A"
    return "".join(i for i in text if ord(i) < 128)

async def export_to_csv(channel_id):
    """Ekspor data channel spesifik ke CSV."""
    results = list(collection.find({"channel_id": channel_id}).sort("waktu_raw", 1))
    if not results: return None
    output = io.StringIO()
    writer = csv.writer(output, delimiter=',', quotechar='"')
    writer.writerow(['RANK', 'IGN', 'ID GAME', 'CLUB', 'TIME', 'SUBMITTED'])
    for i, row in enumerate(results, 1):
        st = row.get('last_submit')
        fmt_date = st.strftime("%d/%m/%y %H:%M") if isinstance(st, datetime.datetime) else "N/A"
        writer.writerow([f"#{i}", clean_text(row.get('ign')), row.get('game_id'), clean_text(row.get('club')), row.get('waktu'), fmt_date])
    output.seek(0)
    return discord.File(io.BytesIO(output.getvalue().encode('utf-8')), filename=f"REKAP_{channel_id}.csv")

# --- UI COMPONENTS ---
class SubmitModal(ui.Modal, title='Submit Time Attack'):
    ign = ui.TextInput(label='Nama In-Game (IGN)', placeholder='RFF•SuperFae')
    idx = ui.TextInput(label='ID In-Game', placeholder='12345678')
    clb = ui.TextInput(label='Nama Club', placeholder='APEX')
    wkt = ui.TextInput(label='Waktu (MM:SS.ms)', placeholder='01:35.34')

    async def on_submit(self, interaction: discord.Interaction):
        uid, cid = interaction.user.id, interaction.channel_id
        
        # Anti-Spam: Cek cooldown 10 menit.
        user_data = collection.find_one({"_id": f"{uid}_{cid}"})
        if user_data and "last_submit" in user_data:
            diff = datetime.datetime.now() - user_data["last_submit"]
            if diff.total_seconds() < 600:
                return await interaction.response.send_message(f"⏳ Tunggu {int((600-diff.total_seconds())/60)} menit lagi.", ephemeral=True)

        await interaction.response.send_message(f"✅ Terdaftar! Kirim screenshot rekor sekarang.", ephemeral=True)
        def check(m): return m.author.id == uid and m.channel.id == cid and m.attachments
        
        try:
            msg = await bot.wait_for('message', timeout=60.0, check=check)
            img = await msg.attachments[0].read()
            collection.update_one(
                {"_id": f"{uid}_{cid}"}, 
                {"$set": {
                    "user_id": uid, "channel_id": cid, "ign": self.ign.value, 
                    "game_id": self.idx.value, "club": self.clb.value, 
                    "waktu": self.wkt.value, "waktu_raw": time_to_seconds(self.wkt.value),
                    "last_submit": datetime.datetime.now()
                }}, upsert=True
            )
            try: await msg.delete() 
            except: pass

            embed = discord.Embed(title="🌟 REKOR BARU TERCATAT", color=0x2ecc71)
            embed.add_field(name="👤 Peserta", value=f"**{self.ign.value}**", inline=False)
            embed.add_field(name="🛡️ Club", value=f"{self.clb.value}", inline=False)
            embed.add_field(name="🆔 ID Game", value=f"{self.idx.value}", inline=False)
            embed.add_field(name="⏱️ Waktu", value=f"`{self.wkt.value}`", inline=False)
            embed.set_footer(text=f"Submitter: {interaction.user.display_name}")
            file = discord.File(io.BytesIO(img), filename="rekor.png")
            embed.set_image(url="attachment://rekor.png")
            await interaction.channel.send(file=file, embed=embed)
        except asyncio.TimeoutError:
            await interaction.followup.send("⚠️ Waktu habis!", ephemeral=True)

class LeaderboardPagination(ui.View):
    def __init__(self, cid, page=1):
        super().__init__(timeout=60)
        self.cid, self.page = cid, page
    @ui.button(label='⬅️ Prev', style=discord.ButtonStyle.blurple)
    async def prev(self, interaction, button):
        if self.page > 1: self.page -= 1; await self.update(interaction)
        else: await interaction.response.defer()
    @ui.button(label='Next ➡️', style=discord.ButtonStyle.blurple)
    async def next(self, interaction, button):
        _, tp = create_lb_embed(self.cid, self.page)
        if self.page < tp: self.page += 1; await self.update(interaction)
        else: await interaction.response.defer()
    @ui.button(label='📊 Export', style=discord.ButtonStyle.green)
    async def export(self, interaction, button):
        if not interaction.user.guild_permissions.administrator: return await interaction.response.send_message("❌ Admin Only!", ephemeral=True)
        f = await export_to_csv(self.cid)
        if f: await interaction.response.send_message("📂 Data Channel:", file=f, ephemeral=True)
    @ui.button(label='🏠 Menu', style=discord.ButtonStyle.red)
    async def back_to_menu(self, interaction, button):
        await interaction.response.edit_message(embed=discord.Embed(title="🏎️ TIME ATTACK", color=0x2ecc71), view=PersistentView())
    async def update(self, interaction):
        emb, _ = create_lb_embed(self.cid, self.page)
        await interaction.response.edit_message(embed=emb, view=self)

def create_lb_embed(cid, page=1):
    res = list(collection.find({"channel_id": cid}).sort("waktu_raw", 1)) 
    tp = math.ceil(len(res) / 10) or 1
    if not res: return discord.Embed(title="⏱️ LEADERBOARD", description="Kosong.", color=0xff0000), 1
    data = res[(page-1)*10 : page*10]
    table = "RK | IGN             | TIME\n---|-----------------|----------\n"
    for i, r in enumerate(data, (page-1)*10 + 1):
        table += f"{i:<2} | {clean_text(r.get('ign'))[:15]:<15} | {r.get('waktu')}\n"
    emb = discord.Embed(title="⏱️ LEADERBOARD", description=f"```\n{table}```", color=0x3498db)
    emb.set_footer(text=f"Halaman {page}/{tp}")
    return emb, tp

class PersistentView(ui.View):
    def __init__(self): super().__init__(timeout=None) 
    @ui.button(label='Submit', style=discord.ButtonStyle.green, custom_id='sub_v')
    async def sub(self, interaction, button): await interaction.response.send_modal(SubmitModal())
    @ui.button(label='Leaderboard', style=discord.ButtonStyle.grey, custom_id='lb_v')
    async def lb(self, interaction, button):
        emb, _ = create_lb_embed(interaction.channel_id, 1)
        await interaction.response.send_message(embed=emb, view=LeaderboardPagination(interaction.channel_id, 1), ephemeral=True)

# --- SIMPLE COMMANDS ---
@bot.event
async def on_ready(): bot.add_view(PersistentView()); print(f'{bot.user.name} online!')

@bot.command(name="ta")
async def setup_ta_simple(ctx):
    """Menampilkan panel utama."""
    await ctx.send(embed=discord.Embed(title="🏎️ TIME ATTACK COMPETITION", color=0x2ecc71), view=PersistentView())

@bot.command(name="reset")
@commands.has_permissions(administrator=True)
async def reset_channel_simple(ctx):
    """Hapus data hanya di channel ini."""
    collection.delete_many({"channel_id": ctx.channel.id})
    await ctx.send(f"✅ Data channel **{ctx.channel.name}** dihapus.")

@bot.command(name="clear")
@commands.has_permissions(administrator=True)
async def reset_global_simple(ctx):
    """Hapus seluruh data global."""
    def check(m): return m.author == ctx.author and m.content.lower() == 'konfirmasi'
    await ctx.send("⚠️ Ketik `konfirmasi` untuk hapus SEMUA data global.")
    try:
        await bot.wait_for('message', timeout=15.0, check=check)
        collection.delete_many({}) 
        await ctx.send("✅ Database bersih.")
    except asyncio.TimeoutError: await ctx.send("❌ Reset dibatalkan.")

@bot.command(name="del")
@commands.has_permissions(administrator=True)
async def delete_one_simple(ctx, *, ign: str):
    """Menghapus satu pemain berdasarkan IGN."""
    collection.delete_one({"channel_id": ctx.channel.id, "ign": {"$regex": f"^{ign}$", "$options": "i"}})
    await ctx.send(f"🗑️ Data **{ign}** dihapus.")

bot.run(TOKEN)
