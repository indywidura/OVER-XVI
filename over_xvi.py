import discord
from discord.ext import commands
import sqlite3
import datetime

# --- KONFIGURASI ---
TOKEN = 'MTQ4NjE1MTQ4NzUxOTQ1NzM2MA.GerHXg.UA69z1BlBK0aGtY63FEZo1dU9iSHn-TgtHl0i8' 
BOT_NAME = "OVER-XVI"

# Setting hak akses bot (Intents)
intents = discord.Intents.default()
intents.message_content = True  
intents.members = True          

bot = commands.Bot(command_prefix='!', intents=intents, help_command=None)

# --- DATABASE SETUP (SQLite) ---
def init_db():
    conn = sqlite3.connect('timeattack.db')
    cursor = conn.cursor()
    # Tabel untuk menyimpan skor player
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS timeattack (
            user_id INTEGER PRIMARY KEY,
            user_name TEXT,
            waktu TEXT,
            tanggal TEXT
        )
    ''')
    conn.commit()
    conn.close()

init_db()

# --- DATA STATIS (Leaderboard Manual) ---
leaderboard_manual = [
    {"rank": "🥇", "nama": "player 1", "waktu": "00:07.458"},
    {"rank": "🥈", "nama": "player 2", "waktu": "00:09.458"},
    {"rank": "🥉", "nama": "player 3", "waktu": "00:10.458"},
    {"rank": "#4", "nama": "player 4", "waktu": "00:11.469"},
    {"rank": "#5", "nama": "player 5", "waktu": "00:19.458"},
]

@bot.event
async def on_ready():
    print(f'Bot {BOT_NAME} sudah online dan Database aktif!')

# --- PERINTAH 1: LEADERBOARD MANUAL ---
@bot.command()
async def leaderboard(ctx):
    embed = discord.Embed(
        title="🏆 LEADERBOARD CLASSIC", 
        color=0x0099ff,
        timestamp=datetime.datetime.now()
    )
    description_text = ""
    for entry in leaderboard_manual:
        description_text += f"{entry['rank']} **{entry['nama']}** - `{entry['waktu']}`\n"
    
    embed.description = description_text
    await ctx.send(embed=embed)

# --- PERINTAH 2: SUBMIT WAKTU (OTOMATIS) ---
@bot.command()
async def submit(ctx, waktu: str):
    """Cara pakai: !submit 00:05.123"""
    user_id = ctx.author.id
    user_name = ctx
