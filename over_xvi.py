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
    """Mengonversi MM:SS.ms ke total detik untuk sortir akurat."""
    try:
        parts = time_str.replace(':', '.').split('.')
        if len(parts) == 3: # MM:SS.ms
            return int(parts[0]) * 60 + int(parts[1]) + float(f"0.{parts[2]}")
        elif len(parts) == 2: # SS.ms
            return int(parts[0]) + float(f"0.{parts[1]}")
        return float(time_str)
    except:
        return 999999.0

def clean_text(text):
    """Mencegah karakter khusus merusak tampilan di HP."""
    if not text: return "N/A"
    return "".join(i for i in text if ord(i) < 128)

async def export_to_csv(channel_id):
    """Ekspor data khusus channel ini ke CSV."""
    results = list(collection.find({"channel_id": channel_id}).sort("waktu_raw", 1))
    if not results: return None
    output = io.StringIO()
    writer = csv.writer(output, delimiter=',', quotechar='"')
    writer.writerow(['RANK', 'NAMA PEMAIN', 'ID GAME', 'NAMA CLUB', 'REKOR WAKTU', 'WAKTU SUBMIT'])
    for i, row in enumerate(results, 1):
        submit_time = row.get('last_submit')
        fmt_date = submit_time.strftime("%d %b %Y, %H:%M") if isinstance(submit_time, datetime.datetime) else "N/A"
        writer.writerow([f"#{i}", clean_text(row.get('ign')), f"ID:{row.get('game_id', 'N/A')}", clean_text(row.get('club')), row.get('waktu', 'N/A'), fmt_date])
    output.seek(0)
    return discord.File(io.BytesIO(output.getvalue().encode('utf-8')), filename=f"REKAP_TA_{channel_id}.csv")

# --- UI COMPONENTS ---
class SubmitModal(ui.Modal, title='Submit Time Attack'):
    ign_input = ui.TextInput(label='Nama In-Game (IGN)', placeholder='Contoh: RFF•SuperFae')
    id_input = ui.TextInput(label='ID In-Game', placeholder='Masukkan ID Akun')
    club_input = ui.TextInput(label='Nama Club', placeholder='Contoh: APEX')
    waktu_input = ui.TextInput(label='Waktu (MM:SS.ms)', placeholder='Contoh: 01:35.34')

    async def on_submit(self, interaction: discord.Interaction):
        user_id = interaction.user.id
        channel_id = interaction.channel_id
        
        # Integrasi Anti-Spam dari kode asli
        user_data = collection.find_one({"_id": f"{user_id}_{channel_id}"})
        if user_data and "last_submit" in user_data:
            diff = datetime.datetime.now() - user_data["last_submit"]
            if diff.total_seconds() < 600: # 10 Menit Cooldown
                return await interaction.response.send_message(f"⏳ **Anti-Spam!** Tunggu {int((600-diff.total_seconds())/60)} menit lagi.", ephemeral=True)

        await interaction.response.send_message(f"✅ Data terdaftar! Kirim screenshot rekor Anda sekarang.", ephemeral=True)
        
        def check(m): return m.author.id == user_id and m.channel.id == channel_id and m.attachments
        
        try:
            msg = await bot.wait_for('message', timeout=60.0, check=check)
            img_bytes = await msg.attachments[0].read()
            
            time_val = time_to_seconds(self.waktu_input.value)
            unique_id = f"{user_id}_{channel_id}"
            
            collection.update_one(
                {"_id": unique_id}, 
                {"$set": {
                    "user_id": user_id, "channel_id": channel_id,
                    "ign": self.ign_input.value, "game_id": self.id_input.value, 
                    "club": self.club_input.value, "waktu": self.waktu_input.value, 
                    "waktu_raw": time_val, "last_submit": datetime.datetime.now()
                }}, upsert=True
            )

            try: await msg.delete() 
            except: pass

            # Embed Lengkap sesuai Screenshot
            embed = discord.Embed(title="🌟 REKOR BARU TERCATAT", color=0x2ecc71)
            embed.add_field(name="👤 Peserta", value=f"**{self.ign_input.value}**", inline=False)
            embed.add_field(name="🛡️ Club", value=f"{self.club_input.value}", inline=False)
            embed.add_field(name="🆔 ID Game", value=f"{self.id_input.value}", inline=False)
            embed.add_field(name="⏱️ Waktu", value=f"`{self.waktu_input.value}`", inline=False)
            embed.set_footer(text=f"Submitter: {interaction.user.display_name}")
            
            file = discord.File(io.BytesIO(img_bytes), filename="rekor.png")
            embed.set_image(url="attachment://rekor.png")
            await interaction.channel.send(file=file, embed=embed)
            
        except asyncio.TimeoutError:
            await interaction.followup.send("⚠️ Waktu habis! Silakan ulangi submit.", ephemeral=True)

class LeaderboardPagination(ui.View):
    def __init__(self, channel_id, page=1):
        super().__init__(timeout=60)
        self.channel_id = channel_id
        self.page = page

    @ui.button(label='⬅️ Prev', style=discord.ButtonStyle.blurple)
    async def prev(self, interaction, button):
        if self.page > 1:
            self.page -= 1
            await self.update_view(interaction)
        else: await interaction.response.defer()

    @ui.button(label='Next ➡️', style=discord.ButtonStyle.blurple)
    async def next(self, interaction, button):
        _, total_pages = create_leaderboard_embed(self.channel_id, self.page)
        if self.page < total_pages:
            self.page += 1
            await self.update_view(interaction)
        else: await interaction.response.defer()

    @ui.button(label='📊 Export CSV', style=discord.ButtonStyle.green)
    async def export(self, interaction, button):
        if not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message("❌ Hanya Admin!", ephemeral=True)
        file = await export_to_csv(self.channel_id)
        if file: await interaction.response.send_message("📂 File Rekap Channel Ini:", file=file, ephemeral=True)
        else: await interaction.response.send_message("⚠️ Data Kosong.", ephemeral=True)

    @ui.button(label='🏠 Menu', style=discord.ButtonStyle.red)
    async def back_to_menu(self, interaction, button):
        embed = discord.Embed(title="🏎️ TIME ATTACK COMPETITION", description="Gunakan tombol di bawah untuk berpartisipasi.", color=0x2ecc71)
        await interaction.response.edit_message(embed=embed, view=PersistentView())

    async def update_view(self, interaction):
        embed, _ = create_leaderboard_embed(self.channel_id, self.page)
        await interaction.response.edit_message(embed=embed, view=self)

def create_leaderboard_embed(channel_id, page=1):
    items_per_page = 10
    results = list(collection.find({"channel_id": channel_id}).sort("waktu_raw", 1)) 
    total_pages = math.ceil(len(results) / items_per_page) or 1
    if not results: return discord.Embed(title="⏱️ LEADERBOARD", description="Belum ada data di channel ini.", color=0xff0000), 1
    
    start = (page - 1) * items_per_page
    current_data = results[start:start+items_per_page]
    table = "RK | IGN             | TIME\n---|-----------------|----------\n"
    for i, row in enumerate(current_data, start + 1):
        ign = clean_text(row.get('ign'))[:15]
        table += f"{i:<2} | {ign:<15} | {row.get('waktu')}\n"
        
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
        embed, _ = create_leaderboard_embed(interaction.channel_id, 1)
        await interaction.response.send_message(embed=embed, view=LeaderboardPagination(interaction.channel_id, 1), ephemeral=True)

# --- BOT COMMANDS ---
@bot.event
async def on_ready():
    bot.add_view(PersistentView()) 
    print(f'Bot {bot.user.name} online!')

@bot.command()
async def setup_ta(ctx):
    """Menampilkan menu utama kompetisi."""
    embed = discord.Embed(title="🏎️ TIME ATTACK COMPETITION", description="Klik tombol di bawah untuk mendaftar.", color=0x2ecc71)
    await ctx.send(embed=embed, view=PersistentView())

@bot.command()
@commands.has_permissions(administrator=True)
async def reset_ta(ctx):
    """MENGHAPUS SEMUA DATA GLOBAL."""
    def check(m): return m.author == ctx.author and m.content.lower() == 'konfirmasi'
    await ctx.send("⚠️ **GLOBAL RESET!** Ketik `konfirmasi` untuk menghapus SEMUA data di seluruh server.")
    try:
        await bot.wait_for('message', timeout=15.0, check=check)
        collection.delete_many({}) 
        await ctx.send("✅ Seluruh database telah dibersihkan.")
    except asyncio.TimeoutError: await ctx.send("❌ Reset dibatalkan.")

@bot.command()
@commands.has_permissions(administrator=True)
async def reset_channel(ctx):
    """MENGHAPUS DATA KHUSUS CHANNEL INI."""
    collection.delete_many({"channel_id": ctx.channel.id})
    await ctx.send(f"✅ Data channel **{ctx.channel.name}** telah dihapus.")

@bot.command()
@commands.has_permissions(administrator=True)
async def del_ta(ctx, *, ign_name: str):
    """Menghapus satu peserta berdasarkan IGN di channel ini."""
    result = collection.delete_one({"channel_id": ctx.channel.id, "ign": {"$regex": f"^{ign_name}$", "$options": "i"}})
    if result.deleted_count > 0: await ctx.send(f"🗑️ Data **{ign_name}** di channel ini dihapus.")
    else: await ctx.send("❓ IGN tidak ditemukan di channel ini.")

bot.run(TOKEN)
