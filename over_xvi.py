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

# --- FUNGSI PEMBUAT EMBED LEADERBOARD ---
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

# --- KELAS MODAL (Input Waktu + Screenshot) ---
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
        now = datetime.datetime.now()

        # --- LOGIKA ANTI-SPAM (COOLDOWN 10 MENIT) ---
        user_data = collection.find_one({"_id": user.id})
        if user_data and "last_submit" in user_data:
            last_submit = user_data["last_submit"]
            diff = now - last_submit
            if diff.total_seconds() < 600:  # 600 detik = 10 menit
                sisa_waktu = int((600 - diff.total_seconds()) / 60)
                await interaction.response.send_message(
                    f"⏳ **Cooldown!** Kamu baru saja menginput data. Silakan tunggu **{sisa_waktu} menit** lagi.", 
                    ephemeral=True
                )
                return

        # Lanjut jika lolos cooldown
        await interaction.response.send_message(
            f"✅ Data waktu `{waktu}` diterima!\n**Mohon unggah (upload) screenshot bukti Anda di sini dalam 60 detik.**", 
            ephemeral=True
        )

        def check(m):
            return m.author == user and m.channel == interaction.channel and len(m.attachments) > 0

        try:
            msg = await bot.wait_for('message', timeout=60.0, check=check)
            screenshot_url = msg.attachments[0].url
            tanggal_str = now.strftime("%d/%m/%Y")

            if user_data is None or waktu < user_data["waktu"]:
                collection.update_one(
                    {"_id": user.id},
                    {
                        "$set": {
                            "user_name": user.display_name, 
                            "waktu": waktu, 
                            "tanggal": tanggal_str,
                            "last_submit": now  # Simpan waktu submit terakhir
                        }
                    },
                    upsert=True
                )
                
                embed_konfirmasi = discord.Embed(
                    title="📸 BUKTI REKOR BARU",
                    description=f"Peserta: **{user.display_name}**\nWaktu: `{waktu}`\nStatus: **Tercatat!**",
                    color=0x2ecc71
                )
                embed_konfirmasi.set_image(url=screenshot_url)
                await interaction.channel.send(embed=embed_konfirmasi)
                
            else:
                # Update last_submit saja meski waktu tidak lebih cepat (mencegah spam gagal)
                collection.update_one({"_id": user.id}, {"$set": {"last_submit": now}})
                await interaction.followup.send(
                    f"❌ Waktu `{waktu}` tidak lebih baik dari rekor terbaikmu.", 
                    ephemeral=True
                )

        except asyncio.TimeoutError:
            await interaction.followup.send("⚠️ Waktu habis. Data gagal dicatat.", ephemeral=True)

# --- VIEW NAVIGASI & MENU ---
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

    @ui.button(label='🏠 Kembali ke Menu', style=discord.ButtonStyle.red)
    async def back_to_menu(self, interaction: discord.Interaction, button: ui.Button):
        embed = discord.Embed(
            title="🏎️ TIME ATTACK COMPETITION",
            description="Klik tombol di bawah untuk berpartisipasi!",
            color=0x2ecc71
        )
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
    await ctx.send(embed=embed, view=PersistentView())

# --- PERINTAH ADMIN ---
@bot.command()
@commands.has_permissions(administrator=True)
async def del_ta(ctx, *, name: str):
    result = collection.delete_one({"user_name": {"$regex": f"^{name}$", "$options": "i"}})
    if result.deleted_count > 0:
        await ctx.send(f"🗑️ Data **{name}** berhasil dihapus.")
    else:
        await ctx.send(f"❓ Nama **{name}** tidak ditemukan.")

bot.run(TOKEN)            await interaction.followup.send("⚠️ Waktu habis. Data gagal dicatat.", ephemeral=True)

# --- VIEW NAVIGASI LEADERBOARD ---
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

    @ui.button(label='🏠 Kembali ke Menu', style=discord.ButtonStyle.red)
    async def back_to_menu(self, interaction: discord.Interaction, button: ui.Button):
        embed = discord.Embed(
            title="🏎️ TIME ATTACK COMPETITION",
            description="Klik tombol di bawah untuk berpartisipasi!",
            color=0x2ecc71
        )
        await interaction.response.edit_message(embed=embed, view=PersistentView())

# --- VIEW UTAMA ---
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
    await ctx.send(embed=embed, view=PersistentView())

# --- PERINTAH ADMIN: HAPUS DATA ---
@bot.command()
@commands.has_permissions(administrator=True)
async def del_ta(ctx, *, name: str):
    """Menghapus data peserta berdasarkan nama di database"""
    # Mencari data dengan nama (case insensitive)
    result = collection.delete_one({"user_name": {"$regex": f"^{name}$", "$options": "i"}})
    
    if result.deleted_count > 0:
        await ctx.send(f"🗑️ Data peserta dengan nama **{name}** telah dihapus dari leaderboard.")
    else:
        await ctx.send(f"❓ Peserta dengan nama **{name}** tidak ditemukan.")

@del_ta.error
async def del_ta_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("🚫 Kamu tidak punya izin (Admin) untuk menghapus data!")

bot.run(TOKEN)
