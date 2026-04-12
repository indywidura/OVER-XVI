import discord
from discord.ext import commands
from discord import ui
from pymongo import MongoClient
import datetime, asyncio, re, io, csv, threading, os, functools
from flask import Flask, jsonify
import pytesseract
from PIL import Image, ImageOps, ImageEnhance, ImageFilter

# ================= CONFIGURATION =================
TOKEN = os.getenv('TOKEN') 
MONGO_URL = os.getenv('MONGO_URL')

bot = commands.Bot(
    command_prefix="!",
    intents=discord.Intents.all(),
    help_command=None
)

# Database Setup (Optimized for 1000+ Players)
db = MongoClient(MONGO_URL, maxPoolSize=50)["over_xvi_db"]
col = db["timeattack"]
events = db["events"]

user_cooldowns = {}

# ================= WEB SERVER (DASHBOARD) =================
app = Flask(__name__)

@app.route("/")
def home(): 
    return jsonify({
        "bot_status": "Online",
        "total_players": col.count_documents({}),
        "active_events": events.count_documents({}),
        "engine": "Gemini-Powered OCR System (Async Optimized)"
    })

def run_web():
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)

# ================= UTILS & OCR ENGINE =================
def parse_time(t):
    if not re.match(r'^\d{2}:\d{2}\.\d{3}$', t): 
        return None
    try:
        m, s_ms = t.split(":")
        s, ms = s_ms.split(".")
        return int(m)*60 + int(s) + float(f"0.{ms}")
    except: 
        return None

def scan_time(image_bytes):
    try:
        img = Image.open(io.BytesIO(image_bytes))
        img = img.convert('L') 
        enhancer = ImageEnhance.Contrast(img)
        img = enhancer.enhance(3.0) 
        img = img.point(lambda x: 0 if x < 200 else 255) 
        custom_config = r'--psm 7 -c tessedit_char_whitelist=0123456789:.'
        text = pytesseract.image_to_string(img, config=custom_config)
        match = re.search(r'\d{2}:\d{2}\.\d{3}', text)
        return match.group(0) if match else None
    except Exception as e:
        print(f"DEBUG OCR ERROR: {e}")
        return None

# ================= MODAL DIALOGS =================
class SearchPlayerModal(ui.Modal):
    def __init__(self, event_name):
        super().__init__(title="🔍 Pencarian Driver")
        self.event_name = event_name
        self.target = ui.TextInput(label="IGN atau ID Game", placeholder="Masukkan Nickname...")
        self.add_item(self.target)

    async def on_submit(self, i: discord.Interaction):
        search_val = self.target.value.lower()
        query = {
            "event": self.event_name, 
            "approved": True, 
            "$or": [
                {"ign": {"$regex": search_val, "$options": "i"}}, 
                {"game_id": search_val}
            ]
        }
        found_data = list(col.find(query).sort("waktu_raw", 1).limit(1))
        
        if found_data:
            d = found_data[0]
            rank = col.count_documents({
                "event": self.event_name, 
                "approved": True, 
                "waktu_raw": {"$lt": d['waktu_raw']}
            }) + 1
            
            emb = discord.Embed(title=f"🔍 DATA DRIVER: {d['ign']}", color=0x3498db)
            emb.add_field(name="🛡️ Club", value=f"{d.get('club', '-')}", inline=True)
            emb.add_field(name="🏆 Rank", value=f"**#{rank}**", inline=True)
            emb.add_field(name="⏱️ Waktu", value=f"`{d['waktu']}`", inline=True)
            emb.add_field(name="📝 Submitter", value=d.get('discord_name', 'Unknown'), inline=False)
            
            if "evidence_url" in d:
                emb.set_image(url=d["evidence_url"])
            
            await i.response.send_message(embed=emb, ephemeral=True)
        else:
            await i.response.send_message(f"❌ Player **{self.target.value}** tidak ditemukan.", ephemeral=True)

class DeletePlayerModal(ui.Modal):
    def __init__(self, event_name):
        super().__init__(title="Hapus Driver")
        self.event_name = event_name
        self.target = ui.TextInput(label="IGN Player", placeholder="Nickname...")
        self.add_item(self.target)

    async def on_submit(self, i: discord.Interaction):
        result = col.delete_one({"event": self.event_name, "ign": {"$regex": f"^{self.target.value}$", "$options": "i"}})
        if result.deleted_count > 0:
            await i.response.send_message(f"✅ **{self.target.value}** berhasil dihapus.", ephemeral=True)
        else:
            await i.response.send_message("❌ Player tidak ditemukan.", ephemeral=True)

class SubmitModal(ui.Modal):
    def __init__(self, event_name):
        super().__init__(title=f"📝 Submit: {event_name}")
        self.event_name = event_name
        self.ign = ui.TextInput(label="IGN (Nickname)", min_length=2, max_length=25)
        self.club = ui.TextInput(label="Club / Tim", default="ENDGAME", max_length=20)
        self.game_id = ui.TextInput(label="ID Game", placeholder="Contoh: 123456")
        self.time_val = ui.TextInput(label="Waktu (MM:SS.ms)", placeholder="01:12.188")
        for item in [self.ign, self.club, self.game_id, self.time_val]: 
            self.add_item(item)

    async def on_submit(self, i: discord.Interaction):
        user_id = i.user.id
        now = datetime.datetime.now()
        cooldown_seconds = 600

        if not i.user.guild_permissions.administrator:
            if user_id in user_cooldowns:
                elapsed = (now - user_cooldowns[user_id]).total_seconds()
                if elapsed < cooldown_seconds:
                    remaining_min = int((cooldown_seconds - elapsed) // 60)
                    remaining_sec = int((cooldown_seconds - elapsed) % 60)
                    return await i.response.send_message(
                        f"⏳ **Anti-Spam Aktif!**\nSilakan tunggu **{remaining_min}m {remaining_sec}s**.", ephemeral=True
                    )

        sec = parse_time(self.time_val.value)
        if not sec: 
            return await i.response.send_message("❌ Format waktu salah! Gunakan **MM:SS.ms**", ephemeral=True)
        
        if not i.user.guild_permissions.administrator:
            user_cooldowns[user_id] = now
        
        await i.response.send_message("📸 Silakan upload screenshot bukti balapan (60 detik)...", ephemeral=True)
        
        try:
            msg = await bot.wait_for(
                "message", 
                timeout=60, 
                check=lambda m: m.author.id == i.user.id and m.attachments
            )
            
            attachment_url = msg.attachments[0].url
            img_bytes = await msg.attachments[0].read()

            loop = asyncio.get_event_loop()
            detected = await loop.run_in_executor(None, scan_time, img_bytes)

            is_match = (detected == self.time_val.value)
            
            entry = {
                "user_id": i.user.id,
                "discord_name": str(i.user),
                "event": self.event_name,
                "ign": self.ign.value,
                "club": self.club.value,
                "game_id": self.game_id.value,
                "waktu": self.time_val.value,
                "waktu_raw": sec,
                "evidence_url": attachment_url,
                "approved": is_match,
                "timestamp": now
            }
            
            col.update_one({"user_id": i.user.id, "event": self.event_name}, {"$set": entry}, upsert=True)
            doc = col.find_one({"user_id": i.user.id, "event": self.event_name})
            file_img = discord.File(io.BytesIO(img_bytes), filename="evidence.png")

            if is_match:
                emb = discord.Embed(title="✅ TERVERIFIKASI OTOMATIS", color=0x2ecc71)
                emb.add_field(name="👤 Driver", value=f"**{self.ign.value}**", inline=True)
                emb.add_field(name="🛡️ Club", value=f"{self.club.value}", inline=True)
                emb.add_field(name="⏱️ Waktu", value=f"`{self.time_val.value}`", inline=False)
                emb.set_image(url="attachment://evidence.png")
                await i.channel.send(embed=emb, file=file_img)
            else:
                adm_emb = discord.Embed(title="📩 MENUNGGU PERSETUJUAN ADMIN", color=0xf1c40f)
                adm_emb.add_field(name="👤 Driver", value=f"{self.ign.value}")
                adm_emb.add_field(name="⌨️ Input", value=f"`{self.time_val.value}`", inline=True)
                adm_emb.add_field(name="🤖 AI", value=f"`{detected or 'Gagal'}`", inline=True)
                adm_emb.set_image(url="attachment://evidence.png")
                await i.channel.send(content="🔔 **ANTREAN BARU:**", embed=adm_emb, file=file_img, view=ApprovalView(doc['_id']))
            
            await msg.delete()

        except asyncio.TimeoutError:
            if not i.user.guild_permissions.administrator and user_id in user_cooldowns: 
                del user_cooldowns[user_id]
            await i.followup.send("❌ Waktu habis! Kamu tidak mengupload gambar.", ephemeral=True)
        except Exception as e:
            print(f"Error: {e}")

# ================= INTERACTIVE VIEWS =================
class ApprovalView(ui.View):
    def __init__(self, entry_id):
        super().__init__(timeout=None)
        self.entry_id = entry_id
        
    async def interaction_check(self, i: discord.Interaction):
        if i.user.guild_permissions.administrator: return True
        await i.response.send_message("❌ Hanya Admin!", ephemeral=True)
        return False

   @ui.button(label="✅ Approve", style=discord.ButtonStyle.green)
    async def approve(self, i: discord.Interaction, b: ui.Button):
        # Ambil nama admin yang menekan tombol
        approver_name = str(i.user)
        
        # 1. Update status 'approved' DAN simpan siapa yang approve
        col.update_one(
            {"_id": self.entry_id}, 
            {"$set": {"approved": True, "approved_by": approver_name}}
        )
        
        # 2. Ambil data lengkap untuk update embed
        data = col.find_one({"_id": self.entry_id})
        
        if data:
            submitter_name = data.get('discord_name', 'Unknown')
            
            emb = discord.Embed(title="🌟 REKOR BARU TERCATAT", color=0x2ecc71)
            emb.add_field(name="👤 Peserta", value=f"**{data['ign']}**", inline=True)
            emb.add_field(name="🛡️ Club", value=f"{data.get('club', '-')}", inline=True)
            emb.add_field(name="⏱️ Waktu", value=f"`{data['waktu']}`", inline=False)
            emb.add_field(name="📥 Submitted by", value=submitter_name, inline=True)
            emb.add_field(name="⚖️ Approved by", value=approver_name, inline=True) # Menampilkan di Discord
            
            if "evidence_url" in data:
                emb.set_image(url=data["evidence_url"])

            await i.response.edit_message(content=None, embed=emb, view=None)

    @ui.button(label="❌ Reject", style=discord.ButtonStyle.danger)
    async def reject(self, i, b):
        col.delete_one({"_id": self.entry_id})
        await i.response.edit_message(content="❌ Data Driver ditolak.", embed=None, view=None)

class LeaderboardView(ui.View):
    def __init__(self, event_name, page=0):
        super().__init__(timeout=60)
        self.event_name = event_name
        self.page = page

    async def get_stats(self):
        skip_val = self.page * 10
        data = list(col.find({"event": self.event_name, "approved": True}).sort("waktu_raw", 1).skip(skip_val).limit(10))
        total_data = col.count_documents({"event": self.event_name, "approved": True})
        total_pages = (total_data - 1) // 10 + 1 if total_data else 1
        return data, total_pages

    def create_embed(self, data, pages):
        description = ""
        for idx, d in enumerate(data):
            rank = (self.page * 10) + idx + 1
            # Menambahkan info approved by di bawah setiap baris leaderboard
            approver = d.get('approved_by', 'Auto/System')
            description += f"**{rank}.** {d['ign']} [{d.get('club', 'Endgame')}] - `{d['waktu']}`\n"
            description += f"└ *Approved by: {approver}*\n" # Info tambahan
        
        emb = discord.Embed(title=f"🏆 LEADERBOARD: {self.event_name.upper()}", 
                            description=description or "Belum ada data.", color=0xf1c40f)
        emb.set_footer(text=f"Halaman {self.page + 1} dari {pages}")
        return emb

    @ui.button(label="⬅️", style=discord.ButtonStyle.grey)
    async def prev(self, i, b):
        if self.page > 0:
            self.page -= 1
            d, p = await self.get_stats()
            await i.response.edit_message(embed=self.create_embed(d, p), view=self)
        else: await i.response.defer()

    @ui.button(label="➡️", style=discord.ButtonStyle.grey)
    async def next(self, i, b):
        d, p = await self.get_stats()
        if self.page < p - 1:
            self.page += 1
            d, p = await self.get_stats()
            await i.response.edit_message(embed=self.create_embed(d, p), view=self)
        else: await i.response.defer()

    @ui.button(label="🔍 Cari", style=discord.ButtonStyle.blurple)
    async def search(self, i, b): 
        await i.response.send_modal(SearchPlayerModal(self.event_name))

    @ui.button(label="🗑️ Hapus Player", style=discord.ButtonStyle.danger)
    async def delete_player(self, i, b):
        if not i.user.guild_permissions.administrator:
            return await i.response.send_message("❌ Khusus Admin!", ephemeral=True)
        await i.response.send_modal(DeletePlayerModal(self.event_name))

    @ui.button(label="🏠 Menu", style=discord.ButtonStyle.green)
    async def home_btn(self, i, b):
        emb = discord.Embed(title=f"🏎️ EVENT: {self.event_name.upper()}", color=0x3498db)
        await i.response.edit_message(embed=emb, view=MainView(self.event_name))

# ================= ADMIN MENU (FIXED INTERACTION FAILED) =================
class AdminMenuView(ui.View):
    def __init__(self, event_name):
        super().__init__(timeout=60)
        self.event_name = event_name

    @ui.button(label="📥 Export Excel", style=discord.ButtonStyle.green)
    async def download(self, i: discord.Interaction, b: ui.Button):
        await i.response.defer(ephemeral=True)
        
        try:
            data = list(col.find({"event": self.event_name}).sort("waktu_raw", 1))
            
            if not data:
                return await i.followup.send("❌ Tidak ada data.", ephemeral=True)

            rows = []
            for idx, d in enumerate(data):
                status = "Approved" if d.get('approved') else "Pending"
                rows.append({
                    "RANK": idx + 1,
                    "IGN": d.get('ign', '-'),
                    "CLUB": d.get('club', '-'),
                    "GAME ID": d.get('game_id', '-'),
                    "TIME": f"'{d['waktu']}", 
                    "STATUS": status,
                    "SUBMITTER": d.get('discord_name', 'Unknown'),
                    "APPROVED BY": d.get('approved_by', '-') # Kolom baru di Excel
                })

            df = pd.DataFrame(rows)
            output = io.BytesIO()
            
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                df.to_excel(writer, index=False, sheet_name='Leaderboard')
                
                # Auto-size kolom
                worksheet = writer.sheets['Leaderboard']
                for idx, col_name in enumerate(df.columns):
                    column_len = max(df[col_name].astype(str).map(len).max(), len(col_name)) + 2
                    worksheet.column_dimensions[chr(65 + idx)].width = column_len

            output.seek(0)
            
            await i.followup.send(
                content=f"📊 Rekap Excel **{self.event_name}**:", 
                file=discord.File(fp=output, filename=f"Leaderboard_{self.event_name}.xlsx"), 
                ephemeral=True
            )
        except Exception as e:
            await i.followup.send(f"❌ Error: {e}", ephemeral=True)

        except Exception as e:
            print(f"Export Error: {e}")
            await i.followup.send(f"❌ Terjadi kesalahan saat generate Excel: {e}", ephemeral=True)

    @ui.button(label="🚨 Reset Semua Data", style=discord.ButtonStyle.danger)
    async def clear(self, i: discord.Interaction, b: ui.Button):
        col.delete_many({"event": self.event_name})
        await i.response.send_message("❌ Leaderboard dikosongkan!", ephemeral=True)

    @ui.button(label="⬅️ Kembali", style=discord.ButtonStyle.blurple)
    async def back(self, i: discord.Interaction, b: ui.Button):
        emb = discord.Embed(title=f"🏎️ EVENT: {self.event_name.upper()}", color=0x3498db)
        await i.response.edit_message(embed=emb, view=MainView(self.event_name))

class MainView(ui.View):
    def __init__(self, event_name):
        super().__init__(timeout=None)
        self.event_name = event_name

    @ui.button(label="Submit Time", style=discord.ButtonStyle.green, custom_id="btn_submit_v4")
    async def submit_btn(self, i, b):
        await i.response.send_modal(SubmitModal(self.event_name))

    @ui.button(label="Leaderboard", style=discord.ButtonStyle.blurple, custom_id="btn_lb_v4")
    async def lb_btn(self, i, b):
        v = LeaderboardView(self.event_name)
        d, p = await v.get_stats()
        await i.response.edit_message(embed=v.create_embed(d, p), view=v)

    @ui.button(label="Menu Admin", style=discord.ButtonStyle.grey, custom_id="btn_admin_v4")
    async def admin_btn(self, i, b):
        if not i.user.guild_permissions.administrator: 
            return await i.response.send_message("🚫 Khusus Admin!", ephemeral=True)
        await i.response.edit_message(embed=discord.Embed(title="🛠️ Admin Panel", color=0x2c3e50), view=AdminMenuView(self.event_name))

# ================= COMMANDS =================
@bot.command()
async def ta(ctx):
    if not events.find_one({"name": ctx.channel.name}): 
        return await ctx.send("❌ Gunakan `!create_event` terlebih dahulu.")
    emb = discord.Embed(title=f"🏎️ OVER-XVI TIME ATTACK: {ctx.channel.name.upper()}", color=0x3498db)
    await ctx.send(embed=emb, view=MainView(ctx.channel.name))

@bot.command()
@commands.has_permissions(administrator=True)
async def create_event(ctx):
    events.update_one({"name": ctx.channel.name}, {"$set": {"name": ctx.channel.name}}, upsert=True)
    await ctx.send(f"✅ Channel **#{ctx.channel.name}** aktif!")

@bot.event
async def on_ready():
    bot.add_view(MainView("")) 
    print(f">>> OVER-XVI SYSTEM ONLINE <<<")
    threading.Thread(target=run_web, daemon=True).start()

bot.run(TOKEN)
