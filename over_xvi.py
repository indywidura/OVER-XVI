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

# --- FUNGSI PEMBERSIH TEKS (Mencegah Karakter Error di HP) ---
def clean_text(text):
    if not text: return "N/A"
    return "".join(i for i in text if ord(i) < 128)

# --- FUNGSI EKSPOR CSV BERSIH ---
async def export_to_csv():
    results = list(collection.find().sort("waktu", 1))
    if not results: return None
    output = io.StringIO()
    writer = csv.writer(output, delimiter=',', quotechar='"')
    writer.writerow(['RANK', 'NAMA PEMAIN', 'ID GAME', 'NAMA CLUB', 'REKOR WAKTU', 'WAKTU SUBMIT'])
    for i, row in enumerate(results, 1):
        submit_time = row.get('last_submit')
        fmt_date = submit_time.strftime("%d %b %Y, %H:%M") if isinstance(submit_time, datetime.datetime) else "N/A"
        writer.writerow([f"#{i}", clean_text(row.get('ign')), f"ID:{row.get('game_id', 'N/A')}", clean_text(row.get('club')), row.get('waktu', 'N/A'), fmt_date])
    output.seek(0)
    return discord.File(io.BytesIO(output.getvalue().encode('utf-8')), filename=f"REKAP_TA_FIXED_{datetime.date.today()}.csv")

# --- MODAL SUBMIT DENGAN ANTI-SPAM ---
class SubmitModal(ui.Modal, title='Submit Time Attack'):
    ign_input = ui.TextInput(label='Nama In-Game (IGN)', placeholder='Contoh: RFF•SuperFae')
    id_input = ui.TextInput(label='ID In-Game', placeholder='Masukkan ID Akun')
    club_input = ui.TextInput(label='Nama Club', placeholder='Contoh: APEX')
    waktu_input = ui.TextInput(label='Waktu (MM:SS.ms)', placeholder='Contoh: 01:35.34')

    async def on_submit(self, interaction: discord.Interaction):
        user_id = interaction.user.id
        user_data = collection.find_one({"_id": user_id})
        if user_data and "last_submit" in user_data:
            diff = datetime.datetime.now() - user_data["last_submit"]
            if diff.total_seconds() < 600:
                return await interaction.response.send_message(f"⏳ **Anti-Spam!** Tunggu {int((600-diff.total_seconds())/60)} menit lagi.", ephemeral=True)

        await interaction.response.send_message(f"✅ Data terdaftar! Kirim screenshot rekor Anda sekarang.", ephemeral=True)
        def check(m): return m.author.id == user_id and m.channel == interaction.channel and m.attachments
        try:
            msg = await bot.wait_for('message', timeout=60.0, check=check)
            img_bytes = await msg.attachments[0].read()
            collection.update_one({"_id": user_id}, {"$set": {"ign": self.ign_input.value, "game_id": self.id_input.value, "club": self.club_input.value, "waktu": self.waktu_input.value, "last_submit": datetime.datetime.now()}}, upsert=True)
            await asyncio.sleep(1)
            try: await msg.delete() # Menghapus pesan asli user
            except: pass
            embed = discord.Embed(title="🌟 REKOR BARU TERCATAT", color=0x2ecc71)
            embed.add_field(name="👤 Peserta", value=f"**{self.ign_input.value}**", inline=True)
            embed.add_field(name="⏱️ Waktu", value=f"`{self.waktu_input.value}`", inline=True)
            file = discord.File(io.BytesIO(img_bytes), filename="rekor.png")
            embed.set_image(url="attachment://rekor.png") # Re-upload gambar
            await interaction.channel.send(file=file, embed=embed)
        except: await interaction.followup.send("⚠️ Waktu habis atau terjadi kesalahan.", ephemeral=True)

# --- VIEW LEADERBOARD (DENGAN TOMBOL MENU) ---
class LeaderboardPagination(ui.View):
    def __init__(self, page=1):
        super().__init__(timeout=60)
        self.page = page

    @ui.button(label='⬅️ Prev', style=discord.ButtonStyle.blurple)
    async def prev(self, interaction, button):
        if self.page > 1:
            self.page -= 1
            await self.update_view(interaction)

    @ui.button(label='Next ➡️', style=discord.ButtonStyle.blurple)
    async def next(self, interaction, button):
        self.page += 1
        await self.update_view(interaction)

    @ui.button(label='📊 Export CSV (Admin)', style=discord.ButtonStyle.green)
    async def export(self, interaction, button):
        if not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message("❌ Hanya Admin!", ephemeral=True)
        file = await export_to_csv()
        await interaction.response.send_message("📂 File CSV Bersih:", file=file, ephemeral=True)

    @ui.button(label='🏠 Menu', style=discord.ButtonStyle.red)
    async def back_to_menu(self, interaction, button):
        embed = discord.Embed(title="🏎️ TIME ATTACK COMPETITION", color=0x2ecc71)
        embed.description = "Gunakan tombol di bawah untuk berpartisipasi."
        await interaction.response.edit_message(embed=embed, view=PersistentView())

    async def update_view(self, interaction):
        embed, _ = create_leaderboard_embed(self.page)
        await interaction.response.edit_message(embed=embed, view=self)

def create_leaderboard_embed(page=1):
    items_per_page = 10
    results = list(collection.find().sort("waktu", 1)) 
    total_pages = math.ceil(len(results) / items_per_page) or 1
    if not results: return discord.Embed(title="⏱️ LEADERBOARD", description="Belum ada data.", color=0xff0000), 1
    start = (page - 1) * items_per_page
    current_data = results[start:start+items_per_page]
    table = "RK | IGN             | TIME\n---|-----------------|----------\n"
    for i, row in enumerate(current_data, start + 1):
        table += f"{i:<2} | {clean_text(row.get('ign'))[:15]:<15} | {row.get('waktu')}\n"
    embed = discord.Embed(title="⏱️ TIME ATTACK LEADERBOARD", description=f"```\n{table}```", color=0x3498db)
    embed.set_footer(text=f"Halaman {page}/{total_pages}")
    return embed, total_pages

class PersistentView(ui.View):
    def __init__(self):
        super().__init__(timeout=None) 
    @ui.button(label='Submit Your Time', style=discord.ButtonStyle.green, custom_id='submit_btn')
    async def sub(self, interaction, button):
        await interaction.response.send_modal(SubmitModal())
    @ui.button(label='View Leaderboard', style=discord.ButtonStyle.grey, custom_id='leaderboard_btn')
    async def lb(self, interaction, button):
        embed, _ = create_leaderboard_embed(1)
        await interaction.response.send_message(embed=embed, view=LeaderboardPagination(1), ephemeral=True)

# --- COMMANDS ---
@bot.event
async def on_ready():
    bot.add_view(PersistentView()) 
    print(f'Bot {bot.user.name} online!')

@bot.command()
async def setup_ta(ctx):
    await ctx.send(embed=discord.Embed(title="🏎️ TIME ATTACK COMPETITION", color=0x2ecc71), view=PersistentView())

# COMMAND RESET DATA (KHUSUS ADMIN)
@bot.command()
@commands.has_permissions(administrator=True)
async def reset_ta(ctx):
    """Menghapus seluruh data peserta dari database."""
    def check(m):
        return m.author == ctx.author and m.content.lower() == 'konfirmasi'
    
    await ctx.send("⚠️ **PERINGATAN!** Ini akan menghapus **SELURUH** data leaderboard. Ketik `konfirmasi` untuk melanjutkan.")
    
    try:
        await bot.wait_for('message', timeout=15.0, check=check)
        collection.delete_many({}) # Menghapus semua dokumen di database
        await ctx.send("✅ **Leaderboard telah di-reset sepenuhnya.**")
    except asyncio.TimeoutError:
        await ctx.send("❌ Reset dibatalkan (waktu habis).")

@bot.command()
@commands.has_permissions(administrator=True)
async def del_ta(ctx, *, ign_name: str):
    """Menghapus data satu peserta berdasarkan IGN."""
    result = collection.delete_one({"ign": {"$regex": f"^{ign_name}$", "$options": "i"}})
    if result.deleted_count > 0:
        await ctx.send(f"🗑️ Data **{ign_name}** dihapus.")
    else:
        await ctx.send(f"❓ IGN tidak ditemukan.")

bot.run(TOKEN)
