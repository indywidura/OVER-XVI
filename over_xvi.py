import discord
from discord.ext import commands
import datetime

# --- KONFIGURASI ---
TOKEN = 'MTQ4NjE1MTQ4NzUxOTQ1NzM2MA.GerHXg.UA69z1BlBK0aGtY63FEZo1dU9iSHn-TgtHl0i8' # Ganti dengan Token dari Developer Portal
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

# List kosong untuk menampung hasil Time Attack (sementara)
time_attack_results = []

@bot.command()
async def submit(ctx, waktu: str):
    """Perintah untuk member setor waktu Time Attack"""
    # Contoh: !submit 01:25
    
    # Simpan data: Nama Member, Waktu, dan Tanggal
    user_name = ctx.author.display_name
    timestamp = datetime.datetime.now().strftime("%d/%m/%Y")
    
    # Masukkan ke list
    time_attack_results.append({
        "nama": user_name,
        "waktu": waktu,
        "tanggal": timestamp
    })
    
    # Urutkan berdasarkan waktu terkecil (Opsional)
    time_attack_results.sort(key=lambda x: x['waktu'])

    await ctx.send(f"✅ **{user_name}**, waktu kamu (**{waktu}**) telah dicatat ke Leaderboard Time Attack!")

@bot.command()
async def timeattack(ctx):
    """Menampilkan papan skor Time Attack terbaru"""
    if not time_attack_results:
        await ctx.send("Belum ada data Time Attack saat ini.")
        return

    embed = discord.Embed(title="⏱️ TIME ATTACK LEADERBOARD", color=0xffd700)
    
    description = ""
    for i, data in enumerate(time_attack_results[:10], 1): # Ambil 10 besar
        description += f"**#{i}** | {data['nama']} - `{data['waktu']}` ({data['tanggal']})\n"
    
    embed.description = description
    await ctx.send(embed=embed)

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
