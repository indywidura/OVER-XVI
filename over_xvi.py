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
    results = list(collection.find().sort("waktu", 1)) 
    total_results = len(results)
    total_pages = math.ceil(total_results / items_per_page) or 1
    
    if not results:
        return discord.Embed(title="⏱️ LEADERBOARD", description="Belum ada data peserta.", color=0xff0000), 1

    start = (page - 1) * items_per_page
    end = start + items_per_page
    current_page_data = results[start:end]

    header = "RANK | IGN             | TIME       | CLUB\n"
    separator = "-----|-----------------|------------|----------\n"
    table_content = ""
    
    for i, row in enumerate(current_page_data, start + 1):
        ign = row.get('ign', 'Unknown')[:15]
        club = row.get('club', '-')[:10]
        table_content += f"{i:<4} | {ign:<15} | {row['waktu']:<10} | {club}\n"

    embed = discord.Embed(title="⏱️ TIME ATTACK LEADERBOARD", color=0x3498db)
    embed.description = f"```\n{header}{separator}{table_content}```"
    embed.set_footer(text=f"Halaman {page} dari {total_pages} | Total: {total_results} Peserta")
    
    return embed, total_pages

# --- KELAS MODAL (Input: IGN, ID, Club, Waktu) ---
class SubmitModal(ui.Modal, title='Submit Time Attack'):
    ign_input = ui.TextInput(label='Nama In-Game (IGN)', placeholder='Contoh: RFF•SuperFae', min_length=2, max_length=30)
    id_input = ui.TextInput(label='ID In-Game', placeholder='Masukkan ID Akun Anda', min_length=5, max_length=20)
    club_input = ui.TextInput(label='Nama Club', placeholder='Contoh: APEX', min_length=2, max_length=20)
    waktu_input = ui.TextInput(label='Waktu (MM:SS.ms)', placeholder='Contoh: 01:35.34', min_length=5, max_length=12)

    async def on_submit(self, interaction: discord.Interaction):
        user = interaction.user
        now = datetime.datetime.now()
        
        # Validasi Cooldown 10 Menit
        user_data = collection.find_one({"_id": user.id})
        if user_data and "last_submit" in user_data:
            diff = now - user_data["last_submit"]
            if diff.total_seconds() < 600:
                sisa = int((600 - diff.total_seconds()) / 60)
                await interaction.response.send_message(f"⏳ **Cooldown!** Tunggu **{sisa} menit** lagi.", ephemeral=True)
                return

        await interaction.response.send_message(f"✅ Data diterima! Silakan unggah screenshot bukti di chat ini (Waktu: 60 detik).", ephemeral=True)

        def check(m):
            return m.author == user and m.channel == interaction.channel and len(m.attachments) > 0

        try:
            msg = await bot.wait_for('message', timeout=60.0, check=check)
            screenshot_url = msg.attachments[0].url
            
            # Cek apakah waktu lebih baik
            if user_data is None or self.waktu_input.value < user_data["waktu"]:
                collection.update_one(
                    {"_id": user.id},
                    {
                        "$set": {
                            "user_name": user.display_name,
                            "ign": self.ign_input.value,
                            "game_id": self.id_input.value,
                            "club": self.club_input.value,
                            "waktu": self.waktu_input.value,
                            "last_submit": now
                        }
                    },
                    upsert=True
                )
                
                # Menampilkan ID di Embed
                embed = discord.Embed(title="🌟 BUKTI REKOR BARU", color=0x2ecc71)
                embed.add_field(name="IGN", value=self.ign_input.value, inline=False)
                embed.add_field(name="ID Game", value=self.id_input.value, inline=False)
                embed.add_field(name="Club", value=self.club_input.value, inline=False)
                embed.add_field(name="Waktu", value=f"`{self.waktu_input.value}`", inline=False)
                embed.set_image(url=screenshot_url)
                await interaction.channel.send(embed=embed)
            else:
                collection.update_one({"_id": user.id}, {"$set": {"last_submit": now}})
                await interaction.followup.send(f"❌ Waktu tidak lebih baik dari rekor terbaikmu.", ephemeral=True)

        except asyncio.TimeoutError:
            await interaction.followup.send("⚠️ Waktu habis. Data gagal dicatat.", ephemeral=True)

# --- VIEW NAVIGASI ---
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

    @ui.button(label='🏠 Menu', style=discord.ButtonStyle.red)
    async def back_to_menu(self, interaction: discord.Interaction, button: ui.Button):
        embed = discord.Embed(title="🏎️ TIME ATTACK COMPETITION", color=0x2ecc71)
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
    embed.description = "Klik tombol di bawah untuk mendaftarkan waktu terbaik kamu!"
    await ctx.send(embed=embed, view=PersistentView())

@bot.command()
@commands.has_permissions(administrator=True)
async def del_ta(ctx, *, ign_name: str):
    result = collection.delete_one({"ign": {"$regex": f"^{ign_name}$", "$options": "i"}})
    if result.deleted_count > 0:
        await ctx.send(f"🗑️ Data IGN **{ign_name}** dihapus.")
    else:
        await ctx.send(f"❓ IGN **{ign_name}** tidak ditemukan.")

# BARIS PALING AKHIR
bot.run(TOKEN)
