import discord
from discord.ext import commands
from discord import ui
from pymongo import MongoClient
import datetime, asyncio, re, io, threading, os
from flask import Flask, jsonify
import pytesseract
from PIL import Image, ImageOps, ImageEnhance
import pandas as pd

# ================= KONFIGURASI SISTEM =================
TOKEN = os.getenv('TOKEN') 
MONGO_URL = os.getenv('MONGO_URL')

bot = commands.Bot(
    command_prefix="!",
    intents=discord.Intents.all(),
    help_command=None
)

# Database Setup
db = MongoClient(MONGO_URL, maxPoolSize=50)["over_xvi_db"]
col = db["timeattack"]
events = db["events"]

# ================= MULTI-LANGUAGE DICTIONARY =================
TRANSLATIONS = {
    "id": {
        "modal_title": "Submit Waktu",
        "ign": "IGN (Nickname)",
        "club": "Nama Club",
        "id_game": "Game ID",
        "time": "Waktu (MM:SS.ms)",
        "invalid_time": "❌ Format Salah! Gunakan **MM:SS.ms**",
        "upload_msg": "📸 Silakan upload screenshot bukti sekarang...",
        "timeout": "❌ Waktu habis! Anda tidak mengupload gambar.",
        "cooldown": "⏳ **COOLDOWN AKTIF!**\nSilakan tunggu **{}m {}s**.",
        "rejected_msg": "❌ **Submission Anda Ditolak**",
        "reason_label": "Alasan Penolakan",
        "reject_button": "Tolak",
    },
    "en": {
        "modal_title": "Submit Time",
        "ign": "IGN (Nickname)",
        "club": "Club Name",
        "id_game": "Game ID",
        "time": "Time (MM:SS.ms)",
        "invalid_time": "❌ Invalid Format! Use **MM:SS.ms**",
        "upload_msg": "📸 Please upload screenshot evidence now...",
        "timeout": "❌ Timeout! No image uploaded.",
        "cooldown": "⏳ **COOLDOWN ACTIVE!**\nPlease wait **{}m {}s**.",
        "rejected_msg": "❌ **Your Submission was Rejected**",
        "reason_label": "Reason for Rejection",
        "reject_button": "Reject",
    },
    "th": {
        "modal_title": "ส่งเวลา",
        "ign": "ชื่อในเกม (IGN)",
        "club": "ชื่อคลับ",
        "id_game": "ไอดีเกม",
        "time": "เวลา (นาที:วินาที.มิลลิวินาที)",
        "invalid_time": "❌ รูปแบบไม่ถูกต้อง! ใช้ **MM:SS.ms**",
        "upload_msg": "📸 กรุณาอัปโหลดภาพหน้าจอหลักฐานตอนนี้...",
        "timeout": "❌ หมดเวลา! ไม่มีการอัปโหลดภาพ",
        "cooldown": "⏳ **คูลดาวน์ทำงาน!**\nกรุณารอ **{}น {}ว**.",
        "rejected_msg": "❌ **การส่งข้อมูลของคุณถูกปฏิเสธ**",
        "reason_label": "เหตุผลในการปฏิเสธ",
        "reject_button": "ปฏิเสธ",
    },
    "ph": {
        "modal_title": "I-submit ang Oras",
        "ign": "IGN (Nickname)",
        "club": "Pangalan ng Club",
        "id_game": "Game ID",
        "time": "Oras (MM:SS.ms)",
        "invalid_time": "❌ Maling Format! Gamitin ang **MM:SS.ms**",
        "upload_msg": "📸 Mangyaring i-upload ang screenshot ngayon...",
        "timeout": "❌ Ubos na ang oras! Walang na-upload na larawan.",
        "cooldown": "⏳ **COOLDOWN AKTIBO!**\nMaghintay ng **{}m {}s**.",
        "rejected_msg": "❌ **Ang iyong Submission ay Tinanggihan**",
        "reason_label": "Dahilan ng Pagtanggi",
        "reject_button": "Tanggihan",
    },
    "ms": {
        "modal_title": "Hantar Masa",
        "ign": "IGN (Nickname)",
        "club": "Nama Kelab",
        "id_game": "ID Permainan",
        "time": "Masa (MM:SS.ms)",
        "invalid_time": "❌ Format Salah! Gunakan **MM:SS.ms**",
        "upload_msg": "📸 Sila muat naik tangkapan skrin sekarang...",
        "timeout": "❌ Masa tamat! Tiada gambar dimuat naik.",
        "cooldown": "⏳ **COOLDOWN AKTIF!**\nSila tunggu **{}m {}s**.",
        "rejected_msg": "❌ **Hantaran Anda Telah Ditolak**",
        "reason_label": "Sebab Penolakan",
        "reject_button": "Tolak",
    }
}

# ================= WEB SERVER (DASHBOARD) =================
app = Flask(__name__)

@app.route("/")
def home(): 
    return jsonify({
        "bot_status": "Online",
        "total_players": col.count_documents({}),
        "active_events": events.count_documents({}),
        "engine": "Gemini-Powered OCR System"
    })

def run_web():
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)

# ================= UTILS & OCR ENGINE =================
def parse_time(t):
    """Mengonversi MM:SS.ms ke float detik untuk sorting"""
    if not re.match(r'^\d{2}:\d{2}\.\d{3}$', t): 
        return None
    try:
        m, s_ms = t.split(":")
        s, ms = s_ms.split(".")
        return int(m)*60 + int(s) + float(f"0.{ms}")
    except: 
        return None

def scan_time(image_bytes):
    """OCR function dengan optimasi Pre-Processing yang lebih kuat"""
    try:
        img = Image.open(io.BytesIO(image_bytes))
        width, height = img.size
        
        # PERBAIKAN CROP: Perlebar sedikit area pencarian (50% lebar, 50% tinggi)
        # untuk memastikan angka tidak terpotong di berbagai resolusi
        left = 0
        top = 0
        right = width * 0.50 
        bottom = height * 0.50
        img_cropped = img.crop((left, top, right, bottom))
        
        # PRE-PROCESSING LANJUTAN
        img_cropped = img_cropped.convert('L') # Grayscale
        
        # Optimasi Kontras & Ketajaman
        img_cropped = ImageEnhance.Contrast(img_cropped).enhance(3.5)
        img_cropped = ImageEnhance.Sharpness(img_cropped).enhance(2.0)
        
        # Opsi tambahan: Jika angka berwarna terang di background gelap, 
        # Tesseract lebih suka angka hitam di background putih (Invert)
        img_cropped = ImageOps.invert(img_cropped) 
        
        # OCR Configuration - Gunakan mode PSM 6 atau 7
        # PSM 7: Menganggap gambar adalah satu baris teks
        custom_config = r'--psm 7 -c tessedit_char_whitelist=0123456789:.'
        text = pytesseract.image_to_string(img_cropped, config=custom_config)
        
        # Bersihkan karakter aneh yang sering muncul
        text = text.replace(" ", "").strip()
        
        # Cari pola MM:SS.ms
        match = re.search(r'\d{2}:\d{2}\.\d{3}', text)
        return match.group(0) if match else None
    except Exception as e:
        print(f"DEBUG OCR ERROR: {e}")
        return None
# ================= MODAL DIALOGS =================
class SearchPlayerModal(ui.Modal):
    """Modal untuk mencari data spesifik driver"""
    def __init__(self, event_name):
        super().__init__(title="🔍 Driver Search")
        self.event_name = event_name
        self.target = ui.TextInput(label="IGN or Game ID", placeholder="Masukkan nickname atau ID...")
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
            
            emb = discord.Embed(title=f"🔍 DRIVER DATA: {d['ign']}", color=0x3498db)
            emb.add_field(name="🛡️ Club", value=f"{d.get('club', '-')}", inline=True)
            emb.add_field(name="🏆 Rank", value=f"**#{rank}**", inline=True)
            emb.add_field(name="⏱️ Time", value=f"`{d['waktu']}`", inline=True)
            emb.add_field(name="🆔 Game ID", value=f"{d.get('game_id', '-')}", inline=True)
            emb.add_field(name="📝 Submitter", value=d.get('discord_name', 'Unknown'), inline=False)
            emb.add_field(name="⚖️ Approved By", value=d.get('approved_by', 'System'), inline=False)
            
            if "evidence_url" in d:
                emb.set_image(url=d["evidence_url"])
            
            await i.response.send_message(embed=emb, ephemeral=True)
        else:
            await i.response.send_message(f"❌ Player **{self.target.value}** tidak ditemukan.", ephemeral=True)

class RejectReasonModal(ui.Modal): # <--- SEJAJARKAN DENGAN CLASS LAIN (KELUARKAN DARI SUBMITMODAL)
    def __init__(self, entry_id, user_id, lang_code):
        self.lang = TRANSLATIONS.get(lang_code, TRANSLATIONS["en"])
        super().__init__(title=self.lang["reject_button"])
        self.entry_id = entry_id
        self.user_id = user_id
        
        self.reason = ui.TextInput(
            label=self.lang["reason_label"],
            placeholder="E.g. Blurred image / Screenshot buram",
            required=True
        )
        self.add_item(self.reason)

    async def on_submit(self, i: discord.Interaction):
        col.delete_one({"_id": self.entry_id})
        try:
            target_user = await i.client.fetch_user(self.user_id)
            reject_emb = discord.Embed(title=self.lang["rejected_msg"], color=0xe74c3c)
            reject_emb.add_field(name="Reason / Alasan", value=self.reason.value)
            await target_user.send(embed=reject_emb)
        except:
            pass 

        final_emb = discord.Embed(title="🚫 SUBMISSION REJECTED", color=0xe74c3c)
        final_emb.add_field(name="Admin", value=i.user.display_name, inline=True)
        final_emb.add_field(name="Reason", value=self.reason.value, inline=True)
        await i.response.edit_message(content=f"🔴 Rejected by {i.user.mention}", embed=final_emb, view=None)

class DeletePlayerModal(ui.Modal):
    def __init__(self, event_name):
        super().__init__(title="🚨 Hapus Data Player")
        self.event_name = event_name
        self.target = ui.TextInput(
            label="IGN atau Game ID", 
            placeholder="Masukkan data yang ingin dihapus...",
            required=True
        )
        self.add_item(self.target)

    async def on_submit(self, i: discord.Interaction):
        search_val = self.target.value
        # Mencari data berdasarkan IGN (case insensitive) atau Game ID
        query = {
            "event": self.event_name,
            "$or": [
                {"ign": {"$regex": f"^{re.escape(search_val)}$", "$options": "i"}},
                {"game_id": search_val}
            ]
        }
        
        # Cek apakah data ada sebelum dihapus
        target_data = col.find_one(query)
        
        if target_data:
            col.delete_one({"_id": target_data["_id"]})
            await i.response.send_message(
                f"✅ Berhasil menghapus data player: **{target_data['ign']}** dari event **{self.event_name}**.", 
                ephemeral=True
            )
        else:
            await i.response.send_message(
                f"❌ Player **{search_val}** tidak ditemukan di event ini.", 
                ephemeral=True
            )

class SubmitModal(ui.Modal):
    def __init__(self, event_name, lang_code="en"):
        self.lang_code = lang_code # <--- TAMBAHKAN INI AGAR BISA DIPANGGIL DI ON_SUBMIT
        self.lang = TRANSLATIONS.get(lang_code, TRANSLATIONS["en"])
        super().__init__(title=f"{self.lang['modal_title']}: {event_name}")
        self.event_name = event_name
        
        self.ign = ui.TextInput(label=self.lang["ign"], min_length=2, max_length=25)
        self.club = ui.TextInput(label=self.lang["club"], placeholder="RFF", max_length=20, required=False)
        self.game_id = ui.TextInput(label=self.lang["id_game"], placeholder="552134")
        self.time_val = ui.TextInput(label=self.lang["time"], placeholder="01:12.188")
        
        for item in [self.ign, self.club, self.game_id, self.time_val]: 
            self.add_item(item)

    async def on_submit(self, i: discord.Interaction):
        sec = parse_time(self.time_val.value)
        if not sec: 
            return await i.response.send_message(self.lang["invalid_time"], ephemeral=True)
        
        await i.response.send_message(self.lang["upload_msg"], ephemeral=True)
        
        try:
            msg = await bot.wait_for(
                "message", 
                timeout=120, 
                check=lambda m: m.author.id == i.user.id and m.attachments
            )
            
            attachment_url = msg.attachments[0].url
            img_bytes = await msg.attachments[0].read()

            loop = asyncio.get_event_loop()
            detected = await loop.run_in_executor(None, scan_time, img_bytes)

            is_match = (detected == self.time_val.value)
            now = datetime.datetime.now()
            
            entry = {
                "user_id": i.user.id,
                "discord_name": str(i.user),
                "event": self.event_name,
                "ign": self.ign.value,
                "club": self.club.value,
                "game_id": self.game_id.value,
                "waktu": self.time_val.value,
                "waktu_raw": sec,  # <--- SEKARANG SUDAH BENAR
                "lang_code": self.lang_code,
                "evidence_url": attachment_url,
                "approved": is_match,
                "timestamp": now
            }
            
            col.update_one({"user_id": i.user.id, "event": self.event_name}, {"$set": entry}, upsert=True)
            doc = col.find_one({"user_id": i.user.id, "event": self.event_name})
            file_img = discord.File(io.BytesIO(img_bytes), filename="evidence.png")

            if is_match:
                emb = discord.Embed(title="🌟 NEW RECORD RECORDED", color=0x2ecc71)
                emb.add_field(name="👤 Driver", value=f"**{self.ign.value}**", inline=True)
                emb.add_field(name="🛡️ Club", value=f"{self.club.value}", inline=True)
                emb.add_field(name="🆔 Game ID", value=f"{self.game_id.value}", inline=True)
                emb.add_field(name="⏱️ Time", value=f"`{self.time_val.value}`", inline=False)
                emb.add_field(name="📥 Submitted by", value=f"{i.user.display_name}", inline=True)
                emb.add_field(name="⚖️ Approved by", value="System (Auto)", inline=True)
                emb.set_image(url="attachment://evidence.png")
                await i.channel.send(embed=emb, file=file_img)
            else:
                adm_emb = discord.Embed(title="📩 PENDING APPROVAL", color=0xf1c40f)
                adm_emb.add_field(name="👤 Driver", value=f"**{self.ign.value}**", inline=True)
                adm_emb.add_field(name="🛡️ Club", value=f"{self.club.value}", inline=True)
                adm_emb.add_field(name="🆔 Game ID", value=f"{self.game_id.value}", inline=True)
                adm_emb.add_field(name="⌨️ User Input", value=f"`{self.time_val.value}`", inline=True)
                adm_emb.add_field(name="🤖 AI Scan", value=f"`{detected or 'Gagal Membaca'}`", inline=True)
                adm_emb.set_image(url="attachment://evidence.png")
                await i.channel.send(
                    content="🔔 **NEW SUBMISSION (MANUAL CHECK REQUIRED):**", 
                    embed=adm_emb, 
                    file=file_img, 
                    view=ApprovalView(doc['_id'])
                )
            
            await msg.delete()

        except asyncio.TimeoutError:
            await i.followup.send(self.lang["timeout"], ephemeral=True)
        except Exception as e:
            print(f"Error: {e}")

# ================= INTERACTIVE VIEWS =================
class ApprovalView(ui.View):
    def __init__(self, entry_id):
        super().__init__(timeout=None)
        self.entry_id = entry_id

    async def interaction_check(self, i: discord.Interaction):
        if i.user.guild_permissions.administrator: return True
        await i.response.send_message("❌ Admin Only!", ephemeral=True)
        return False

    @ui.button(label="✅ Approve", style=discord.ButtonStyle.green)
    async def approve(self, i: discord.Interaction, b: ui.Button):
        approver = i.user.display_name
        col.update_one({"_id": self.entry_id}, {"$set": {"approved": True, "approved_by": approver}})
        data = col.find_one({"_id": self.entry_id})
        
        if data:
            emb = discord.Embed(title="🌟 NEW RECORD RECORDED", color=0x2ecc71)
            emb.add_field(name="👤 Driver", value=f"**{data['ign']}**", inline=True)
            emb.add_field(name="🛡️ Club", value=f"{data.get('club', '-')}", inline=True)
            emb.add_field(name="🆔 Game ID", value=f"{data.get('game_id', '-')}", inline=True)
            emb.add_field(name="⏱️ Time", value=f"`{data['waktu']}`", inline=False)
            submitter = data.get('discord_name', 'Unknown').split('#')[0]
            emb.add_field(name="📥 Submitted by", value=submitter, inline=True)
            emb.add_field(name="⚖️ Approved by", value=approver, inline=True)
            
            if "evidence_url" in data:
                emb.set_image(url=data["evidence_url"])
                
            await i.response.edit_message(content=None, embed=emb, view=None)
            pass
            
    @ui.button(label="❌ Reject", style=discord.ButtonStyle.red)
    async def reject(self, i: discord.Interaction, b: ui.Button):
        data = col.find_one({"_id": self.entry_id})
        if not data:
            return await i.response.send_message("Data not found!", ephemeral=True)
        lang_code = data.get("lang_code", "en")
        await i.response.send_modal(RejectReasonModal(self.entry_id, data['user_id'], lang_code))

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
            description += f"**{rank}.** {d['ign']} [{d.get('club', 'RFF')}] - `{d['waktu']}`\n"
            description += f"└ *Approved by: {d.get('approved_by', 'System')}*\n"
        
        emb = discord.Embed(title=f"🏆 LEADERBOARD: {self.event_name.upper()}", 
                            description=description or "Tidak ada data tersedia.", color=0xf1c40f)
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

    @ui.button(label="🔍 Search", style=discord.ButtonStyle.blurple)
    async def search(self, i, b): 
        await i.response.send_modal(SearchPlayerModal(self.event_name))

    @ui.button(label="🏠 Home", style=discord.ButtonStyle.green)
    async def home_btn(self, i, b):
        emb = discord.Embed(title=f"🏎️ EVENT: {self.event_name.upper()}", color=0x3498db)
        await i.response.edit_message(embed=emb, view=MainView(self.event_name))

class AdminMenuView(ui.View):
    def __init__(self, event_name):
        super().__init__(timeout=60)
        self.event_name = event_name

    @ui.button(label="📥 Export Excel", style=discord.ButtonStyle.green)
    async def download(self, i: discord.Interaction, b: ui.Button):
        await i.response.defer(ephemeral=True)
        try:
            data = list(col.find({"event": self.event_name}).sort("waktu_raw", 1))
            if not data: return await i.followup.send("❌ Tidak ada data untuk di-export.", ephemeral=True)
            rows = []
            for idx, d in enumerate(data):
                rows.append({
                    "RANK": idx + 1,
                    "IGN": d.get('ign', '-'),
                    "CLUB": d.get('club', '-'),
                    "GAME ID": d.get('game_id', '-'),
                    "TIME": f"'{d['waktu']}", 
                    "SUBMITTER": d.get('discord_name', '-'),
                    "APPROVED BY": d.get('approved_by', 'System')
                })
            df = pd.DataFrame(rows)
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                df.to_excel(writer, index=False, sheet_name='Data')
            output.seek(0)
            await i.followup.send(content="📊 Data Berhasil di-Export:", file=discord.File(fp=output, filename=f"Report_{self.event_name}.xlsx"), ephemeral=True)
        except Exception as e:
            await i.followup.send(f"❌ Error: {e}", ephemeral=True)

    @ui.button(label="👤 Hapus Player", style=discord.ButtonStyle.secondary) # Tombol Baru
    async def delete_player(self, i: discord.Interaction, b: ui.Button):
        await i.response.send_modal(DeletePlayerModal(self.event_name))

    @ui.button(label="🚨 Reset All Data", style=discord.ButtonStyle.danger)
    async def clear(self, i: discord.Interaction, b: ui.Button):
        confirm_emb = discord.Embed(
            title="⚠️ KONFIRMASI RESET",
            description=f"Apakah Anda yakin ingin menghapus **SEMUA** data leaderboard untuk **{self.event_name}**?\n\nTindakan ini tidak bisa dibatalkan!",
            color=discord.Color.orange()
        )
        await i.response.send_message(embed=confirm_emb, view=ConfirmResetView(self.event_name, i.user.name), ephemeral=True)

    @ui.button(label="⬅️ Kembali", style=discord.ButtonStyle.blurple)
    async def back(self, i: discord.Interaction, b: ui.Button):
        emb = discord.Embed(title=f"🏎️ EVENT: {self.event_name.upper()}", color=0x3498db)
        await i.response.edit_message(embed=emb, view=MainView(self.event_name))    
        
class ConfirmResetView(ui.View):
    def __init__(self, event_name, admin_name):
        super().__init__(timeout=30)
        self.event_name = event_name
        self.admin_name = admin_name

    @ui.button(label="YA, HAPUS SEMUA", style=discord.ButtonStyle.danger)
    async def confirm(self, i: discord.Interaction, b: ui.Button):
        result = col.delete_many({"event": self.event_name})
        emb = discord.Embed(
            title="🚨 LEADERBOARD RESET", 
            description=f"Semua rekaman untuk event **{self.event_name.upper()}** telah dibersihkan.",
            color=discord.Color.red(),
            timestamp=datetime.datetime.now()
        )
        emb.add_field(name="Total Terhapus", value=f"{result.deleted_count} rekaman", inline=True)
        emb.add_field(name="Eksekutor", value=f"🛡️ {self.admin_name}", inline=True)
        await i.response.edit_message(content=None, embed=emb, view=None)

    @ui.button(label="BATAL", style=discord.ButtonStyle.grey)
    async def cancel(self, i: discord.Interaction, b: ui.Button):
        await i.response.edit_message(content="✅ Operasi reset dibatalkan.", embed=None, view=None)

# ================= NEW: LANGUAGE SELECT VIEW =================
class LanguageSelectView(ui.View):
    """View awal untuk memilih bahasa sebelum masuk ke menu utama"""
    def __init__(self, event_name):
        super().__init__(timeout=60)
        self.event_name = event_name

    @ui.select(
        placeholder="Choose your language / Pilih bahasa anda...",
        options=[
            discord.SelectOption(label="Indonesia", value="id", emoji="🇮🇩"),
            discord.SelectOption(label="English", value="en", emoji="🇬🇧"),
            discord.SelectOption(label="Thailand", value="th", emoji="🇹🇭"),
            discord.SelectOption(label="Philippines", value="ph", emoji="🇵🇭"),
            discord.SelectOption(label="Malaysia", value="ms", emoji="🇲🇾"),
        ]
    )
    async def select_lang(self, i: discord.Interaction, select: ui.Select):
        lang_code = select.values[0]
        emb = discord.Embed(title=f"🏎️ EVENT: {self.event_name.upper()}", color=0x3498db)
        # Teruskan kode bahasa ke MainView
        await i.response.edit_message(embed=emb, view=MainView(self.event_name, lang_code))

class MainView(ui.View):
    def __init__(self, event_name, lang_code="en"):
        super().__init__(timeout=None)
        self.event_name = event_name
        self.lang_code = lang_code # Simpan pilihan bahasa
        
    @ui.button(label="Guide / Panduan / คู่มือ", style=discord.ButtonStyle.grey, custom_id="btn_guide_v5")
    async def guide_btn(self, i: discord.Interaction, b: ui.Button):
        emb = discord.Embed(
            title="📖 HOW TO USE / CARA PENGGUNAAN", 
            description="Please follow these steps / Silakan ikuti langkah-langkah berikut:",
            color=0x95a5a6
        )
        
        # 🇮🇩 INDONESIA
        id_msg = "1. Klik **Submit Time**\n2. Isi Nickname, ID, & Waktu (MM:SS.ms)\n3. Kirim foto bukti screenshot\n4. Tunggu verifikasi."
        # 🇬🇧 ENGLISH
        en_msg = "1. Click **Submit Time**\n2. Fill IGN, ID, & Time (MM:SS.ms)\n3. Upload screenshot evidence\n4. Wait for verification."
        # 🇹🇭 THAILAND
        th_msg = "1. คลิกที่ **Submit Time**\n2. กรอกชื่อในเกม, ID และเวลา (นาที:วินาที.มิลลิวินาที)\n3. อัปโหลดภาพถ่ายหน้าจอหลักฐาน\n4. รอการตรวจสอบ"
        # 🇵🇭 PHILIPPINES (Tagalog)
        ph_msg = "1. I-click ang **Submit Time**\n2. Ilagay ang IGN, ID, at Oras (MM:SS.ms)\n3. I-upload ang screenshot\n4. Maghintay para sa beripikasyon."
        # 🇲🇾 MALAYSIA
        ms_msg = "1. Klik **Submit Time**\n2. Isi Nickname, ID, & Masa (MM:SS.ms)\n3. Muat naik bukti tangkapan skrin\n4. Tunggu pengesahan."

        emb.add_field(name="🇮🇩 Indonesia", value=id_msg, inline=False)
        emb.add_field(name="🇬🇧 English", value=en_msg, inline=False)
        emb.add_field(name="🇹🇭 ภาษาไทย", value=th_msg, inline=False)
        emb.add_field(name="🇵🇭 Tagalog", value=ph_msg, inline=False)
        emb.add_field(name="🇲🇾 Bahasa Melayu", value=ms_msg, inline=False)
        
        await i.response.send_message(embed=emb, ephemeral=True)

    @ui.button(label="Check My PB", style=discord.ButtonStyle.blurple, custom_id="btn_pb_v5")
    async def pb_btn(self, i: discord.Interaction, b: ui.Button):
        # Cari record terbaik user di event ini
        data = col.find_one(
            {"user_id": i.user.id, "event": self.event_name, "approved": True}
        )
        
        if not data:
            return await i.response.send_message(
                "❌ Kamu belum memiliki record yang disetujui di event ini.", 
                ephemeral=True
            )
            
        # Hitung posisi rank (opsional)
        rank = col.count_documents({
            "event": self.event_name, 
            "approved": True, 
            "waktu_raw": {"$lt": data['waktu_raw']}
        }) + 1
        
        emb = discord.Embed(title=f"⏱️ PERSONAL BEST: {i.user.display_name}", color=0x9b59b6)
        emb.add_field(name="Event", value=self.event_name.upper(), inline=True)
        emb.add_field(name="Rank", value=f"#{rank}", inline=True)
        emb.add_field(name="Time", value=f"`{data['waktu']}`", inline=False)
        emb.add_field(name="IGN", value=data['ign'], inline=True)
        emb.add_field(name="Club", value=data.get('club', 'RFF'), inline=True)
        
        if "evidence_url" in data:
            emb.set_image(url=data["evidence_url"])
            
        await i.response.send_message(embed=emb, ephemeral=True)
        
    @ui.button(label="Submit Time", style=discord.ButtonStyle.green, custom_id="btn_sub_v5")
    async def submit_btn(self, i: discord.Interaction, b: ui.Button):
        # ... (Logika cooldown tetap sama seperti sebelumnya)
        user_id = i.user.id
        now = datetime.datetime.now()
        cooldown_seconds = 600
        lang = TRANSLATIONS.get(self.lang_code, TRANSLATIONS["en"])

        last_entry = col.find_one({"user_id": user_id, "event": self.event_name})
        
        if last_entry and "timestamp" in last_entry and not i.user.guild_permissions.administrator:
            last_submit = last_entry["timestamp"]
            elapsed = (now - last_submit).total_seconds()

            if elapsed < cooldown_seconds:
                rem_m = int((cooldown_seconds - elapsed) // 60)
                rem_s = int((cooldown_seconds - elapsed) % 60)
                return await i.response.send_message(
                    lang["cooldown"].format(rem_m, rem_s), 
                    ephemeral=True
                )
        
        # Mengirim modal dengan bahasa yang dipilih
        await i.response.send_modal(SubmitModal(self.event_name, self.lang_code))

    @ui.button(label="Leaderboard", style=discord.ButtonStyle.blurple, custom_id="btn_lb_v5")
    async def lb_btn(self, i, b):
        v = LeaderboardView(self.event_name)
        d, p = await v.get_stats()
        await i.response.edit_message(embed=v.create_embed(d, p), view=v)
        
    @ui.button(label="Admin Panel", style=discord.ButtonStyle.red, custom_id="btn_adm_v5")
    async def admin_btn(self, i, b):
        if not i.user.guild_permissions.administrator: 
            return await i.response.send_message("🚫 Khusus Admin!", ephemeral=True)
        await i.response.edit_message(embed=discord.Embed(title="🛠️ Admin Control Panel", color=0x2c3e50), view=AdminMenuView(self.event_name))

# ================= COMMANDS =================
@bot.command()
async def ta(ctx):
    if not events.find_one({"name": ctx.channel.name}): 
        return await ctx.send("❌ Event tidak ditemukan di channel ini.")
    
    emb = discord.Embed(
        title="🌐 SELECT LANGUAGE", 
        description="Please select your language first to continue.\nSilakan pilih bahasa terlebih dahulu.",
        color=0x3498db
    )
    # Mulai dengan pilihan bahasa
    await ctx.send(embed=emb, view=LanguageSelectView(ctx.channel.name))

@bot.command()
@commands.has_permissions(administrator=True)
async def create_event(ctx):
    events.update_one({"name": ctx.channel.name}, {"$set": {"name": ctx.channel.name}}, upsert=True)
    await ctx.send(f"✅ Channel event **#{ctx.channel.name}** sekarang aktif!")

@bot.event
async def on_ready():
    # Ambil semua channel yang terdaftar sebagai event dari database
    active_events = events.find({})
    
    for event in active_events:
        event_name = event['name']
        # Daftarkan MainView untuk setiap channel event yang aktif
        # Ini memastikan tombol tetap berfungsi setelah restart
        bot.add_view(MainView(event_name=event_name))
        
    print(f">>> OVER-XVI SYSTEM ONLINE <<<")
    print(f"Registered {events.count_documents({})} active event views.")
    
    # Menjalankan Web Server Dashboard
    if not any(thread.name == "FlaskThread" for thread in threading.enumerate()):
        threading.Thread(target=run_web, name="FlaskThread", daemon=True).start()

bot.run(TOKEN)
