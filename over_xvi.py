import discord
from discord.ext import commands
from discord import ui # Tambahan untuk UI (Tombol & Modal)
from pymongo import MongoClient
import datetime

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

# --- KELAS MODAL (Jendela Input Pop-up) ---
class SubmitModal(ui.Modal, title='Submit Time Attack'):
    # Input field untuk waktu
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

        # Cek database
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

# --- KELAS TOMBOL (View) ---
class PersistentView(ui.View):
    def __init__(self):
        super().__init__(timeout=None) # Agar tombol tidak mati saat bot restart

    @ui.button(label='Submit Your Time', style=discord.ButtonStyle.green, custom_id='submit_btn')
    async def submit_button(self, interaction: discord.Interaction, button: ui.Button):
        # Tampilkan Modal saat tombol diklik
        await interaction.response.send_modal(SubmitModal())

@bot.event
async def on_ready():
    # Mendaftarkan View agar tombol tetap berfungsi setelah bot restart
    bot.add_view(PersistentView())
    print(f'Bot {bot.user.name} online dengan fitur Tombol!')

# --- PERINTAH UNTUK MEMUNCULKAN TOMBOL ---
@bot.command()
async def setup_ta(ctx):
    """Gunakan perintah ini sekali saja di channel lomba untuk memunculkan tombol"""
    embed = discord.Embed(
        title="🏎️ TIME ATTACK COMPETITION",
        description="Klik tombol di bawah untuk mendaftarkan waktu terbaik kamu!\n\n**Format:** `MM:SS.ms` (Menit:Detik.Milidetik)",
        color=0x2ecc71
    )
    await ctx.send(embed=embed, view=PersistentView())

# --- PERINTAH TAMPILKAN LEADERBOARD ---
@bot.command()
async def timeattack(ctx):
    results = list(collection.find().sort("waktu", 1).limit(10))
    if not results:
        await ctx.send("Belum ada data. Klik tombol submit!")
        return

    header = "RANK | NAME            | TIME\n"
    separator = "-----|-----------------|----------\n"
    table_content = ""
    for i, row in enumerate(results, 1):
        name = row['user_name'][:15]
        table_content += f"{i:<4} | {name:<15} | {row['waktu']}\n"

    embed = discord.Embed(title="⏱️ TIME ATTACK LEADERBOARD", color=0x00ff00)
    embed.description = f"```\n{header}{separator}{table_content}```"
    await ctx.send(embed=embed)

bot.run(TOKEN)
