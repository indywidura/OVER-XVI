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

# --- FUNGSI PEMBUAT EMBED LEADERBOARD (PAGINATION) ---
def create_leaderboard_embed(page=1):
    items_per_page = 10
    results = list(collection.find().sort("waktu", 1))
    total_results = len(results)
    total_pages = math.ceil(total_results / items_per_page) or 1
    
    if not results:
        return discord.Embed(title="⏱️ LEADERBOARD", description="Belum ada data.", color=0xff0000), 1

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

# --- KELAS MODAL (Input Waktu + Logika Screenshot) ---
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
        tanggal = datetime.datetime.now().strftime("%d/%m/%Y")

        # 1. Beri instruksi unggah foto
        await interaction.response.send_message(
            f"✅ Data waktu `{waktu}` diterima!\n**Mohon unggah (upload) screenshot bukti Anda di sini dalam 60 detik.**", 
            ephemeral=True
        )

        # 2. Tunggu pesan dari user yang berisi gambar
        def check(m):
            return m.author == user and m.channel == interaction.channel and len(m.attachments) > 0

        try:
            msg = await bot.wait_for('message', timeout=60.0, check=check)
            screenshot_url = msg.attachments[0].url
            
            # 3. Cek database dan update jika lebih cepat
            user_data = collection.find_one({"_id": user.id})

            if user_data is None or waktu < user_data["waktu"]:
                collection.update_one(
                    {"_id": user.id},
                    {"$set": {"user_name": user.display_name, "waktu": waktu, "tanggal": tanggal}},
                    upsert=True
                )
                
                # Kirim konfirmasi publik dengan foto
                embed_konfirmasi = discord.Embed(
                    title="📸 BUKTI REKOR BARU",
                    description=f"Peserta: **{user.display_name}**\nWaktu: `{waktu}`\
