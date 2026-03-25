import discord
from discord.ext import commands
from discord import ui
from pymongo import MongoClient
import datetime
import math
import io
import csv
import asyncio

# --- KONFIGURASI (Sangat disarankan pindahkan ke .env) ---
TOKEN = 'MTQ4NjE1MTQ4NzUxOTQ1NzM2MA.GerHXg.UA69z1BlBK0aGtY63FEZo1dU9iSHn-TgtHl0i8'
MONGO_URL = "mongodb+srv://time-attack1:01010101@cluster0.smztndb.mongodb.net/?appName=Cluster0"

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix='!', intents=intents, help_command=None)

cluster = MongoClient(MONGO_URL)
db = cluster["over_xvi_db"]
collection = db["timeattack"]

# --- HELPER: KONVERSI WAKTU KE DETIK (Untuk Sortir Akurat) ---
def time_to_seconds(time_str):
    try:
        # Menangani format MM:SS.ms atau SS.ms
        parts = time_str.replace(':', '.').split('.')
        if len(parts) == 3: # MM:SS.ms
            return int(parts[0]) * 60 + int(parts[1]) + float(f"0.{parts[2]}")
        elif len(parts) == 2: # SS.ms
            return int(parts[0]) + float(f"0.{parts[1]}")
        return float(time_str)
    except:
        return 999999.0

def clean_text(text):
    if not text: return "N/A"
    return "".join(i for i in text if ord(i) < 128)

async def export_to_csv():
    results = list(collection.find().sort("waktu_raw", 1))
    if not results: return None
    output = io.StringIO()
    writer = csv.writer(output, delimiter=',', quotechar='"')
    writer.writerow(['RANK', 'NAMA PEMAIN', 'ID GAME', 'NAMA CLUB', 'REKOR WAKTU', 'WAKTU SUBMIT'])
    for i, row in enumerate(results, 1):
        submit_time = row.get('last_submit')
        fmt_date = submit_time.strftime("%d %b %Y, %H:%M") if isinstance(submit_time, datetime.datetime) else "N/A"
        writer.writerow([f"#{i}", clean_text(row.get('ign')), f"ID:{row.get('game_id', 'N/A')}", clean_text(row.get('club')), row.get('waktu', 'N/A'), fmt_date])
    output.seek(0)
    return discord.File(io.BytesIO(output.getvalue().encode('utf-8')), filename=f"REKAP_TA_{datetime.date.today()}.csv")

# --- MODAL SUBMIT ---
class SubmitModal(ui.Modal, title='Submit Time Attack'):
    ign_input = ui.TextInput(label='Nama In-Game (IGN)', placeholder='Contoh: RFF•SuperFae')
    id_input = ui.TextInput(label='ID In-Game', placeholder='Masukkan ID Akun')
    club_input = ui.TextInput(label='Nama Club', placeholder='Contoh: APEX')
    waktu_input = ui.TextInput(label='Waktu (MM:SS.ms)', placeholder='Contoh: 01:35.34')

    async def on_submit(self, interaction: discord.Interaction):
        user_id = interaction.user.id
        # Konversi waktu ke angka untuk sortir
        time_val = time_to_seconds(self.waktu_input.value)
        
        await interaction.response.send_message(f"✅ Data diterima! **Kirim screenshot** rekor Anda sekarang ke channel ini.", ephemeral=True)
        
        def check(m): return m.author.id == user_id and m.channel == interaction.channel and m.attachments
        
        try:
            msg = await bot.wait_for('message', timeout=60.0, check=check)
            img_bytes = await msg.attachments[0].read()
            
            # Simpan ke DB dengan field 'waktu_raw' untuk sortir
            collection.update_one(
                {"_id": user_id}, 
                {"$set": {
                    "ign": self.ign_input.value, 
                    "game_id": self.id_input.value, 
                    "club": self.club_input.value, 
                    "waktu": self.waktu_input.value, 
                    "waktu_raw": time_val,
                    "last_submit": datetime.datetime.now()
                }}, upsert=True
            )

            try: await msg.delete()
            except: pass

            # PERBAIKAN: Embed menampilkan semua field sesuai screenshot
            embed = discord.Embed(title="🌟 REKOR BARU TERCATAT", color=0x2ecc71)
            embed.add_field(name="👤 Peserta", value=f"**{self.ign_input.value}**", inline=False)
            embed.add_field(name="🛡️ Club", value=f"{self.club_input.value}", inline=False)
            embed.add_field(name="🆔 ID Game", value=f"{self.id_input.value}", inline=False)
            embed.add_field(name="⏱️ Waktu", value=f"`{self.waktu_input.value}`", inline=False)
            embed.set_footer(text=f"Submitter: {interaction.user.display_name}")
            
            file = discord.File(io.BytesIO(img_bytes), filename="rekor.png")
            embed.set_image(url="attachment://rekor.png")
            await interaction.channel.send(file=file, embed=embed)
            
        except asyncio.TimeoutError:
            await interaction.followup.send("⚠️ Waktu habis! Silakan ulangi submit.", ephemeral=True)
        except Exception as e:
            print(f"Error: {e}")
            await interaction.followup.send("⚠️ Terjadi kesalahan teknis.", ephemeral=True)

# --- VIEW LEADERBOARD (DENGAN TOMBOL NAVIGASI, EXPORT, DAN MENU) ---
class LeaderboardPagination(ui.View):
    def __init__(self, page=1):
        super().__init__(timeout=60)
        self.page = page

    @ui.button(label='⬅️ Prev', style=discord.ButtonStyle.blurple)
    async def prev(self, interaction, button):
        if self.page > 1:
            self.page -= 1
            await self.update_view(interaction)
        else:
            await interaction.response.defer()

    @ui.button(label='Next ➡️', style=discord.ButtonStyle.blurple)
    async def next(self, interaction, button):
        _, total_pages = create_leaderboard_embed(self.page)
        if self.page < total_pages:
            self.page += 1
            await self.update_view(interaction)
        else:
            await interaction.response.defer()

    @ui.button(label='📊 Export CSV (Admin)', style=discord.ButtonStyle.green)
    async def export(self, interaction, button):
        # Mengecek izin administrator
        if not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message("❌ Hanya Admin yang bisa mengunduh spreadsheet!", ephemeral=True)
        
        file = await export_to_csv()
        if file:
            await interaction.response.send_message("📂 File rekap leaderboard berhasil dibuat:", file=file, ephemeral=True)
        else:
            await interaction.response.send_message("⚠️ Data masih kosong.", ephemeral=True)

    @ui.button(label='🏠 Menu', style=discord.ButtonStyle.red)
    async def back_to_menu(self, interaction, button):
        # Mengembalikan tampilan ke menu utama PersistentView
        embed = discord.Embed(title="🏎️ TIME ATTACK COMPETITION", description="Klik tombol di bawah untuk mendaftarkan rekor atau melihat peringkat.", color=0x2ecc71)
        await interaction.response.edit_message(embed=embed, view=PersistentView())

    async def update_view(self, interaction):
        embed, _ = create_leaderboard_embed(self.page)
        await interaction.response.edit_message(embed=embed, view=self)

def create_leaderboard_embed(page=1):
    items_per_page = 10
    # Sortir berdasarkan 'waktu_raw' (angka), bukan teks
    results = list(collection.find().sort("waktu_raw", 1)) 
    total_pages = math.ceil(len(results) / items_per_page) or 1
    if not results: return discord.Embed(title="⏱️ LEADERBOARD", description="Belum ada data.", color=0xff0000), 1
    
    start = (page - 1) * items_per_page
    current_data = results[start:start+items_per_page]
    
    table = "RK | IGN             | TIME\n---|-----------------|----------\n"
    for i, row in enumerate(current_data, start + 1):
        ign = clean_text(row.get('ign'))[:15]
        table += f"{i:<2} | {ign:<15} | {row.get('waktu')}\n"
        
    embed = discord.Embed(title="⏱️ TIME ATTACK LEADERBOARD", description=f"```\n{table}```", color=0x3498db)
    embed.set_footer(text=f"Halaman {page}/{total_pages}")
    return embed, total_pages

class PersistentView(ui.View):
    def __init__(self):
        super().__init__(timeout=None) 

    @ui.button(label='Submit Your Time', style=discord.ButtonStyle.green, custom_id='submit_btn')
    async def sub(self, interaction, button):
        await interaction.response.send_modal(SubmitModal())

    @ui.button(label='View Leaderboard', style=discord.ButtonStyle.grey, custom_id='leaderboard_btn')
    async def lb(self, interaction, button):
        embed, _ = create_leaderboard_embed(1)
        # Pastikan menggunakan LeaderboardPagination agar tombol navigasi dan menu muncul
        await interaction.response.send_message(embed=embed, view=LeaderboardPagination(1), ephemeral=True)

@bot.event
async def on_ready():
    bot.add_view(PersistentView()) 
    print(f'Bot {bot.user.name} online!')

@bot.command()
async def setup_ta(ctx):
    embed = discord.Embed(title="🏎️ TIME ATTACK COMPETITION", description="Klik tombol di bawah untuk mendaftarkan rekor atau melihat peringkat.", color=0x2ecc71)
    await ctx.send(embed=embed, view=PersistentView())

# (Command reset_ta dan del_ta tetap sama seperti sebelumnya...)
bot.run(TOKEN)
