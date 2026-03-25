import discord
from discord.ext import commands
from discord import ui
from pymongo import MongoClient
import datetime
import math

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

# --- FUNGSI PEMBUAT EMBED LEADERBOARD (PAGINATION) ---
def create_leaderboard_embed(page=1):
    items_per_page = 10
    results = list(collection.find().sort("waktu", 1))
    total_results = len(results)
    total_pages = math.ceil(total_results / items_per_page) or 1
    
    if not results:
        return discord.Embed(title="⏱️ LEADERBOARD", description="Belum ada data.", color=0xff0000), 1

    # Mengambil potongan data untuk halaman tertentu
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

# --- VIEW KHUSUS UNTUK NAVIGASI HALAMAN ---
class LeaderboardPagination(ui.View):
    def __init__(self, current_page=1):
        super().__init__(timeout=60) # Tombol navigasi mati setelah 60 detik tidak aktif
        self.current_page = current_page

    @ui.button(label='⬅️ Prev', style=discord.ButtonStyle.blurple)
    async def prev_button(self, interaction: discord.Interaction, button: ui.Button):
        if self.current_page > 1:
            self.current_page -= 1
            embed, _ = create_leaderboard_embed(self.current_page)
            await interaction.response.edit_message(embed=embed, view=self)
        else:
            await interaction.response.send_message("Ini sudah halaman pertama!", ephemeral=True)

    @ui.button(label='Next ➡️', style=discord.ButtonStyle.blurple)
    async def next_button(self, interaction: discord.Interaction, button: ui.Button):
        embed, total_pages = create_leaderboard_embed(self.current_page + 1)
        if self.current_page < total_pages:
            self.current_page += 1
            await interaction.response.edit_message(embed=embed, view=self)
        else:
            await interaction.response.send_message("Ini sudah halaman terakhir!", ephemeral=True)

# --- MODAL SUBMIT ---
class SubmitModal(ui.Modal, title='Submit Time Attack'):
    waktu_input = ui.TextInput(label='Waktu (MM:SS.ms)', placeholder='00:05.123', min_length=5, max_length=12)

    async def on_submit(self, interaction: discord.Interaction):
        user_id, user_name, waktu = interaction.user.id, interaction.user.display_name, self.waktu_input.value
        tanggal = datetime.datetime.now().strftime("%d/%m/%Y")
        
        user_data = collection.find_one({"_id": user_id})
        if user_data is None or waktu < user_data["waktu"]:
            collection.update_one({"_id": user_id}, {"$set": {"user_name": user_name, "waktu": waktu, "tanggal": tanggal}}, upsert=True)
            await interaction.response.send_message(f"✅ Rekor dicatat: `{waktu}`!", ephemeral=True)
        else:
            await interaction.response.send_message(f"❌ Waktumu `{waktu}` lebih lambat dari rekor terbaikmu.", ephemeral=True)

# --- VIEW UTAMA (DI CHANNEL) ---
class PersistentView(ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @ui.button(label='Submit Your Time', style=discord.ButtonStyle.green, custom_id='submit_btn')
    async def submit_button(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_modal(SubmitModal())

    @ui.button(label='View Leaderboard', style=discord.ButtonStyle.grey, custom_id='leaderboard_btn')
    async def leaderboard_button(self, interaction: discord.Interaction, button: ui.Button):
        embed, total_pages = create_leaderboard_embed(page=1)
        # Menampilkan leaderboard dengan tombol navigasi (hanya bisa dilihat pengklik)
        await interaction.response.send_message(embed=embed, view=LeaderboardPagination(1), ephemeral=True)

@bot.event
async def on_ready():
    bot.add_view(PersistentView())
    print(f'Bot {bot.user.name} Siap!')

@bot.command()
async def setup_ta(ctx):
    embed = discord.Embed(title="🏎️ TIME ATTACK COMPETITION", description="Klik tombol di bawah untuk berpartisipasi!", color=0x2ecc71)
    await ctx.send(embed=embed, view=PersistentView())

bot.run(TOKEN)
# --- PERINTAH SETUP ---
@bot.command()
async def setup_ta(ctx):
    embed = discord.Embed(
        title="🏎️ TIME ATTACK COMPETITION",
        description="Gunakan tombol di bawah untuk interaksi:\n\n"
                    "🟢 **Submit Your Time**: Kirim rekor waktu terbaru.\n"
                    "⚪ **View Leaderboard**: Lihat 10 besar klasemen saat ini.",
        color=0x2ecc71
    )
    await ctx.send(embed=embed, view=PersistentView())

# --- PERINTAH TAMPILKAN LEADERBOARD (Tetap ada sebagai cadangan) ---
@bot.command()
async def timeattack(ctx):
    embed = get_leaderboard_embed()
    await ctx.send(embed=embed)

bot.run(TOKEN)
