import discord
from discord.ext import commands
from discord import ui 
from pymongo import MongoClient
import datetime

# --- KONFIGURASI ---
# Catatan: Selalu jaga kerahasiaan TOKEN Anda!
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

# --- FUNGSI HELPER UNTUK LEADERBOARD ---
def get_leaderboard_embed():
    """Fungsi mandiri untuk mengambil data dan membuat embed leaderboard"""
    results = list(collection.find().sort("waktu", 1).limit(10))
    if not results:
        return discord.Embed(title="⏱️ TIME ATTACK LEADERBOARD", description="Belum ada data. Klik tombol submit!", color=0xff0000)

    header = "RANK | NAME            | TIME\n"
    separator = "-----|-----------------|----------\n"
    table_content = ""
    for i, row in enumerate(results, 1):
        name = row['user_name'][:15]
        table_content += f"{i:<4} | {name:<15} | {row['waktu']}\n"

    embed = discord.Embed(title="⏱️ TIME ATTACK LEADERBOARD", color=0x00ff00)
    embed.description = f"```\n{header}{separator}{table_content}```"
    return embed

# --- KELAS MODAL ---
class SubmitModal(ui.Modal, title='Submit Time Attack'):
    waktu_input = ui.TextInput(
        label='Masukkan Waktu (Contoh: 00:05.123)',
        placeholder='MM:SS.ms',
        min_length=5,
        max_length=12,
        required=True
    )

    async def on_submit(self, interaction: discord.Interaction):
        user_id = interaction.user.id
        user_name = interaction.user.display_name
        waktu = self.waktu_input.value
        tanggal = datetime.datetime.now().strftime("%d/%m/%Y")

        user_data = collection.find_one({"_id": user_id})

        if user_data is None or waktu < user_data["waktu"]:
            collection.update_one(
                {"_id": user_id},
                {"$set": {"user_name": user_name, "waktu": waktu, "tanggal": tanggal}},
                upsert=True
            )
            await interaction.response.send_message(f"✅ **{user_name}**, rekor baru dicatat: `{waktu}`!", ephemeral=True)
        else:
            await interaction.response.send_message(f"❌ Waktu `{waktu}` lebih lambat dari rekor terbaikmu (`{user_data['waktu']}`).", ephemeral=True)

# --- KELAS TOMBOL (View yang Diperbarui) ---
class PersistentView(ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @ui.button(label='Submit Your Time', style=discord.ButtonStyle.green, custom_id='submit_btn')
    async def submit_button(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_modal(SubmitModal())

    @ui.button(label='View Leaderboard', style=discord.ButtonStyle.grey, custom_id='leaderboard_btn')
    async def leaderboard_button(self, interaction: discord.Interaction, button: ui.Button):
        # Mengambil embed leaderboard menggunakan fungsi helper
        embed = get_leaderboard_embed()
        # Mengirim sebagai pesan ephemeral (hanya dilihat oleh pengklik) agar tidak menumpuk di channel
        await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.event
async def on_ready():
    bot.add_view(PersistentView())
    print(f'Bot {bot.user.name} online dengan fitur Tombol!')

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
