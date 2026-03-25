import discord
from discord.ext import commands
from discord import ui
from pymongo import MongoClient
import datetime
import math
import io

# --- KONFIGURASI ---
TOKEN = 'MTQ4NjE1MTQ4NzUxOTQ1NzM2MA.GerHXg.UA69z1BlBK0aGtY63FEZo1dU9iSHn-TgtHl0i8'
MONGO_URL = "mongodb+srv://time-attack1:01010101@cluster0.smztndb.mongodb.net/?appName=Cluster0"

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix='!', intents=intents, help_command=None)

cluster = MongoClient(MONGO_URL)
db = cluster["over_xvi_db"]
collection = db["timeattack"]

# --- LEADERBOARD ---
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

    header = "RK | IGN             | ID GAME    | TIME\n"
    sep    = "---|-----------------|------------|----------\n"
    table_content = ""
    
    for i, row in enumerate(current_page_data, start + 1):
        ign = row.get('ign', 'Unknown')[:15]
        g_id = str(row.get('game_id', '-'))[:10]
        waktu = row.get('waktu', '--:--.--')
        table_content += f"{i:<2} | {ign:<15} | {g_id:<10} | {waktu}\n"

    embed = discord.Embed(title="⏱️ TIME ATTACK LEADERBOARD", color=0x3498db)
    embed.description = f"```\n{header}{sep}{table_content}```"
    embed.set_footer(text=f"Halaman {page}/{total_pages}")
    return embed, total_pages

# --- MODAL ---
class SubmitModal(ui.Modal, title='Submit Time Attack'):
    ign_input = ui.TextInput(label='Nama In-Game (IGN)', placeholder='Contoh: RFF•SuperFae', min_length=2, max_length=30)
    id_input = ui.TextInput(label='ID In-Game', placeholder='Masukkan ID Akun Anda')
    club_input = ui.TextInput(label='Nama Club', placeholder='Contoh: APEX')
    waktu_input = ui.TextInput(label='Waktu (MM:SS.ms)', placeholder='Contoh: 01:35.34')

    async def on_submit(self, interaction: discord.Interaction):
        user = interaction.user
        
        # Ephemeral: Hanya pengirim yang melihat instruksi ini
        await interaction.response.send_message(
            f"✅ **Data Terdaftar!** Kirim screenshot rekor Anda sekarang di channel ini.\n"
            f"*Gambar Anda akan diproses dan pesan aslinya akan dihapus.*", 
            ephemeral=True
        )

        def check(m):
            return m.author == user and m.channel == interaction.channel and len(m.attachments) > 0

        try:
            msg = await bot.wait_for('message', timeout=60.0, check=check)
            attachment = msg.attachments[0]
            
            # SOLUSI UTAMA: Mengunduh gambar ke memory agar tidak hilang saat pesan dihapus
            image_bytes = await attachment.read()
            file_name = attachment.filename
            
            # Simpan data
            collection.update_one(
                {"_id": user.id},
                {
                    "$set": {
                        "ign": self.ign_input.value,
                        "game_id": self.id_input.value,
                        "club": self.club_input.value,
                        "waktu": self.waktu_input.value,
                        "last_submit": datetime.datetime.now()
                    }
                },
                upsert=True
            )

            # Hapus pesan asli user segera
            try:
                await msg.delete()
            except:
                pass

            # Kirim Embed publik dengan Re-Upload File
            embed = discord.Embed(title="🌟 REKOR BARU TERCATAT", color=0x2ecc71)
            embed.add_field(name="👤 Peserta", value=f"**{self.ign_input.value}**", inline=True)
            embed.add_field(name="🛡️ Club", value=self.club_input.value, inline=True)
            embed.add_field(name="🆔 ID Game", value=self.id_input.value, inline=False)
            embed.add_field(name="⏱️ Waktu", value=f"`{self.waktu_input.value}`", inline=False)
            
            # Mengirimkan kembali file gambar secara resmi dari bot
            file = discord.File(io.BytesIO(image_bytes), filename=file_name)
            embed.set_image(url=f"attachment://{file_name}")
            embed.set_footer(text=f"Submitter: {user.display_name}")
            
            await interaction.channel.send(file=file, embed=embed)

        except Exception as e:
            print(f"Error: {e}")
            await interaction.followup.send("⚠️ Terjadi kesalahan atau waktu habis.", ephemeral=True)

# --- SISTEM NAVIGASI ---
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
    embed.description = "Gunakan tombol di bawah untuk berpartisipasi."
    await ctx.send(embed=embed, view=PersistentView())

@bot.command()
@commands.has_permissions(administrator=True)
async def del_ta(ctx, *, ign_name: str):
    result = collection.delete_one({"ign": {"$regex": f"^{ign_name}$", "$options": "i"}})
    if result.deleted_count > 0:
        await ctx.send(f"🗑️ Data **{ign_name}** dihapus.")
    else:
        await ctx.send(f"❓ IGN tidak ditemukan.")

bot.run(TOKEN)
