import discord
from discord.ext import commands
from discord import ui
from pymongo import MongoClient
import datetime
import math
import asyncio

# --- KONFIGURASI ---
TOKEN = 'MTQ4NjE1MTQ4NzUxOTQ1NzM2MA.GerHXg.UA69z1BlBK0aGtY63FEZo1dU9iSHn-TgtHl0i8'
MONGO_URL = "mongodb+srv://time-attack1:01010101@cluster0.smztndb.mongodb.net/?appName=Cluster0"

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix='!', intents=intents, help_command=None)

# --- SETUP MONGODB ---
cluster = MongoClient(MONGO_URL)
db = cluster["over_xvi_db"]
collection = db["timeattack"]

# --- FUNGSI PEMBUAT EMBED LEADERBOARD ---
def create_leaderboard_embed(page=1):
    items_per_page = 10
    # Menampilkan keseluruhan leaderboard (semua data)
    results = list(collection.find().sort("waktu", 1)) 
    total_results = len(results)
    total_pages = math.ceil(total_results / items_per_page) or 1
    
    if not results:
        return discord.Embed(title="⏱️ LEADERBOARD", description="Belum ada data.", color=0xff0000), 1

    # Logika Pagination
    start = (page - 1) * items_per_page
    end = start + items_per_page
    current_page_data = results[start:end]

    header = "RANK | NAME            | TIME\n"
    separator = "-----|-----------------|----------\n"
    table_content = ""
    
    for i, row in enumerate(current_page_data, start + 1):
        name = row['user_name'][:15]
        table_content += f"{i:<4} | {name:<15} | {row['waktu']}\n"

    embed = discord.Embed(title="⏱️ TIME ATTACK LEADERBOARD", color=0x3498db)
    embed.description = f"```\n{header}{separator}{table_content}```"
    embed.set_footer(text=f"Halaman {page} dari {total_pages} | Total: {total_results} Peserta")
    
    return embed, total_pages

# --- KELAS MODAL (Input Waktu + Screenshot) ---
class SubmitModal(ui.Modal, title='Submit Time Attack'):
    waktu_input = ui.TextInput(
        label='Masukkan Waktu (Contoh: 00:05.123)',
        placeholder='MM:SS.ms',
        min_length=5,
        max_length=12,
        required=True
    )

    async def on_submit(self, interaction: discord.Interaction):
        user = interaction.user
        waktu = self.waktu_input.value
        now = datetime.datetime.now()

        # Fitur Jeda (Cooldown 10 Menit) per Player
        user_data = collection.find_one({"_id": user.id})
        if user_data and "last_submit" in user_data:
            last_submit = user_data["last_submit"]
            diff = now - last_submit
            if diff.total_seconds() < 600:
                sisa_menit = int((600 - diff.total_seconds()) / 60)
                await interaction.response.send_message(f"⏳ **Anti-Spam!** Tunggu **{sisa_menit} menit** lagi sebelum menginput data baru.", ephemeral=True)
                return

        await interaction.response.send_message(f"✅ Waktu `{waktu}` diterima! Silakan unggah screenshot bukti di chat ini (60 detik).", ephemeral=True)

        # Menunggu screenshot bukti (hanya di chat, tidak masuk database)
        def check(m):
            return m.author == user and m.channel == interaction.channel and len(m.attachments) > 0

        try:
            msg = await bot.wait_for('message', timeout=60.0, check=check)
            screenshot_url = msg.attachments[0].url
            
            if user_data is None or waktu < user_data["waktu"]:
                collection.update_one(
                    {"_id": user.id},
                    {"$set": {"user_name": user.display_name, "waktu": waktu, "last_submit": now}},
                    upsert=True
                )
                
                embed_bukti = discord.Embed(title="📸 BUKTI REKOR BARU", color=0x2ecc71)
                embed_bukti.add_field(name="Peserta", value=user.display_name)
                embed_bukti.add_field(name="Waktu", value=f"`{waktu}`")
                embed_bukti.set_image(url=screenshot_url)
                await interaction.channel.send(embed=embed_bukti)
            else:
                # Update timestamp terakhir meskipun rekor tidak pecah untuk mencegah spam
                collection.update_one({"_id": user.id}, {"$set": {"last_submit": now}})
                await interaction.followup.send(f"❌ Waktu `{waktu}` tidak lebih baik dari rekor terbaikmu.", ephemeral=True)

        except asyncio.TimeoutError:
            await interaction.followup.send("⚠️ Waktu habis. Bukti screenshot tidak diunggah, data gagal dicatat.", ephemeral=True)

# --- VIEW NAVIGASI & MENU ---
class LeaderboardPagination(ui.View):
    def __init__(self, current_page=1):
        super().__init__(timeout=60)
        self.current_page = current_page

    @ui.button(label='⬅️ Prev', style=discord.ButtonStyle.blurple)
    async def prev_button(self, interaction: discord.Interaction, button: ui.Button):
        if self.current_page > 1:
            self.current_page -= 1
            embed, _ = create_leaderboard_embed(self.current_page)
            await interaction.response.edit_message(embed=embed, view=self)

    @ui.button(label='Next ➡️', style=discord.ButtonStyle.blurple)
    async def next_button(self, interaction: discord.Interaction, button: ui.Button):
        embed, total_pages = create_leaderboard_embed(self.current_page + 1)
        if self.current_page < total_pages:
            self.current_page += 1
            await interaction.response.edit_message(embed=embed, view=self)

    @ui.button(label='🏠 Kembali ke Menu', style=discord.ButtonStyle.red)
    async def back_to_menu(self, interaction: discord.Interaction, button: ui.Button):
        """Tombol kembali ke menu awal"""
        embed = discord.Embed(title="🏎️ TIME ATTACK COMPETITION", description="Silakan pilih menu di bawah:", color=0x2ecc71)
        await interaction.response.edit_message(embed=embed, view=PersistentView())

class PersistentView(ui.View):
    def __init__(self):
        super().__init__(timeout=None) 

    @ui.button(label='Submit Your Time', style=discord.ButtonStyle.green, custom_id='submit_btn')
    async def submit_button(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_modal(SubmitModal())

    @ui.button(label='View Leaderboard', style=discord.ButtonStyle.grey, custom_id='leaderboard_btn')
    async def leaderboard_button(self, interaction: discord.Interaction, button: ui.Button):
        embed, _ = create_leaderboard_embed(page=1)
        await interaction.response.send_message(embed=embed, view=LeaderboardPagination(1), ephemeral=True)

@bot.event
async def on_ready():
    bot.add_view(PersistentView()) 
    print(f'Bot {bot.user.name} online!')

@bot.command()
async def setup_ta(ctx):
    embed = discord.Embed(title="🏎️ TIME ATTACK COMPETITION", color=0x2ecc71)
    await ctx.send(embed=embed, view=PersistentView())

@bot.command()
@commands.has_permissions(administrator=True)
async def del_ta(ctx, *, name: str):
    """Fitur hapus data peserta untuk Admin"""
    result = collection.delete_one({"user_name": {"$regex": f"^{name}$", "$options": "i"}})
    if result.deleted_count > 0:
        await ctx.send(f"🗑️ Data **{name}** telah dihapus dari database.")
    else:
        await ctx.send(f"❓ Nama **{name}** tidak ditemukan.")

# BARIS PALING AKHIR: Pastikan tidak ada karakter apapun setelah ini
bot.run(TOKEN)
