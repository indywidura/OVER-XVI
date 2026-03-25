import discord
from discord.ext import commands
from pymongo import MongoClient
import datetime

# --- KONFIGURASI ---
TOKEN = 'MTQ4NjE1MTQ4NzUxOTQ1NzM2MA.GerHXg.UA69z1BlBK0aGtY63FEZo1dU9iSHn-TgtHl0i8'

# GANTI INI dengan Connection String MongoDB kamu!
# Jangan lupa masukkan password yang benar di dalam linknya.
MONGO_URL = "mongodb+srv://time-attack1:01010101@cluster0.smztndb.mongodb.net/?appName=Cluster0"

BOT_NAME = "OVER-XVI"

# Setting hak akses bot (Intents)
intents = discord.Intents.default()
intents.message_content = True  
intents.members = True          

bot = commands.Bot(command_prefix='!', intents=intents, help_command=None)

# --- SETUP MONGODB ---
try:
    cluster = MongoClient(MONGO_URL)
    db = cluster["over_xvi_db"]       # Nama Database
    collection = db["timeattack"]     # Nama Koleksi/Tabel
    print("✅ Berhasil terhubung ke MongoDB Atlas!")
except Exception as e:
    print(f"❌ Gagal koneksi MongoDB: {e}")

# --- DATA MANUAL (Tetap Ada) ---
leaderboard_manual = [
    {"rank": "🥇", "nama": "player 1", "waktu": "00:07.458"},
    {"rank": "🥈", "nama": "player 2", "waktu": "00:09.458"},
    {"rank": "🥉", "nama": "player 3", "waktu": "00:10.458"},
]

@bot.event
async def on_ready():
    print(f'Bot {BOT_NAME} sudah online!')

# --- PERINTAH 1: !leaderboard (Data Manual) ---
@bot.command()
async def leaderboard(ctx):
    embed = discord.Embed(title="🏆 LEADERBOARD CLASSIC", color=0x0099ff)
    desc = ""
    for entry in leaderboard_manual:
        desc += f"{entry['rank']} **{entry['nama']}** - `{entry['waktu']}`\n"
    embed.description = desc
    await ctx.send(embed=embed)

# --- PERINTAH 2: !submit (Simpan ke MongoDB) ---
@bot.command()
async def submit(ctx, waktu: str):
    """Cara pakai: !submit 00:05.123"""
    user_id = ctx.author.id
    user_name = ctx.author.display_name
    tanggal = datetime.datetime.now().strftime("%d/%m/%Y")

    # Cari apakah user sudah pernah submit
    user_data = collection.find_one({"_id": user_id})

    # Cek jika data baru ATAU waktu baru lebih cepat
    if user_data is None or waktu < user_data["waktu"]:
        collection.update_one(
            {"_id": user_id},
            {"$set": {
                "user_name": user_name,
                "waktu": waktu,
                "tanggal": tanggal
            }},
            upsert=True
        )
        await ctx.send(f"✅ **{user_name}**, rekor baru tersimpan di Cloud: `{waktu}`!")
    else:
        await ctx.send(f"❌ **{user_name}**, waktu `{waktu}` belum mengalahkan rekor terbaikmu (`{user_data['waktu']}`).")

# --- PERINTAH 3: !timeattack (Ambil dari MongoDB) ---
@bot.command()
async def timeattack(ctx):
    # Ambil 10 besar dari MongoDB, urutkan dari waktu terkecil (1 = Ascending)
    results = collection.find().sort("waktu", 1).limit(10)
    
    if collection.count_documents({}) == 0:
        await ctx.send("Belum ada data di Time Attack. Ayo ketik `!submit MM:SS.ms`!")
        return

    embed = discord.Embed(title="⏱️ TIME ATTACK (PERMANENT STORAGE)", color=0x00ff00)
    msg = ""
    for i, row in enumerate(results, 1):
        medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"#{i}"
        msg += f"{medal} **{row['user_name']}** - `{row['waktu']}` ({row['tanggal']})\n"
    
    embed.description = msg
    await ctx.send(embed=embed)

bot.run(TOKEN)
