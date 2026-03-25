import discord
from discord.ext import commands
import datetime

# --- KONFIGURASI ---
TOKEN = 'MTQ4NjE1MTQ4NzUxOTQ1NzM2MA.G78R5E.Ny8t2ec_iNPGgZVbWzr0j7HaJnycoOHGFsTtVg' # Ganti dengan Token dari Developer Portal
BOT_NAME = "OVER-XVI"

# Setting hak akses bot (Intents)
intents = discord.Intents.default()
intents.message_content = True  # Agar bot bisa membaca perintah pesan
intents.members = True          # <--- Tambahkan juga ini agar aman

bot = commands.Bot(command_prefix='!', intents=intents, help_command=None)

# --- DATA CONTOH (Bisa diubah sesuai kebutuhan) ---
leaderboard_data = [
    {"rank": "🥇", "nama": "player 1", "waktu": "00:07.458"},
    {"rank": "🥈", "nama": "player 2", "waktu": "00:09.458"},
    {"rank": "🥉", "nama": "player 3", "waktu": "00:10.458"},
    {"rank": "#4", "nama": "player 4", "waktu": "00:11.469"},
    {"rank": "#5", "nama": "player 5", "waktu": "00:19.458"},
]

@bot.event
async def on_ready():
    print(f'Bot {BOT_NAME} sudah online!')
    print('--------------------------')

@bot.command()
async def leaderboard(ctx):
    # 1. Membuat Embed (Kotak Berwarna)
    # 0x0099ff adalah kode warna biru muda seperti di gambar
    embed = discord.Embed(
        title="🏆 LEADERBOARD", 
        color=0x0099ff,
        timestamp=datetime.datetime.now()
    )

    # 2. Menyusun isi pesan berdasarkan data
    description_text = ""
    for entry in leaderboard_data:
        # Format: Emoji/Rank - Nama - Waktu (dalam box hitam)
        line = f"{entry['rank']} **{entry['nama']}** — `{entry['waktu']}`\n"
        description_text += line
    
    embed.description = description_text

    # 3. Menambahkan info Total di bagian bawah
    embed.set_footer(text=f"Total: {len(leaderboard_data)}")

    # 4. Kirim ke Discord
    await ctx.send(embed=embed)

# Menjalankan bot
bot.run(TOKEN)
