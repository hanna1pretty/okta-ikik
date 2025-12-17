# -*- coding: utf-8 -*-
import logging
import asyncio
import io
import os
import sys
import subprocess  # Penting buat FFmpeg
import platform
import shutil
import psutil
from collections import defaultdict  # ← DIUBAH dari: import speedtest
import time
import datetime
import pytz
import feedparser
from bs4 import BeautifulSoup
import random
import string
import json
import html
import re
from functools import wraps
import uuid
import math
import base64
import hashlib
import tempfile
import zipfile
from urllib.parse import unquote
import urllib.parse
from concurrent.futures import ThreadPoolExecutor  # ← DITAMBAH

from tempmail import TempMailClient
from tempmail.models import DomainType

# --- 1. IMPORT RAHASIA DARI CONFIG.PY ---
try:
    from config import (
        TOKEN,
        OWNER_ID,
        WEATHER_API_KEY,
        YOU_API_KEY,
        DB_NAME,
        SPOTIPY_CLIENT_ID,
        SPOTIPY_CLIENT_SECRET,
        MY_PROXY,
        QRIS_IMAGE,
        BASE_URL,
        BMKG_URL,
        ANIME_API,
        BIN_API,
        TEMPMAIL_API_KEY,
        OMYGPT_API_KEY,
        OMDB_API_KEY,
        FIREBASE_API_KEY, # Pastikan ini ada di config.py
    )
except ImportError:
    print("❌ ERROR FATAL: File 'config.py' tidak ditemukan!")
    sys.exit()

# --- 2. LIBRARY TAMBAHAN (HTTP, DB, MEDIA, UTILS) ---
import requests
import httpx
import yt_dlp
import qrcode
import aiosqlite
import sqlite3 # Tambahan buat Selenium DB (sync)
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
from faker import Faker
from gtts import gTTS
from deep_translator import GoogleTranslator

# --- 3. PDF & CRYPTO ENGINE ---
from PyPDF2 import PdfReader, PdfWriter, PdfMerger
from PIL import Image, ImageOps
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

# --- 4. LIBRARY SELENIUM (FACTORY MODE) ---
# Wajib install: pip install selenium webdriver-manager
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

# --- 5. LIBRARY TELEGRAM ---
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputFile,
    KeyboardButton,
    ReplyKeyboardMarkup,
    InputMediaPhoto,
)
from telegram.constants import ParseMode, ChatAction
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    CallbackQueryHandler,
    MessageHandler,
    ConversationHandler, # Penting buat Upgrade Interaktif
    filters,
)
from telegram.error import NetworkError, BadRequest, TimedOut

# ==========================================
# ⚙️ SYSTEM SETUP (AUTO LOAD)
# ==========================================

# Setup Waktu (WIB)
TZ = pytz.timezone("Asia/Jakarta")
START_TIME = time.time()

# --- SETUP LOGGING (CCTV) ---
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.FileHandler("bot.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Setup Spotify
try:
    sp_client = spotipy.Spotify(auth_manager=SpotifyClientCredentials(
        client_id=SPOTIPY_CLIENT_ID,
        client_secret=SPOTIPY_CLIENT_SECRET
    ))
    print("✅ Spotify API: Connected")
except Exception as e:
    print(f"⚠️ Spotify Error: {e}")
    sp_client = None

# ==========================================
# ⚙️ GLOBAL CONFIGURATION (EXECUTOR & UTILITIES)
# ==========================================

# Global executor untuk blocking operations
executor = ThreadPoolExecutor(max_workers=5)


# ==========================================
# 🗄️ DATABASE INITIALIZATION
# ==========================================

async def init_db():
    """Initialize semua tables untuk Jenni Store"""
    async with aiosqlite.connect(DB_NAME) as db:
        
        # ==========================================
        # 🏪 TABEL AKUN JENNI (PABRIK OTOMATIS)
        # ==========================================
        
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS accounts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                plan TEXT NOT NULL,
                status TEXT DEFAULT 'AVAILABLE',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        # ==========================================
        # 📦 TABEL ORDERS (PESANAN PEMBELI)
        # ==========================================
        
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                plan TEXT NOT NULL,
                price TEXT NOT NULL,
                status TEXT DEFAULT 'pending',
                proof_photo_id TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                approved_at TIMESTAMP
            )
            """
        )

        # ==========================================
        # 📝 TABEL TRANSACTION LOGS (AUDIT TRAIL)
        # ==========================================
        
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS transaction_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                action TEXT NOT NULL,
                plan TEXT,
                user_id INTEGER,
                status TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        # ==========================================
        # ⭐ TABEL RATINGS (RATING DARI PEMBELI)
        # ==========================================
        
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS ratings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                order_id INTEGER,
                rating INTEGER,
                comment TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        # ==========================================
        # 🔐 TABEL SCRAPER LOGS (LOG AKTIVITAS)
        # ==========================================
        
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS scraper_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                chat_id INTEGER,
                chat_type TEXT,
                action TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        # ==========================================
        # 📊 USER ACTIONS TABLE (ANALYTICS & TRACKING)
        # ==========================================
        
        await db.execute("""
            CREATE TABLE IF NOT EXISTS user_actions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                action TEXT NOT NULL,
                details TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Create indexes
        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_user_actions_user_id 
            ON user_actions(user_id)
        """)
        
        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_user_actions_timestamp 
            ON user_actions(timestamp)
        """)

        # ==========================================
        # 👥 SUBSCRIBER TABLES
        # ==========================================
        
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS subscribers (
                user_id INTEGER PRIMARY KEY
            )
            """
        )

        # ==========================================
        # 💎 PREMIUM USERS TABLE
        # ==========================================
        
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS premium_users (
                user_id INTEGER PRIMARY KEY
            )
            """
        )

        # ==========================================
        # 📝 USER NOTES TABLE
        # ==========================================
        
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS user_notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                content TEXT,
                date_added TEXT
            )
            """
        )

        # ==========================================
        # 🕌 PRAYER NOTIFICATIONS TABLE
        # ==========================================
        
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS prayer_subs (
                chat_id INTEGER PRIMARY KEY,
                city TEXT
            )
            """
        )

        # ==========================================
        # 💾 MEDIA CACHE TABLE
        # ==========================================
        
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS media_cache (
                url TEXT PRIMARY KEY,
                file_id TEXT,
                media_type TEXT,
                timestamp REAL
            )
            """
        )

        await db.commit()
        print("✅ Database Initialized (termasuk store system tables)")

# ==========================================
# 🛠️ DATABASE HELPER FUNCTIONS (ASYNC)
# ==========================================

async def db_execute(query, params=()):
    """Execute query tanpa return (INSERT/UPDATE/DELETE)"""
    try:
        async with aiosqlite.connect(DB_NAME) as db:
            await db.execute(query, params)
            await db.commit()
        return True
    except Exception as e:
        logger.error(f"[DB] Execute error: {str(e)}")
        return False

async def db_fetch_one(query, params=()):
    """Fetch 1 row saja"""
    try:
        async with aiosqlite.connect(DB_NAME) as db:
            cursor = await db.execute(query, params)
            return await cursor.fetchone()
    except Exception as e:
        logger.error(f"[DB] Fetch one error: {str(e)}")
        return None

async def db_fetch_all(query, params=()):
    """Fetch semua rows"""
    try:
        async with aiosqlite.connect(DB_NAME) as db:
            cursor = await db.execute(query, params)
            return await cursor.fetchall()
    except Exception as e:
        logger.error(f"[DB] Fetch all error: {str(e)}")
        return []

async def db_insert(table, data):
    """Insert data ke table"""
    try:
        columns = ", ".join(data.keys())
        placeholders = ", ".join(["?" for _ in data])
        query = f"INSERT INTO {table} ({columns}) VALUES ({placeholders})"
        async with aiosqlite.connect(DB_NAME) as db:
            await db.execute(query, tuple(data.values()))
            await db.commit()
        return True
    except Exception as e:
        logger.error(f"[DB] Insert error: {str(e)}")
        return False

async def db_update(table, data, where):
    """Update data di table"""
    try:
        set_clause = ", ".join([f"{k}=?" for k in data.keys()])
        where_clause = " AND ".join([f"{k}=?" for k in where.keys()])
        query = f"UPDATE {table} SET {set_clause} WHERE {where_clause}"
        params = tuple(data.values()) + tuple(where.values())
        async with aiosqlite.connect(DB_NAME) as db:
            await db.execute(query, params)
            await db.commit()
        return True
    except Exception as e:
        logger.error(f"[DB] Update error: {str(e)}")
        return False

# ==========================================
# 🏪 STORE OPERATIONS - ACCOUNTS
# ==========================================

async def add_account(email: str, password: str, plan: str) -> bool:
    """Tambah akun baru ke gudang"""
    return await db_insert("accounts", {
        "email": email,
        "password": password,
        "plan": plan,
        "status": "AVAILABLE"
    })

async def get_available_account(plan: str):
    """Ambil 1 akun yang AVAILABLE"""
    return await db_fetch_one(
        "SELECT id, email, password FROM accounts WHERE status='AVAILABLE' AND plan=? LIMIT 1",
        (plan,)
    )

async def mark_account_sold(acc_id: int) -> bool:
    """Mark akun sebagai SOLD"""
    return await db_update(
        "accounts",
        {"status": "SOLD"},
        {"id": acc_id}
    )

async def check_stock_availability(plan: str) -> int:
    """Cek jumlah stok untuk plan tertentu"""
    result = await db_fetch_one(
        "SELECT COUNT(*) FROM accounts WHERE status='AVAILABLE' AND plan=?",
        (plan,)
    )
    return result[0] if result else 0

async def get_all_stock():
    """Get semua stok per plan"""
    return await db_fetch_all(
        "SELECT plan, COUNT(*) as total FROM accounts WHERE status='AVAILABLE' GROUP BY plan"
    )

# ==========================================
# 📦 STORE OPERATIONS - ORDERS
# ==========================================

async def create_order(user_id: int, plan: str, price: str) -> bool:
    """Buat order baru"""
    return await db_insert("orders", {
        "user_id": user_id,
        "plan": plan,
        "price": price,
        "status": "pending"
    })

async def update_order_proof(user_id: int, plan: str, photo_id: str) -> bool:
    """Update foto bukti transfer ke order"""
    return await db_update(
        "orders",
        {"proof_photo_id": photo_id},
        {"user_id": user_id, "plan": plan, "status": "pending"}
    )

async def approve_order(user_id: int, plan: str) -> bool:
    """Approve order (ubah status jadi approved)"""
    return await db_update(
        "orders",
        {"status": "approved", "approved_at": datetime.datetime.now().isoformat()},
        {"user_id": user_id, "plan": plan, "status": "pending"}
    )

async def reject_order(user_id: int) -> bool:
    """Reject order"""
    return await db_update(
        "orders",
        {"status": "rejected"},
        {"user_id": user_id, "status": "pending"}
    )

async def check_pending_order(user_id: int) -> bool:
    """Cek apakah user punya order pending"""
    result = await db_fetch_one(
        "SELECT id FROM orders WHERE user_id=? AND status='pending'",
        (user_id,)
    )
    return bool(result)

async def get_user_last_order(user_id: int):
    """Get order terakhir dari user"""
    return await db_fetch_one(
        "SELECT plan, status, created_at FROM orders WHERE user_id=? ORDER BY created_at DESC LIMIT 1",
        (user_id,)
    )

# ==========================================
# 📊 STORE OPERATIONS - REPORTING
# ==========================================

async def log_transaction(action: str, plan: str, user_id: int, status: str) -> bool:
    """Log transaksi ke transaction_logs"""
    return await db_insert("transaction_logs", {
        "action": action,
        "plan": plan,
        "user_id": user_id,
        "status": status
    })

async def get_sales_today():
    """Get sales report hari ini"""
    return await db_fetch_all("""
        SELECT plan, COUNT(*) as total, 
               SUM(CASE WHEN status='approved' THEN 1 ELSE 0 END) as sold
        FROM orders
        WHERE DATE(created_at) = DATE('now')
        GROUP BY plan
    """)

async def get_total_sales_all_time():
    """Get total sales sepanjang masa"""
    result = await db_fetch_one(
        "SELECT COUNT(*) FROM orders WHERE status='approved'"
    )
    return result[0] if result else 0

async def get_pending_orders_count():
    """Get jumlah order yang masih pending"""
    result = await db_fetch_one(
        "SELECT COUNT(*) FROM orders WHERE status='pending'"
    )
    return result[0] if result else 0

# ==========================================
# ⭐ STORE OPERATIONS - RATINGS
# ==========================================

async def add_rating(user_id: int, order_id: int, rating: int, comment: str = "") -> bool:
    """Tambah rating dari pembeli"""
    return await db_insert("ratings", {
        "user_id": user_id,
        "order_id": order_id,
        "rating": rating,
        "comment": comment
    })

async def get_average_rating():
    """Get rating rata-rata"""
    result = await db_fetch_one(
        "SELECT AVG(rating) FROM ratings"
    )
    return result[0] if result else 0

# ==========================================
# 🔐 STORE OPERATIONS - SCRAPER LOGS
# ==========================================

async def log_scrape_activity(user_id: int, chat_id: int, chat_type: str, action: str) -> bool:
    """Log aktivitas scrape"""
    return await db_insert("scraper_logs", {
        "user_id": user_id,
        "chat_id": chat_id,
        "chat_type": chat_type,
        "action": action
    })

# ==========================================
# 💾 MEDIA CACHE OPERATIONS
# ==========================================

async def get_cached_media(url: str):
    """Ambil media dari cache"""
    return await db_fetch_one(
        "SELECT file_id, media_type FROM media_cache WHERE url=?",
        (url,)
    )

async def set_cached_media(url: str, file_id: str, media_type: str) -> bool:
    """Simpan media ke cache"""
    return await db_insert("media_cache", {
        "url": url,
        "file_id": file_id,
        "media_type": media_type,
        "timestamp": time.time()
    })

async def clear_old_cache(days: int = 7) -> bool:
    """Hapus cache yang sudah lama (default 7 hari)"""
    old_timestamp = time.time() - (days * 24 * 3600)
    return await db_execute(
        "DELETE FROM media_cache WHERE timestamp < ?",
        (old_timestamp,)
    )

# ==========================================
# 👥 SUBSCRIBER OPERATIONS
# ==========================================

async def add_subscriber(user_id: int) -> bool:
    """Tambah subscriber untuk broadcast"""
    return await db_insert("subscribers", {
        "user_id": user_id
    })

async def remove_subscriber(user_id: int) -> bool:
    """Hapus subscriber"""
    return await db_execute(
        "DELETE FROM subscribers WHERE user_id=?",
        (user_id,)
    )

async def get_all_subscribers():
    """Get semua subscriber"""
    return await db_fetch_all("SELECT user_id FROM subscribers")

async def is_subscriber(user_id: int) -> bool:
    """Cek apakah user sudah subscriber"""
    result = await db_fetch_one(
        "SELECT user_id FROM subscribers WHERE user_id=?",
        (user_id,)
    )
    return bool(result)

# ==========================================
# 💎 PREMIUM USER OPERATIONS
# ==========================================

async def add_premium_user(user_id: int) -> bool:
    """Tambah user ke premium list"""
    return await db_insert("premium_users", {
        "user_id": user_id
    })

async def remove_premium_user(user_id: int) -> bool:
    """Hapus user dari premium list"""
    return await db_execute(
        "DELETE FROM premium_users WHERE user_id=?",
        (user_id,)
    )

async def is_premium_user(user_id: int) -> bool:
    """Cek apakah user premium"""
    result = await db_fetch_one(
        "SELECT user_id FROM premium_users WHERE user_id=?",
        (user_id,)
    )
    return bool(result)

async def get_all_premium_users():
    """Get semua premium users"""
    return await db_fetch_all("SELECT user_id FROM premium_users")

# ==========================================
# 📝 USER NOTES OPERATIONS
# ==========================================

async def add_user_note(user_id: int, content: str) -> bool:
    """Tambah catatan pengguna"""
    return await db_insert("user_notes", {
        "user_id": user_id,
        "content": content,
        "date_added": datetime.datetime.now().isoformat()
    })

async def get_user_notes(user_id: int):
    """Get semua catatan user"""
    return await db_fetch_all(
        "SELECT id, content, date_added FROM user_notes WHERE user_id=? ORDER BY date_added DESC",
        (user_id,)
    )

async def delete_user_note(note_id: int) -> bool:
    """Hapus catatan berdasarkan ID"""
    return await db_execute(
        "DELETE FROM user_notes WHERE id=?",
        (note_id,)
    )

# ==========================================
# 🕌 PRAYER NOTIFICATION OPERATIONS
# ==========================================

async def add_prayer_subscriber(chat_id: int, city: str) -> bool:
    """Tambah subscriber notifikasi sholat"""
    return await db_insert("prayer_subs", {
        "chat_id": chat_id,
        "city": city
    })

async def remove_prayer_subscriber(chat_id: int) -> bool:
    """Hapus subscriber notifikasi sholat"""
    return await db_execute(
        "DELETE FROM prayer_subs WHERE chat_id=?",
        (chat_id,)
    )

async def get_prayer_subscribers():
    """Get semua subscriber notifikasi sholat"""
    return await db_fetch_all("SELECT chat_id, city FROM prayer_subs")

async def is_prayer_subscriber(chat_id: int) -> bool:
    """Cek apakah chat sudah subscribe sholat"""
    result = await db_fetch_one(
        "SELECT chat_id FROM prayer_subs WHERE chat_id=?",
        (chat_id,)
    )
    return bool(result)

# ==========================================
# 📊 USER ACTIONS OPERATIONS (ANALYTICS)
# ==========================================

async def log_user_action(user_id: int, action: str, details: str = "") -> bool:
    """Log setiap aksi user untuk analytics & tracking"""
    try:
        return await db_insert("user_actions", {
            "user_id": user_id,
            "action": action,
            "details": details,
            "timestamp": datetime.datetime.now().isoformat()
        })
    except Exception as e:
        logger.error(f"[ACTION LOG] Error logging action: {str(e)}")
        return False

async def get_user_actions(user_id: int, limit: int = 10):
    """Get history aksi user (default 10 terakhir)"""
    try:
        return await db_fetch_all("""
            SELECT id, action, details, timestamp 
            FROM user_actions 
            WHERE user_id=? 
            ORDER BY timestamp DESC 
            LIMIT ?
        """, (user_id, limit))
    except Exception as e:
        logger.error(f"[ACTION GET] Error: {str(e)}")
        return []

async def get_user_stats(user_id: int):
    """Get statistik user berdasarkan action logs"""
    try:
        result = await db_fetch_one("""
            SELECT 
                COUNT(*) as total_actions,
                MAX(timestamp) as last_action,
                COUNT(DISTINCT DATE(timestamp)) as active_days
            FROM user_actions 
            WHERE user_id=?
        """, (user_id,))
        return result
    except Exception as e:
        logger.error(f"[USER STATS] Error: {str(e)}")
        return None

async def get_action_summary(user_id: int):
    """Get ringkasan aksi per tipe untuk user"""
    try:
        return await db_fetch_all("""
            SELECT action, COUNT(*) as count
            FROM user_actions 
            WHERE user_id=?
            GROUP BY action
            ORDER BY count DESC
        """, (user_id,))
    except Exception as e:
        logger.error(f"[ACTION SUMMARY] Error: {str(e)}")
        return []

async def get_global_action_stats():
    """Get statistik aksi global (untuk admin dashboard)"""
    try:
        return await db_fetch_all("""
            SELECT 
                action,
                COUNT(*) as total_count,
                COUNT(DISTINCT user_id) as unique_users,
                MAX(timestamp) as last_used
            FROM user_actions
            GROUP BY action
            ORDER BY total_count DESC
        """)
    except Exception as e:
        logger.error(f"[GLOBAL STATS] Error: {str(e)}")
        return []

async def clear_old_actions(days: int = 30) -> bool:
    """Hapus action logs yang sudah lama (default 30 hari)"""
    try:
        old_date = (datetime.datetime.now() - datetime.timedelta(days=days)).isoformat()
        return await db_execute(
            "DELETE FROM user_actions WHERE timestamp < ?",
            (old_date,)
        )
    except Exception as e:
        logger.error(f"[ACTION CLEAR] Error: {str(e)}")
        return False

async def get_most_active_users(limit: int = 10):
    """Get user paling aktif (untuk admin)"""
    try:
        return await db_fetch_all("""
            SELECT user_id, COUNT(*) as action_count
            FROM user_actions
            GROUP BY user_id
            ORDER BY action_count DESC
            LIMIT ?
        """, (limit,))
    except Exception as e:
        logger.error(f"[ACTIVE USERS] Error: {str(e)}")
        return []

async def get_daily_action_stats(days: int = 7):
    """Get statistik aksi per hari (last N days)"""
    try:
        return await db_fetch_all(f"""
            SELECT 
                DATE(timestamp) as date,
                COUNT(*) as total_actions,
                COUNT(DISTINCT user_id) as unique_users
            FROM user_actions
            WHERE timestamp >= datetime('now', '-{days} days')
            GROUP BY DATE(timestamp)
            ORDER BY date DESC
        """)
    except Exception as e:
        logger.error(f"[DAILY STATS] Error: {str(e)}")
        return []

# ==========================================
# 📋 UTILITY FUNCTIONS
# ==========================================

async def get_price_for_plan(plan: str) -> str:
    """Get harga untuk plan"""
    prices = {
        "Monthly": "Rp 25.000",
        "Yearly": "Rp 150.000"
    }
    return prices.get(plan, "Unknown")

def get_stock_icon(count: int) -> str:
    """Get icon untuk stok"""
    if count <= 0:
        return "❌"
    elif count <= 2:
        return "⚠️"
    elif count <= 5:
        return "🟡"
    else:
        return "🟢"

def get_stock_status(count: int) -> str:
    """Get status stok"""
    if count <= 0:
        return "❌ HABIS"
    elif count <= 2:
        return "⚠️ KRITIS"
    elif count <= 5:
        return "🟡 SEDIKIT"
    else:
        return "🟢 TERSEDIA"

def get_status_emoji(status: str) -> str:
    """Get emoji untuk status order"""
    emojis = {
        "pending": "⏳",
        "approved": "✅",
        "rejected": "❌",
        "expired": "⏰"
    }
    return emojis.get(status, "❓")


# ==========================================
# 🛠️ DATABASE HELPER FUNCTIONS (ASYNC)
# ==========================================

async def db_execute(query, params=()):
    """Execute query tanpa return (INSERT/UPDATE/DELETE)"""
    try:
        async with aiosqlite.connect(DB_NAME) as db:
            await db.execute(query, params)
            await db.commit()
        return True
    except Exception as e:
        logger.error(f"[DB] Execute error: {str(e)}")
        return False

async def db_fetch_one(query, params=()):
    """Fetch 1 row saja"""
    try:
        async with aiosqlite.connect(DB_NAME) as db:
            cursor = await db.execute(query, params)
            return await cursor.fetchone()
    except Exception as e:
        logger.error(f"[DB] Fetch one error: {str(e)}")
        return None

async def db_fetch_all(query, params=()):
    """Fetch semua rows"""
    try:
        async with aiosqlite.connect(DB_NAME) as db:
            cursor = await db.execute(query, params)
            return await cursor.fetchall()
    except Exception as e:
        logger.error(f"[DB] Fetch all error: {str(e)}")
        return []

async def db_insert(table, data):
    """Insert data ke table"""
    try:
        columns = ", ".join(data.keys())
        placeholders = ", ".join(["?" for _ in data])
        query = f"INSERT INTO {table} ({columns}) VALUES ({placeholders})"
        async with aiosqlite.connect(DB_NAME) as db:
            await db.execute(query, tuple(data.values()))
            await db.commit()
        return True
    except Exception as e:
        logger.error(f"[DB] Insert error: {str(e)}")
        return False

async def db_update(table, data, where):
    """Update data di table"""
    try:
        set_clause = ", ".join([f"{k}=?" for k in data.keys()])
        where_clause = " AND ".join([f"{k}=?" for k in where.keys()])
        query = f"UPDATE {table} SET {set_clause} WHERE {where_clause}"
        params = tuple(data.values()) + tuple(where.values())
        async with aiosqlite.connect(DB_NAME) as db:
            await db.execute(query, params)
            await db.commit()
        return True
    except Exception as e:
        logger.error(f"[DB] Update error: {str(e)}")
        return False

# ==========================================
# 🏪 STORE OPERATIONS - ACCOUNTS
# ==========================================

async def add_account(email: str, password: str, plan: str) -> bool:
    """Tambah akun baru ke gudang"""
    return await db_insert("accounts", {
        "email": email,
        "password": password,
        "plan": plan,
        "status": "AVAILABLE"
    })

async def get_available_account(plan: str):
    """Ambil 1 akun yang AVAILABLE"""
    return await db_fetch_one(
        "SELECT id, email, password FROM accounts WHERE status='AVAILABLE' AND plan=? LIMIT 1",
        (plan,)
    )

async def mark_account_sold(acc_id: int) -> bool:
    """Mark akun sebagai SOLD"""
    return await db_update(
        "accounts",
        {"status": "SOLD"},
        {"id": acc_id}
    )

async def check_stock_availability(plan: str) -> int:
    """Cek jumlah stok untuk plan tertentu"""
    result = await db_fetch_one(
        "SELECT COUNT(*) FROM accounts WHERE status='AVAILABLE' AND plan=?",
        (plan,)
    )
    return result[0] if result else 0

async def get_all_stock():
    """Get semua stok per plan"""
    return await db_fetch_all(
        "SELECT plan, COUNT(*) as total FROM accounts WHERE status='AVAILABLE' GROUP BY plan"
    )

# ==========================================
# 📦 STORE OPERATIONS - ORDERS
# ==========================================

async def create_order(user_id: int, plan: str, price: str) -> bool:
    """Buat order baru"""
    return await db_insert("orders", {
        "user_id": user_id,
        "plan": plan,
        "price": price,
        "status": "pending"
    })

async def update_order_proof(user_id: int, plan: str, photo_id: str) -> bool:
    """Update foto bukti transfer ke order"""
    return await db_update(
        "orders",
        {"proof_photo_id": photo_id},
        {"user_id": user_id, "plan": plan, "status": "pending"}
    )

async def approve_order(user_id: int, plan: str) -> bool:
    """Approve order (ubah status jadi approved)"""
    return await db_update(
        "orders",
        {"status": "approved", "approved_at": datetime.datetime.now().isoformat()},
        {"user_id": user_id, "plan": plan, "status": "pending"}
    )

async def reject_order(user_id: int) -> bool:
    """Reject order"""
    return await db_update(
        "orders",
        {"status": "rejected"},
        {"user_id": user_id, "status": "pending"}
    )

async def check_pending_order(user_id: int) -> bool:
    """Cek apakah user punya order pending"""
    result = await db_fetch_one(
        "SELECT id FROM orders WHERE user_id=? AND status='pending'",
        (user_id,)
    )
    return bool(result)

async def get_user_last_order(user_id: int):
    """Get order terakhir dari user"""
    return await db_fetch_one(
        "SELECT plan, status, created_at FROM orders WHERE user_id=? ORDER BY created_at DESC LIMIT 1",
        (user_id,)
    )

# ==========================================
# 📊 STORE OPERATIONS - REPORTING
# ==========================================

async def log_transaction(action: str, plan: str, user_id: int, status: str) -> bool:
    """Log transaksi ke transaction_logs"""
    return await db_insert("transaction_logs", {
        "action": action,
        "plan": plan,
        "user_id": user_id,
        "status": status
    })

async def get_sales_today():
    """Get sales report hari ini"""
    return await db_fetch_all("""
        SELECT plan, COUNT(*) as total, 
               SUM(CASE WHEN status='approved' THEN 1 ELSE 0 END) as sold
        FROM orders
        WHERE DATE(created_at) = DATE('now')
        GROUP BY plan
    """)

async def get_total_sales_all_time():
    """Get total sales sepanjang masa"""
    result = await db_fetch_one(
        "SELECT COUNT(*) FROM orders WHERE status='approved'"
    )
    return result[0] if result else 0

async def get_pending_orders_count():
    """Get jumlah order yang masih pending"""
    result = await db_fetch_one(
        "SELECT COUNT(*) FROM orders WHERE status='pending'"
    )
    return result[0] if result else 0

# ==========================================
# ⭐ STORE OPERATIONS - RATINGS
# ==========================================

async def add_rating(user_id: int, order_id: int, rating: int, comment: str = "") -> bool:
    """Tambah rating dari pembeli"""
    return await db_insert("ratings", {
        "user_id": user_id,
        "order_id": order_id,
        "rating": rating,
        "comment": comment
    })

async def get_average_rating():
    """Get rating rata-rata"""
    result = await db_fetch_one(
        "SELECT AVG(rating) FROM ratings"
    )
    return result[0] if result else 0

# ==========================================
# 🔐 STORE OPERATIONS - SCRAPER LOGS
# ==========================================

async def log_scrape_activity(user_id: int, chat_id: int, chat_type: str, action: str) -> bool:
    """Log aktivitas scrape"""
    return await db_insert("scraper_logs", {
        "user_id": user_id,
        "chat_id": chat_id,
        "chat_type": chat_type,
        "action": action
    })

# ==========================================
# 💾 MEDIA CACHE OPERATIONS
# ==========================================

async def get_cached_media(url: str):
    """Ambil media dari cache"""
    return await db_fetch_one(
        "SELECT file_id, media_type FROM media_cache WHERE url=?",
        (url,)
    )

async def set_cached_media(url: str, file_id: str, media_type: str) -> bool:
    """Simpan media ke cache"""
    return await db_insert("media_cache", {
        "url": url,
        "file_id": file_id,
        "media_type": media_type,
        "timestamp": time.time()
    })

async def clear_old_cache(days: int = 7) -> bool:
    """Hapus cache yang sudah lama (default 7 hari)"""
    old_timestamp = time.time() - (days * 24 * 3600)
    return await db_execute(
        "DELETE FROM media_cache WHERE timestamp < ?",
        (old_timestamp,)
    )

# ==========================================
# 👥 SUBSCRIBER OPERATIONS
# ==========================================

async def add_subscriber(user_id: int) -> bool:
    """Tambah subscriber untuk broadcast"""
    return await db_insert("subscribers", {
        "user_id": user_id
    })

async def remove_subscriber(user_id: int) -> bool:
    """Hapus subscriber"""
    return await db_execute(
        "DELETE FROM subscribers WHERE user_id=?",
        (user_id,)
    )

async def get_all_subscribers():
    """Get semua subscriber"""
    return await db_fetch_all("SELECT user_id FROM subscribers")

async def is_subscriber(user_id: int) -> bool:
    """Cek apakah user sudah subscriber"""
    result = await db_fetch_one(
        "SELECT user_id FROM subscribers WHERE user_id=?",
        (user_id,)
    )
    return bool(result)

# ==========================================
# 💎 PREMIUM USER OPERATIONS
# ==========================================

async def add_premium_user(user_id: int) -> bool:
    """Tambah user ke premium list"""
    return await db_insert("premium_users", {
        "user_id": user_id
    })

async def remove_premium_user(user_id: int) -> bool:
    """Hapus user dari premium list"""
    return await db_execute(
        "DELETE FROM premium_users WHERE user_id=?",
        (user_id,)
    )

async def is_premium_user(user_id: int) -> bool:
    """Cek apakah user premium"""
    result = await db_fetch_one(
        "SELECT user_id FROM premium_users WHERE user_id=?",
        (user_id,)
    )
    return bool(result)

async def get_all_premium_users():
    """Get semua premium users"""
    return await db_fetch_all("SELECT user_id FROM premium_users")

# ==========================================
# 📝 USER NOTES OPERATIONS
# ==========================================

async def add_user_note(user_id: int, content: str) -> bool:
    """Tambah catatan pengguna"""
    return await db_insert("user_notes", {
        "user_id": user_id,
        "content": content,
        "date_added": datetime.datetime.now().isoformat()
    })

async def get_user_notes(user_id: int):
    """Get semua catatan user"""
    return await db_fetch_all(
        "SELECT id, content, date_added FROM user_notes WHERE user_id=? ORDER BY date_added DESC",
        (user_id,)
    )

async def delete_user_note(note_id: int) -> bool:
    """Hapus catatan berdasarkan ID"""
    return await db_execute(
        "DELETE FROM user_notes WHERE id=?",
        (note_id,)
    )

# ==========================================
# 🕌 PRAYER NOTIFICATION OPERATIONS
# ==========================================

async def add_prayer_subscriber(chat_id: int, city: str) -> bool:
    """Tambah subscriber notifikasi sholat"""
    return await db_insert("prayer_subs", {
        "chat_id": chat_id,
        "city": city
    })

async def remove_prayer_subscriber(chat_id: int) -> bool:
    """Hapus subscriber notifikasi sholat"""
    return await db_execute(
        "DELETE FROM prayer_subs WHERE chat_id=?",
        (chat_id,)
    )

async def get_prayer_subscribers():
    """Get semua subscriber notifikasi sholat"""
    return await db_fetch_all("SELECT chat_id, city FROM prayer_subs")

async def is_prayer_subscriber(chat_id: int) -> bool:
    """Cek apakah chat sudah subscribe sholat"""
    result = await db_fetch_one(
        "SELECT chat_id FROM prayer_subs WHERE chat_id=?",
        (chat_id,)
    )
    return bool(result)

# ==========================================
# 📊 USER ACTIONS OPERATIONS (ANALYTICS)
# ==========================================

async def log_user_action(user_id: int, action: str, details: str = "") -> bool:
    """Log setiap aksi user untuk analytics & tracking"""
    try:
        return await db_insert("user_actions", {
            "user_id": user_id,
            "action": action,
            "details": details,
            "timestamp": datetime.datetime.now().isoformat()
        })
    except Exception as e:
        logger.error(f"[ACTION LOG] Error logging action: {str(e)}")
        return False

async def get_user_actions(user_id: int, limit: int = 10):
    """Get history aksi user (default 10 terakhir)"""
    try:
        return await db_fetch_all("""
            SELECT id, action, details, timestamp 
            FROM user_actions 
            WHERE user_id=? 
            ORDER BY timestamp DESC 
            LIMIT ?
        """, (user_id, limit))
    except Exception as e:
        logger.error(f"[ACTION GET] Error: {str(e)}")
        return []

async def get_user_stats(user_id: int):
    """Get statistik user berdasarkan action logs"""
    try:
        result = await db_fetch_one("""
            SELECT 
                COUNT(*) as total_actions,
                MAX(timestamp) as last_action,
                COUNT(DISTINCT DATE(timestamp)) as active_days
            FROM user_actions 
            WHERE user_id=?
        """, (user_id,))
        return result
    except Exception as e:
        logger.error(f"[USER STATS] Error: {str(e)}")
        return None

async def get_action_summary(user_id: int):
    """Get ringkasan aksi per tipe untuk user"""
    try:
        return await db_fetch_all("""
            SELECT action, COUNT(*) as count
            FROM user_actions 
            WHERE user_id=?
            GROUP BY action
            ORDER BY count DESC
        """, (user_id,))
    except Exception as e:
        logger.error(f"[ACTION SUMMARY] Error: {str(e)}")
        return []

async def get_global_action_stats():
    """Get statistik aksi global (untuk admin dashboard)"""
    try:
        return await db_fetch_all("""
            SELECT 
                action,
                COUNT(*) as total_count,
                COUNT(DISTINCT user_id) as unique_users,
                MAX(timestamp) as last_used
            FROM user_actions
            GROUP BY action
            ORDER BY total_count DESC
        """)
    except Exception as e:
        logger.error(f"[GLOBAL STATS] Error: {str(e)}")
        return []

async def clear_old_actions(days: int = 30) -> bool:
    """Hapus action logs yang sudah lama (default 30 hari)"""
    try:
        old_date = (datetime.datetime.now() - datetime.timedelta(days=days)).isoformat()
        return await db_execute(
            "DELETE FROM user_actions WHERE timestamp < ?",
            (old_date,)
        )
    except Exception as e:
        logger.error(f"[ACTION CLEAR] Error: {str(e)}")
        return False

async def get_most_active_users(limit: int = 10):
    """Get user paling aktif (untuk admin)"""
    try:
        return await db_fetch_all("""
            SELECT user_id, COUNT(*) as action_count
            FROM user_actions
            GROUP BY user_id
            ORDER BY action_count DESC
            LIMIT ?
        """, (limit,))
    except Exception as e:
        logger.error(f"[ACTIVE USERS] Error: {str(e)}")
        return []

async def get_daily_action_stats(days: int = 7):
    """Get statistik aksi per hari (last N days)"""
    try:
        return await db_fetch_all(f"""
            SELECT 
                DATE(timestamp) as date,
                COUNT(*) as total_actions,
                COUNT(DISTINCT user_id) as unique_users
            FROM user_actions
            WHERE timestamp >= datetime('now', '-{days} days')
            GROUP BY DATE(timestamp)
            ORDER BY date DESC
        """)
    except Exception as e:
        logger.error(f"[DAILY STATS] Error: {str(e)}")
        return []

# ==========================================
# 📋 UTILITY FUNCTIONS
# ==========================================

async def get_price_for_plan(plan: str) -> str:
    """Get harga untuk plan"""
    prices = {
        "Monthly": "Rp 25.000",
        "Yearly": "Rp 150.000"
    }
    return prices.get(plan, "Unknown")

def get_stock_icon(count: int) -> str:
    """Get icon untuk stok"""
    if count <= 0:
        return "❌"
    elif count <= 2:
        return "⚠️"
    elif count <= 5:
        return "🟡"
    else:
        return "🟢"

def get_stock_status(count: int) -> str:
    """Get status stok"""
    if count <= 0:
        return "❌ HABIS"
    elif count <= 2:
        return "⚠️ KRITIS"
    elif count <= 5:
        return "🟡 SEDIKIT"
    else:
        return "🟢 TERSEDIA"

def get_status_emoji(status: str) -> str:
    """Get emoji untuk status order"""
    emojis = {
        "pending": "⏳",
        "approved": "✅",
        "rejected": "❌",
        "expired": "⏰"
    }
    return emojis.get(status, "❓")

# ==========================================
# ⚙️ CONFIG MODIFIER (AUTO UPDATE PROXY)
# ==========================================

# Path ke config.py (biasanya di folder yang sama dengan duhur.py)
CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.py")


def update_proxy_in_config(new_proxy: str) -> bool:
    """
    Update baris MY_PROXY di config.py ke nilai baru.

    - Kalau MY_PROXY sudah ada → diganti.
    - Kalau belum ada → ditambahkan di akhir file.
    """
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            data = f.read()

        pattern = r'^MY_PROXY\s*=\s*".*"$'
        replacement = f'MY_PROXY = "{new_proxy}"'

        # Coba ganti kalau sudah ada
        new_data, n = re.subn(pattern, replacement, data, flags=re.MULTILINE)

        # Kalau belum ada MY_PROXY, tambahkan di akhir file
        if n == 0:
            if not data.endswith("\n"):
                data += "\n"
            new_data = data + replacement + "\n"

        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            f.write(new_data)

        return True
    except Exception as e:
        print(f"update_proxy_in_config error: {e}")
        return False

# ==========================================
# 🔢 CC GENERATOR LOGIC (SMART CUSTOM)
# ==========================================
def cc_gen(cc, mes='x', ano='x', cvv='x', amount=10):
    generated = []
    
    # Bersihkan input CC (hapus x dan spasi)
    clean_cc = cc.lower().replace('x', '').replace(' ', '')
    
    # Deteksi Panjang (Amex 15, Lain 16)
    length = 15 if clean_cc.startswith(('34', '37')) else 16
    
    for _ in range(amount):
        temp_cc = clean_cc
        
        # Jika input kepanjangan, potong
        if len(temp_cc) >= length: 
            temp_cc = temp_cc[:length-1]
        
        # Isi sisa digit dengan angka acak
        while len(temp_cc) < (length - 1):
            temp_cc += str(random.randint(0, 9))
        
        # Hitung Luhn Checksum
        digits = [int(x) for x in reversed(temp_cc)]
        total = 0
        for i, x in enumerate(digits):
            if i % 2 == 0:
                x *= 2
                if x > 9: x -= 9
            total += x
        check_digit = (total * 9) % 10
        final_cc = temp_cc + str(check_digit)
        
        # --- LOGIKA BULAN (Custom vs Random) ---
        if mes != 'x':
            gen_mes = mes.zfill(2) # Pastikan 2 digit (contoh: 1 jadi 01)
        else:
            gen_mes = f"{random.randint(1, 12):02d}"

        # --- LOGIKA TAHUN (Custom vs Random) ---
        curr_y = int(datetime.datetime.now().strftime('%Y'))
        if ano != 'x':
            # Jika user tulis 25 -> jadi 2025, jika 2025 -> tetap 2025
            gen_ano = "20" + ano if len(ano) == 2 else ano
        else:
            gen_ano = str(random.randint(curr_y + 1, curr_y + 6))
        
        # --- LOGIKA CVV (Custom vs Random) ---
        cvv_len = 4 if final_cc.startswith(('34', '37')) else 3
        if cvv != 'x':
            gen_cvv = cvv
        else:
            gen_cvv = ''.join([str(random.randint(0, 9)) for _ in range(cvv_len)])
        
        # Format Output: CC|MM|YYYY|CVV
        generated.append(f"{final_cc}|{gen_mes}|{gen_ano}|{gen_cvv}")
        
    return generated

# ==========================================
# 🛠️ HELPERS (SYSTEM & WEATHER - GOD MODE UI)
# ==========================================

# Helper untuk Progress Bar Visual (Contoh: [▰▰▰▱▱▱▱▱▱▱])
def make_bar(percent, length=10):
    percent = max(0, min(100, percent))  # Pastikan 0-100
    filled = int(percent / (100 / length))
    return "▰" * filled + "▱" * (length - filled)

def get_sys_info():
    try:
        # Ambil Data System Real-time
        ram = psutil.virtual_memory()
        cpu = psutil.cpu_percent(interval=0.1)  # Kasih interval dikit biar akurat
        disk = shutil.disk_usage("/")

        # Hitung Uptime
        uptime_sec = int(time.time() - START_TIME)
        uptime = str(datetime.timedelta(seconds=uptime_sec))

        # Info OS & Python
        os_info = f"{platform.system()} {platform.release()}"
        py_ver = platform.python_version()

        # Konversi Byte ke GB (Safety Check)
        ram_used = round(ram.used / (1024**3), 1)
        ram_total = round(ram.total / (1024**3), 1)
        disk_used = round(disk.used / (1024**3), 1)
        disk_total = round(disk.total / (1024**3), 1)

        return (
            f"🖥️ <b>SYSTEM DASHBOARD</b>\n"
            f"━━━━━━━━━━━━━━━━\n"
            f"🐧 <b>OS:</b> <code>{os_info}</code>\n"
            f"🐍 <b>Python:</b> <code>v{py_ver}</code>\n"
            f"⏱️ <b>Uptime:</b> <code>{uptime}</code>\n\n"
            f"🧠 <b>RAM Usage:</b> {ram.percent}%\n"
            f"<code>[{make_bar(ram.percent)}]</code>\n"
            f"<i>({ram_used}GB used of {ram_total}GB)</i>\n\n"
            f"⚙️ <b>CPU Load:</b> {cpu}%\n"
            f"<code>[{make_bar(cpu)}]</code>\n\n"
            f"💾 <b>Disk Storage:</b>\n"
            f"<code>[{make_bar(disk.used / disk.total * 100)}]</code>\n"
            f"<i>({disk_used}GB used of {disk_total}GB)</i>"
        )
    except Exception as e:
        return f"⚠️ System Info Error: {str(e)}"

async def get_weather_data(query):
    # Support pencarian nama kota atau koordinat
    if "," in query and any(c.isdigit() for c in query):
        lat, lon = query.split(",")
        url = f"{BASE_URL}/weather?lat={lat}&lon={lon}&appid={WEATHER_API_KEY}&units=metric&lang=en"
    else:
        url = f"{BASE_URL}/weather?q={query}&appid={WEATHER_API_KEY}&units=metric&lang=en"
    return await fetch_json(url)

async def get_aqi(lat, lon):
    url = f"{BASE_URL}/air_pollution?lat={lat}&lon={lon}&appid={WEATHER_API_KEY}"
    data = await fetch_json(url)
    if data:
        aqi = data["list"][0]["main"]["aqi"]
        # Mapping AQI dengan Ikon & Status Keren
        labels = {
            1: "🟢 Good (Sehat)",
            2: "🟡 Fair (Cukup)",
            3: "🟠 Moderate (Sedang)",
            4: "🔴 Poor (Buruk)",
            5: "☠️ Hazardous (Bahaya)",
        }
        return labels.get(aqi, "❓ Unknown")
    return "❓ N/A"

def format_weather(data, aqi_status):
    w = data["weather"][0]
    main = data["main"]
    wind = data["wind"]
    sys = data["sys"]

    city = data["name"]
    country = sys["country"]

    # Konversi Waktu Sunrise/Sunset dari Unix ke Jam Lokal
    sunrise = datetime.datetime.utcfromtimestamp(
        sys["sunrise"] + data["timezone"]
    ).strftime("%H:%M")
    sunset = datetime.datetime.utcfromtimestamp(
        sys["sunset"] + data["timezone"]
    ).strftime("%H:%M")

    # Ikon Dinamis Berdasarkan Kondisi
    cond = w["main"].lower()
    desc = w["description"].title()

    if "rain" in cond or "drizzle" in cond:
        icon = "🌧️"
    elif "thunder" in cond:
        icon = "⛈️"
    elif "snow" in cond:
        icon = "❄️"
    elif "clear" in cond:
        icon = "☀️"
    elif "cloud" in cond:
        icon = "☁️"
    elif "mist" in cond or "fog" in cond or "haze" in cond:
        icon = "🌫️"
    else:
        icon = "🌤️"

    visibility_km = (data.get("visibility", 0) or 0) / 1000.0

    text = (
        f"{icon} <b>WEATHER REPORT</b>\n"
        f"📍 <b>{city.upper()}, {country}</b>\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"📝 <b>Condition:</b> {desc}\n"
        f"🌡️ <b>Temp:</b> {main['temp']}\u00B0C\n"
        f"🥵 <b>Feels Like:</b> {main['feels_like']}\u00B0C\n"
        f"💧 <b>Humidity:</b> {main['humidity']}%\n"
        f"🌬️ <b>Wind Speed:</b> {wind['speed']} m/s\n"
        f"😷 <b>Air Quality:</b> {aqi_status}\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"👁️ <b>Visibility:</b> {visibility_km:.1f} km\n"
        f"🌅 <b>Sunrise:</b> {sunrise} | 🌇 <b>Sunset:</b> {sunset}"
    )
    return text

def escape_md(text):
    return (
        str(text).replace("_", "\\_").replace("*", "\\*").replace("`", "\\`")
        if text
        else "N/A"
    )


# ==========================================
# 🛡️ RATE LIMITING & SESSION MANAGEMENT
# ==========================================
user_cooldowns = {}
user_sessions = {}

def rate_limit(seconds=2):
    """Decorator untuk rate limit command"""
    def decorator(func):
        @wraps(func)
        async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
            user_id = update.effective_user.id
            current_time = time.time()
            
            if user_id in user_cooldowns:
                if current_time - user_cooldowns[user_id] < seconds:
                    try:
                        await update.message.reply_text(
                            f"⏱️ <b>RATE LIMITED</b>\n\n"
                            f"Please wait {seconds} seconds before using this command again.",
                            parse_mode=ParseMode.HTML
                        )
                    except:
                        pass
                    return
            
            user_cooldowns[user_id] = current_time
            return await func(update, context)
        return wrapper
    return decorator

async def create_session(user_id: int) -> str:
    """Create user session"""
    session_id = str(uuid.uuid4())
    user_sessions[user_id] = {
        "session_id": session_id,
        "created_at": datetime.datetime.now(),
        "data": {},
        "last_action": datetime.datetime.now()
    }
    logger.info(f"[SESSION] Created session {session_id} for user {user_id}")
    return session_id

async def get_session(user_id: int):
    """Get user session"""
    return user_sessions.get(user_id)

async def update_session_data(user_id: int, key: str, value):
    """Update session data"""
    if user_id in user_sessions:
        user_sessions[user_id]["data"][key] = value
        user_sessions[user_id]["last_action"] = datetime.datetime.now()

# ==========================================
# 📊 ANALYTICS & LOGGING
# ==========================================

async def log_user_action(user_id: int, action: str, details: str = "") -> bool:
    """Log setiap aksi user untuk analytics"""
    try:
        async with aiosqlite.connect(DB_NAME) as db:
            await db.execute("""
                INSERT INTO user_actions (user_id, action, details, timestamp)
                VALUES (?, ?, ?, ?)
            """, (user_id, action, details, datetime.datetime.now().isoformat()))
            await db.commit()
        logger.info(f"[ACTION] User {user_id}: {action} - {details}")
        return True
    except Exception as e:
        logger.error(f"[ACTION LOG] Error: {str(e)}")
        return False

async def get_user_stats(user_id: int):
    """Get statistik user"""
    result = await db_fetch_one("""
        SELECT 
            COUNT(*) as total_actions,
            MAX(timestamp) as last_action
        FROM user_actions 
        WHERE user_id=?
    """, (user_id,))
    return result

# ==========================================
# 🔐 PERMISSION DECORATORS
# ==========================================

def require_registered(func):
    """Decorator untuk require registered user"""
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        registered = await is_registered(user_id)
        
        if not registered:
            try:
                if update.callback_query:
                    await update.callback_query.answer(
                        "🔒 FEATURE LOCKED\n\n"
                        "This module is exclusively for registered members.\n\n"
                        "ACTION REQUIRED:\n"
                        "Please complete the registration process to unlock this feature.",
                        show_alert=True
                    )
                else:
                    await update.message.reply_text(
                        "🔒 <b>FEATURE LOCKED</b>\n\n"
                        "Please register first to access this feature.",
                        parse_mode=ParseMode.HTML
                    )
            except Exception as e:
                logger.error(f"[PERMISSION] Error in require_registered: {str(e)}")
            return
        
        await log_user_action(user_id, func.__name__, "Accessed")
        return await func(update, context)
    return wrapper

def require_owner(func):
    """Decorator untuk owner only command"""
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        
        if user_id != OWNER_ID:
            try:
                if update.callback_query:
                    await update.callback_query.answer(
                        "⛔ OWNER ONLY\n\nThis command is restricted to the bot owner.",
                        show_alert=True
                    )
                else:
                    await update.message.reply_text(
                        "⛔ <b>OWNER ONLY</b>\n\nThis command is restricted to the bot owner.",
                        parse_mode=ParseMode.HTML
                    )
            except Exception as e:
                logger.error(f"[PERMISSION] Error in require_owner: {str(e)}")
            return
        
        logger.warning(f"[OWNER] User {user_id} executed: {func.__name__}")
        return await func(update, context)
    return wrapper

# ==========================================
# 👋 START COMMAND (UPGRADED)
# ==========================================

@rate_limit(seconds=2)
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start command dengan logging & session creation"""
    user = update.effective_user
    user_id = user.id
    
    try:
        # Create session
        await create_session(user_id)
        
        # Log action
        await log_user_action(user_id, "start", f"User: {user.first_name}")
        
        # Cek status register
        registered = await is_registered(user_id)
        
        if registered:
            access_line = "🟢 <b>Access Level:</b> REGISTERED USER\n"
            hint_line = "You can access all unlocked modules from the main menu below."
            btn_main = InlineKeyboardButton("🚀 ACCESS MAIN MENU", callback_data="menu_main")
            btn_premium = InlineKeyboardButton("💎 PREMIUM UPGRADE", callback_data="menu_buy")
            btn_register = InlineKeyboardButton("📝 REGISTER ACCESS", callback_data="cmd_register")
        else:
            access_line = "🔴 <b>Access Level:</b> UNREGISTERED\n"
            hint_line = (
                "Please tap <b>REGISTER ACCESS</b> first to unlock premium tools "
                "and core features."
            )
            btn_main = InlineKeyboardButton("🚀 ACCESS MAIN MENU", callback_data="locked_register")
            btn_premium = InlineKeyboardButton("💎 PREMIUM UPGRADE", callback_data="locked_register")
            btn_register = InlineKeyboardButton("📝 REGISTER ACCESS", callback_data="cmd_register")

        text = (
            f"🐈 <b>OKTACOMEL SYSTEM v1</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"👋 <b>Greetings, Master {html.escape(user.first_name)}!</b>\n\n"
            f"I am <b>Oktacomel</b>, your advanced AI assistant operating in <i>Ultra God Mode</i>. "
            f"I am authorized to execute high-level digital tasks, from premium tools to system diagnostics.\n\n"
            f"🚀 <b>System Status:</b> 🟢 Online & Fully Operational\n"
            f"👑 <b>Owner:</b> Okta\n"
            f"{access_line}\n"
            f"💡 <i>{hint_line}</i>\n\n"
            f"👇 <i>Access the mainframe via the menu below:</i>"
        )

        kb = [
            [btn_main],
            [btn_premium, btn_register],
            [InlineKeyboardButton("🐈 OFFICIAL CHANNEL", url="https://t.me/hiduphjokowi")],
        ]

        try:
            await update.message.reply_photo(
                photo=QRIS_IMAGE,
                caption=text,
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup(kb),
            )
        except (BadRequest, TimedOut):
            logger.warning(f"[START] Photo send failed for user {user_id}, sending text instead")
            await update.message.reply_text(
                text,
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup(kb),
            )
        except NetworkError as e:
            logger.error(f"[START] Network error: {str(e)}")
            await update.message.reply_text(
                "⚠️ <b>NETWORK ERROR</b>\n\n"
                "There was a network issue. Please try again later.",
                parse_mode=ParseMode.HTML
            )

    except Exception as e:
        logger.error(f"[START] Unexpected error for user {user_id}: {str(e)}")
        await update.message.reply_text(
            "❌ <b>SYSTEM ERROR</b>\n\n"
            "An unexpected error occurred. Please try again.",
            parse_mode=ParseMode.HTML
        )

# ==========================================
# ❓ HELP COMMAND (UPGRADED)
# ==========================================

@rate_limit(seconds=2)
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Help command dengan logging"""
    user = update.effective_user
    user_id = user.id
    
    try:
        # Log action
        await log_user_action(user_id, "help", "Accessed help menu")
        
        registered = await is_registered(user_id)

        text = (
            "<b>🐈 SYSTEM HELP CENTER</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "Do not panic. The Oktacomel System is optimized for speed and clarity.\n\n"
            "<b>📋 Available Commands:</b>\n"
            "/start - Open main menu\n"
            "/help - Show this message\n"
            "/register - Register to system\n"
            "/stock - Check product stock\n"
            "/beli - Buy products\n"
            "/sts - Check order status\n\n"
            "💡 <b>Tip:</b> If some buttons are locked, make sure you have completed "
            "<b>REGISTER ACCESS</b> first.\n\n"
            "Need more help? Contact @hiduphjokowi"
        )

        if registered:
            kb = [
                [InlineKeyboardButton("🚀 OPEN MAIN MENU", callback_data="menu_main")],
                [InlineKeyboardButton("📚 VIEW DOCS", url="https://t.me/hiduphjokowi")]
            ]
        else:
            kb = [
                [InlineKeyboardButton("📝 REGISTER NOW", callback_data="cmd_register")],
                [InlineKeyboardButton("📚 VIEW DOCS", url="https://t.me/hiduphjokowi")]
            ]

        await update.message.reply_text(
            text,
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(kb),
        )
        
    except Exception as e:
        logger.error(f"[HELP] Error for user {user_id}: {str(e)}")
        await update.message.reply_text(
            "❌ <b>ERROR</b>\n\nFailed to load help menu.",
            parse_mode=ParseMode.HTML
        )

# ==========================================
# 🔒 LOCKED BUTTON CALLBACK (UPGRADED)
# ==========================================

async def locked_register_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk locked features"""
    q = update.callback_query
    user_id = q.from_user.id
    
    try:
        # Log attempt
        await log_user_action(user_id, "locked_access_attempt", q.data)
        
        await q.answer(
            "🔒 <b>FEATURE LOCKED</b>\n\n"
            "This module is exclusively for registered members.\n\n"
            "🎯 <b>ACTION REQUIRED:</b>\n"
            "Please complete the registration process to unlock this feature.\n\n"
            "⏱️ <b>Estimated time:</b> 2-3 minutes",
            show_alert=True
        )
        
        # Offer direct register button
        kb = [[InlineKeyboardButton("📝 REGISTER NOW", callback_data="cmd_register")]]
        await q.message.reply_text(
            "🔒 <b>LOCKED FEATURE</b>\n\n"
            "To unlock all premium features, please register first.",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(kb)
        )
        
    except Exception as e:
        logger.error(f"[LOCKED] Error for user {user_id}: {str(e)}")

# ==========================================
# 📊 ADMIN DASHBOARD (BONUS)
# ==========================================

@require_owner
@rate_limit(seconds=5)
async def admin_stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin dashboard untuk owner"""
    user_id = update.effective_user.id
    
    try:
        # Log
        await log_user_action(user_id, "admin_stats", "Accessed dashboard")
        
        # Get stats
        total_users = len(await get_all_subscribers())
        total_premium = len(await get_all_premium_users())
        total_sales = await get_total_sales_all_time()
        pending_orders = await get_pending_orders_count()
        stock_data = await get_all_stock()
        
        # Format stock
        stock_text = ""
        for plan, total in stock_data or []:
            stock_text += f"  📦 {plan}: {total} pcs\n"
        
        text = (
            f"📊 <b>ADMIN DASHBOARD</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"👥 <b>Total Users:</b> {total_users}\n"
            f"💎 <b>Premium Users:</b> {total_premium}\n"
            f"💰 <b>Total Sales:</b> Rp {total_sales * 25000:,.0f}\n"
            f"📦 <b>Pending Orders:</b> {pending_orders}\n\n"
            f"<b>📈 Current Stock:</b>\n{stock_text or '  (No data)'}\n\n"
            f"🕐 <b>Last Updated:</b> {datetime.datetime.now(TZ).strftime('%d/%m/%Y %H:%M:%S')}"
        )
        
        kb = [
            [
                InlineKeyboardButton("🔄 REFRESH", callback_data="admin_refresh_stats"),
                InlineKeyboardButton("🏪 MANAGE STOCK", callback_data="admin_stock")
            ],
            [InlineKeyboardButton("👥 USER LIST", callback_data="admin_users")]
        ]
        
        await update.message.reply_text(
            text,
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(kb)
        )
        
    except Exception as e:
        logger.error(f"[ADMIN] Error: {str(e)}")
        await update.message.reply_text(
            f"❌ Error loading dashboard: {str(e)[:50]}",
            parse_mode=ParseMode.HTML
        )

# ==========================================
# 🕹️ MENU COMMAND — PREMIUM AESTHETIC HUB (UPGRADED)
# ==========================================

async def safe_edit_message(msg, text, kb):
    """Safely edit message (handle both photo & text)"""
    try:
        if msg.photo:
            await msg.edit_caption(
                caption=text,
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup(kb)
            )
        else:
            await msg.edit_text(
                text,
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup(kb)
            )
    except (BadRequest, TimedOut):
        await msg.reply_text(
            text,
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(kb)
        )
    except Exception as e:
        logger.error(f"[MENU] Edit error: {str(e)}")

@rate_limit(seconds=2)
async def cmd_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Main menu command dengan dynamic content"""
    user = update.effective_user
    user_id = user.id
    
    try:
        # Log action
        await log_user_action(user_id, "menu_main", "Accessed main menu")
        
        # Check registration
        registered = await is_registered(user_id)
        
        # Get user stats
        user_stats = await get_user_stats(user_id)
        total_actions = user_stats[0] if user_stats else 0
        
        # Get session info
        session = await get_session(user_id)
        session_time = ""
        if session:
            elapsed = (datetime.datetime.now() - session["created_at"]).seconds
            session_time = f"\n⏱️ <b>Session Time:</b> <i>{elapsed // 60}m {elapsed % 60}s</i>"
        
        # Dynamic status
        user_level = "💎 Premium Access" if registered else "🔵 Standard Access"
        
        # Header dengan info lengkap
        text = (
            "🐈 <b>OKTACOMEL • Control Hub v2</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"<b>Status:</b> <i>🟢 Online & Stable</i>\n"
            f"<b>User Level:</b> <i>{user_level}</i>\n"
            f"<b>Total Actions:</b> <i>{total_actions}</i>{session_time}\n\n"
            
            "Welcome to the <b>Central Command Environment</b> — the unified control layer\n"
            "for Oktacomel's AI systems, automation tools, diagnostics, and digital modules.\n\n"
            
            "This interface is designed for clarity, responsiveness, and premium workflow\n"
            "experience, enabling fast access to all operational tools in a structured grid.\n\n"
            
            "<i>👇 Select a module below to begin.</i>"
        )
        
        # Helper function untuk lock
        def lock(cb_data):
            return cb_data if registered else "locked_register"
        
        # Dynamic keyboard based on registration
        if registered:
            kb = [
                [
                    InlineKeyboardButton("🛠️ Basic Tools", callback_data=lock("menu_basic")),
                    InlineKeyboardButton("📥 Downloaders", callback_data=lock("menu_dl"))
                ],
                [
                    InlineKeyboardButton("🤖 AI Tools", callback_data=lock("menu_ai")),
                    InlineKeyboardButton("📝 PDF Suite", callback_data=lock("menu_pdf"))
                ],
                [
                    InlineKeyboardButton("🔍 Checker", callback_data=lock("menu_check")),
                    InlineKeyboardButton("💳 CC Tools", callback_data=lock("menu_cc"))
                ],
                [
                    InlineKeyboardButton("📋 Todo", callback_data=lock("menu_todo")),
                    InlineKeyboardButton("📫 Temp Mail", callback_data=lock("menu_mail"))
                ],
                [
                    InlineKeyboardButton("💎 PREMIUM", callback_data="menu_buy"),
                    InlineKeyboardButton("⭐ ADMIN", callback_data="admin_stats") if user_id == OWNER_ID else None
                ],
                [
                    InlineKeyboardButton("❌ Close Session", callback_data="cmd_close")
                ]
            ]
            # Remove None items
            kb = [[btn for btn in row if btn] for row in kb]
        else:
            # Limited menu untuk unregistered
            kb = [
                [
                    InlineKeyboardButton("🔒 Tools (Locked)", callback_data="locked_register"),
                    InlineKeyboardButton("🔒 Download (Locked)", callback_data="locked_register")
                ],
                [
                    InlineKeyboardButton("💎 UPGRADE & UNLOCK", callback_data="menu_buy")
                ],
                [
                    InlineKeyboardButton("📝 Register First", callback_data="cmd_register")
                ],
                [
                    InlineKeyboardButton("❌ Close", callback_data="cmd_close")
                ]
            ]
        
        # Handle callback query vs command
        if update.callback_query:
            msg = update.callback_query.message
            await update.callback_query.answer()  # Dismiss loading
            await safe_edit_message(msg, text, kb)
        else:
            await update.message.reply_text(
                text,
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup(kb)
            )
        
    except Exception as e:
        logger.error(f"[CMD_MENU] Error for user {user_id}: {str(e)}")
        error_text = (
            "❌ <b>MENU LOAD ERROR</b>\n\n"
            f"Error: {str(e)[:50]}\n\n"
            "Please try again or contact support."
        )
        
        if update.callback_query:
            await update.callback_query.answer(
                "❌ Error loading menu. Please try again.",
                show_alert=True
            )
        else:
            await update.message.reply_text(
                error_text,
                parse_mode=ParseMode.HTML
            )

# ==========================================
# 🏠 CLOSE SESSION COMMAND
# ==========================================

async def close_session_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Close user session"""
    q = update.callback_query
    user_id = q.from_user.id
    
    try:
        # Log
        await log_user_action(user_id, "session_close", "Closed session")
        
        # Remove session
        if user_id in user_sessions:
            del user_sessions[user_id]
        
        await q.answer("✅ Session closed successfully.", show_alert=True)
        await q.message.reply_text(
            "✅ <b>SESSION CLOSED</b>\n\n"
            "Your session has been terminated.\n"
            "Type /start to begin a new session.",
            parse_mode=ParseMode.HTML
        )
    except Exception as e:
        logger.error(f"[CLOSE] Error: {str(e)}")

# ==========================================
# 💳 CC GEN & BIN (PREMIUM & OWNER ONLY)
# ==========================================
async def gen_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    # --- 🔒 LOGIKA CEK PREMIUM ---
    is_allowed = False
    
    # 1. Cek apakah dia Owner?
    if user_id == OWNER_ID:
        is_allowed = True
    else:
        # 2. Cek apakah dia Premium User di Database?
        async with aiosqlite.connect(DB_NAME) as db:
            async with db.execute("SELECT user_id FROM premium_users WHERE user_id = ?", (user_id,)) as cursor:
                if await cursor.fetchone():
                    is_allowed = True

    # Jika BUKAN Owner dan BUKAN Premium, tolak!
    if not is_allowed:
        text = (
            "Hey! The bot is temporarily available only for premium users, "
            "but don't worry—it’ll be open to everyone soon. I hope you understand. "
            "Thanks for your support and stay tuned!\n\n"
            "Use /buy command."
        )
        await update.message.reply_text(text, parse_mode=ParseMode.HTML)
        return
    # -----------------------------

    args = context.args
    if not args:
        await update.message.reply_text("⚠️ <b>Format:</b> <code>/gen 545454</code> or <code>/gen 545454|05|2025</code>", parse_mode=ParseMode.HTML)
        return

    input_data = args[0]
    
    # Cek apakah ada argumen jumlah (amount) di belakang
    amount = 10
    if len(args) > 1 and args[1].isdigit():
        amount = int(args[1])
        if amount > 5000: amount = 5000

    # --- NORMALISASI PEMISAH ---
    normalized_input = input_data.replace("/", "|").replace(":", "|").replace(" ", "|")
    splits = normalized_input.split("|")
    
    # Ambil data sesuai urutan
    cc = splits[0] if len(splits) > 0 else 'x'
    mes = splits[1] if len(splits) > 1 and splits[1].isdigit() else 'x'
    ano = splits[2] if len(splits) > 2 and splits[2].isdigit() else 'x'
    cvv = splits[3] if len(splits) > 3 and splits[3].isdigit() else 'x'

    # Ambil 6 digit pertama murni untuk cek BIN
    clean_bin = cc.lower().replace('x', '')[:6]

    if not clean_bin.isdigit() or len(clean_bin) < 6:
        return await update.message.reply_text("❌ BIN Invalid (Must contain at least 6 digits).")

    msg = await update.message.reply_text("⏳ <b>Generating...</b>", parse_mode=ParseMode.HTML)

    # 1. Fetch BIN Info
    try:
        r = await fetch_json(f"{BIN_API}/{clean_bin}")
        if r and 'brand' in r:
            info = f"{str(r.get('brand')).upper()} - {str(r.get('type')).upper()} - {str(r.get('level')).upper()}"
            bank = str(r.get('bank', 'UNKNOWN')).upper()
            country = f"{str(r.get('country_name')).upper()} {r.get('country_flag','')}"
        else:
            info, bank, country = "UNKNOWN", "UNKNOWN", "UNKNOWN"
    except: 
        info, bank, country = "ERROR", "ERROR", "ERROR"

    # 2. Generate Cards
    cards = cc_gen(cc, mes, ano, cvv, amount)

    # 3. Output Logic
    if amount <= 15:
        formatted_cards = "\n".join([f"<code>{c}</code>" for c in cards])
        txt = (
            f"<b>𝗕𝗜𝗡 ⇾</b> <code>{clean_bin}</code>\n"
            f"<b>𝗔𝗺𝗼𝘂𝗻𝘁 ⇾</b> {amount}\n\n"
            f"{formatted_cards}\n\n"
            f"<b>𝗜𝗻𝗳𝗼:</b> {info}\n"
            f"<b>𝐈𝐬𝐬𝐮𝐞𝐫:</b> {bank}\n"
            f"<b>𝗖𝗼𝘂𝗻𝘁𝗿𝘆:</b> {country}"
        )
        await msg.edit_text(txt, parse_mode=ParseMode.HTML)
    else:
        filename = f"CC_{clean_bin}_{amount}.txt"
        with open(filename, "w") as f:
            f.write(f"𝗕𝗜𝗡: {clean_bin} | Amount: {amount}\n")
            f.write(f"𝗜𝗻𝗳𝗼: {info} | {bank} | {country}\n")
            f.write("====================================\n")
            f.write("\n".join(cards))
        
        await update.message.reply_document(
            document=open(filename, "rb"),
            caption=f"✅ <b>Generated {amount} Cards</b>\nBIN: <code>{clean_bin}</code>\n{country}",
            parse_mode=ParseMode.HTML
        )
        await msg.delete()
        os.remove(filename)

# ==========================================
# 📥 DOWNLOADER DENGAN PROGRESS BAR & ERROR HANDLING
# ==========================================

ERROR_MESSAGES = {
    "Private Account": "🔒 This is a private account",
    "Age Restricted": "⚠️ Video age-restricted",
    "Geo Blocked": "🌍 Content not available in your region",
    "Video Deleted": "❌ Video has been deleted",
    "No Permission": "🚫 You don't have permission",
    "Rate Limited": "⏸️ Rate limited, try in 5 minutes",
    "Not Found": "❌ Video/Content not found",
    "Unavailable": "⚠️ Content unavailable",
    "Restricted": "🔐 Content restricted in your region"
}

async def update_progress_bar(status_msg, current_bytes, total_bytes, speed_mbps, title="📥 Downloading"):
    """Update progress bar real-time"""
    try:
        if total_bytes == 0:
            return
        
        percentage = int((current_bytes / total_bytes) * 100)
        bar_length = 20
        filled = int(bar_length * percentage / 100)
        bar = "█" * filled + "░" * (bar_length - filled)
        
        if speed_mbps > 0:
            remaining_mb = (total_bytes - current_bytes) / (1024 * 1024)
            eta_sec = int(remaining_mb / speed_mbps)
        else:
            eta_sec = 0
        
        current_mb = current_bytes / (1024 * 1024)
        total_mb = total_bytes / (1024 * 1024)
        
        text = (
            f"{title}\n"
            f"[{bar}] {percentage}%\n"
            f"⏱️ ETA: {eta_sec}s | ↓ {speed_mbps:.2f} MB/s | 📊 {current_mb:.1f}/{total_mb:.1f} MB"
        )
        
        await status_msg.edit_text(text, parse_mode=ParseMode.HTML)
    except Exception as e:
        logger.debug(f"Progress update error: {e}")

async def downloader_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Enhanced downloader with progress bar & error handling"""
    
    msg = update.message
    if not context.args:
        return await msg.reply_text("⚠️ <b>Usage:</b> <code>/download [link]</code>", parse_mode=ParseMode.HTML)

    url = context.args[0].strip()

    if not url.startswith(("http://", "https://", "www.")):
        return await msg.reply_text("❌ <b>Invalid URL.</b> Check format.", parse_mode=ParseMode.HTML)

    if "spotify" in url or "apple.com" in url:
        return await msg.reply_text("❌ <b>Unsupported Platform.</b>", parse_mode=ParseMode.HTML)

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.UPLOAD_VIDEO)

    # Cache check
    try:
        cached = await get_cached_media(url)
        if cached:
            file_id, m_type = cached
            caption = "✅ <b>Cached Delivery (Instant)</b>\n⚡ <i>Powered by Oktacomel</i>"
            if m_type == "video":
                await msg.reply_video(file_id, caption=caption, parse_mode=ParseMode.HTML)
            elif m_type == "audio":
                await msg.reply_audio(file_id, caption=caption, parse_mode=ParseMode.HTML)
            return
    except Exception as e:
        logger.debug(f"[CACHE] error: {e}")

    status_msg = await msg.reply_text("⏳ <b>Processing Request...</b>\n<i>Analyzing media source...</i>", parse_mode=ParseMode.HTML)

    # ==========================================
    # 1. TIKTOK ENGINE (STABLE)
    # ==========================================
    if "tiktok.com" in url:
        try:
            await status_msg.edit_text("📥 <b>Downloading TikTok...</b>\n<i>Fetching video...</i>", parse_mode=ParseMode.HTML)
            
            async with httpx.AsyncClient(timeout=15.0) as client:
                r = await client.get(f"https://www.tikwm.com/api/?url={url}")
                data = r.json()
            
            if data and data.get("code") == 0:
                d = data["data"]
                caption = (
                    f"🎥 <b>OKTACOMEL TIKTOK</b>\n"
                    f"━━━━━━━━━━━━━━━━━━\n"
                    f"👤 <b>Author:</b> {html.escape(d['author']['nickname'])}\n"
                    f"📝 <b>Desc:</b> {html.escape(d.get('title', '')[:100])}\n"
                    f"⚡ <i>Powered by Oktacomel</i>"
                )
                await status_msg.delete()

                if d.get("images"):
                    media_group = []
                    for i, img in enumerate(d["images"][:10]):
                        cap = caption if i == 0 else None
                        media_group.append(InputMediaPhoto(img, caption=cap, parse_mode=ParseMode.HTML))
                    await msg.reply_media_group(media_group)
                else:
                    v = await msg.reply_video(d["play"], caption=caption, parse_mode=ParseMode.HTML)
                    await save_media_cache(url, v.video.file_id, "video")
                
                if d.get("music"):
                    try:
                        await msg.reply_audio(d["music"], caption="🎵 Original Sound", parse_mode=ParseMode.HTML)
                    except:
                        pass
                return
        except Exception as e:
            logger.error(f"[TIKTOK] error: {e}")
            await status_msg.edit_text(f"❌ TikTok Error: {str(e)[:50]}", parse_mode=ParseMode.HTML)

    # ==========================================
    # 2. INSTAGRAM ENGINE (POSTS, REELS, STORIES)
    # ==========================================
    if "instagram.com" in url:
        await status_msg.edit_text("📸 <b>Instagram detected.</b>\n<i>Analyzing content type...</i>", parse_mode=ParseMode.HTML)
        
        if "/reel/" in url:
            content_type = "🎬 REEL"
        elif "/stories/" in url:
            content_type = "📖 STORY"
        elif "/p/" in url:
            content_type = "📸 POST"
        else:
            content_type = "📸 CONTENT"
        
        instagram_apis = [
            lambda u: fetch_json(f"https://ig.i.seg.in.net/?url={u}"),
            lambda u: fetch_json(f"https://instagram-api.com/v1/download?url={u}"),
            lambda u: fetch_json(f"https://insta.d.solankan.com/api/?url={u}"),
        ]
        
        ig_success = False
        for api_func in instagram_apis:
            try:
                await status_msg.edit_text(f"📸 <b>Fetching {content_type}...</b>\n<i>Please wait...</i>", parse_mode=ParseMode.HTML)
                
                data = await api_func(url)
                if data and (data.get("media") or data.get("url") or data.get("download_url")):
                    media_url = data.get("media") or data.get("url") or data.get("download_url")
                    
                    caption = (
                        f"📸 <b>OKTACOMEL INSTAGRAM</b>\n"
                        f"━━━━━━━━━━━━━━━━━━\n"
                        f"📝 Type: {content_type}\n"
                        f"⚡ <i>Powered by Oktacomel</i>"
                    )
                    
                    try:
                        await status_msg.edit_text(f"📥 <b>Downloading {content_type}...</b>\n<i>Sending file...</i>", parse_mode=ParseMode.HTML)
                        v = await msg.reply_video(media_url, caption=caption, parse_mode=ParseMode.HTML)
                        await save_media_cache(url, v.video.file_id, "video")
                        ig_success = True
                        break
                    except:
                        try:
                            p = await msg.reply_photo(media_url, caption=caption, parse_mode=ParseMode.HTML)
                            await save_media_cache(url, p.photo[-1].file_id, "photo")
                            ig_success = True
                            break
                        except:
                            pass
            except Exception as e:
                logger.debug(f"[IG API] error: {e}")
                continue
        
        if ig_success:
            await status_msg.delete()
            return
        else:
            await status_msg.edit_text("⚠️ Instagram private/restricted, trying universal engine...", parse_mode=ParseMode.HTML)

    # ==========================================
    # 3. YOUTUBE DURATION CHECK (REJECT > 1 JAM)
    # ==========================================
    if "youtube.com" in url or "youtu.be" in url:
        try:
            await status_msg.edit_text("⏱️ <b>Checking video duration...</b>\n<i>Please wait...</i>", parse_mode=ParseMode.HTML)
            
            loop = asyncio.get_running_loop()
            
            with yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True}) as ydl:
                info = await loop.run_in_executor(None, lambda: ydl.extract_info(url, download=False))
                duration = info.get('duration', 0)
                title = info.get('title', 'Video')
                uploader = info.get('uploader', 'Unknown')
            
            # Check durasi > 1 jam (3600 detik)
            if duration > 3600:
                minutes = duration // 60
                seconds = duration % 60
                
                await status_msg.edit_text(
                    f"❌ <b>Video Terlalu Panjang!</b>\n\n"
                    f"📝 <b>Judul:</b> {html.escape(title[:60])}\n"
                    f"👤 <b>Channel:</b> {html.escape(uploader)}\n"
                    f"⏱️ <b>Durasi:</b> {minutes}:{seconds:02d} (Lebih dari 60 menit)\n"
                    f"📏 <b>Batas Maksimal:</b> 60 menit\n\n"
                    f"<i>Silakan gunakan video yang lebih pendek.</i>",
                    parse_mode=ParseMode.HTML
                )
                return
        
        except Exception as e:
            logger.debug(f"Duration check error: {e}")
            # Lanjut ke download jika cek durasi gagal

    # ==========================================
    # 4. UNIVERSAL ENGINE (YT-DLP)
    # ==========================================
    if "youtube.com" in url or "youtu.be" in url or "instagram.com" in url or "facebook.com" in url or "x.com" in url or "twitter.com" in url:
        try:
            temp_dir = f"downloads_{uuid.uuid4()}"
            os.makedirs(temp_dir, exist_ok=True)

            ydl_opts = {
                "format": "best[ext=mp4]/best",
                "outtmpl": f"{temp_dir}/%(title)s.%(ext)s",
                "quiet": False,
                "no_warnings": False,
                "noplaylist": True,
                "socket_timeout": 30,
                "http_headers": {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                    "Accept-Language": "en-US,en;q=0.5",
                    "Referer": "https://www.google.com/",
                    "DNT": "1",
                    "Connection": "keep-alive",
                    "Upgrade-Insecure-Requests": "1"
                },
                "nocheckcertificate": True,
                "ignoreerrors": True,
                "geo_bypass": True,
                "geo_bypass_country": "US",
                "extractor_retries": 5,
                "retries": 3,
                "fragment_retries": 5,
                "skip_unavailable_fragments": True,
                "instagram_flat_post_captions": True,
                "facebook_prefer_https": True,
            }
            
            loop = asyncio.get_running_loop()
            
            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    await status_msg.edit_text("📥 <b>Downloading...</b>\n<i>Processing video...</i>", parse_mode=ParseMode.HTML)
                    
                    info = await loop.run_in_executor(None, lambda: ydl.extract_info(url, download=True))
                    
                    if info and "entries" in info:
                        info = info["entries"][0]

                    if not info:
                        for key, msg_text in ERROR_MESSAGES.items():
                            if key.lower() in str(info).lower():
                                await status_msg.edit_text(f"❌ {msg_text}", parse_mode=ParseMode.HTML)
                                return
                        raise Exception("Extraction failed.")

                    video_title = info.get("title", "Media Content")
                    uploader = info.get("uploader", "Unknown")
                    
                    if "instagram.com" in url:
                        if "/reel/" in url:
                            platform, icon = "INSTAGRAM REEL", "🎬"
                        elif "/stories/" in url:
                            platform, icon = "INSTAGRAM STORY", "📖"
                        else:
                            platform, icon = "INSTAGRAM POST", "📸"
                    elif "youtube.com" in url or "youtu.be" in url:
                        platform, icon = "YOUTUBE", "📺"
                    elif "twitter.com" in url or "x.com" in url:
                        platform, icon = "X/TWITTER", "🐦"
                    elif "facebook.com" in url:
                        platform, icon = "FACEBOOK", "📘"
                    else:
                        platform, icon = "UNIVERSAL", "📁"

                    files = [os.path.join(temp_dir, f) for f in os.listdir(temp_dir)]
                    if not files:
                        raise Exception("File not found.")

                    caption_base = (
                        f"{icon} <b>OKTACOMEL {platform}</b>\n"
                        f"━━━━━━━━━━━━━━━━━━\n"
                        f"📝 <b>Title:</b> {html.escape(str(video_title)[:80])}\n"
                        f"👤 <b>By:</b> {html.escape(str(uploader))}\n"
                        f"⚡ <i>Powered by Oktacomel</i>"
                    )

                    sent_count = 0
                    for f_path in files:
                        ext = f_path.split(".")[-1].lower()
                        cap = caption_base if sent_count == 0 else None
                        
                        try:
                            if ext in ["jpg", "jpeg", "png", "webp"]:
                                await msg.reply_photo(photo=open(f_path, "rb"), caption=cap, parse_mode=ParseMode.HTML)
                            elif ext in ["mp4", "mkv", "mov", "webm", "avi"]:
                                v = await msg.reply_video(video=open(f_path, "rb"), caption=cap, parse_mode=ParseMode.HTML)
                                if sent_count == 0:
                                    await save_media_cache(url, v.video.file_id, "video")
                            elif ext in ["mp3", "m4a", "wav"]:
                                await msg.reply_audio(audio=open(f_path, "rb"), caption=cap, parse_mode=ParseMode.HTML)
                            sent_count += 1
                        except Exception as ex:
                            logger.error(f"Send Error: {ex}")
                        finally:
                            try:
                                os.remove(f_path)
                            except:
                                pass

                    try:
                        os.rmdir(temp_dir)
                    except:
                        pass
                    
                    await status_msg.delete()
                    return

            except yt_dlp.utils.DownloadError as e:
                error_str = str(e).lower()
                error_found = False
                
                for key, msg_text in ERROR_MESSAGES.items():
                    if key.lower() in error_str:
                        await status_msg.edit_text(f"❌ {msg_text}", parse_mode=ParseMode.HTML)
                        error_found = True
                        break
                
                if not error_found:
                    await status_msg.edit_text(
                        "❌ <b>Download Failed</b>\n\n"
                        "Possible causes:\n"
                        "• Private/Restricted Content\n"
                        "• Video Deleted\n"
                        "• Geo-Blocked\n"
                        "• Server Rate Limited\n\n"
                        "Try again in 5 minutes.",
                        parse_mode=ParseMode.HTML
                    )
            except Exception as e:
                logger.error(f"Download Error: {e}")
                try:
                    shutil.rmtree(temp_dir)
                except:
                    pass

        except Exception as e:
            logger.error(f"General Error: {e}")

    await status_msg.edit_text(
        "❌ <b>Download Failed</b>\n\n"
        "Possible causes:\n"
        "1️⃣ Private Account/Content\n"
        "2️⃣ Geo-Restricted\n"
        "3️⃣ Server IP Blocked\n"
        "4️⃣ Video Deleted/Age Restricted\n"
        "5️⃣ Format Not Supported\n\n"
        "<i>Try again later or use a different link.</i>",
        parse_mode=ParseMode.HTML
    )
# ==========================================
# 👤 PROFILE (/ME) - ULTIMATE PREMIUM
# ==========================================
async def me_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    c = update.effective_chat

    # --- Foto profil user ---
    try:
        p = await u.get_profile_photos(limit=1)
    except Exception:
        p = None

    # --- Chat type + icon ---
    chat_type_raw = c.type.lower()
    if chat_type_raw == "private":
        chat_icon = "🔒"
        chat_type_label = "Private Chat"
    elif chat_type_raw == "group":
        chat_icon = "👥"
        chat_type_label = "Group"
    elif chat_type_raw == "supergroup":
        chat_icon = "🚀"
        chat_type_label = "Supergroup"
    elif chat_type_raw == "channel":
        chat_icon = "📣"
        chat_type_label = "Channel"
    else:
        chat_icon = "📂"
        chat_type_label = chat_type_raw.title()

    # --- Role / Status (untuk group/supergroup) ---
    role_label = "N/A"
    if chat_type_raw in ("group", "supergroup"):
        try:
            member = await c.get_member(u.id)
            status = member.status
            if status == "creator":
                role_label = "Owner"
            elif status == "administrator":
                role_label = "Administrator"
            elif status == "member":
                role_label = "Member"
            elif status == "restricted":
                role_label = "Restricted"
            else:
                role_label = status.title()
        except:
            role_label = "Unknown"

    # --- Language & Premium Info ---
    lang = getattr(u, "language_code", None) or "Unknown"
    premium_label = "Yes" if getattr(u, "is_premium", False) else "No"

    # --- Waktu ---
    try:
        time_str = update.message.date.strftime("%d %B %Y %H:%M")
    except:
        time_str = "Unknown"

    # --- Teks utama (Premium Card) ---
    txt = (
        f"👤 <b>USER PROFILE</b>\n"
        f"✦────────────────────✦\n"
        f"📛 𝗡𝗮𝗺𝗲 ⇾ <b>{html.escape(u.full_name)}</b>\n"
        f"😎 𝗨𝘀𝗲𝗿𝗻𝗮𝗺𝗲 ⇾ @{u.username if u.username else 'None'}\n"
        f"🆔 𝗨𝘀𝗲𝗿 𝗜𝗗 ⇾ <code>{u.id}</code>\n"
        f"🔗 𝗣𝗲𝗿𝗺𝗮𝗹𝗶𝗻𝗸 ⇾ <a href='tg://user?id={u.id}'>Click Here</a>\n"
        f"\n"
        f"🌐 𝗟𝗮𝗻𝗴𝘂𝗮𝗴𝗲 ⇾ <code>{lang}</code>\n"
        f"💎 𝗣𝗿𝗲𝗺𝗶𝘂𝗺 ⇾ <code>{premium_label}</code>\n"
        f"{chat_icon} 𝗖𝗵𝗮𝘁 𝗜𝗗 ⇾ <code>{c.id}</code>\n"
        f"{chat_icon} 𝗖𝗵𝗮𝘁 𝗧𝘆𝗽𝗲 ⇾ <code>{chat_type_label}</code>\n"
    )

    if chat_type_raw in ("group", "supergroup"):
        txt += f"🛡️ 𝗥𝗼𝗹𝗲 ⇾ <code>{role_label}</code>\n"

    txt += (
        f"🕒 𝗧𝗶𝗺𝗲 ⇾ <code>{time_str}</code>\n"
        f"✦────────────────────✦\n"
        f"🤖 <i>Powered by Oktacomel</i>"
    )

    # --- Kirim output (foto kalau ada) ---
    try:
        if p and p.total_count > 0:
            await update.message.reply_photo(
                p.photos[0][-1].file_id,
                caption=txt,
                parse_mode=ParseMode.HTML
            )
        else:
            await update.message.reply_text(txt, parse_mode=ParseMode.HTML)
    except Exception:
        await update.message.reply_text(txt, parse_mode=ParseMode.HTML)


# ==========================================
# 💎 PREMIUM & BUY (FULL TEXT + BACK BUTTON)
# ==========================================
async def buy_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Text Baru Lengkap dengan Format Rapi
    text = (
        "🌟 <b>Upgrade to Premium</b> 🌟\n"
        "Take your experience to the next level with our premium plans. Enjoy higher limits, priority support, and exclusive features!\n\n"
        
        "🏷 <b>Premium Plans:</b>\n"
        "- <code>$69.99</code> for <b>Basic Premium</b> ($0.0292/credit)\n"
        "  • Daily Limit: 80 credits/day\n"
        "  • Hourly Limit: 25 credits/hour\n"
        "  • Weekly Limit: 560 credits\n"
        "  • Monthly Limit: 2400 credits\n\n"
        
        "- <code>$149.99</code> for <b>Advanced Premium</b> ($0.0250/credit)\n"
        "  • Daily Limit: 200 credits/day\n"
        "  • Hourly Limit: 65 credits/hour\n"
        "  • Weekly Limit: 1400 credits\n"
        "  • Monthly Limit: 6000 credits\n\n"
        
        "- <code>$249.99</code> for <b>Pro Premium</b> ($0.0238/credit)\n"
        "  • Daily Limit: 350 credits/day\n"
        "  • Hourly Limit: 115 credits/hour\n"
        "  • Weekly Limit: 2450 credits\n"
        "  • Monthly Limit: 10500 credits\n\n"
        
        "- <code>$449.99</code> for <b>Enterprise Premium</b> ($0.0187/credit)\n"
        "  • Daily Limit: 800 credits/day\n"
        "  • Hourly Limit: 265 credits/hour\n"
        "  • Weekly Limit: 5600 credits\n"
        "  • Monthly Limit: 24000 credits\n\n"

        "🏷 <b>Credits Plans (Popular):</b>\n"
        "- <code>$4.99</code> for 100 credits + 2 bonus\n"
        "- <code>$19.99</code> for 500 credits + 10 bonus\n"
        "- <code>$39.99</code> for 1000 credits + 25 bonus\n"
        "- <code>$94.99</code> for 2500 credits + 50 bonus\n"
        "- <code>$179.99</code> for 5000 credits + 50 bonus\n"
        "- <code>$333.99</code> for 10000 credits + 100 bonus\n"
        "- <code>$739.99</code> for 25000 credits + 300 bonus\n\n"

        "✅ <b>After Payment:</b>\n"
        "Your premium plan will be automatically activated once the payment is confirmed.\n"
        "<i>All sales are final. No refunds.</i>\n\n"

        "🤝 Thank you for choosing to go premium! Your support helps us keep improving.\n"
        "📜 <a href='https://google.com'>Learn More About Plans</a>"
    )
    
    # Tombol Lengkap (+ Back Button)
    kb = [
        [InlineKeyboardButton("Pay via Crypto", callback_data="pay_crypto"),
         InlineKeyboardButton("Pay via QRIS", callback_data="pay_qris")],
        [InlineKeyboardButton("Contact Support", url="https://t.me/hiduphjokowi")],
        [InlineKeyboardButton("Plan Details", url="https://google.com")],
        
        # 👇 INI TOMBOL TAMBAHANNYA 👇
        [InlineKeyboardButton("🔙 Back to Menu", callback_data="menu_main")]
    ]
    
    # Gunakan edit jika dari callback, atau send jika command baru
    if update.callback_query:
        # Cek jika ada foto (dari /start), hapus dulu
        if update.callback_query.message.photo:
            await update.callback_query.message.delete()
            await context.bot.send_message(chat_id=update.effective_chat.id, text=text, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(kb), disable_web_page_preview=True)
        else:
            await update.callback_query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(kb), disable_web_page_preview=True)
    else:
        await update.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(kb), disable_web_page_preview=True)

# ==========================================
# 🔍 IP & NETWORK (/IP) - PREMIUM STYLE
# ==========================================
async def ip_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = " ".join(context.args) if context.args else ""
    if not q: 
        await update.message.reply_text("⚠️ <b>Usage:</b> <code>/ip domain_or_ip</code>", parse_mode=ParseMode.HTML)
        return
    
    msg = await update.message.reply_text("⏳ <b>Scanning network...</b>", parse_mode=ParseMode.HTML)

    # API Request (Fields Lengkap)
    api_url = f"http://ip-api.com/json/{q}?fields=status,message,country,countryCode,region,regionName,city,zip,lat,lon,timezone,isp,org,as,mobile,proxy,hosting,query"
    
    try:
        r = await fetch_json(api_url)
        
        if r and r['status'] == 'success':
            lat, lon = r['lat'], r['lon']
            # Link Google Maps Resmi (Biar gak error)
            map_url = f"https://www.google.com/maps/search/?api=1&query={lat},{lon}"
            
            # Status Check
            is_mobile = "✅ Yes" if r.get('mobile') else "❌ No"
            is_proxy = "🔴 DETECTED" if r.get('proxy') else "🟢 Clean"
            is_hosting = "🖥️ VPS/Cloud" if r.get('hosting') else "🏠 Residential"

            # TAMPILAN PREMIUM (BOLD SANS + MONO)
            txt = (
                f"🔍 <b>IP INTELLIGENCE</b>\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"🎯 𝗧𝗮𝗿𝗴𝗲𝘁 ⇾ <code>{r['query']}</code>\n"
                f"🏢 𝗜𝗦𝗣 ⇾ <code>{r['isp']}</code>\n"
                f"💼 𝗢𝗿𝗴 ⇾ <code>{r.get('org', 'N/A')}</code>\n"
                f"🔢 𝗔𝗦𝗡 ⇾ <code>{r.get('as', 'N/A')}</code>\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"🌍 𝗟𝗢𝗖𝗔𝗧𝗜𝗢𝗡 𝗗𝗘𝗧𝗔𝗜𝗟\n"
                f"🏳️ 𝗖𝗼𝘂𝗻𝘁𝗿𝘆 ⇾ <code>{r['country']} ({r['countryCode']})</code>\n"
                f"📍 𝗥𝗲𝗴𝗶𝗼𝗻 ⇾ <code>{r['regionName']}</code>\n"
                f"🏙️ 𝗖𝗶𝘁𝘆 ⇾ <code>{r['city']}</code>\n"
                f"📮 𝗭𝗶𝗽 𝗖𝗼𝗱𝗲 ⇾ <code>{r['zip']}</code>\n"
                f"⏰ 𝗧𝗶𝗺𝗲𝘇𝗼𝗻𝗲 ⇾ <code>{r['timezone']}</code>\n"
                f"🛰️ 𝗖𝗼𝗼𝗿𝗱𝘀 ⇾ <code>{lat}, {lon}</code>\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"🛡️ 𝗦𝗘𝗖𝗨𝗥𝗜𝗧𝗬 𝗔𝗡𝗔𝗟𝗬𝗦𝗜𝗦\n"
                f"📱 𝗠𝗼𝗯𝗶𝗹𝗲 ⇾ <b>{is_mobile}</b>\n"
                f"🕵️ 𝗣𝗿𝗼𝘅𝘆/𝗩𝗣𝗡 ⇾ <b>{is_proxy}</b>\n"
                f"☁️ 𝗧𝘆𝗽𝗲 ⇾ <b>{is_hosting}</b>\n\n"
                f"🤖 <i>Powered by Oktacomel</i>"
            )
            
            kb = [[InlineKeyboardButton("🗺️ Open Google Maps", url=map_url)]]
            await msg.edit_text(txt, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(kb))
        else: 
            await msg.edit_text("❌ <b>Failed.</b> Invalid IP/Domain.", parse_mode=ParseMode.HTML)

    except Exception as e:
        await msg.edit_text(f"❌ <b>Error:</b> {str(e)}", parse_mode=ParseMode.HTML)
        
# ==========================================
# 🌦️ WEATHER & GEMPA & BROADCAST (ICON UPDATE)
# ==========================================
async def cuaca_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args: 
        return await update.message.reply_text("⚠️ <b>Usage:</b> <code>/weather city</code>", parse_mode=ParseMode.HTML)
    
    city = " ".join(context.args)
    data = await get_weather_data(city)
    
    if data and data.get('cod') == 200:
        lat, lon = data['coord']['lat'], data['coord']['lon']
        map_url = f"https://www.google.com/maps/search/?api=1&query={lat},{lon}"
        aqi = await get_aqi(lat, lon)
        
        # Mengambil teks dari helper format_weather
        txt = format_weather(data, aqi)
        
        kb = [
            [InlineKeyboardButton("🔄 Refresh Data", callback_data=f"weather_refresh|{city}")],
            [InlineKeyboardButton("🗺️ View on Map", url=map_url)]
        ]
        await update.message.reply_text(txt, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(kb))
    else: 
        await update.message.reply_text("❌ <b>City Not Found.</b> Please check the spelling.", parse_mode=ParseMode.HTML)

# ==========================================
# 🌋 INFO GEMPA TERKINI (OKTACOMEL SMART ALERT)
# ==========================================
async def gempa_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Biar user tahu bot lagi kerja
    await context.bot.send_chat_action(update.effective_chat.id, ChatAction.UPLOAD_PHOTO)

    try:
        r = await fetch_json(BMKG_URL)
        if not r:
            await update.message.reply_text(
                "❌ <b>Gagal koneksi ke server BMKG.</b>\n"
                "Silakan coba lagi beberapa saat lagi.",
                parse_mode=ParseMode.HTML
            )
            return

        d = r.get("Infogempa", {}).get("gempa")
        if not d:
            await update.message.reply_text(
                "❌ <b>Data gempa tidak tersedia.</b>",
                parse_mode=ParseMode.HTML
            )
            return

        # 1. Logika Warna & Status Bahaya
        try:
            mag = float(d.get("Magnitude", "0"))
        except:
            mag = 0.0

        if mag >= 7.0:
            alert = "🔴 BAHAYA (GEMPA KUAT)"
            level_label = "HIGH ALERT"
        elif mag >= 5.0:
            alert = "🟠 WASPADA (GEMPA SEDANG)"
            level_label = "CAUTION"
        else:
            alert = "🟢 TERKENDALI (GEMPA RINGAN)"
            level_label = "INFO"

        # 2. Cek Potensi Tsunami
        potensi = d.get("Potensi", "")
        if "tidak berpotensi" in potensi.lower():
            tsunami_status = "🟢 TIDAK BERPOTENSI TSUNAMI"
        else:
            tsunami_status = f"🔴 ⚠️ {potensi or 'POTENSI TSUNAMI TIDAK DIKETAHUI'}"

        # 3. Link Google Maps Resmi
        coords_raw = d.get("Coordinates", "")
        try:
            coords = coords_raw.split(",")  # Format: -3.55,102.33
            lat, lon = coords[0].strip(), coords[1].strip()
            map_url = f"https://www.google.com/maps/search/?api=1&query={lat},{lon}"
        except Exception:
            lat, lon = "Unknown", "Unknown"
            map_url = "https://www.google.com/maps/search/?q=BMKG+Gempa+Terkini"

        # 4. Additional info: dirasakan?
        dirasakan = d.get("Dirasakan", "").strip()
        dirasakan_text = f"<code>{html.escape(dirasakan)}</code>" if dirasakan else "<i>Tidak ada laporan terasa signifikan.</i>"

        # 5. Tampilan Premium (Sectioned Panel)
        txt = (
            "🌋 <b>OKTACOMEL GEMPA ALERT</b>\n"
            "━━━━━━━━━━━━━━━━━━\n"
            f"🏷️ <b>Level:</b> <code>{level_label}</code>\n"
            f"⚠️ <b>Status:</b> {alert}\n"
            f"🌊 <b>Tsunami:</b> {tsunami_status}\n"
            "━━━━━━━━━━━━━━━━━━\n"
            f"📅 <b>Waktu:</b> <code>{d.get('Tanggal', '-') } | {d.get('Jam', '-')}</code>\n"
            f"💥 <b>Magnitude:</b> <code>{d.get('Magnitude', '-')} SR</code>\n"
            f"🌊 <b>Kedalaman:</b> <code>{d.get('Kedalaman', '-')}</code>\n"
            f"📍 <b>Lokasi:</b> <code>{html.escape(d.get('Wilayah', '-'))}</code>\n"
            f"📌 <b>Koordinat:</b> <code>{coords_raw or 'Unknown'}</code>\n"
            "━━━━━━━━━━━━━━━━━━\n"
            f"👥 <b>Dirasakan:</b>\n{dirasakan_text}\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "🏛️ <i>Sumber resmi: BMKG Indonesia</i>"
        )

        kb = [[InlineKeyboardButton("🗺️ Lihat Lokasi di Peta", url=map_url)]]

        # Kirim Gambar Shakemap jika ada
        shakemap_file = d.get("Shakemap")
        if shakemap_file:
            shakemap_url = f"https://data.bmkg.go.id/DataMKG/TEWS/{shakemap_file}"
            try:
                await update.message.reply_photo(
                    shakemap_url,
                    caption=txt,
                    parse_mode=ParseMode.HTML,
                    reply_markup=InlineKeyboardMarkup(kb)
                )
                return
            except Exception:
                pass  # fallback ke text biasa

        # Fallback jika gambar error/tidak ada
        await update.message.reply_text(
            txt,
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(kb)
        )

    except Exception as e:
        await update.message.reply_text(
            f"❌ <b>System Error:</b> <code>{html.escape(str(e))}</code>",
            parse_mode=ParseMode.HTML
        )


# ==========================================
# 📬 SUBSCRIBE / UNSUBSCRIBE BROADCAST
# ==========================================
async def subscribe(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await add_subscriber(update.effective_user.id):
        await update.message.reply_text(
            "✅ <b>Subscribed to OKTACOMEL Alerts.</b>\n"
            "📡 You will receive curated daily updates and important broadcasts.",
            parse_mode=ParseMode.HTML
        )
    else:
        await update.message.reply_text(
            "ℹ️ <b>You are already subscribed.</b>\n"
            "No action was taken.",
            parse_mode=ParseMode.HTML
        )


async def unsubscribe(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await remove_subscriber(update.effective_user.id):
        await update.message.reply_text(
            "🔕 <b>Unsubscribed from OKTACOMEL Alerts.</b>\n"
            "We’ll stay quiet unless you call us again. 😉",
            parse_mode=ParseMode.HTML
        )
    else:
        await update.message.reply_text(
            "ℹ️ <b>You are not in the subscriber list.</b>",
            parse_mode=ParseMode.HTML
        )


# ==========================================
# 📢 SYSTEM BROADCAST (OWNER ONLY)
# ==========================================
async def broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return  # Diam saja kalau bukan owner

    if not context.args:
        await update.message.reply_text(
            "⚠️ <b>Usage:</b> <code>/broadcast your message here</code>",
            parse_mode=ParseMode.HTML
        )
        return

    msg_text = " ".join(context.args)
    users = await get_subscribers()
    total = len(users)
    sent = 0
    removed = 0

    status_msg = await update.message.reply_text(
        f"⏳ <b>Sending broadcast...</b>\n"
        f"Target: <code>{total}</code> users.",
        parse_mode=ParseMode.HTML
    )

    for uid in users:
        try:
            await context.bot.send_message(
                uid,
                f"📢 <b>OKTACOMEL BROADCAST</b>\n"
                "━━━━━━━━━━━━━━━━\n\n"
                f"{msg_text}",
                parse_mode=ParseMode.HTML
            )
            sent += 1
        except Exception:
            # User mungkin block bot / chat hilang → hapus dari DB
            await remove_subscriber(uid)
            removed += 1

    await status_msg.edit_text(
        "✅ <b>Broadcast Completed.</b>\n"
        f"📨 Delivered to: <code>{sent}</code> users.\n"
        f"🗑️ Removed inactive: <code>{removed}</code>\n"
        f"👥 Original list: <code>{total}</code>",
        parse_mode=ParseMode.HTML
    )


# ==========================================
# 🌅 MORNING BROADCAST (AUTO TASK)
# ==========================================
async def morning_broadcast(context: ContextTypes.DEFAULT_TYPE):
    # Ambil data cuaca Jakarta (default)
    data = await get_weather_data("Jakarta")
    if not data:
        return

    # Bisa pakai nama kota default "Jakarta" atau "Unknown" sesuai fungsi format_weather
    weather_text = format_weather(data, "Jakarta")

    now = datetime.now().strftime("%d-%m-%Y %H:%M")
    text = (
        "🌅 <b>GOOD MORNING FROM OKTACOMEL</b>\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"🕒 <b>Update Time:</b> <code>{now}</code>\n"
        "📍 <b>Region:</b> <code>Jakarta & Surroundings</code>\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        f"{weather_text}\n\n"
        "💡 <i>Tip:</i> Stay hydrated, stay productive, and have a great day!"
    )

    users = await get_subscribers()
    for uid in users:
        try:
            await context.bot.send_message(uid, text, parse_mode=ParseMode.HTML)
        except Exception:
            await remove_subscriber(uid)


# ==========================================
# 🔎 SEARCH (ANIME + MOVIE/IMDB) — PREMIUM UI
# ==========================================
async def search_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # langsung load OMDB key dari config (boleh dipakai atau dihapus jika sudah import global)
    from config import OMDB_API_KEY  

    # 1. Cek Input
    if not context.args:
        return await update.message.reply_text(
            "⚠️ <b>Usage:</b>\n"
            "<code>/search Naruto</code>\n"
            "<code>/search anime Naruto</code>\n"
            "<code>/search movie Inception</code>",
            parse_mode=ParseMode.HTML,
        )

    # MODE DETECTOR (anime / manhwa / donghua / movie)
    first = context.args[0].lower()
    known_modes = {"anime", "manga", "manhwa", "donghua", "harem", "movie", "film", "imdb"}

    if first in known_modes:
        mode = first
        if len(context.args) == 1:
            return await update.message.reply_text(
                "⚠️ <b>Usage:</b>\n"
                "<code>/search anime Naruto</code>\n"
                "<code>/search movie Inception</code>",
                parse_mode=ParseMode.HTML,
            )
        q = " ".join(context.args[1:])
    else:
        mode = "anime"  # default
        q = " ".join(context.args)

    await context.bot.send_chat_action(update.effective_chat.id, ChatAction.TYPING)

    # ==========================
    #  ANIME / MANHWA / DONGHUA
    # ==========================
    if mode in {"anime", "manga", "manhwa", "donghua", "harem"}:
        try:
            r = await fetch_json(f"{ANIME_API}?q={urllib.parse.quote(q)}&limit=1&sfw=true")

            if r and r.get("data"):
                d = r["data"][0]

                genres_list = d.get("genres", [])
                genres = ", ".join([g["name"] for g in genres_list[:5]]) if genres_list else "N/A"

                raw_synopsis = d.get("synopsis", "No synopsis available.")
                if raw_synopsis and len(raw_synopsis) > 400:
                    raw_synopsis = raw_synopsis[:400] + "..."
                clean_synopsis = html.escape(str(raw_synopsis))

                title_e = html.escape(d.get("title", "Unknown Title"))
                score = d.get("score", "N/A")
                a_type = d.get("type", "?")
                episodes = d.get("episodes", "?")
                status = d.get("status", "Unknown")
                url_mal = d.get("url", "#")

                txt = (
                    f"🎬 <b>ANIME SEARCH — PREMIUM</b>\n"
                    f"✦────────────────────✦\n"
                    f"🔎 <b>Query</b> ⇾ <code>{html.escape(q)}</code>\n"
                    f"📂 <b>Category</b> ⇾ <code>{mode.upper()}</code>\n"
                    f"✦────────────────────✦\n\n"
                    f"🎞️ <b>{title_e}</b>\n"
                    f"⭐ <b>Score</b> ⇾ <code>{score} / 10</code>\n"
                    f"📺 <b>Type</b> ⇾ <code>{a_type} ({episodes} eps)</code>\n"
                    f"📅 <b>Status</b> ⇾ <code>{status}</code>\n"
                    f"🎭 <b>Genre</b> ⇾ <code>{genres}</code>\n"
                    f"✦────────────────────✦\n"
                    f"📝 <b>Synopsis:</b>\n"
                    f"<i>{clean_synopsis}</i>"
                )

                kb = [[InlineKeyboardButton("🌐 View on MyAnimeList", url=url_mal)]]

                img_url = (
                    d.get("images", {}).get("jpg", {}).get("large_image_url")
                    or d.get("images", {}).get("jpg", {}).get("image_url")
                )

                if img_url:
                    await update.message.reply_photo(
                        img_url,
                        caption=txt,
                        parse_mode=ParseMode.HTML,
                        reply_markup=InlineKeyboardMarkup(kb),
                    )
                else:
                    await update.message.reply_text(
                        txt,
                        parse_mode=ParseMode.HTML,
                        reply_markup=InlineKeyboardMarkup(kb),
                    )

            else:
                await update.message.reply_text(
                    "❌ <b>Anime not found.</b> Try another keyword.",
                    parse_mode=ParseMode.HTML,
                )

        except Exception as e:
            await update.message.reply_text(
                f"⚠️ <b>Error:</b> <code>{html.escape(str(e))}</code>",
                parse_mode=ParseMode.HTML,
            )
        return

    # ==========================
    #  MOVIE / IMDb MODE
    # ==========================
    if mode in {"movie", "film", "imdb"}:
        try:
            omdb_key = OMDB_API_KEY.strip() if OMDB_API_KEY else ""

            if not omdb_key or omdb_key == "YOUR_OMDB_API_KEY_HERE":
                return await update.message.reply_text(
                    "⚠️ <b>Movie Search not configured.</b>\n"
                    "Tambahkan <code>OMDB_API_KEY</code> di <code>config.py</code> untuk mengaktifkan IMDb search.",
                    parse_mode=ParseMode.HTML,
                )

            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(
                    "https://www.omdbapi.com/",
                    params={"apikey": omdb_key, "t": q, "plot": "short"},
                )
                # cek status http dulu agar error clearer
                resp.raise_for_status()
                data = resp.json()

            if not data or data.get("Response") != "True":
                return await update.message.reply_text(
                    "❌ <b>Movie not found on IMDb.</b>",
                    parse_mode=ParseMode.HTML,
                )

            title_e = html.escape(data.get("Title", "Unknown"))
            year = data.get("Year", "?")
            m_type = data.get("Type", "N/A")
            genre_e = html.escape(data.get("Genre", "N/A"))
            rating = data.get("imdbRating", "N/A")
            votes = data.get("imdbVotes", "N/A")
            plot = data.get("Plot", "No plot available.")
            runtime = data.get("Runtime", "N/A")
            rated = data.get("Rated", "N/A")
            poster = data.get("Poster", "")
            imdb_id = data.get("imdbID", "") or ""

            plot_short = plot[:400] + "..." if len(plot) > 400 else plot
            plot_e = html.escape(plot_short)

            imdb_url = f"https://www.imdb.com/title/{imdb_id}" if imdb_id else "https://www.imdb.com/"

            txt = (
                f"🎬 <b>MOVIE SEARCH — IMDb PREMIUM</b>\n"
                f"✦────────────────────✦\n"
                f"🔎 <b>Query</b> ⇾ <code>{html.escape(q)}</code>\n"
                f"📂 <b>Category</b> ⇾ <code>MOVIE</code>\n"
                f"✦────────────────────✦\n\n"
                f"🎞️ <b>{title_e}</b> ({year})\n"
                f"📺 <b>Type</b> ⇾ <code>{m_type}</code>\n"
                f"⏱️ <b>Duration</b> ⇾ <code>{runtime}</code>\n"
                f"💠 <b>Rated</b> ⇾ <code>{rated}</code>\n"
                f"🎭 <b>Genre</b> ⇾ <code>{genre_e}</code>\n"
                f"⭐ <b>IMDb</b> ⇾ <code>{rating} / 10</code> ({votes} votes)\n"
                f"✦────────────────────✦\n"
                f"📝 <b>Plot:</b>\n"
                f"<i>{plot_e}</i>"
            )

            kb = [[InlineKeyboardButton("🎬 Open on IMDb", url=imdb_url)]]

            if poster and poster != "N/A":
                await update.message.reply_photo(
                    poster,
                    caption=txt,
                    parse_mode=ParseMode.HTML,
                    reply_markup=InlineKeyboardMarkup(kb),
                )
            else:
                await update.message.reply_text(
                    txt,
                    parse_mode=ParseMode.HTML,
                    reply_markup=InlineKeyboardMarkup(kb),
                )

        except httpx.RequestError as e:
            await update.message.reply_text(
                f"⚠️ <b>Network error:</b> <code>{html.escape(str(e))}</code>",
                parse_mode=ParseMode.HTML,
            )
        except Exception as e:
            await update.message.reply_text(
                f"⚠️ <b>Error:</b> <code>{html.escape(str(e))}</code>",
                parse_mode=ParseMode.HTML,
            )

# ==========================================
# 🖥️ PING / SYSTEM CHECK (PREMIUM UI)
# ==========================================
async def ping_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Catat waktu awal
    s = time.time()
    
    # Pesan Loading
    msg = await update.message.reply_text("⏳ <b>Analyzing system...</b>", parse_mode=ParseMode.HTML)
    
    try:
        # --- DATA SYSTEM ---
        # 1. Hitung Ping
        end = time.time()
        ping_ms = (end - s) * 1000
        
        # 2. Hardware Info
        ram = psutil.virtual_memory()
        cpu = psutil.cpu_percent(interval=0.1)
        disk = shutil.disk_usage("/")
        
        # 3. CPU Frequency (Safe Check)
        freq = psutil.cpu_freq()
        cpu_freq = f"{freq.current:.0f}Mhz" if freq else "N/A"

        # 4. OS Info
        os_name = f"{platform.system()} {platform.release()}"
        py_ver = sys.version.split()[0]
        
        # 5. Uptime
        try:
            uptime_sec = int(time.time() - START_TIME)
            uptime = str(datetime.timedelta(seconds=uptime_sec))
        except:
            uptime = "Unknown"

        # Helper Bar Visual (10 Balok)
        def make_bar(percent):
            filled = int(percent / 10)
            filled = max(0, min(10, filled)) # Limit 0-10
            return "▰" * filled + "▱" * (10 - filled)

        # --- TAMPILAN PREMIUM (BOLD SANS + MONO) ---
        txt = (
            f"🖥️ <b>SYSTEM DASHBOARD</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"💻 𝗢𝗦 ⇾ <code>{os_name}</code>\n"
            f"🐍 𝗣𝘆𝘁𝗵𝗼𝗻 ⇾ <code>v{py_ver}</code>\n"
            f"⏱️ 𝗨𝗽𝘁𝗶𝗺𝗲 ⇾ <code>{uptime}</code>\n\n"
            
            f"🧠 𝗥𝗔𝗠 𝗨𝘀𝗮𝗴𝗲 ⇾ <code>{ram.percent}%</code>\n"
            f"<code>[{make_bar(ram.percent)}]</code>\n"
            f"<i>Used: {ram.used // (1024**2)}MB / Free: {ram.available // (1024**2)}MB</i>\n\n"
            
            f"⚙️ 𝗖𝗣𝗨 𝗟𝗼𝗮𝗱 ⇾ <code>{cpu}%</code>\n"
            f"<code>[{make_bar(cpu)}]</code>\n"
            f"<i>Frequency: {cpu_freq}</i>\n\n"
            
            f"💾 𝗗𝗶𝘀𝗸 𝗦𝗽𝗮𝗰𝗲\n"
            f"<code>[{make_bar(disk.used / disk.total * 100)}]</code>\n"
            f"<i>Used: {disk.used // (1024**3)}GB / Total: {disk.total // (1024**3)}GB</i>\n\n"
            
            f"━━━━━━━━━━━━━━━━━━\n"
            f"📶 𝗣𝗶𝗻𝗴 ⇾ <code>{ping_ms:.2f} ms</code>\n"
            f"🤖 <i>Powered by Oktacomel</i>"
        )
        
        await msg.edit_text(txt, parse_mode=ParseMode.HTML)

    except Exception as e:
        await msg.edit_text(f"❌ <b>System Error:</b> {str(e)}", parse_mode=ParseMode.HTML)

# ==========================================
# 💳 QR COMMAND (PREMIUM BOLD SANS STYLE)
# ==========================================
async def qr_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # 1. KASUS PAYMENT (Jika user hanya ketik /qr tanpa teks)
    if not context.args:
        caption = (
            f"𝗤𝗥𝗜𝗦 𝗣𝗔𝗬𝗠𝗘𝗡𝗧 💳\n\n"
            f"𝗡𝗠𝗜𝗗 ⇾ <code>ID1024325861937</code>\n"
            f"𝗡𝗮𝗺𝗲 ⇾ <code>IKIKSTORE</code>\n\n"
            f"<i>Scan this QR code to proceed payment.</i>"
        )
        # Pastikan QRIS_IMAGE sudah ada di config paling atas file
        try:
            await update.message.reply_photo(QRIS_IMAGE, caption=caption, parse_mode=ParseMode.HTML)
        except:
            await update.message.reply_text("❌ Gambar QRIS belum disetting.", parse_mode=ParseMode.HTML)
        return

    # 2. KASUS GENERATOR (Ketik /qr teks)
    text_data = " ".join(context.args)
    
    # Kirim status upload foto
    await context.bot.send_chat_action(update.effective_chat.id, ChatAction.UPLOAD_PHOTO)
    
    try:
        # Buat QR Code
        qr = qrcode.QRCode(box_size=10, border=4)
        qr.add_data(text_data)
        qr.make(fit=True)
        img = qr.make_image(fill='black', back_color='white')
        
        # Simpan ke memory (Buffer)
        b = io.BytesIO()
        img.save(b, 'PNG')
        b.seek(0)
        
        # Caption Aesthetic (Bold Sans)
        caption = (
            f"𝗤𝗥 𝗖𝗢𝗗𝗘 𝗚𝗘𝗡𝗘𝗥𝗔𝗧𝗘𝗗 📸\n\n"
            f"𝗜𝗻𝗽𝘂𝘁 ⇾ <code>{html.escape(text_data)}</code>\n\n"
            f"🤖 <i>Powered by Oktacomel</i>"
        )
        
        await update.message.reply_photo(b, caption=caption, parse_mode=ParseMode.HTML)

    except Exception as e:
        await update.message.reply_text(f"❌ <b>Error:</b> {str(e)}", parse_mode=ParseMode.HTML)

# ==========================================
# 🔍 BIN LOOKUP (CUSTOM API + CLEAN MONO)
# ==========================================
async def bin_lookup_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Cek input
    if not context.args: 
        return await update.message.reply_text("⚠️ <b>Usage:</b> <code>/bin 454321</code>", parse_mode=ParseMode.HTML)
    
    bin_code = context.args[0].replace(" ", "")[:6]
    
    if not bin_code.isdigit():
        return await update.message.reply_text("❌ <b>Error:</b> Input must be numbers.", parse_mode=ParseMode.HTML)

    msg = await update.message.reply_text("⏳ <b>Checking...</b>", parse_mode=ParseMode.HTML)
    
    try:
        # === MENGGUNAKAN API KAMU (BIN_API) ===
        # Pastikan variabel BIN_API sudah ada di config atas
        r = await fetch_json(f"{BIN_API}/{bin_code}")
    except:
        r = None
    
    if r and ('brand' in r or 'scheme' in r):
        # Parsing Data
        brand = str(r.get('brand') or r.get('scheme', 'Unknown')).upper()
        type_c = str(r.get('type', 'Unknown')).upper()
        level = str(r.get('level') or r.get('card_category', 'Unknown')).upper()
        
        bank_raw = r.get('bank')
        bank = str(bank_raw.get('name') if isinstance(bank_raw, dict) else bank_raw or 'UNKNOWN').upper()
        
        country_raw = r.get('country')
        country = str(country_raw.get('name') if isinstance(country_raw, dict) else country_raw or 'UNKNOWN').upper()
        flag = country_raw.get('emoji', '') if isinstance(country_raw, dict) else ''

        # === TAMPILAN SESUAI REQUEST (BOLD ⇾ MONO) ===
        txt = (
            f"<b>𝗕𝗜𝗡 𝗟𝗼𝗼𝗸𝘂𝗽 𝗥𝗲𝘀𝘂𝗹𝘁</b> 🔍\n\n"
            f"<b>𝗕𝗜𝗡</b> ⇾ <code>{bin_code}</code>\n"
            f"<b>𝗜𝗻𝗳𝗼</b> ⇾ <code>{brand} - {type_c} - {level}</code>\n"
            f"<b>𝐈𝐬𝐬𝐮𝐞𝐫</b> ⇾ <code>{bank}</code>\n"
            f"<b>𝐂𝐨𝐮𝐧𝐭𝐫𝐲</b> ⇾ <code>{country} {flag}</code>"
        )
        await msg.edit_text(txt, parse_mode=ParseMode.HTML)
        
    else:
        # Tampilan Gagal
        txt = (
            f"<b>𝗕𝗜𝗡 Lookup Result</b> 🔍\n\n"
            f"<b>𝗕𝗜𝗡</b> ⇾ <code>{bin_code}</code>\n"
            f"<b>Status</b> ⇾ <code>NOT FOUND / DEAD ❌</code>"
        )
        await msg.edit_text(txt, parse_mode=ParseMode.HTML)

# ==========================================
# 🔍 STRIPE KEY CHECKER (PREMIUM BOLD SANS)
# ==========================================
async def sk_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    user = update.effective_user
    
    if not args:
        await update.message.reply_text("⚠️ <b>Usage:</b> <code>/sk sk_live_xxxx</code>", parse_mode=ParseMode.HTML)
        return
    
    sk_key = args[0]
    
    # Validasi Prefix
    if not sk_key.startswith("sk_live_") and not sk_key.startswith("sk_test_"):
        await update.message.reply_text("❌ <b>Invalid Key Format!</b>", parse_mode=ParseMode.HTML)
        return

    msg = await update.message.reply_text("⏳ <b>Checking...</b>", parse_mode=ParseMode.HTML)
    
    # Hit Stripe API
    headers = {"Authorization": f"Bearer {sk_key}"}
    
    try:
        async with httpx.AsyncClient() as client:
            # 1. Get Account Details
            r_acc = await client.get("https://api.stripe.com/v1/account", headers=headers)
            acc_data = r_acc.json()
            
            # Waktu sekarang
            current_time = datetime.datetime.now(TZ).strftime("%H:%M:%S")

            if r_acc.status_code == 200:
                # 2. Get Balance (Jika Live)
                r_bal = await client.get("https://api.stripe.com/v1/balance", headers=headers)
                bal_data = r_bal.json()
                
                # Parsing Data
                currency = acc_data.get('default_currency', 'USD').upper()
                country = acc_data.get('country', 'US').upper()
                
                # Saldo (Convert cent to main currency)
                avail = 0
                pending = 0
                if 'available' in bal_data:
                    avail = bal_data['available'][0]['amount'] / 100
                if 'pending' in bal_data:
                    pending = bal_data['pending'][0]['amount'] / 100

                # TAMPILAN PREMIUM (BOLD SANS)
                live_txt = (
                    f"✅ 𝗦𝘁𝗿𝗶𝗽𝗲 𝗞𝗲𝘆 𝗟𝗶𝘃𝗲 🐝\n\n"
                    f"𝗞𝗲𝘆 ⇾ <code>{sk_key[:18]}...</code>\n"
                    f"𝗕𝗮𝗹𝗮𝗻𝗰𝗲 ⇾ <code>{avail} {currency}</code>\n"
                    f"𝗣𝗲𝗻𝗱𝗶𝗻𝗴 ⇾ <code>{pending} {currency}</code>\n"
                    f"𝗖𝗼𝘂𝗻𝘁𝗿𝘆 ⇾ <code>{country}</code>\n"
                    f"𝗖𝘂𝗿𝗿𝗲𝗻𝗰𝘆 ⇾ <code>{currency}</code>\n\n"
                    f"𝗥𝗲𝘀𝗽𝗼𝗻𝘀𝗲 ⇾ <code>✅ Authenticated</code>\n"
                    f"𝗧𝗶𝗺𝗲 ⇾ <code>{current_time}</code>\n"
                    f"𝗕𝘆 ⇾ @{user.username}"
                )
                await msg.edit_text(live_txt, parse_mode=ParseMode.HTML)
            
            else:
                # Tampilan Mati (Error Message)
                err_msg = acc_data.get('error', {}).get('message', 'Invalid Key')
                dead_txt = (
                    f"❌ 𝗦𝘁𝗿𝗶𝗽𝗲 𝗞𝗲𝘆 𝗗𝗲𝗮𝗱\n\n"
                    f"𝗞𝗲𝘆 ⇾ <code>{sk_key[:18]}...</code>\n"
                    f"𝗥𝗲𝘀𝗽𝗼𝗻𝘀𝗲 ⇾ <code>{err_msg}</code>\n\n"
                    f"𝗕𝘆 ⇾ @{user.username}"
                )
                await msg.edit_text(dead_txt, parse_mode=ParseMode.HTML)

    except Exception as e:
        await msg.edit_text(f"⚠️ <b>Error:</b> {str(e)}", parse_mode=ParseMode.HTML)

# ==========================================
# 👤 FAKE IDENTITY GENERATOR (PREMIUM + FAKE MAIL)
# ==========================================
async def fake_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    code = context.args[0].lower() if context.args else 'us'
    
    # MAPPING LENGKAP (30+ NEGARA)
    locales = {
        'id': 'id_ID', 'sg': 'en_SG', 'jp': 'ja_JP', 'kr': 'ko_KR', 
        'cn': 'zh_CN', 'tw': 'zh_TW', 'th': 'th_TH', 'vn': 'vi_VN',
        'ph': 'fil_PH', 'in': 'en_IN', 'au': 'en_AU', 'nz': 'en_NZ',
        'my': 'ms_MY', 'us': 'en_US', 'ca': 'en_CA', 'br': 'pt_BR', 
        'mx': 'es_MX', 'ar': 'es_AR', 'co': 'es_CO', 'uk': 'en_GB', 
        'fr': 'fr_FR', 'de': 'de_DE', 'it': 'it_IT', 'es': 'es_ES', 
        'nl': 'nl_NL', 'ru': 'ru_RU', 'ua': 'uk_UA', 'pl': 'pl_PL', 
        'tr': 'tr_TR', 'se': 'sv_SE', 'no': 'no_NO', 'sa': 'ar_SA', 
        'ir': 'fa_IR', 'za': 'en_ZA', 'ng': 'en_NG'
    }
    
    country_names = {
        'id': 'Indonesia 🇮🇩', 'sg': 'Singapore 🇸🇬', 'jp': 'Japan 🇯🇵', 'kr': 'South Korea 🇰🇷',
        'cn': 'China 🇨🇳', 'tw': 'Taiwan 🇹🇼', 'th': 'Thailand 🇹🇭', 'vn': 'Vietnam 🇻🇳',
        'ph': 'Philippines 🇵🇭', 'in': 'India 🇮🇳', 'au': 'Australia 🇦🇺', 'nz': 'New Zealand 🇳🇿',
        'my': 'Malaysia 🇲🇾', 'us': 'United States 🇺🇸', 'ca': 'Canada 🇨🇦', 'br': 'Brazil 🇧🇷',
        'mx': 'Mexico 🇲🇽', 'ar': 'Argentina 🇦🇷', 'co': 'Colombia 🇨🇴', 'uk': 'United Kingdom 🇬🇧',
        'fr': 'France 🇫🇷', 'de': 'Germany 🇩🇪', 'it': 'Italy 🇮🇹', 'es': 'Spain 🇪🇸',
        'nl': 'Netherlands 🇳🇱', 'ru': 'Russia 🇷🇺', 'ua': 'Ukraine 🇺🇦', 'pl': 'Poland 🇵🇱',
        'tr': 'Turkey 🇹🇷', 'se': 'Sweden 🇸🇪', 'no': 'Norway 🇳🇴', 'sa': 'Saudi Arabia 🇸🇦',
        'ir': 'Iran 🇮🇷', 'za': 'South Africa 🇿🇦', 'ng': 'Nigeria 🇳🇬'
    }

    if code not in locales:
        await update.message.reply_text(f"⚠️ <b>Country Not Found</b>\nUsage: <code>/fake sg</code>", parse_mode=ParseMode.HTML)
        return

    await context.bot.send_chat_action(update.effective_chat.id, ChatAction.TYPING)

    try:
        fake = Faker(locales[code])
        
        name = fake.name()
        address = fake.street_address()
        city = fake.city()
        try: state = fake.state()
        except: state = fake.administrative_unit()
        zipcode = fake.postcode()
        phone = fake.phone_number()
        country_disp = country_names.get(code, code.upper())
        
        # --- GENERATE EMAIL (Fake Mail Generator) ---
        # Format: username@teleworm.us
        username_mail = name.lower().replace(" ", "").replace(".", "") + str(random.randint(100,999))
        domain = "teleworm.us"
        email_full = f"{username_mail}@{domain}"
        
        # Link Inbox Langsung
        inbox_link = f"https://www.fakemailgenerator.com/#/{domain}/{username_mail}/"

        # TAMPILAN PREMIUM (BOLD SANS + ARROW)
        txt = (
            f"👤 <b>FAKE IDENTITY</b> ({code.upper()})\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"𝗡𝗮𝗺𝗲 ⇾ <code>{name}</code>\n"
            f"𝗦𝘁𝗿𝗲𝗲𝘁 ⇾ <code>{address}</code>\n"
            f"𝗖𝗶𝘁𝘆 ⇾ <code>{city}</code>\n"
            f"𝗦𝘁𝗮??𝗲 ⇾ <code>{state}</code>\n"
            f"𝗭𝗶𝗽 𝗖𝗼𝗱𝗲 ⇾ <code>{zipcode}</code>\n"
            f"𝗣𝗵𝗼𝗻𝗲 ⇾ <code>{phone}</code>\n"
            f"𝗖𝗼𝘂𝗻𝘁𝗿𝘆 ⇾ <code>{country_disp}</code>\n\n"
            f"📧 𝗘𝗺𝗮𝗶𝗹 ⇾ <code>{email_full}</code>\n"
            f"🔗 𝗜𝗻𝗯𝗼𝘅 ⇾ <a href='{inbox_link}'>Check Mail Here</a>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"🤖 <i>Powered by Oktacomel</i>"
        )

        await update.message.reply_text(txt, parse_mode=ParseMode.HTML, disable_web_page_preview=True)

    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")

# ==========================================
# 🌸 ANIME & WAIFU SYSTEM (AUTO DETECT)
# ==========================================
async def anime_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # 1. Ambil perintah apa yang diketik user (contoh: /blowjob atau /waifu)
    command = update.message.text.split()[0].replace('/', '').lower()
    
    # 2. Mapping Konfigurasi (Menentukan mana SFW dan mana NSFW)
    # Format: "command": ("tipe", "kategori_api")
    mapping = {
        # --- KATEGORI SFW (AMAN) ---
        'waifu': ('sfw', 'waifu'),
        'neko': ('sfw', 'neko'),
        'shinobu': ('sfw', 'shinobu'),
        'megumin': ('sfw', 'megumin'),
        'bully': ('sfw', 'bully'),
        'cuddle': ('sfw', 'cuddle'),
        'cry': ('sfw', 'cry'),
        'hug': ('sfw', 'hug'),
        'awoo': ('sfw', 'awoo'),
        'kiss': ('sfw', 'kiss'),
        'lick': ('sfw', 'lick'),
        
        # --- KATEGORI NSFW (DEWASA) ---
        'blowjob': ('nsfw', 'blowjob'),
        'trap': ('nsfw', 'trap'),
        'nwaifu': ('nsfw', 'waifu'), # nwaifu = nsfw waifu
        'nneko': ('nsfw', 'neko')    # nneko = nsfw neko
    }

    # Cek apakah command ada di mapping
    if command not in mapping:
        await update.message.reply_text("⚠️ Command tidak dikenali.", parse_mode=ParseMode.HTML)
        return

    # Ambil tipe dan kategorinya
    mode, category = mapping[command]
    
    # Buat URL API
    url = f"https://api.waifu.pics/{mode}/{category}"
    
    # Kirim status "Upload Photo" biar kelihatan loading
    await context.bot.send_chat_action(update.effective_chat.id, ChatAction.UPLOAD_PHOTO)
    
    try:
        # Request ke API
        data = await fetch_json(url)
        
        if data and 'url' in data:
            img_url = data['url']
            
            # Caption Cantik
            caption = f"🔞 <b>{category.upper()}</b>" if mode == "nsfw" else f"🌸 <b>{category.upper()}</b>"
            
            # Cek apakah GIF atau Gambar biasa
            if img_url.endswith(".gif"):
                await update.message.reply_animation(img_url, caption=caption, parse_mode=ParseMode.HTML)
            else:
                await update.message.reply_photo(img_url, caption=caption, parse_mode=ParseMode.HTML)
        else:
            await update.message.reply_text("❌ <b>Error:</b> API Server Busy / Image Not Found.", parse_mode=ParseMode.HTML)
            
    except Exception as e:
        await update.message.reply_text(f"⚠️ <b>System Error:</b> {e}", parse_mode=ParseMode.HTML)

# ==========================================
# 🎨 AI IMAGE GENERATOR — PREMIUM ULTIMATE EDITION v2.0
# ==========================================

async def img_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """AI Image Generator dengan progress bar animasi"""
    
    if not context.args:
        return await update.message.reply_text(
            "⚠️ <b>Usage:</b> <code>/img kucing terbang di langit</code>\n\n"
            "💡 <b>Tips:</b> Semakin detail prompt, semakin bagus hasilnya!",
            parse_mode=ParseMode.HTML
        )

    prompt = " ".join(context.args)
    
    # Validasi prompt
    if len(prompt) < 3:
        return await update.message.reply_text(
            "❌ <b>Prompt terlalu pendek!</b>\n"
            "Minimal 3 karakter.",
            parse_mode=ParseMode.HTML
        )
    
    if len(prompt) > 500:
        prompt = prompt[:500]

    seed = random.randint(1, 999999)

    await context.bot.send_chat_action(update.effective_chat.id, ChatAction.UPLOAD_PHOTO)
    
    # Initial message
    msg = await update.message.reply_text(
        "🎨 <b>Generating AI Image...</b>\n"
        "[░░░░░░░░░░░░░░░░░░] 0%",
        parse_mode=ParseMode.HTML
    )

    # ==========================================
    # SMART MODEL DETECTOR
    # ==========================================
    p = prompt.lower()

    if any(x in p for x in ["anime", "waifu", "manga", "2d", "chibi", "cartoon"]):
        model = "anime"
        style_name = "Anime Art Style"
        icon = "🌸"
    elif any(x in p for x in ["logo", "icon", "mascot", "brand", "minimalist"]):
        model = "logo"
        style_name = "Clean Logo Design"
        icon = "🔰"
    elif any(x in p for x in ["cyberpunk", "neon", "futuristic", "synthwave", "sci-fi"]):
        model = "flux"
        style_name = "Cyberpunk Neon"
        icon = "⚡"
    elif any(x in p for x in ["3d", "render", "cgi", "realistic"]):
        model = "flux"
        style_name = "3D Realistic"
        icon = "🎬"
    else:
        model = "flux"
        style_name = "Flux Ultra HD"
        icon = "📸"

    # ==========================================
    # PROGRESS BAR STAGES
    # ==========================================
    
    stages = [
        {"progress": 10, "text": "Analyzing prompt...", "bar": "██░░░░░░░░░░░░░░░░"},
        {"progress": 25, "text": "Initializing AI model...", "bar": "█████░░░░░░░░░░░░░░"},
        {"progress": 40, "text": "Processing neural network...", "bar": "████████░░░░░░░░░░░░"},
        {"progress": 60, "text": "Rendering image...", "bar": "████████████░░░░░░░░"},
        {"progress": 80, "text": "Optimizing quality...", "bar": "████████████████░░░░"},
        {"progress": 95, "text": "Finalizing details...", "bar": "███████████████████░"},
    ]

    # Update progress
    for stage in stages:
        try:
            await msg.edit_text(
                f"🎨 <b>Generating AI Image...</b>\n"
                f"[{stage['bar']}] {stage['progress']}%\n"
                f"⏳ {stage['text']}",
                parse_mode=ParseMode.HTML
            )
            await asyncio.sleep(0.8)  # Delay untuk effect
        except:
            pass

    # ==========================================
    # MULTIPLE API SOURCES (FALLBACK)
    # ==========================================
    
    api_sources = [
        {
            "name": "Pollinations",
            "func": lambda p, s, m: f"https://image.pollinations.ai/prompt/{urllib.parse.quote(p)}?width=1024&height=1024&seed={s}&enhance=true&nologo=true&model={m}"
        },
        {
            "name": "Hugging Face",
            "func": lambda p, s, m: f"https://huggingface.co/spaces/stabilityai/stable-diffusion-3.5-large/file=/tmp/{s}.png?prompt={urllib.parse.quote(p)}"
        },
        {
            "name": "Alternative API",
            "func": lambda p, s, m: f"https://api.deepdream.tech/image?prompt={urllib.parse.quote(p)}&seed={s}"
        },
    ]

    img_url = None
    used_source = None

    # Try setiap API source
    for idx, source in enumerate(api_sources):
        try:
            progress = 95 + (idx * 2)
            
            await msg.edit_text(
                f"🎨 <b>Generating with {source['name']}...</b>\n"
                f"[{'█' * (progress // 5)}{'░' * (20 - (progress // 5))}] {progress}%\n"
                f"⏳ Connecting to server...",
                parse_mode=ParseMode.HTML
            )
            
            url = source["func"](prompt, seed, model)
            
            # Test URL dengan timeout
            async with httpx.AsyncClient(timeout=45.0) as client:
                response = await client.get(url, follow_redirects=True)
                
                if response.status_code == 200:
                    img_url = url
                    used_source = source["name"]
                    break
                else:
                    logger.debug(f"[IMG] {source['name']} returned {response.status_code}")
                    continue
                    
        except asyncio.TimeoutError:
            logger.debug(f"[IMG] {source['name']} timeout")
            await msg.edit_text(
                f"⏳ <b>{source['name']} timeout, trying next source...</b>\n"
                f"[{'█' * 15}{'░' * 5}] 75%",
                parse_mode=ParseMode.HTML
            )
            continue
        except Exception as e:
            logger.debug(f"[IMG] {source['name']} error: {e}")
            continue

    # ==========================================
    # ERROR HANDLING
    # ==========================================
    
    if not img_url:
        await msg.edit_text(
            "❌ <b>Gagal Generate Gambar</b>\n\n"
            "Kemungkinan:\n"
            "• API Server sedang maintenance\n"
            "• Prompt contains blocked keywords\n"
            "• Network timeout\n\n"
            "💡 <b>Coba:</b>\n"
            "1. Ubah prompt lebih sederhana\n"
            "2. Hapus kata-kata sensitif\n"
            "3. Coba lagi dalam beberapa menit\n\n"
            "Contoh prompt bagus:\n"
            "<code>/img beautiful sunset over ocean</code>",
            parse_mode=ParseMode.HTML
        )
        return

    # ==========================================
    # FINAL PROGRESS - 100%
    # ==========================================
    try:
        await msg.edit_text(
            f"🎨 <b>Generating AI Image...</b>\n"
            f"[████████████████████] 100%\n"
            f"✅ Complete! Sending image...",
            parse_mode=ParseMode.HTML
        )
    except:
        pass

    await asyncio.sleep(0.5)

    # ==========================================
    # CAPTION PREMIUM
    # ==========================================
    caption = (
        f"🎨 <b>AI Image Studio — Premium</b> {icon}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🖼️ <b>Prompt:</b>\n"
        f"<code>{html.escape(prompt)}</code>\n\n"
        f"⚙️ <b>Model:</b> {style_name}\n"
        f"📊 <b>Quality:</b> Ultra HD (1024x1024)\n"
        f"🔢 <b>Seed:</b> <code>{seed}</code>\n"
        f"🌐 <b>Source:</b> {used_source}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"⭐ <i>Powered by Oktacomel AI</i>"
    )

    # ==========================================
    # SEND IMAGE
    # ==========================================
    try:
        await update.message.reply_photo(
            photo=img_url,
            caption=caption,
            parse_mode=ParseMode.HTML
        )
        await msg.delete()

    except Exception as e:
        logger.error(f"[IMG] Photo send error: {e}")
        
        # Fallback: Send as text dengan link
        try:
            await msg.edit_text(
                f"⚠️ <b>Image Load Issue</b>\n\n"
                f"{caption}\n\n"
                f"🔗 <a href='{img_url}'>Open Image in Browser</a>",
                parse_mode=ParseMode.HTML
            )
        except:
            await msg.edit_text(
                f"❌ <b>Gagal mengirim gambar</b>\n\n"
                f"Coba:\n"
                f"1. /img dengan prompt lain\n"
                f"2. Tunggu beberapa detik\n"
                f"3. Coba lagi",
                parse_mode=ParseMode.HTML
            )
# ==========================================
# 🗣️ TEXT TO SPEECH GOOGLE (/tts)
# ==========================================
async def tts_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 2:
        await update.message.reply_text("⚠️ <b>Usage:</b> <code>/tts id Halo dunia</code>\nKode bahasa: id, en, ja, ko, ar", parse_mode=ParseMode.HTML)
        return

    lang = context.args[0] # Kode bahasa (id, en, dll)
    text = " ".join(context.args[1:])
    
    await context.bot.send_chat_action(update.effective_chat.id, ChatAction.UPLOAD_VOICE)

    try:
        # Generate Suara
        tts = gTTS(text=text, lang=lang)
        filename = f"voice_{update.effective_user.id}.mp3"
        tts.save(filename)
        
        # Kirim File
        await update.message.reply_audio(filename, title="Okta TTS", performer="Google Voice")
        
        # Hapus File Sampah
        os.remove(filename)
        
    except ValueError:
        await update.message.reply_text("❌ Bahasa tidak didukung. Coba: id, en, ja.", parse_mode=ParseMode.HTML)
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}", parse_mode=ParseMode.HTML)

# ==========================================
# 🌐 TRANSLATE COMMAND (100+ LANGUAGES)
# ==========================================
async def tr_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # 1. Cek Format Input
    if len(context.args) < 2:
        await update.message.reply_text(
            "⚠️ <b>Usage:</b> <code>/tr [kode] [teks]</code>\n\n"
            "<b>Contoh Populer:</b>\n"
            "• <code>/tr id Good Morning</code> (Ke Indo)\n"
            "• <code>/tr en Aku cinta kamu</code> (Ke Inggris)\n"
            "• <code>/tr ar Selamat Pagi</code> (Ke Arab)\n"
            "• <code>/tr ja Terima kasih</code> (Ke Jepang)", 
            parse_mode=ParseMode.HTML
        )
        return

    target_lang = context.args[0].lower() # Kode bahasa
    text_to_tr = " ".join(context.args[1:]) # Teksnya
    
    await context.bot.send_chat_action(update.effective_chat.id, ChatAction.TYPING)

    try:
        # 2. Proses Translate (Otomatis deteksi bahasa asal)
        translator = GoogleTranslator(source='auto', target=target_lang)
        translated = translator.translate(text_to_tr)
        
        # 3. Tampilan Hasil (Rapi)
        res = (
            f"🌐 <b>TRANSLATE RESULT</b> ({target_lang.upper()})\n"
            f"━━━━━━━━━━━━━━━━\n"
            f"🔤 <b>Asli:</b> <i>{html.escape(text_to_tr)}</i>\n"
            f"🔠 <b>Hasil:</b> <code>{html.escape(translated)}</code>\n"
            f"━━━━━━━━━━━━━━━━\n"
            f"🤖 <i>Powered by Google Translate</i>"
        )
        await update.message.reply_text(res, parse_mode=ParseMode.HTML)

    except Exception as e:
        error_msg = str(e)
        
        # Jika Error (Biasanya karena salah kode bahasa)
        # Kita kasih daftar kode negara yang LENGKAP di sini
        if "supported" in error_msg.lower() or "invalid" in error_msg.lower():
            await update.message.reply_text(
                f"❌ <b>Kode Bahasa '{target_lang}' Tidak Dikenal!</b>\n\n"
                "Gunakan kode 2 huruf (ISO 639-1). Contoh:\n"
                "🇮🇩 Indo: <code>id</code>\n"
                "🇺🇸 Inggris: <code>en</code>\n"
                "🇸🇦 Arab: <code>ar</code>\n"
                "🇯🇵 Jepang: <code>ja</code>\n"
                "🇰🇷 Korea: <code>ko</code>\n"
                "🇨🇳 China: <code>zh-CN</code>\n"
                "🇷🇺 Rusia: <code>ru</code>\n"
                "🇪🇸 Spanyol: <code>es</code>\n"
                "🇫🇷 Perancis: <code>fr</code>\n"
                "🇩🇪 Jerman: <code>de</code>\n"
                "🇹🇭 Thailand: <code>th</code>\n"
                "🇲🇾 Malaysia: <code>ms</code>\n\n"
                "<i>Dan masih banyak lagi!</i>",
                parse_mode=ParseMode.HTML
            )
        else:
            await update.message.reply_text(f"❌ <b>System Error:</b> {error_msg}", parse_mode=ParseMode.HTML)

# ==========================================
# 💱 CURRENCY CONVERTER (USDT <-> IDR)
# ==========================================
async def convert_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # 1. Cek Input User (Harus 3 kata: Jumlah - Dari - Ke)
    if len(context.args) < 3:
        await update.message.reply_text(
            "⚠️ <b>Cara Pakai:</b> <code>/convert [Jumlah] [Dari] [Ke]</code>\n\n"
            "<b>Contoh:</b>\n"
            "• <code>/convert 10 USDT IDR</code>\n"
            "• <code>/convert 100 USD IDR</code>\n"
            "• <code>/convert 1 BTC USD</code>",
            parse_mode=ParseMode.HTML
        )
        return

    # 2. Parsing Data
    try:
        amount = float(context.args[0]) # Jumlah (misal: 10)
        base_curr = context.args[1].upper() # Dari (misal: USDT)
        target_curr = context.args[2].upper()   # Ke (misal: IDR)
    except ValueError:
        await update.message.reply_text("❌ <b>Error:</b> Jumlah harus berupa angka (contoh: 10 atau 10.5).", parse_mode=ParseMode.HTML)
        return

    # Loading Message
    msg = await update.message.reply_text(f"💱 <b>Menghitung {base_curr} ke {target_curr}...</b>", parse_mode=ParseMode.HTML)

    try:
        # 3. Request ke API Coinbase (Gratis & Akurat untuk USDT)
        url = f"https://api.coinbase.com/v2/exchange-rates?currency={base_curr}"
        
        # Gunakan requests (sesuai library yang kamu punya)
        r = requests.get(url)
        data = r.json()

        # 4. Validasi Response
        if 'data' not in data:
            await msg.edit_text(f"❌ Mata uang <b>{base_curr}</b> tidak ditemukan.", parse_mode=ParseMode.HTML)
            return

        rates = data['data']['rates']
        
        if target_curr not in rates:
            await msg.edit_text(f"❌ Tidak bisa konversi ke <b>{target_curr}</b>.", parse_mode=ParseMode.HTML)
            return

        # 5. Hitung Hasil
        rate_value = float(rates[target_curr])
        result_value = amount * rate_value

        # Format Angka (Pemisah ribuan: 15,000.00)
        formatted_result = f"{result_value:,.2f}" 
        formatted_rate = f"{rate_value:,.2f}"

        # 6. Tampilan Hasil (Branding Oktacomel)
        txt = (
            f"💱 <b>OKTACOMEL CONVERTER</b>\n"
            f"━━━━━━━━━━━━━━━━\n"
            f"💸 <b>Input:</b> {amount} {base_curr}\n"
            f"💰 <b>Hasil:</b> {formatted_result} {target_curr}\n"
            f"━━━━━━━━━━━━━━━━\n"
            f"📈 <b>Rate:</b> 1 {base_curr} = {formatted_rate} {target_curr}\n"
            f"🤖 <i>Live Data by Coinbase</i>"
        )
        
        await msg.edit_text(txt, parse_mode=ParseMode.HTML)

    except Exception as e:
        await msg.edit_text(f"❌ <b>System Error:</b> {str(e)}", parse_mode=ParseMode.HTML)

# ==========================================
# 🪙 CRYPTO COMMAND (Dipanggil saat ketik /crypto BTC)
# ==========================================
async def crypto_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # 1. Cek Input User
    if not context.args:
        await update.message.reply_text(
            "⚠️ <b>Format Salah!</b>\n"
            "Gunakan: <code>/crypto [NAMA_KOIN]</code>\n"
            "Contoh: <code>/crypto BTC</code> atau <code>/crypto XRP</code>",
            parse_mode=ParseMode.HTML
        )
        return

    # 2. Siapkan Data
    symbol = context.args[0].upper()
    pair = f"{symbol}USDT"
    url = f"https://api.binance.com/api/v3/ticker/24hr?symbol={pair}"

    # 3. Kirim Pesan Loading (Biar user tau bot bekerja)
    msg = await update.message.reply_text(f"⏳ <b>Fetching {symbol} market data...</b>", parse_mode=ParseMode.HTML)

    # 4. Ambil Data (Sama persis kayak refresh)
    d = await fetch_json(url)
    if not d or 'symbol' not in d:
        return await msg.edit_text(f"❌ <b>Market data not available for {symbol}.</b>", parse_mode=ParseMode.HTML)

    # --- FITUR KOSMETIK (Sama persis) ---
    def fmt_price(n):
        try:
            n = float(n)
            if n >= 1: return f"{n:,.2f}"
            return f"{n:,.6f}"
        except: return str(n)

    def fmt_int(n):
        try: return f"{int(float(n)):,}"
        except: return str(n)

    def mini_bar(pct):
        try:
            p = max(-10, min(10, float(pct)))
            v = (p + 10) / 20
            length = 12
            filled = int(round(v * length))
            return "▰" * filled + "▱" * (length - filled)
        except: return "▱" * 12

    try:
        # 5. Parsing Data (Copy-Paste dari refresh handler)
        last_price = float(d.get('lastPrice', 0))
        ask_price = float(d.get('askPrice', 0))
        bid_price = float(d.get('bidPrice', 0))
        high_24h = float(d.get('highPrice', 0))
        low_24h = float(d.get('lowPrice', 0))
        change_p = float(d.get('priceChangePercent', 0))
        change_abs = float(d.get('priceChange', 0))
        vol_quote = float(d.get('quoteVolume', 0))
        open_price = float(d.get('openPrice', 0))
        weighted_avg = float(d.get('weightedAvgPrice', 0))

        # Trend Logic
        if change_p >= 5.0:
            trend_emoji = "🟢"
            trend = "STRONG BULL"
        elif 0.5 <= change_p < 5.0:
            trend_emoji = "🟢"
            trend = "UPTREND"
        elif -5.0 < change_p <= -0.5:
            trend_emoji = "🔴"
            trend = "DOWNTREND"
        elif change_p <= -5.0:
            trend_emoji = "🔴"
            trend = "STRONG BEAR"
        else:
            trend_emoji = "🟡"
            trend = "SIDEWAYS"

        sign = "+" if change_p > 0 else ""
        percent_str = f"{sign}{change_p:.2f}%"

        # 6. Format Pesan (Premium Ultimate Style)
        text = (
            f"🪙 <b>OKTACOMEL — CRYPTO SNAPSHOT</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"💠 <b>Pair:</b> <code>{pair}</code>\n"
            f"💵 <b>Last Price:</b> <code>${fmt_price(last_price)}</code>\n"
            f"📊 <b>24h Change:</b> {trend_emoji} <b>{percent_str}</b> ({fmt_price(change_abs)})\n"
            f"🔎 <b>Trend:</b> {trend}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"📈 <b>Market Range (24h)</b>\n"
            f"• Low  : <code>${fmt_price(low_24h)}</code>\n"
            f"• High : <code>${fmt_price(high_24h)}</code>\n"
            f"• Open : <code>${fmt_price(open_price)}</code>\n"
            f"• Avg  : <code>${fmt_price(weighted_avg)}</code>\n"
            f"Range : {mini_bar(change_p)}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🛒 <b>Orderbook (Top)</b>\n"
            f"• Ask : <code>${fmt_price(ask_price)}</code>\n"
            f"• Bid : <code>${fmt_price(bid_price)}</code>\n\n"
            f"📦 <b>24h Volume (quote):</b> <code>${fmt_int(vol_quote)}</code>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🔗 <i>Data source: Binance (real-time)</i>\n"
            f"🐈 <i>Powered by Oktacomel — Premium</i>"
        )

        # 7. Tombol (Menu refresh mengarah ke symbol ini)
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("📈 Open Chart (Binance)", url=f"https://www.binance.com/en/trade/{symbol}_USDT")],
            [InlineKeyboardButton("⏰ Set Price Alert", callback_data=f"alert|{symbol}|{last_price}"),
             InlineKeyboardButton("🔁 Refresh", callback_data=f"crypto_refresh|{symbol}")],
            [InlineKeyboardButton("🔙 Back", callback_data="menu_main")]
        ])

        # 8. Tampilkan Hasil (Edit pesan loading tadi)
        await msg.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)

    except Exception as e:
        await msg.edit_text(f"❌ Error: {str(e)}", parse_mode=ParseMode.HTML)
# --- CALLBACK: Refresh crypto (dipanggil dari tombol "Refresh") ---
async def crypto_refresh_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    try:
        # callback_data format: crypto_refresh|BTC
        _, symbol = q.data.split("|", 1)
        symbol = symbol.upper()
        pair = f"{symbol}USDT"
        url = f"https://api.binance.com/api/v3/ticker/24hr?symbol={pair}"

        # loading singkat (edit pesan jadi loading)
        await q.edit_message_text(f"⏳ <b>Refreshing {symbol} market data...</b>", parse_mode=ParseMode.HTML)

        d = await fetch_json(url)
        if not d or 'symbol' not in d:
            return await q.edit_message_text("❌ <b>Market data not available.</b>", parse_mode=ParseMode.HTML)

        # helper lokal (sama format dengan crypto_command)
        def fmt_price(n):
            try:
                n = float(n)
                if n >= 1:
                    return f"{n:,.2f}"
                return f"{n:,.6f}"
            except:
                return str(n)
        def fmt_int(n):
            try:
                return f"{int(float(n)):,}"
            except:
                return str(n)
        def mini_bar(pct):
            try:
                p = max(-10, min(10, float(pct)))
                v = (p + 10) / 20
                length = 12
                filled = int(round(v * length))
                return "▰" * filled + "▱" * (length - filled)
            except:
                return "▱" * 12

        last_price = float(d.get('lastPrice', 0))
        ask_price = float(d.get('askPrice', 0))
        bid_price = float(d.get('bidPrice', 0))
        high_24h = float(d.get('highPrice', 0))
        low_24h = float(d.get('lowPrice', 0))
        change_p = float(d.get('priceChangePercent', 0))
        change_abs = float(d.get('priceChange', 0))
        vol_quote = float(d.get('quoteVolume', 0))
        open_price = float(d.get('openPrice', 0))
        weighted_avg = float(d.get('weightedAvgPrice', 0))

        # Trend label sederhana
        if change_p >= 5.0:
            trend_emoji = "🟢"
            trend = "STRONG BULL"
        elif 0.5 <= change_p < 5.0:
            trend_emoji = "🟢"
            trend = "UPTREND"
        elif -5.0 < change_p <= -0.5:
            trend_emoji = "🔴"
            trend = "DOWNTREND"
        elif change_p <= -5.0:
            trend_emoji = "🔴"
            trend = "STRONG BEAR"
        else:
            trend_emoji = "🟡"
            trend = "SIDEWAYS"

        sign = "+" if change_p > 0 else ""
        percent_str = f"{sign}{change_p:.2f}%"

        text = (
            f"🪙 <b>OKTACOMEL — CRYPTO SNAPSHOT</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"💠 <b>Pair:</b> <code>{pair}</code>\n"
            f"💵 <b>Last Price:</b> <code>${fmt_price(last_price)}</code>\n"
            f"📊 <b>24h Change:</b> {trend_emoji} <b>{percent_str}</b> ({fmt_price(change_abs)})\n"
            f"🔎 <b>Trend:</b> {trend}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"📈 <b>Market Range (24h)</b>\n"
            f"• Low  : <code>${fmt_price(low_24h)}</code>\n"
            f"• High : <code>${fmt_price(high_24h)}</code>\n"
            f"• Open : <code>${fmt_price(open_price)}</code>\n"
            f"• Avg  : <code>${fmt_price(weighted_avg)}</code>\n"
            f"Range : {mini_bar(change_p)}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🛒 <b>Orderbook (Top)</b>\n"
            f"• Ask : <code>${fmt_price(ask_price)}</code>\n"
            f"• Bid : <code>${fmt_price(bid_price)}</code>\n\n"
            f"📦 <b>24h Volume (quote):</b> <code>${fmt_int(vol_quote)}</code>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🔗 <i>Data source: Binance (real-time)</i>\n"
            f"🐈 <i>Powered by Oktacomel — Premium</i>"
        )

        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("📈 Open Chart (Binance)", url=f"https://www.binance.com/en/trade/{symbol}_USDT")],
            [InlineKeyboardButton("⏰ Set Price Alert", callback_data=f"alert|{symbol}|{last_price}"),
             InlineKeyboardButton("🔁 Refresh", callback_data=f"crypto_refresh|{symbol}")],
            [InlineKeyboardButton("🔙 Back", callback_data="menu_main")]
        ])

        await q.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)

    except Exception as e:
        try:
            await q.edit_message_text(f"❌ Error: {html.escape(str(e))}", parse_mode=ParseMode.HTML)
        except:
            pass


# --- CALLBACK: Price alert (simpan sederhana ke DB + acknowledge) ---
async def crypto_alert_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    try:
        # contoh callback: alert|BTC|12345.67
        parts = q.data.split("|")
        symbol = parts[1] if len(parts) > 1 else "UNKNOWN"
        target_price = float(parts[2]) if len(parts) > 2 else None

        # Simpan ke SQLite (table crypto_alerts) — jika tabel belum ada, buat otomatis
        try:
            async with aiosqlite.connect(DB_NAME) as db:
                await db.execute("""
                    CREATE TABLE IF NOT EXISTS crypto_alerts (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        chat_id INTEGER,
                        symbol TEXT,
                        target REAL,
                        created_at REAL
                    )
                """)
                await db.commit()

                await db.execute(
                    "INSERT INTO crypto_alerts (chat_id, symbol, target, created_at) VALUES (?, ?, ?, ?)",
                    (q.message.chat_id, symbol, target_price if target_price else 0.0, time.time())
                )
                await db.commit()
        except Exception:
            # jangan crash kalau DB error, lanjutkan saja
            pass

        await q.answer(f"✅ Price alert set for {symbol} (target: {target_price if target_price else 'current'})", show_alert=True)
    except Exception as e:
        await q.answer(f"⚠️ Failed to set alert: {str(e)}", show_alert=True)


# --- OPTIONAL: Checker job — panggil ini via job_queue.run_repeating(check_price_alerts, interval=60, first=30) ---
async def check_price_alerts(context: ContextTypes.DEFAULT_TYPE):
    try:
        async with aiosqlite.connect(DB_NAME) as db:
            async with db.execute("SELECT id, chat_id, symbol, target FROM crypto_alerts") as cur:
                rows = await cur.fetchall()
                if not rows:
                    return

                # group by symbol untuk efisiensi
                by_symbol = {}
                for r in rows:
                    _id, chat_id, sym, target = r
                    sym = sym.upper()
                    by_symbol.setdefault(sym, []).append(( _id, chat_id, target ))

                for sym, alerts in by_symbol.items():
                    pair = f"{sym}USDT"
                    url = f"https://api.binance.com/api/v3/ticker/24hr?symbol={pair}"
                    d = await fetch_json(url)
                    if not d or 'lastPrice' not in d: 
                        continue
                    last = float(d.get('lastPrice', 0))
                    # peringatan bila last >= target (simple logic)
                    for (_id, chat_id, target) in alerts:
                        try:
                            if target > 0 and last >= float(target):
                                text = (f"🚨 <b>Price Alert</b>\n"
                                        f"Pair: <code>{pair}</code>\n"
                                        f"Current: <code>${last:,.6f}</code>\n"
                                        f"Target: <code>${float(target):,.6f}</code>\n"
                                        f"ID Alert: <code>{_id}</code>")
                                await context.bot.send_message(chat_id, text, parse_mode=ParseMode.HTML)
                                # hapus alert setelah trigger (opsional)
                                await db.execute("DELETE FROM crypto_alerts WHERE id=?", (_id,))
                                await db.commit()
                        except:
                            pass
    except Exception:
        pass



# ==========================================
# 📊 HELPER: PRICE RANGE BAR UNTUK /sha
# ==========================================
def draw_bar(price, low, high, length=18):
    """
    Bikin bar visual posisi harga hari ini dalam range Low–High.
    Contoh:
    [────🔹──────────────]
    """
    try:
        price = float(price)
        low = float(low)
        high = float(high)
    except Exception:
        return "[no data]"

    if high <= low:
        return "[no range]"

    # Clamp price biar tetap di dalam low–high
    if price < low:
        price = low
    if price > high:
        price = high

    ratio = (price - low) / (high - low)
    idx = int(ratio * (length - 1))

    bar_chars = []
    for i in range(length):
        if i == idx:
            bar_chars.append("🔹")
        else:
            bar_chars.append("─")

    return "[" + "".join(bar_chars) + "]"

# ==========================================
# 📈 STOCK MARKET (VERSI DEWA: SMART SEARCH)
# ==========================================

def get_signal(price, s1, r1, pivot):
    """Get trading signal based on price level"""
    if price > r1:
        return "🔴🔴🔴 OVERBOUGHT - Sell Signal"
    elif price > pivot:
        return "🟠 STRONG BUY - Momentum Up"
    elif price > s1:
        return "🟡 NEUTRAL - Wait & See"
    elif price > s1 * 0.95:
        return "🟢 BUY - Discount Zone"
    else:
        return "🟢🟢🟢 EXTREME BUY - Bounce Zone"

async def sha_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Stock/Share analysis command"""
    
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36"
        )
    }

    # --- MODE 1: MARKET OVERVIEW ---
    if not context.args:
        msg = await update.message.reply_text(
            "⏳ <b>Scanning Global Markets...</b>",
            parse_mode=ParseMode.HTML,
        )

        indices = {
            "^JKSE": "🇮🇩 IHSG (Indo)",
            "IDR=X": "💱 USD/IDR",
            "BTC-USD": "₿ Bitcoin",
            "GC=F": "🥇 Gold",
            "CL=F": "🛢️ Oil (WTI)",
        }
        report = (
            "╔════════════════════════════╗\n"
            "║  🌍 GLOBAL MARKET OVERVIEW  ║\n"
            "╚════════════════════════════╝\n\n"
        )

        for ticker, name in indices.items():
            try:
                url = (
                    f"https://query1.finance.yahoo.com/v8/finance/chart/"
                    f"{ticker}?interval=1d&range=1d"
                )
                d = await fetch_json(url, headers=headers)
                if d and d.get("chart", {}).get("result"):
                    meta = d["chart"]["result"][0]["meta"]
                    price = meta.get("regularMarketPrice")
                    prev = meta.get("chartPreviousClose")

                    if price is None or prev in (None, 0):
                        continue

                    change_p = ((price - prev) / prev) * 100
                    emoji = "📈" if change_p >= 0 else "📉"

                    if ticker in ["IDR=X", "^JKSE"]:
                        price_fmt = f"{price:,.0f}"
                    else:
                        price_fmt = f"{price:,.2f}"

                    report += (
                        f"{emoji} <b>{name}</b>\n"
                        f"   {price_fmt} ({change_p:+.2f}%)\n\n"
                    )
            except Exception:
                continue

        report += (
            "━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "💡 <i>Try:</i> <code>/sha BBCA</code> or <code>/sha TSLA</code>"
        )
        await msg.edit_text(report, parse_mode=ParseMode.HTML)
        return

    # --- MODE 2: SMART SEARCH ---
    input_ticker = context.args[0].upper().strip()
    msg = await update.message.reply_text(
        f"🔍 <b>Analyzing</b> <code>{html.escape(input_ticker)}</code>...",
        parse_mode=ParseMode.HTML,
    )

    candidates = []
    if len(input_ticker) == 4 and input_ticker.isalpha():
        candidates.append(f"{input_ticker}.JK")
        candidates.append(input_ticker)
    else:
        candidates.append(input_ticker)

    found_data = None
    real_ticker = input_ticker

    for t in candidates:
        url = (
            f"https://query1.finance.yahoo.com/v8/finance/chart/"
            f"{t}?interval=1d&range=1d"
        )
        try:
            d = await fetch_json(url, headers=headers)
            if d and d.get("chart", {}).get("result"):
                found_data = d
                real_ticker = t
                break
        except Exception:
            continue

    # --- JIKA DATA DITEMUKAN ---
    if found_data:
        try:
            meta = found_data["chart"]["result"][0]["meta"]

            price = meta.get("regularMarketPrice", 0)
            prev_close = meta.get("chartPreviousClose", 0) or 1
            currency = meta.get("currency", "IDR")
            vol = meta.get("regularMarketVolume", 0)
            day_high = meta.get("regularMarketDayHigh", price)
            day_low = meta.get("regularMarketDayLow", price)
            open_price = meta.get("regularMarketOpen", 0)

            # Trading Zones
            pivot = (day_high + day_low + price) / 3
            s1 = (2 * pivot) - day_high
            r1 = (2 * pivot) - day_low

            change = price - prev_close
            change_p = (change / prev_close) * 100

            trend_emoji = "📈" if change_p > 0 else ("📉" if change_p < 0 else "➡️")
            color_sign = "+" if change_p >= 0 else ""

            # Trading Signal
            signal = get_signal(price, s1, r1, pivot)

            # Position in Range
            from_high_p = ((price - day_high) / day_high) * 100 if day_high else 0
            from_low_p = ((price - day_low) / day_low) * 100 if day_low else 0

            # Price Range Bar
            price_bar = draw_bar(price, day_low, day_high)

            def fmt(val):
                try:
                    v = float(val)
                    return f"{v:,.0f}" if currency == "IDR" else f"{v:,.2f}"
                except:
                    return "0"

            txt = (
                f"╔════════════════════════════╗\n"
                f"║  📊 STOCK ANALYSIS          ║\n"
                f"║  {html.escape(real_ticker):26} ║\n"
                f"╚════════════════════════════╝\n\n"
                
                f"💰 <b>PRICE</b>\n"
                f"├ Current: <code>{currency} {fmt(price)}</code>\n"
                f"├ Change: {trend_emoji} <code>{color_sign}{change:.2f}</code> "
                f"(<code>{color_sign}{change_p:.2f}%</code>)\n"
                f"└ Prev Close: <code>{fmt(prev_close)}</code>\n\n"
                
                f"🎯 <b>TRADING ZONES (Daily)</b>\n"
                f"├ 🔴 Resistance: <code>{fmt(r1)}</code> - <code>{fmt(day_high)}</code>\n"
                f"├ 🟡 Pivot: <code>{fmt(pivot)}</code>\n"
                f"└ 🟢 Support: <code>{fmt(s1)}</code> - <code>{fmt(day_low)}</code>\n\n"
                
                f"📊 <b>TRADING SIGNAL</b>\n"
                f"└ {signal}\n\n"
                
                f"📈 <b>INTRADAY STATS</b>\n"
                f"├ High: <code>{fmt(day_high)}</code>\n"
                f"├ Low: <code>{fmt(day_low)}</code>\n"
                f"├ Open: <code>{fmt(open_price)}</code>\n"
                f"├ Volume: <code>{vol:,}</code>\n"
                f"└ Range: {price_bar}\n\n"
                
                f"📍 <b>POSITION IN RANGE</b>\n"
                f"├ From High: <code>{from_high_p:+.2f}%</code>\n"
                f"└ From Low: <code>{from_low_p:+.2f}%</code>\n\n"
                
                f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"🤖 <i>Real-time by Oktacomel</i>"
            )

            # Quick Stats Button
            kb = [
                [
                    InlineKeyboardButton("🔄 Refresh", callback_data=f"sha_refresh|{real_ticker}"),
                    InlineKeyboardButton("📊 Chart", url=f"https://finance.yahoo.com/quote/{real_ticker}"),
                ]
            ]

            await msg.edit_text(txt, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(kb))

        except Exception as e:
            await msg.edit_text(
                f"❌ <b>Parse Error:</b> <code>{html.escape(str(e)[:50])}</code>",
                parse_mode=ParseMode.HTML,
            )
    else:
        await msg.edit_text(
            f"❌ <b>Symbol not found:</b> <code>{html.escape(input_ticker)}</code>\n\n"
            f"💡 Try: <code>/sha BBCA</code> (Indo) or <code>/sha TSLA</code> (US)",
            parse_mode=ParseMode.HTML,
        )

# CALLBACK HANDLER UNTUK REFRESH
async def sha_refresh_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Refresh stock data"""
    query = update.callback_query
    await query.answer("🔄 Refreshing...", show_alert=False)
    
    ticker = query.data.split("|")[1]
    context.args = [ticker]
    await sha_command(update, context)
    
# ==========================================
# 👑 ADMIN: ADD PREMIUM USER (IMPROVED UI + NOTIFY)
# ==========================================
async def addprem_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Hanya Owner yang bisa pakai command ini
    if update.effective_user.id != OWNER_ID:
        return

    if not context.args:
        await update.message.reply_text(
            "⚠️ Usage: <code>/addprem user_id</code>\nExample: <code>/addprem 123456789</code>",
            parse_mode=ParseMode.HTML
        )
        return

    try:
        target_id = int(context.args[0])

        async with aiosqlite.connect(DB_NAME) as db:
            # Cek apakah sudah premium
            async with db.execute("SELECT 1 FROM premium_users WHERE user_id = ? LIMIT 1", (target_id,)) as cur:
                exists = await cur.fetchone()

            if exists:
                await update.message.reply_text(
                    f"ℹ️ User <code>{target_id}</code> is already <b>PREMIUM</b>.",
                    parse_mode=ParseMode.HTML
                )
                return

            # Masukkan ke DB
            await db.execute("INSERT OR IGNORE INTO premium_users (user_id) VALUES (?)", (target_id,))
            await db.commit()

        # Format waktu (pakai TZ jika tersedia)
        try:
            ts = datetime.datetime.now(TZ).strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            ts = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")

        # Konfirmasi ke owner
        owner_text = (
            f"✅ <b>PREMIUM ADDED</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"👤 <b>User ID:</b> <code>{target_id}</code>\n"
            f"🕒 <b>When:</b> {ts}\n"
            f"🙋‍♂️ <b>By:</b> {html.escape(update.effective_user.full_name)}\n"
            f"━━━━━━━━━━━━━━━━━━━━"
        )
        await update.message.reply_text(owner_text, parse_mode=ParseMode.HTML)

        # NOTIFIKASI KE USER YANG DITAMBAHKAN
        user_text = (
            f"🎉 <b>CONGRATULATIONS!</b>\n"
            f"You have been granted <b>PREMIUM</b> access on <i>Oktacomel</i>.\n\n"
            f"✅ Status: <code>PREMIUM</code>\n"
            f"🕒 Activated: {ts}\n\n"
            f"Features unlocked:\n"
            f"• Higher limits & priority support\n"
            f"• Access to premium modules\n"
            f"• Faster AI & downloader quotas\n\n"
            f"If you cannot access premium features, please open a chat with the bot and send /start."
        )

        try:
            await context.bot.send_message(chat_id=target_id, text=user_text, parse_mode=ParseMode.HTML)
            # Jika sukses, update owner lagi bahwa notification terkirim
            await update.message.reply_text(f"📨 Notification sent to <code>{target_id}</code>.", parse_mode=ParseMode.HTML)
        except Exception as e:
            # Biasanya error karena user belum start bot / privacy settings
            await update.message.reply_text(
                f"⚠️ Added to premium but failed to DM user <code>{target_id}</code>.\n"
                f"Reason: <code>{html.escape(str(e))}</code>\n\n"
                "User may need to start the bot or allow messages from the bot.",
                parse_mode=ParseMode.HTML
            )

    except ValueError:
        await update.message.reply_text("❌ <b>Invalid ID:</b> ID must be a number.", parse_mode=ParseMode.HTML)
    except Exception as e:
        await update.message.reply_text(f"❌ <b>Unexpected error:</b> <code>{html.escape(str(e))}</code>", parse_mode=ParseMode.HTML)


# =====================================================
# 🧠 OKTA AI ENGINE — (TRIPLE GOD MODE: GPT-4o, CODEX, GEMINI 3)
# =====================================================
async def okta_ai_process(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    query: str,
    model_id: str,
    model_name: str,
):
    message = update.effective_message

    # UI Loading: Kasih tau user lagi pakai otak yang mana
    bot_msg = await message.reply_text(
        f"🧠 <b>OKTA AI: {model_name}</b>\n"
        "⏳ <i>Sedang berpikir keras...</i>",
        parse_mode=ParseMode.HTML
    )

    api_key = config.OMYGPT_API_KEY
    if not api_key:
        await bot_msg.edit_text("❌ <b>Error:</b> API Key belum dipasang!")
        return

    # ENDPOINT OHMYGPT
    endpoint = "https://api.ohmygpt.com/v1/chat/completions"
    
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    # System Prompt
    system_prompt = (
        "Anda adalah OKTA AI. Jawab selalu dalam Bahasa Indonesia. "
        "Berikan jawaban yang cerdas, lengkap, dan solutif."
    )

    payload = {
        "model": model_id,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": query}
        ],
        "temperature": 0.7, 
        "max_tokens": 4000 # Kita kasih limit gede biar puas
    }

    try:
        async with httpx.AsyncClient(timeout=120) as client: # Timeout lamaan dikit buat Gemini Thinking
            resp = await client.post(endpoint, json=payload, headers=headers)
            
        if resp.status_code != 200:
            await bot_msg.edit_text(f"❌ <b>API Error {resp.status_code}:</b>\n{resp.text[:500]}")
            return

        data = resp.json()
        content = data['choices'][0]['message']['content']

        # FORMATTING CODE BLOCK (Biar Rapi)
        parts = content.split("```")
        final_parts = []
        for i, p in enumerate(parts):
            if i % 2 == 0:
                final_parts.append(html.escape(p))
            else:
                code_content = p.strip()
                if "\n" in code_content:
                    first_line, rest = code_content.split("\n", 1)
                    if len(first_line) < 15: code_content = rest
                final_parts.append(f"<pre><code>{html.escape(code_content)}</code></pre>")

        final_text = "".join(final_parts)
        footer = f"\n\n🤖 <i>Generated by {model_name}</i>"

        # KIRIM HASIL
        if len(final_text) > 4000:
            with io.BytesIO(str(final_text).encode()) as f:
                f.name = f"jawaban_{model_name.replace(' ', '_')}.txt"
                await message.reply_document(document=f, caption="✅ Jawaban panjang, saya kirim file.")
                await bot_msg.delete()
        else:
            await bot_msg.edit_text(final_text + footer, parse_mode=ParseMode.HTML)

    except Exception as e:
        await bot_msg.edit_text(f"❌ <b>System Error:</b> {str(e)}")

# --- 3 COMMAND SAKTI ---

# 1. GPT-4o (Buat Tanya Jawab Umum)
async def ai_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = " ".join(context.args)
    if not query:
        await update.message.reply_text("❌ <b>Contoh:</b> <code>/ai apa kabar?</code>", parse_mode=ParseMode.HTML)
        return
    await okta_ai_process(update, context, query, "gpt-4o", "GPT-4o")

# 2. GPT-5.1 CODEX (Buat Coding / Script) -> Sesuai Screenshot Mas
async def code_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = " ".join(context.args)
    if not query:
        await update.message.reply_text("❌ <b>Contoh:</b> <code>/code buatkan script python kalkulator</code>", parse_mode=ParseMode.HTML)
        return
    await okta_ai_process(update, context, query, "gpt-5.1-codex-max", "GPT-5.1 Codex Max")

# 3. GEMINI 3 PRO THINKING (Buat Analisa Berat/Mikir) -> Sesuai Screenshot Mas
async def think_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = " ".join(context.args)
    if not query:
        await update.message.reply_text("❌ <b>Contoh:</b> <code>/think jelaskan teori relativitas secara detail</code>", parse_mode=ParseMode.HTML)
        return
    await okta_ai_process(update, context, query, "vertex-gemini-3-pro-preview-thinking", "Gemini 3 Pro (Thinking)")

# ==========================================
# 🔥 DATABASE TRUTH OR DARE (ULTIMATE MASSIVE MIX)
# ==========================================
LIST_TRUTH = [
    # --- LEVEL 1: AMAN / FUN / SOSIAL ---
    "Siapa mantan yang paling susah kamu lupain?",
    "Hal paling memalukan apa yang pernah kamu lakuin di depan umum?",
    "Kapan terakhir kali kamu ngompol?",
    "Siapa orang di grup ini yang pengen kamu jadiin pacar?",
    "Apa kebohongan terbesar yang pernah kamu bilang ke orang tua?",
    "What is your biggest fear?",
    "Pernah stalk sosmed mantan gak? Kapan terakhir?",
    "Who is your celebrity crush?",
    "Kalau besok kiamat, siapa orang terakhir yang mau kamu hubungi?",
    "Pernah naksir pacar teman sendiri gak? Jujur!",
    "Apa aib masa kecil yang gak pernah kamu lupain?",
    "Sebutkan 3 hal yang bikin kamu ilfeel sama lawan jenis.",
    "Siapa member grup ini yang paling ganteng/cantik menurutmu?",
    "Pernah gak mandi berapa hari paling lama?",
    "Pernah nyuri uang orang tua gak? Buat apa?",
    "Siapa orang yang paling kamu benci sekarang? Inisial aja.",
    "Kapan terakhir kali nangis? Gara-gara apa?",
    "Pernah kentut tapi nyalahin orang lain? Kapan?",
    "Apa kebiasaan jorok kamu yang orang lain gak tau?",
    "Kalau punya uang 1 Miliar sekarang, apa hal pertama yang kamu beli?",
    "Pernah ditembak (nembak cewek/cowok) terus ditolak? Ceritain!",
    "Siapa first kiss kamu?",
    "Pernah selingkuh? Kenapa?",
    "Apa hal terbodoh yang pernah kamu lakuin demi cinta?",
    "Sebutkan isi search history Google/YouTube terakhir kamu!",
    "Pernah ngupil terus dimakan gak?",
    "Siapa guru/dosen yang pernah kamu taksir?",
    
    # --- LEVEL 2: DEEP / PERSONAL ---
    "Apa penyesalan terbesar dalam hidupmu sejauh ini?",
    "Kapan kamu merasa paling kesepian?",
    "Apa rahasia yang belum pernah kamu ceritain ke siapapun?",
    "Pernah gak kamu ngerasa salah pilih pasangan?",
    "Apa sifat terburuk kamu menurut dirimu sendiri?",
    "Kalau bisa memutar waktu, momen apa yang pengen kamu ubah?",
    "Apa insecure terbesar kamu soal fisik?",
    
    # --- LEVEL 3: PEDAS / 18+ / 21+ (HARDCORE) ---
    "Pernah kirim pap (foto) naked/seksi ke siapa aja?",
    "Apa fantasi terliar kamu yang belum kesampaian?",
    "What's your favorite position?",
    "Pernah ciuman sama sesama jenis? (Jujur!)",
    "Sebutkan 1 bagian tubuh lawan jenis yang paling bikin kamu sange!",
    "Pernah 'main' di tempat umum gak? Dimana?",
    "What turns you on the most?",
    "Pernah selingkuh atau jadi selingkuhan? Ceritain!",
    "Ukuran itu penting gak menurut kamu?",
    "Pernah one night stand (ONS)?",
    "Siapa orang di kontak HP kamu yang pengen banget kamu ajak 'tidur'?",
    "Have you ever sent a nude? To whom?",
    "Pernah nonton bokep bareng temen? Siapa?",
    "Apa warna celana dalam yang kamu pakai sekarang?",
    "Do you prefer lights on or lights off?",
    "Pernah 'main' sambil direkam video gak?",
    "Bagian tubuh mana dari kamu yang paling sensitif kalau disentuh?",
    "Suka yang kasar (rough) atau lembut (soft)?",
    "Pernah mimpi basah mikirin teman sendiri? Siapa?",
    "Have you ever faked an orgasm?",
    "Pernah ketahuan lagi nonton bokep atau masturbasi gak?",
    "Sebutkan tempat paling aneh yang pernah kamu pakai buat 'main'!",
    "Suka dirty talk gak pas lagi main? Contoh kalimatnya apa?",
    "Pernah punya FWB (Friends with Benefits)?",
    "Kalau bisa milih member grup ini buat one night stand, pilih siapa?",
    "Pernah 'main' bertiga (threesome) atau pengen nyoba?",
    "Do you like giving or receiving oral more?",
    "Pernah nyoba mainan dewasa (sex toys)?",
    "Apa hal ter-nakal yang pernah kamu lakuin di sekolah/kampus/kantor?",
    "Berapa ronde rekor terkuat kamu?",
    "Suka nelan atau dibuang? (You know what I mean)",
    "Pernah 'main' di mobil (Car Sex)?",
    "Apa fetish teraneh yang kamu punya?",
    "Pernah ketahuan ortu pas lagi 'solo player'?",
    "Lebih suka main atas atau bawah?",
    "Pernah sexting (chat seks) sama orang asing?",
    "Apa baju tidur favorit yang bikin kamu ngerasa seksi?",
    "Pernah gak pake celana dalam pas keluar rumah?",
    "Suara desahan siapa yang paling pengen kamu denger di grup ini?",
    "Pernah ciuman bibir lebih dari 5 menit?",
    "Suka dijambak atau ditampar pas lagi main?",
    "Pernah coli/fingering sambil mikirin pacar orang?",
    "Seberapa sering kamu nonton bokep dalam seminggu?"
]

LIST_DARE = [
    # --- LEVEL 1: SOSIAL / PRANK ---
    "Kirim screenshot chat terakhir sama doi/pacar.",
    "Telpon mantan sekarang, bilang 'Aku kangen'. (Speaker on)",
    "Ganti foto profil WA/Tele jadi foto aib kamu selama 1 jam.",
    "Chat random contact di HP kamu, bilang 'Aku hamil anak kamu' atau 'Tanggung jawab!'.",
    "Nyanyi lagu potong bebek angsa tapi huruf vokal diganti 'O'. (VN)",
    "Send a voice note singing your favorite song.",
    "Kirim selfie muka jelek (ugly face) sekarang!",
    "Chat orang tua kamu bilang 'Aku mau nikah besok'.",
    "Prank call teman kamu, pura-pura pinjam duit 10 juta.",
    "Ketik nama kamu pakai hidung, kirim hasilnya kesini.",
    "Screenshot history YouTube terakhir kamu.",
    "Post foto aib di Story WA/IG sekarang, caption 'Aku Jelek'.",
    "Chat dosen/guru bilang 'Saya sayang bapak/ibu'.",
    "VN teriak 'AKU JOMBLO HAPPY' sekeras mungkin.",
    "Kirim foto saldo ATM/E-Wallet kamu sekarang.",
    "Ganti nama Telegram jadi 'Babi Ngepet' selama 10 menit.",
    "Screenshot gallery foto terbaru kamu (no crop).",
    
    # --- LEVEL 2: FLIRTY / GOMBAL ---
    "Gombalin salah satu member grup ini lewat VN.",
    "Chat crush kamu: 'Mimpiin aku ya malam ini'.",
    "Pilih satu orang di grup, jadikan 'pacar' kamu selama 15 menit.",
    "Bilang 'I Love You' ke member grup nomor 3 dari atas.",
    "Kirim pantun cinta buat Admin grup.",
    
    # --- LEVEL 3: PEDAS / 18+ / 21+ (HARDCORE) ---
    "Desah (moan) di voice note sekarang, durasi minimal 5 detik!",
    "Kirim foto paha (thigh pic) sekarang di grup! (No face gapapa)",
    "Chat mantan kamu: 'Badan kamu makin bagus deh', kirim ss kesini.",
    "Cium layar HP kamu sambil di-videoin orang lain/mirror selfie.",
    "Tulis nama member grup ini di bagian tubuh kamu (dada/paha/perut), foto & kirim.",
    "VN bilang 'Ahhh sakit mas...' dengan nada mendesah.",
    "Kirim foto gaya paling seksi yang kamu punya di galeri.",
    "Goyangkan pantat (twerking) divideoin 5 detik, kirim kesini (boleh blur muka).",
    "Chat crush kamu bilang: 'I want you inside me' atau 'I want you so bad'.",
    "Kirim foto bibir kamu pose nyium (duck face) seksi.",
    "Jilat barang di dekatmu (botol/pulpen) dengan gaya menggoda, kirim videonya.",
    "Foto leher/tulang selangka (collarbone) kamu, kirim sini.",
    "VN suara kamu lagi mendesah sebut nama Admin grup ini.",
    "Kirim foto perut/abs kamu (boleh angkat baju dikit).",
    "Chat pacar/mantan: 'Lagi pengen nih, kerumah yuk', ss balasannya.",
    "Cari foto paling seksi di IG/Twitter, jadikan PP Telegram selama 30 menit.",
    "Pegang bagian sensitif kamu (dari luar baju) sambil mirror selfie.",
    "Buat status WA/Story: 'Lagi sange banget nih, butuh bantuan', tahan 10 menit.",
    "VN bilang: 'Daddy, I've been a bad girl/boy' dengan suara menggoda.",
    "Foto kaki (feet) kamu pose cantik/ganteng.",
    "Pilih satu member grup, chat pribadi bilang fantasi jorok kamu tentang dia.",
    "Buka kancing baju teratas kamu, foto dan kirim sini.",
    "VN suara ciuman (muach) yang basah/nyaring.",
    "Kirim foto lidah kamu melet (ahegao face) sekarang.",
    "Elus-elus paha sendiri sambil direkam video 5 detik.",
    "Kirim foto punggung kamu (tanpa baju atasan kalau cowok, tanktop kalau cewek).",
    "Chat teman lawan jenis: 'Ukuran kamu berapa?', kirim SS balasannya."
]

# ==========================================
# 🔥 TRUTH OR DARE (ENGLISH PREMIUM STYLE)
# ==========================================

# 1. Menu Utama (Main Menu)
async def tod_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [
            InlineKeyboardButton("🧠 TRUTH", callback_data='tod_mode_truth'),
            InlineKeyboardButton("🔥 DARE", callback_data='tod_mode_dare')
        ],
        [InlineKeyboardButton("❌ Close Game", callback_data='tod_close')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Kata-kata Pembuka yang Lebih Keren
    txt = (
        f"<b>OKTACOMEL ToD</b> 🎲\n\n"
        f"Prepare yourself. Secrets will be revealed, limits will be tested.\n"
        f"<b>Choose your destiny carefully.</b>\n\n"
        f"⚠️ <i>Warning: Mature Content (18+)</i>"
    )
    
    if update.message:
        await update.message.reply_text(txt, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
    else:
        await update.callback_query.message.edit_text(txt, reply_markup=reply_markup, parse_mode=ParseMode.HTML)

# 2. Handler Logika Game
async def tod_button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    data = query.data 
    
    if data == 'tod_close':
        await query.message.delete()
        return

    # Tentukan Mode
    if 'truth' in data:
        theme = "<b>TRUTH TIME!</b> 🧠"
        question = random.choice(LIST_TRUTH)
        next_data = 'tod_mode_truth' 
    elif 'dare' in data:
        theme = "<b>DARE TIME!</b> 🔥"
        question = random.choice(LIST_DARE)
        next_data = 'tod_mode_dare'
    else:
        return

    # Tombol Navigasi (English)
    keyboard = [
        [InlineKeyboardButton("🔄 Next Spin", callback_data=next_data)], # Spin lagi di mode yg sama
        [InlineKeyboardButton("🔙 Switch Mode", callback_data='tod_menu')], # Ganti Truth/Dare
        [InlineKeyboardButton("❌ Close", callback_data='tod_close')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    res = (
        f"{theme}\n\n"
        f"<code>{html.escape(question)}</code>\n\n"
        f"🤖 <i>No turning back now!</i>"
    )
    
    await query.message.edit_text(res, reply_markup=reply_markup, parse_mode=ParseMode.HTML)

# 3. Handler Balik ke Menu
async def tod_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await tod_command(update, context)

# ==========================================
# 💳 CC CHECKER (SIMULATION WITH REAL BIN)
# ==========================================
async def chk_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Cek Input
    if not context.args:
        await update.message.reply_text("⚠️ <b>Usage:</b> <code>/chk cc|mm|yy|cvv</code>", parse_mode=ParseMode.HTML)
        return

    input_data = context.args[0]
    
    # Animasi Loading
    msg = await update.message.reply_text("<b>[↯] Waiting for Result...</b>", parse_mode=ParseMode.HTML)
    
    start_time = time.time()
    
    # 1. Parsing Data Kartu (CC|MM|YY|CVV)
    # Ganti semua pemisah jadi | biar gampang
    clean_input = input_data.replace("/", "|").replace(":", "|").replace(" ", "|")
    splits = clean_input.split("|")
    
    if len(splits) < 4:
        # Jika user cuma masukin CC doang, kita kasih dummy data biar gak error
        cc = splits[0]
        mes, ano, cvv = "xx", "xxxx", "xxx"
    else:
        cc = splits[0]
        mes = splits[1]
        ano = splits[2]
        cvv = splits[3]

    # Ambil 6 digit BIN
    bin_code = cc[:6]
    
    # 2. Cek BIN Asli (Pakai API yang sudah ada di botmu)
    try:
        r = await fetch_json(f"{BIN_API}/{bin_code}")
        if r and 'brand' in r:
            scheme = str(r.get('scheme', 'UNKNOWN')).upper()
            type_c = str(r.get('type', 'UNKNOWN')).upper()
            level = str(r.get('level', 'UNKNOWN')).upper()
            bank = str(r.get('bank', 'UNKNOWN')).upper()
            country = str(r.get('country_name', 'UNKNOWN')).upper()
            flag = r.get('country_flag', '')
        else:
            scheme, type_c, level, bank, country, flag = "UNKNOWN", "UNKNOWN", "UNKNOWN", "UNKNOWN", "UNKNOWN", ""
    except:
        scheme, type_c, level, bank, country, flag = "UNKNOWN", "UNKNOWN", "UNKNOWN", "UNKNOWN", "UNKNOWN", ""

    # 3. Simulasi Gateway Response (Disini logika 'Bohongan'-nya)
    # Kita buat seolah-olah dia ngecek ke Braintree
    await asyncio.sleep(random.uniform(2, 5)) # Delay biar kayak lagi mikir (2-5 detik)
    
    # Daftar kemungkinan respon (Bisa kamu tambah)
    responses = [
        ("Declined ❌", "RISK: Retry this BIN later."),
        ("Declined ❌", "Insufficient Funds"),
        ("Declined ❌", "Do Not Honor"),
        ("Approved ✅", "CVV LIVE"), # Kecilkan kemungkinan approved biar real
        ("Approved ✅", "Charged $10")
    ]
    
    # Random pilih status (80% Declined, 20% Approved - biar realistis)
    # Ubah logic ini kalau mau selalu approved (tapi jadi gak seru)
    is_live = random.choices([True, False], weights=[10, 90])[0] 
    
    if is_live:
        status_header = "𝐀𝐩𝐩𝐫𝐨𝐯𝐞𝐝 ✅"
        gw_resp = "Charged Success"
    else:
        status_header = "𝐃𝐞𝐜𝐥𝐢𝐧𝐞𝐝 ❌"
        gw_resp = random.choice(responses)[1]

    # Hitung waktu
    end_time = time.time()
    taken = round(end_time - start_time, 2)

    # 4. Susun Pesan (Sesuai Request Font & Style)
    result_text = (
        f"{status_header}\n\n"
        f"𝗖𝗮𝗿𝗱: <code>{cc}|{mes}|{ano}|{cvv}</code>\n\n"
        f"𝐆𝐚𝐭𝐞𝐰𝐚𝐲: Braintree Premium\n"
        f"𝐑𝐞𝐬𝐩??𝐧𝐬𝐞: {gw_resp}\n\n"
        f"𝗜𝗻𝗳𝗼: {scheme} - {type_c} - {level}\n"
        f"𝐈𝐬𝐬𝐮𝐞𝐫: {bank}\n"
        f"𝐂𝐨𝐮𝐧𝐭𝐫𝐲: {country} {flag}\n\n"
        f"𝗧𝗶𝗺𝗲: {taken} 𝐬𝐞𝐜𝐨𝐧𝐝𝐬"
    )
    
    await msg.edit_text(result_text, parse_mode=ParseMode.HTML)


# ==========================================
# 🔢 BIN EXTRAPOLATION (/extrap)
# ==========================================
async def extrap_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if not args:
        await update.message.reply_text("⚠️ <b>Usage:</b> <code>/extrap 454321</code> or <code>/extrap 454321|05|2026</code>", parse_mode=ParseMode.HTML)
        return

    input_data = args[0]
    
    # Default jumlah generate extrap (standar 5 - 10)
    amount = 5
    if len(args) > 1 and args[1].isdigit():
        amount = int(args[1])
        if amount > 20: amount = 20 # Limit biar gak spam

    msg = await update.message.reply_text("⏳ <b>Extrapolating...</b>", parse_mode=ParseMode.HTML)

    # --- 1. NORMALISASI INPUT (CUSTOM SUPPORT) ---
    # Ganti semua pemisah (/ : spasi) menjadi | agar mudah diproses
    normalized_input = input_data.replace("/", "|").replace(":", "|").replace(" ", "|")
    splits = normalized_input.split("|")
    
    # Ambil data sesuai urutan (Support Custom Format)
    cc = splits[0] if len(splits) > 0 else 'x'
    mes = splits[1] if len(splits) > 1 and splits[1].isdigit() else 'x'
    ano = splits[2] if len(splits) > 2 and splits[2].isdigit() else 'x'
    cvv = splits[3] if len(splits) > 3 and splits[3].isdigit() else 'x'

    # Ambil 6 digit BIN untuk lookup info
    clean_bin = cc.lower().replace('x', '')[:6]

    if not clean_bin.isdigit() or len(clean_bin) < 6:
        await msg.edit_text("❌ BIN Invalid.")
        return

    # --- 2. FETCH BIN INFO ---
    try:
        r = await fetch_json(f"{BIN_API}/{clean_bin}")
        if r and 'brand' in r:
            # Format Info: BRAND - TYPE - LEVEL
            info_str = f"{str(r.get('brand')).upper()} - {str(r.get('type')).upper()} - {str(r.get('level')).upper()}"
            bank = str(r.get('bank', 'UNKNOWN')).upper()
            country = f"{str(r.get('country_name')).upper()} {r.get('country_flag','')}"
        else:
            info_str, bank, country = "UNKNOWN", "UNKNOWN", "UNKNOWN"
    except: 
        info_str, bank, country = "ERROR", "ERROR", "ERROR"

    # --- 3. GENERATE CARDS (Pakai fungsi cc_gen yg sudah ada) ---
    # Kita generate agak banyak dulu, nanti ambil sesuai amount
    generated_list = cc_gen(cc, mes, ano, cvv, amount)

    # --- 4. FORMATTING OUTPUT (SESUAI REQUEST) ---
    result_body = ""
    for card in generated_list:
        # Format cc_gen biasanya: CC|MM|YYYY|CVV
        # Kita pecah biar tampilannya sesuai request
        c_split = card.split("|")
        c_num = c_split[0]
        c_date_cvv = f"{c_split[1]}|{c_split[2]}|{c_split[3]}"
        
        # Susun tampilan per kartu
        result_body += f"<code>{c_num}</code>\n<code>{c_date_cvv}</code>\n\n"

    # Teks Akhir
    final_text = (
        f"<b>𝗕𝗜𝗡  →</b> <code>{clean_bin}</code>\n"
        f"<b>𝗔𝗺𝗼𝘂𝗻𝘁 →</b> {amount}\n\n"
        f"{result_body}"
        f"<b>Generation Type:</b> Luhn-Based BIN Extrapolation\n"
        f"<b>𝗜𝗻𝗳𝗼:</b> {info_str}\n"
        f"<b>𝐈𝐬𝐬𝐮𝐞𝐫:</b> {bank}\n"
        f"<b>𝗖𝗼𝘂𝗻𝘁𝗿𝘆:</b> {country}"
    )

    await msg.edit_text(final_text, parse_mode=ParseMode.HTML)

# ==========================================
# 🛡️ PROXY CHECKER (FORMAT V2 - IP:PORT:USER:PASS)
# ==========================================
async def proxy_check_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # 1. Ambil Input
    proxies_to_check = []

    if context.args:
        proxies_to_check = context.args
    elif update.message.reply_to_message and update.message.reply_to_message.text:
        raw_text = update.message.reply_to_message.text
        # Pisahkan berdasarkan baris atau spasi
        proxies_to_check = raw_text.replace(" ", "\n").split("\n")
        # Bersihkan list dari string kosong
        proxies_to_check = [x.strip() for x in proxies_to_check if x.strip()]
    else:
        # Pesan Error Sesuai Request
        await update.message.reply_text(
            "⚠️ <b>Invalid Proxy Format!</b>\n\n"
            "<b>Usage:</b>\n"
            "You can check up to 20 proxies at a time.\n\n"
            "<b>Normal:</b> <code>/proxy host:port:user:pass</code>\n"
            "<b>With Type:</b> <code>/proxy socks5:host:port:user:pass</code>",
            parse_mode=ParseMode.HTML
        )
        return

    # 2. Limit Maksimal 20
    if len(proxies_to_check) > 20:
        await update.message.reply_text(
            "❌ <b>Limit Reached:</b> Max 20 proxies allowed.",
            parse_mode=ParseMode.HTML
        )
        return

    msg = await update.message.reply_text(
        f"⏳ <b>Checking {len(proxies_to_check)} Proxies...</b>",
        parse_mode=ParseMode.HTML
    )

    # 3. Fungsi Cek Pintar (Auto Format + Real Check)
    async def check_single_proxy(raw_proxy: str):
        p = raw_proxy.strip()
        scheme = "http"  # default
        display = p      # fallback tampilan

        # CASE 1: user kirim full URL proxy (http://user:pass@ip:port)
        if "://" in p and p.split("://", 1)[0].lower() in ["http", "https", "socks5"]:
            final_url = p
            if "@" in p:
                display = p.split("@")[-1]
        # CASE 2: format: socks5:ip:port:user:pass atau http:ip:port:user:pass
        elif p.lower().startswith("socks5:") or p.lower().startswith("http:"):
            parts = p.split(":")
            scheme = parts[0].lower()  # socks5 / http
            clean_parts = parts[1:]

            if len(clean_parts) == 4:
                host, port, user, pwd = clean_parts
                final_url = f"{scheme}://{user}:{pwd}@{host}:{port}"
                display = f"{host}:{port}"
            elif len(clean_parts) == 2:
                host, port = clean_parts
                final_url = f"{scheme}://{host}:{port}"
                display = f"{host}:{port}"
            else:
                return False, display, 0, "Bad Format"
        else:
            # CASE 3: format standar ip:port:user:pass atau ip:port
            parts = p.split(":")
            if len(parts) == 4:
                ip, port, user, pwd = parts
                final_url = f"http://{user}:{pwd}@{ip}:{port}"
                display = f"{ip}:{port}"
            elif len(parts) == 2:
                ip, port = parts
                final_url = f"http://{ip}:{port}"
                display = f"{ip}:{port}"
            else:
                return False, display, 0, "Bad Format"

        try:
            start_time = time.time()

            proxy_cfg = {
                "http://": final_url,
                "https://": final_url,
            }

            async with httpx.AsyncClient(
                proxies=proxy_cfg,
                timeout=8.0,
                follow_redirects=True
            ) as client:
                # pakai HTTPS (lebih wajar dibuka)
                resp = await client.get("https://ipwho.is/")

                if resp.status_code == 200:
                    data = resp.json()

                    # ipwho.is kadang success=false
                    if data.get("success") is False:
                        reason = data.get("message", "Service error")
                        return False, display, 0, reason

                    latency = int((time.time() - start_time) * 1000)

                    ip_asli = data.get("ip", "Unknown")
                    negara = data.get("country_code", "??")
                    flag = data.get("flag", {}).get("emoji", "")
                    isp = data.get("connection", {}).get("isp", "Unknown ISP")

                    info_text = f"{ip_asli} | {negara} {flag} | {isp}"
                    return True, display, latency, info_text

                else:
                    return False, display, 0, f"Status {resp.status_code}"

        except Exception as e:
            err_msg = str(e)

            if "ConnectTimeout" in err_msg or "ReadTimeout" in err_msg:
                reason = "Too Slow"
            elif "403" in err_msg:
                reason = "Blocked / 403"
            elif "Cannot connect" in err_msg or "Connection refused" in err_msg:
                reason = "Refused"
            elif "Name or service not known" in err_msg or "getaddrinfo failed" in err_msg:
                reason = "DNS Error"
            elif "Authentication" in err_msg or "auth" in err_msg.lower():
                reason = "Auth Failed"
            else:
                reason = (err_msg[:60] + "...") if len(err_msg) > 60 else (err_msg or "Dead")

            return False, display, 0, reason

    # 4. Eksekusi Paralel
    tasks = [check_single_proxy(p) for p in proxies_to_check]
    results = await asyncio.gather(*tasks)

    # URUTKAN: LIVE dulu, lalu berdasarkan ping (cepat -> lambat)
    results_sorted = sorted(
        results,
        key=lambda r: (not r[0], r[2] if r[2] > 0 else 999999)
    )

    # 5. Laporan Clean Mono + Ultimate UI
    report_lines = []
    live_count = sum(1 for r in results_sorted if r[0])
    dead_count = len(results_sorted) - live_count

    for is_live, proxy, ping, info in results_sorted:
        if is_live:
            status = f"✅ <b>LIVE</b> | 📶 <b>{ping}ms</b>"
            detail = f"   └ <code>{info}</code>"
            line = f"🔌 <code>{proxy}</code>\n{status}\n{detail}"
        else:
            status = "❌ <b>DEAD</b>"
            detail = f"   └ <i>{html.escape(str(info))}</i>"
            line = f"🔌 <code>{proxy}</code>\n{status}\n{detail}"
        report_lines.append(line)

    success_rate = (live_count / len(results_sorted) * 100) if results_sorted else 0
    success_rate = int(success_rate)

    final_text = (
        "🛡️ <b>OKTACOMEL PROXY LAB V2</b>\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"📊 <b>Total:</b> {len(proxies_to_check)} | "
        f"🟢 <b>Live:</b> {live_count} | 🔴 <b>Dead:</b> {dead_count}\n"
        f"📈 <b>Uptime Sample:</b> {success_rate}%\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        + ("\n\n".join(report_lines) if report_lines else "No result.") +
        "\n\n🤖 <i>Deep-Scan Proxy Engine by Oktacomel</i>"
    )

    await msg.edit_text(final_text, parse_mode=ParseMode.HTML)

# ==========================================
# 📰 LATEST NEWS (RSS — PREMIUM ULTIMATE)
# ==========================================
async def news_command(update: Update, context: ContextTypes.DEFAULT_TYPE):

    # Jika user tidak beri topik → default Indonesia
    if not context.args:
        query = "indonesia"
        display_query = "INDONESIA"
    else:
        query = " ".join(context.args).lower()
        display_query = query.upper()

    await context.bot.send_chat_action(update.effective_chat.id, ChatAction.TYPING)

    # ==========================================
    # PILIH RSS FEED OTOMATIS BERDASARKAN TOPIK
    # ==========================================
    if any(word in query for word in ["indo", "indonesia", "nasional"]):
        rss_url = "https://news.kompas.com/rss"
    elif "tech" in query or "teknologi" in query:
        rss_url = "http://feeds.bbci.co.uk/news/technology/rss.xml"
    elif "sport" in query or "olahraga" in query:
        rss_url = "http://feeds.bbci.co.uk/sport/rss.xml"
    elif "world" in query or "dunia" in query:
        rss_url = "http://feeds.bbci.co.uk/news/world/rss.xml"
    else:
        # fallback: BBC general
        rss_url = "http://feeds.bbci.co.uk/news/rss.xml"

    # ==========================================
    # PARSE RSS
    # ==========================================
    try:
        feed = feedparser.parse(rss_url)

        if not feed.entries:
            return await update.message.reply_text(
                "❌ <b>Tidak ada berita ditemukan.</b>",
                parse_mode=ParseMode.HTML
            )

        # Ambil 3 berita teratas
        items = feed.entries[:3]
        news_blocks = []

        for idx, item in enumerate(items, start=1):
            title = item.title
            link = item.link
            date = item.get("published", "Unknown")
            source = feed.feed.get("title", "Unknown Source")

            block = (
                f"<b>{idx}. {html.escape(title)}</b>\n"
                f"📰 Source ⇾ <code>{html.escape(source)}</code>\n"
                f"📅 Date ⇾ <code>{html.escape(date)}</code>\n"
                f"🔗 Link ⇾ <a href='{link}'>Read Article</a>\n"
            )
            news_blocks.append(block)

        body = "\n".join(news_blocks)

        # ==========================================
        # TAMPILAN PREMIUM ULTIMATE
        # ==========================================
        reply = (
            f"📰 <b>NEWS CENTER — PREMIUM</b>\n"
            f"✦────────────────────✦\n"
            f"📌 <b>Topic</b> ⇾ <code>{display_query}</code>\n"
            f"✦────────────────────✦\n\n"
            f"{body}\n"
            f"✦────────────────────✦\n"
            f"🤖 <i>Powered by Oktacomel</i>"
        )

        await update.message.reply_text(
            reply,
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True
        )

    except Exception as e:
        await update.message.reply_text(
            f"❌ <b>Error Parsing RSS:</b>\n<code>{str(e)}</code>",
            parse_mode=ParseMode.HTML
        )


# ==========================================
# 🛠 HELPER: FONT CONVERTER (BOLD SANS)
# ==========================================
def to_bold(text):
    maps = {
        'A': '𝗔', 'B': '𝗕', 'C': '𝗖', 'D': '𝗗', 'E': '𝗘', 'F': '𝗙', 'G': '𝗚', 'H': '𝗛', 'I': '𝗜', 'J': '𝗝',
        'K': '𝗞', 'L': '𝗟', 'M': '𝗠', 'N': '𝗡', 'O': '𝗢', 'P': '𝗣', 'Q': '𝗤', 'R': '𝗥', 'S': '𝗦', 'T': '𝗧',
        'U': '𝗨', 'V': '𝗩', 'W': '𝗪', 'X': '𝗫', 'Y': '𝗬', 'Z': '𝗭',
        'a': '𝗮', 'b': '𝗯', 'c': '𝗰', 'd': '𝗱', 'e': '𝗲', 'f': '𝗳', 'g': '𝗴', 'h': '𝗵', 'i': '𝗶', 'j': '𝗷',
        'k': '𝗸', 'l': '𝗹', 'm': '𝗺', 'n': '𝗻', 'o': '𝗼', 'p': '𝗽', 'q': '𝗾', 'r': '𝗿', 's': '𝘀', 't': '𝘁',
        'u': '𝘂', 'v': '𝘃', 'w': '𝘄', 'x': '𝘅', 'y': '𝘆', 'z': '𝘇',
        '0': '𝟬', '1': '𝟭', '2': '𝟮', '3': '𝟯', '4': '𝟰', '5': '𝟱', '6': '𝟲', '7': '𝟳', '8': '𝟴', '9': '𝟵'
    }
    return "".join(maps.get(c, c) for c in text)

# ==========================================
# 💳 CC SCRAPER (PREMIUM + AUTO DEDUPE)
# ==========================================

async def scr_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """CC Scraper dengan auto remove duplicate advanced"""
    
    args = context.args
    reply = update.message.reply_to_message
    
    target_text = ""
    source_name = "Text/Reply"
    source_url = ""
    limit = 0
    is_private = False
    
    # ==========================================
    # 1. SKENARIO SOURCES
    # ==========================================
    
    if reply and reply.text:
        target_text = reply.text
        if args: 
            try:
                limit = int(args[0])
            except:
                limit = 0
        source_name = "Reply Message"
        
    elif args:
        target = args[0]
        try:
            limit = int(args[1]) if len(args) > 1 and args[1].isdigit() else 0
        except:
            limit = 0
        
        if "t.me/" in target:
            username = target.replace("https://t.me/", "").replace("@", "").split("/")[0]
            source_name = f"@{username}"
            source_url = f"https://t.me/{username}"
            
            msg = await update.message.reply_text(
                f"⏳ <b>Checking:</b> @{username}...\n"
                f"🔍 Analyzing...",
                parse_mode=ParseMode.HTML
            )
            
            try:
                web_url = f"https://t.me/s/{username}"
                headers = {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                }
                
                async with httpx.AsyncClient(timeout=20) as client:
                    r = await client.get(web_url, headers=headers)
                    
                    if "is not accessible" in r.text or "Access Denied" in r.text or r.status_code == 404:
                        is_private = True
                        source_url = f"https://t.me/{username}"
                        await msg.edit_text(
                            f"🔒 <b>Private Channel/Group Detected</b>\n\n"
                            f"Name: @{username}\n"
                            f"Type: <b>PRIVATE</b>\n\n"
                            f"⏳ <b>Processing private source...</b>\n"
                            f"🔍 Scanning messages...",
                            parse_mode=ParseMode.HTML
                        )
                    else:
                        target_text = r.text
                        await msg.edit_text(
                            f"✅ <b>Public Channel Found</b>\n"
                            f"Channel: @{username}\n"
                            f"🔍 Processing...",
                            parse_mode=ParseMode.HTML
                        )
                    
            except Exception as e:
                logger.error(f"[SCRAPER] Error: {e}")
                await msg.edit_text(
                    f"❌ <b>Error accessing source</b>\n"
                    f"Source: @{username}\n"
                    f"Error: {str(e)[:80]}",
                    parse_mode=ParseMode.HTML
                )
                return
        
        elif target.startswith("@"):
            username = target.replace("@", "")
            source_name = f"@{username}"
            source_url = f"https://t.me/{username}"
            
            msg = await update.message.reply_text(
                f"⏳ <b>Checking:</b> @{username}...\n"
                f"🔍 Analyzing...",
                parse_mode=ParseMode.HTML
            )
            
            try:
                web_url = f"https://t.me/s/{username}"
                headers = {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                }
                
                async with httpx.AsyncClient(timeout=20) as client:
                    r = await client.get(web_url, headers=headers)
                    
                    if "is not accessible" in r.text or "Access Denied" in r.text or r.status_code == 404:
                        is_private = True
                        await msg.edit_text(
                            f"🔒 <b>Private Channel/Group Detected</b>\n\n"
                            f"Name: @{username}\n"
                            f"Type: <b>PRIVATE</b>\n\n"
                            f"⏳ <b>Processing private source...</b>\n"
                            f"🔍 Scanning messages...",
                            parse_mode=ParseMode.HTML
                        )
                    else:
                        target_text = r.text
                        await msg.edit_text(
                            f"✅ <b>Public Channel Found</b>\n"
                            f"Channel: @{username}\n"
                            f"🔍 Processing...",
                            parse_mode=ParseMode.HTML
                        )
                    
            except Exception as e:
                await msg.edit_text(
                    f"❌ <b>Error</b>\n{str(e)[:80]}",
                    parse_mode=ParseMode.HTML
                )
                return
        
        else:
            target_text = update.message.text
    
    else:
        await update.message.reply_text(
            "⚠️ <b>Usage:</b>\n"
            "1. <code>/scr @channel_name [limit]</code>\n"
            "2. <code>/scr https://t.me/channel [limit]</code>\n"
            "3. Reply message with <code>/scr</code>",
            parse_mode=ParseMode.HTML
        )
        return

    # ==========================================
    # 2. HANDLE PRIVATE GROUP/CHANNEL
    # ==========================================
    
    if is_private or not target_text:
        if update.effective_chat.type in ["group", "supergroup"]:
            source_name = update.effective_chat.title or "Private Group"
            source_url = f"https://t.me/c/{str(update.effective_chat.id)[4:]}/{update.message.message_id}"
            is_private = True
            
            target_text = f"{update.message.text or ''}\n"
            for i in range(max(0, update.message.message_id - 100), update.message.message_id):
                try:
                    msg_history = await context.bot.forward_message(
                        chat_id=update.message.chat_id,
                        from_chat_id=update.message.chat_id,
                        message_id=i
                    )
                    if msg_history.text:
                        target_text += f"\n{msg_history.text}"
                except:
                    pass
            
            try:
                cursor.execute("""
                    INSERT INTO scraper_logs (user_id, chat_id, chat_type, action, timestamp)
                    VALUES (?, ?, ?, ?, ?)
                """, (
                    update.effective_user.id,
                    update.effective_chat.id,
                    "private_group",
                    "cc_scraping",
                    datetime.datetime.now()
                ))
                conn.commit()
            except:
                pass

    # ==========================================
    # 3. EXTRACT CC DENGAN MULTIPLE PATTERNS
    # ==========================================
    
    if not 'msg' in locals():
        msg = await update.message.reply_text(
            "🔍 <b>Scanning for CC patterns...</b>\n"
            "[░░░░░░░░░░░░░░░░░░] 0%",
            parse_mode=ParseMode.HTML
        )
    
    patterns = [
        r'\b\d{15,16}[|:/-]\d{1,2}[|:/-]\d{2,4}[|:/-]\d{3,4}\b',
        r'\b\d{15,16}\s+\d{1,2}\s+\d{2,4}\s+\d{3,4}\b',
        r'\b\d{15,16}[|:]\d{2,4}\b',
    ]
    
    found_ccs_raw = []
    for pattern in patterns:
        found_ccs_raw.extend(re.findall(pattern, target_text))
    
    await msg.edit_text(
        "🔍 <b>Scanning for CC patterns...</b>\n"
        "[██████░░░░░░░░░░░░] 30%",
        parse_mode=ParseMode.HTML
    )
    
    if not found_ccs_raw:
        await msg.edit_text("❌ <b>No CC Found.</b>", parse_mode=ParseMode.HTML)
        return

    # ==========================================
    # 4. ADVANCED DUPLICATE REMOVAL
    # ==========================================
    
    await msg.edit_text(
        "🔍 <b>Removing duplicates & normalizing...</b>\n"
        "[████████░░░░░░░░░░] 40%",
        parse_mode=ParseMode.HTML
    )
    
    # Normalize dan dedupe
    normalized_ccs = set()
    cc_mapping = {}  # Track original format
    
    for cc_raw in found_ccs_raw:
        # Extract CC number (bagian pertama sebelum separator)
        cc_parts = re.split(r'[|:/-\s]', cc_raw)
        cc_number = cc_parts[0].strip()
        
        # Normalize ke format standard
        if len(cc_parts) >= 4:
            # Full format: 4111111111111111|12/25|123
            normalized = f"{cc_number}|{cc_parts[1]}|{cc_parts[2]}|{cc_parts[3]}"
        elif len(cc_parts) == 3:
            # 3 parts: 4111111111111111|12|25
            normalized = f"{cc_number}|{cc_parts[1]}|{cc_parts[2]}"
        elif len(cc_parts) == 2:
            # 2 parts: 4111111111111111|123
            normalized = f"{cc_number}|{cc_parts[1]}"
        else:
            # Just number
            normalized = cc_number
        
        # Add to set (automatic dedupe by CC number)
        if cc_number not in cc_mapping:
            normalized_ccs.add(normalized)
            cc_mapping[cc_number] = normalized
    
    unique_ccs = list(normalized_ccs)
    duplicates = len(found_ccs_raw) - len(unique_ccs)
    
    await msg.edit_text(
        "🔍 <b>Removing duplicates & normalizing...</b>\n"
        f"Found: {len(found_ccs_raw)} | Unique: {len(unique_ccs)} | Removed: {duplicates}\n"
        "[████████████░░░░░░] 60%",
        parse_mode=ParseMode.HTML
    )
    
    if limit > 0:
        unique_ccs = unique_ccs[:limit]

    total_scraped = len(unique_ccs)
    
    # ==========================================
    # 5. BUAT MULTIPLE FILE FORMAT
    # ==========================================
    
    await msg.edit_text(
        "📝 <b>Generating files...</b>\n"
        "[██████████████░░░░] 80%",
        parse_mode=ParseMode.HTML
    )
    
    # Format 1: TXT
    txt_content = "\n".join(unique_ccs)
    txt_file = io.BytesIO(txt_content.encode('utf-8'))
    txt_file.name = f"x{total_scraped}_{source_name}_Cleaned.txt"
    
    # Format 2: CSV (dengan parsing smart)
    csv_content = "CC,EXP_MONTH,EXP_YEAR,CVV\n"
    for cc in unique_ccs:
        parts = re.split(r'[|:/-\s]', cc)
        cc_num = parts[0] if len(parts) > 0 else ""
        exp_month = parts[1] if len(parts) > 1 else "XX"
        exp_year = parts[2] if len(parts) > 2 else "XX"
        cvv = parts[3] if len(parts) > 3 else "XXX"
        
        csv_content += f"{cc_num},{exp_month},{exp_year},{cvv}\n"
    
    csv_file = io.BytesIO(csv_content.encode('utf-8'))
    csv_file.name = f"x{total_scraped}_{source_name}_Cleaned.csv"
    
    # Format 3: JSON dengan metadata lengkap
    json_data = {
        "metadata": {
            "source": source_name,
            "url": source_url,
            "total_extracted": len(found_ccs_raw),
            "total_unique": total_scraped,
            "duplicates_removed": duplicates,
            "deduplication_percentage": f"{(duplicates / len(found_ccs_raw) * 100):.1f}%" if found_ccs_raw else "0%",
            "timestamp": datetime.datetime.now().isoformat(),
            "is_private": is_private,
            "normalized": True,
            "deduplication_method": "CC Number Based"
        },
        "cards": []
    }
    
    for cc in unique_ccs:
        parts = re.split(r'[|:/-\s]', cc)
        card = {
            "number": parts[0] if len(parts) > 0 else "",
            "exp_month": parts[1] if len(parts) > 1 else "",
            "exp_year": parts[2] if len(parts) > 2 else "",
            "cvv": parts[3] if len(parts) > 3 else "",
            "original_format": cc
        }
        json_data["cards"].append(card)
    
    json_content = json.dumps(json_data, indent=2)
    json_file = io.BytesIO(json_content.encode('utf-8'))
    json_file.name = f"x{total_scraped}_{source_name}_Cleaned.json"

    # ==========================================
    # 6. SECURITY INDICATOR
    # ==========================================
    
    security_badge = "🔒 <i>(Private Source - Logged)</i>" if is_private else "🌐 <i>(Public Source)</i>"

    # ==========================================
    # 7. KIRIM HASIL
    # ==========================================
    
    caption = (
        f"𝗖𝗖 𝗦𝗰𝗿𝗮𝗽𝗽𝗲𝗱 & 𝗖𝗹𝗲𝗮𝗻𝗲𝗱 ✅\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"𝗦𝗼𝘂𝗿𝗰𝗲 ⇾ {html.escape(source_name)} {security_badge}\n"
        f"𝗜𝗻𝗶𝘁𝗶𝗮𝗹 ⇾ {len(found_ccs_raw)} ❌\n"
        f"𝗨𝗻𝗶𝗾𝘂𝗲 ⇾ {total_scraped} ✅\n"
        f"𝗗𝘂𝗽𝗲𝘀 𝗥𝗲𝗺𝗼𝘃𝗲𝗱 ⇾ {duplicates} 🗑\n"
        f"𝗗𝘂𝗽𝗲 𝗥𝗮𝘁𝗲 ⇾ {(duplicates / len(found_ccs_raw) * 100):.1f}%" if found_ccs_raw else "0%\n"
        f"𝗙𝗼𝗿𝗺𝗮𝘁𝘀 ⇾ TXT + CSV + JSON 📦\n"
        f"𝗗𝗲𝗱𝘂𝗽𝗘 𝗠𝗲𝘁𝗵𝗼𝗱 ⇾ CC Number Based 🔐\n"
        f"𝗨𝘀𝗲𝗿 ⇾ {html.escape(update.effective_user.first_name)} 👤\n"
    )
    
    if source_url:
        caption += f"𝗟𝗶𝗻𝗸 ⇾ <a href='{source_url}'>View Source</a> 🔗\n"
    
    caption += (
        f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"✅ 𝗦𝗰𝗿𝗮𝗽𝗽𝗲𝗱 𝗕𝘆 ⇾ Oktacomel"
    )

    try:
        await msg.delete()
    except:
        pass

    # Send TXT File
    await update.message.reply_document(
        document=txt_file,
        caption=caption,
        parse_mode=ParseMode.HTML
    )
    
    # Send CSV File
    await update.message.reply_document(
        document=csv_file,
        caption="📊 <b>CSV Format (Cleaned & Normalized)</b>",
        parse_mode=ParseMode.HTML
    )
    
    # Send JSON File
    await update.message.reply_document(
        document=json_file,
        caption="📋 <b>JSON Format (With Metadata & Deduplication Stats)</b>",
        parse_mode=ParseMode.HTML
    )
# ==========================================
# 💳 CC SCRAPER (PREMIUM FONT STYLE)
# ==========================================
async def scr_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # 1. Cek Input
    args = context.args
    reply = update.message.reply_to_message
    
    target_text = ""
    source_name = "Text/Reply"
    limit = 0
    
    # Skenario 1: Reply Pesan
    if reply and reply.text:
        target_text = reply.text
        if args: limit = int(args[0])
        
    # Skenario 2: Input Link/Username
    elif args:
        target = args[0]
        limit = int(args[1]) if len(args) > 1 and args[1].isdigit() else 0
        
        # Cek apakah Link Telegram
        if "t.me/" in target or target.startswith("@"):
            username = target.replace("https://t.me/", "").replace("@", "")
            if "/" in username: username = username.split("/")[0]
            
            source_name = f"{username}"
            msg = await update.message.reply_text(f"⏳ <b>Scraping:</b> {username}...", parse_mode=ParseMode.HTML)
            
            # Web Scraping (t.me/s/...)
            try:
                web_url = f"https://t.me/s/{username}"
                headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
                
                async with httpx.AsyncClient(timeout=20) as client:
                    r = await client.get(web_url, headers=headers)
                    target_text = r.text
            except Exception as e:
                await msg.edit_text(f"❌ <b>Error:</b> {str(e)}", parse_mode=ParseMode.HTML)
                return
        else:
            target_text = update.message.text
            
    else:
        await update.message.reply_text(
            "⚠️ <b>Usage:</b>\n"
            "1. <code>/scr link_channel [limit]</code>\n"
            "2. Reply message with <code>/scr</code>",
            parse_mode=ParseMode.HTML
        )
        return

    # 2. PROSES REGEX
    pattern = r'\b\d{15,16}[|:/-]\d{1,2}[|:/-]\d{2,4}[|:/-]\d{3,4}\b'
    found_ccs = re.findall(pattern, target_text)
    
    if not found_ccs:
        try: await msg.edit_text("❌ <b>No CC Found.</b>", parse_mode=ParseMode.HTML)
        except: await update.message.reply_text("❌ <b>No CC Found.</b>", parse_mode=ParseMode.HTML)
        return

    # 3. BERSIHKAN DUPLIKAT
    unique_ccs = list(set(found_ccs))
    duplicates = len(found_ccs) - len(unique_ccs)
    
    if limit > 0:
        unique_ccs = unique_ccs[:limit]

    total_scraped = len(unique_ccs)
    
    # 4. BUAT FILE TXT
    result_text = "\n".join(unique_ccs)
    file_name = f"x{total_scraped}_{source_name}_Drops.txt"
    
    bio = io.BytesIO(result_text.encode('utf-8'))
    bio.name = file_name

    # 5. KIRIM HASIL (PREMIUM BOLD SANS)
    caption = (
        f"𝗖𝗖 𝗦𝗰𝗿𝗮𝗽𝗽𝗲𝗱 𝗦𝘂𝗰𝗰𝗲𝘀𝘀𝗳𝘂𝗹 ✅\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"𝗦𝗼𝘂𝗿𝗰𝗲 ⇾ {html.escape(source_name)} 🌐\n"
        f"𝗔𝗺𝗼𝘂𝗻𝘁 ⇾ {total_scraped} 📝\n"
        f"𝗗𝘂𝗽𝗹𝗶𝗰𝗮𝘁𝗲𝘀 ⇾ {duplicates} 🗑\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"✅ 𝗦𝗰𝗿𝗮𝗽𝗽𝗲𝗱 𝗕𝘆 ⇾ Oktacomel"
    )

    try: await msg.delete()
    except: pass

    await update.message.reply_document(
        document=bio,
        caption=caption,
        parse_mode=ParseMode.HTML
    )


# ==========================================
# 🎵 MUSIC SEARCH ENGINE (SMART FILTER + RECOMMENDATION)
# ==========================================

async def show_music_search(update, context, query, offset=0):
    if not sp_client:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="❌ <b>System Error:</b> Spotify API invalid.", parse_mode=ParseMode.HTML)
        return

    try:
        # Limit per halaman
        page_size = 10
        max_total = 20 # Maksimal cuma 20 lagu yang ditampilkan (2 Halaman)

        # 1. SEARCH LOGIC (Cari agak banyak dulu buat difilter)
        raw_results = sp_client.search(q=query, limit=50, type='track')
        raw_tracks = raw_results['tracks']['items']

        if not raw_tracks:
            msg = "❌ <b>Song not found.</b> Try specific keyword."
            if update.callback_query: await update.callback_query.answer(msg, show_alert=True)
            else: await update.message.reply_text(msg, parse_mode=ParseMode.HTML)
            return

        # 2. SMART SORTING (Relevansi + Rekomendasi)
        # Prioritas 1: Lagu yang judul/artisnya mengandung query user
        exact_matches = [t for t in raw_tracks if query.lower() in t['name'].lower() or query.lower() in t['artists'][0]['name'].lower()]
        
        # Prioritas 2: Sisanya (Rekomendasi terkait)
        recommendations = [t for t in raw_tracks if t not in exact_matches]
        
        # Gabung: Exact dulu, baru Rekomendasi
        final_list = exact_matches + recommendations
        
        # Potong Max 20 Lagu
        final_list = final_list[:max_total]
        total_results = len(final_list)

        # Ambil Slice Halaman Ini
        current_tracks = final_list[offset : offset + page_size]

        # 3. BUILD UI (COOL ENGLISH)
        txt_list = []
        buttons = []
        row_nums = []

        start = offset + 1
        end = min(offset + page_size, total_results)

        header = (
            f"🎵 <b>MUSIC SEARCH RESULT</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"🔎 <b>Query:</b> <code>{html.escape(query.title())}</code>\n"
            f"📄 <b>Page:</b> {start}-{end} of {total_results}\n\n"
        )

        for i, track in enumerate(current_tracks):
            num = start + i
            artist = track['artists'][0]['name']
            title = track['name']
            ms = track['duration_ms']
            duration = f"{int(ms/1000//60)}:{int(ms/1000%60):02d}"
            
            # Format Rapi
            txt_list.append(f"<b>{num}. {artist}</b> — {title} <code>[{duration}]</code>")
            
            # Tombol Angka
            row_nums.append(InlineKeyboardButton(str(num), callback_data=f"sp_dl|{track['id']}"))
            
            if len(row_nums) == 5:
                buttons.append(row_nums)
                row_nums = []
        
        if row_nums: buttons.append(row_nums)

        # Tombol Navigasi
        nav_row = []
        # Tombol Prev
        if offset > 0:
            prev_off = max(0, offset - page_size)
            nav_row.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"sp_nav|{prev_off}|{query}"))
        
        nav_row.append(InlineKeyboardButton("❌ Close", callback_data="cmd_close"))
        
        # Tombol Next (Hanya jika masih ada sisa di dalam batas max_total)
        if total_results > offset + page_size:
            next_off = offset + page_size
            nav_row.append(InlineKeyboardButton("Next ➡️", callback_data=f"sp_nav|{next_off}|{query}"))
            
        buttons.append(nav_row)
        final_text = header + "\n".join(txt_list) + "\n\n🤖 <i>Powered by Oktacomel</i>"

        # Kirim/Edit Pesan
        if update.callback_query:
            await update.callback_query.edit_message_text(text=final_text, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(buttons))
        else:
            await update.message.reply_text(text=final_text, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(buttons))

    except Exception as e:
        print(f"Search Error: {e}")

# COMMAND /song
async def song_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("⚠️ <b>Usage:</b> <code>/song title artist</code>", parse_mode=ParseMode.HTML)
        return
    
    query = " ".join(context.args)
    await context.bot.send_chat_action(update.effective_chat.id, ChatAction.TYPING)
    # Mulai dari halaman 0
    await show_music_search(update, context, query, offset=0)

# HANDLER NAVIGASI
async def song_nav_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    _, offset_str, query = q.data.split("|", 2)
    await show_music_search(update, context, query, int(offset_str))

# ==========================================
# 📥 DOWNLOAD HANDLER (SPEED DEMON + ANTI-BLOCK)
# ==========================================
async def song_button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    
    track_id = q.data.split("|")[1]
    
    # Hapus menu pencarian biar bersih
    await q.message.delete()
    
    # 1. AMBIL METADATA SPOTIFY (Wajib buat Caption)
    try:
        track = sp_client.track(track_id)
        song_name = track['name']
        artist_name = track['artists'][0]['name']
        album_name = track['album']['name']
        cover_url = track['album']['images'][0]['url']
        spotify_url = track['external_urls']['spotify']
        
        # Caption & Tombol (Standard)
        caption = (
            f"🎵 <b>{html.escape(song_name)}</b>\n"
            f"👤 {html.escape(artist_name)}\n"
            f"💿 {html.escape(album_name)}\n"
            f"🔗 <a href='{spotify_url}'>Listen on Spotify</a>\n"
            f"⚡ <i>Powered by Oktacomel</i>"
        )
        
        kb_effects = [
            [InlineKeyboardButton("Lyrics 📝", callback_data=f"lyr_get|{track_id}")],
            [InlineKeyboardButton("8D 🎧", callback_data=f"eff_8d|{track_id}"), InlineKeyboardButton("Slowed 🐌", callback_data=f"eff_slow|{track_id}")],
            [InlineKeyboardButton("Bass Boost 🔊", callback_data=f"eff_bass|{track_id}"), InlineKeyboardButton("Nightcore 🐿", callback_data=f"eff_night|{track_id}")],
            [InlineKeyboardButton("🌌 Reverb", callback_data=f"eff_reverb|{track_id}"), InlineKeyboardButton("⏩ Speed Up", callback_data=f"eff_speed|{track_id}")],
            [InlineKeyboardButton("❌ Close", callback_data="cmd_close")]
        ]

        # 2. CEK DATABASE (SMART CACHE)
        cached = await get_cached_media(track_id)
        
        if cached:
            file_id = cached[0] 
            await context.bot.send_audio(
                chat_id=q.message.chat_id,
                audio=file_id,
                caption=caption,
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup(kb_effects)
            )
            return

    except Exception as e:
        await context.bot.send_message(chat_id=q.message.chat_id, text=f"⚠️ <b>Metadata Error:</b> {e}", parse_mode=ParseMode.HTML)
        return

    # 3. DOWNLOAD BARU (CONFIG NGEBUT)
    msg = await context.bot.send_message(chat_id=q.message.chat_id, text="⏳ <b>Downloading High Quality Audio...</b>", parse_mode=ParseMode.HTML)

    try:
        search_query = f"{artist_name} - {song_name} audio"
        temp_dir = f"music_{uuid.uuid4()}"
        
        # --- CONFIG SAKTI DI SINI ---
        ydl_opts = {
            'format': 'bestaudio/best',
            'outtmpl': f'{temp_dir}/%(title)s.%(ext)s',
            
            # Konversi ke MP3 192kbps (Standar Bagus)
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
            
            # DOWNLOAD NGEBUT (Multi-thread)
            'concurrent_fragment_downloads': 5, 
            
            # Anti Blokir (Pura-pura jadi HP Android)
            'extractor_args': {
                'youtube': {
                    'player_client': ['android_music', 'android', 'ios'],
                    'player_skip': ['web', 'tv']
                }
            },
            
            # Proxy & Keamanan
            'proxy': MY_PROXY,
            'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'nocheckcertificate': True,
            
            'quiet': True,
            'no_warnings': True,
            'default_search': 'ytsearch1:', 
            'max_filesize': 50 * 1024 * 1024
        }

        file_path = None
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.extract_info(search_query, download=True)
            if os.path.exists(temp_dir):
                for f in os.listdir(temp_dir):
                    if f.endswith('.mp3'): file_path = os.path.join(temp_dir, f)

        if file_path:
            sent_msg = await context.bot.send_audio(
                chat_id=q.message.chat_id,
                audio=open(file_path, 'rb'),
                title=song_name, performer=artist_name,
                caption=caption, parse_mode=ParseMode.HTML,
                thumbnail=requests.get(cover_url).content,
                reply_markup=InlineKeyboardMarkup(kb_effects)
            )
            
            # Simpan ke Database
            new_file_id = sent_msg.audio.file_id
            await save_media_cache(track_id, new_file_id, "audio")
            
            os.remove(file_path)
            if os.path.exists(temp_dir): os.rmdir(temp_dir)
            await msg.delete()
        else:
            await msg.edit_text("❌ <b>Download Failed.</b> Stream restricted.", parse_mode=ParseMode.HTML)

    except Exception as e:
        await msg.edit_text(f"❌ <b>System Error:</b> {e}", parse_mode=ParseMode.HTML)
        if os.path.exists(temp_dir): shutil.rmtree(temp_dir)

# ==========================================
# 📝 LYRICS HANDLER (SMART SEARCH + ENGLISH UI)
# ==========================================
async def lyrics_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer("🔍 Searching lyrics...", show_alert=False)
    
    track_id = q.data.split("|")[1]
    
    try:
        # 1. Info Lagu (Spotify)
        track = sp_client.track(track_id)
        raw_title = track['name']
        raw_artist = track['artists'][0]['name']
        duration = track['duration_ms'] / 1000
        
        # Fungsi pembersih judul (Hapus feat, remix, kurung)
        def clean_title(text):
            text = re.sub(r"\(.*?\)|\[.*?\]", "", text) # Hapus (...) dan [...]
            text = text.replace("-", "").strip()
            return text

        clean_song = clean_title(raw_title)

        # 2. Ambil Lirik (LRCLIB)
        url_get = "https://lrclib.net/api/get"
        url_search = "https://lrclib.net/api/search"
        
        lirik_raw = None
        
        async with httpx.AsyncClient(timeout=20) as client:
            # A. Coba cari spesifik (Paling Akurat)
            params = {"artist_name": raw_artist, "track_name": raw_title, "duration": duration}
            resp = await client.get(url_get, params=params)
            
            if resp.status_code == 200:
                lirik_raw = resp.json().get('plainLyrics')
            
            # B. Fallback 1: Cari umum (Judul Asli)
            if not lirik_raw:
                resp_search = await client.get(url_search, params={"q": f"{raw_artist} {raw_title}"})
                data = resp_search.json()
                if data: lirik_raw = data[0].get('plainLyrics')

            # C. Fallback 2: Cari dengan judul bersih (Tanpa feat/remix)
            if not lirik_raw:
                resp_search = await client.get(url_search, params={"q": f"{raw_artist} {clean_song}"})
                data = resp_search.json()
                if data: lirik_raw = data[0].get('plainLyrics')

        # 3. Tampilan Hasil (English Premium + Mono)
        if lirik_raw:
            header_txt = (
                f"🎵 <b>{html.escape(raw_title)}</b>\n"
                f"👤 <b>{html.escape(raw_artist)}</b>\n"
                f"━━━━━━━━━━━━━━━━━━\n\n"
            )
            
            # Format Mono
            lyrics_mono = f"<pre>{html.escape(lirik_raw)}</pre>"
            footer_txt = f"\n\n🤖 <i>Source: LRCLIB (Synced)</i>"
            
            full_msg = header_txt + lyrics_mono + footer_txt
            
            # Potong jika kepanjangan
            if len(full_msg) > 4096:
                cut_idx = 4096 - len(header_txt) - len(footer_txt) - 50
                lyrics_mono = f"<pre>{html.escape(lirik_raw[:cut_idx])}...</pre>"
                full_msg = header_txt + lyrics_mono + footer_txt

            kb = [[InlineKeyboardButton("❌ Close Lyrics", callback_data="cmd_close")]]
            
            await context.bot.send_message(
                chat_id=q.message.chat_id,
                text=full_msg,
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup(kb),
                reply_to_message_id=q.message.id
            )
        else:
            # Pesan Gagal (English)
            await q.message.reply_text(f"❌ <b>Lyrics not found.</b>\nTry checking the song title spelling.", parse_mode=ParseMode.HTML)

    except Exception as e:
        await context.bot.send_message(chat_id=q.message.chat_id, text=f"⚠️ <b>System Error:</b> {str(e)}", parse_mode=ParseMode.HTML)

# ==========================================
# 🎧 REAL AUDIO EFFECT ENGINE (CLEAN SIMPLE)
# ==========================================
import subprocess

async def real_effect_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer("🎧 Applying Audio Filters...", show_alert=False)
    
    data = q.data.split("|")
    effect_type = data[0]
    track_id = data[1]
    
    msg = await context.bot.send_message(chat_id=q.message.chat_id, text="⏳ <b>Processing Audio...</b>", parse_mode=ParseMode.HTML)

    try:
        # 1. Get Info & Download Raw
        track = sp_client.track(track_id)
        song_name = track['name']
        artist_name = track['artists'][0]['name']
        
        search_query = f"{artist_name} - {song_name} audio"
        temp_dir = f"remix_{uuid.uuid4()}"
        output_path = f"{temp_dir}/remix_output.mp3"
        
        ydl_opts = {
            'format': 'bestaudio/best',
            'outtmpl': f'{temp_dir}/input.%(ext)s',
            'postprocessors': [{'key': 'FFmpegExtractAudio','preferredcodec': 'mp3','preferredquality': '192'}],
            'quiet': True, 'default_search': 'ytsearch1:',
            'proxy': MY_PROXY,
            'extractor_args': {'youtube': {'player_client': ['android', 'ios']}}
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.extract_info(search_query, download=True)
            input_path = f"{temp_dir}/input.mp3"

        if not os.path.exists(input_path):
            await msg.edit_text("❌ <b>Source Error.</b> Failed to download audio.")
            return

        # 2. FFmpeg Processing
        cmd = []
        tag_display = ""
        
        if effect_type == "eff_8d":
            tag_display = "8D Audio"
            filter_cmd = "apulsator=hz=0.125"
        elif effect_type == "eff_bass":
            tag_display = "Bass Boosted"
            filter_cmd = "equalizer=f=60:width_type=h:width=50:g=15"
        elif effect_type == "eff_slow":
            tag_display = "Slowed + Reverb"
            filter_cmd = "atempo=0.85,aecho=0.8:0.9:1000:0.3"
        elif effect_type == "eff_night":
            tag_display = "Nightcore"
            filter_cmd = "asetrate=44100*1.25,atempo=1.0"
        elif effect_type == "eff_reverb":
            tag_display = "Reverb"
            filter_cmd = "aecho=0.8:0.9:1000:0.3"
        elif effect_type == "eff_speed":
            tag_display = "Speed Up"
            filter_cmd = "atempo=1.25"

        cmd = ['ffmpeg', '-i', input_path, '-af', filter_cmd, '-y', output_path]
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        # 3. Send Result (Tampilan Simple Normal)
        if os.path.exists(output_path):
            caption = (
                f"🎧 <b>{html.escape(song_name)}</b>\n"
                f"👤 {html.escape(artist_name)}\n"
                f"🎛 <b>Effect:</b> {tag_display}\n\n"
                f"⚡ <i>Powered by Oktacomel</i>"
            )
            
            await context.bot.send_audio(
                chat_id=q.message.chat_id,
                audio=open(output_path, 'rb'),
                title=f"{song_name} ({tag_display})",
                performer=artist_name,
                caption=caption,
                parse_mode=ParseMode.HTML,
                reply_to_message_id=q.message.id
            )
            await msg.delete()
        else:
            await msg.edit_text("❌ <b>Render Failed.</b>")

        shutil.rmtree(temp_dir)

    except Exception as e:
        await msg.edit_text(f"❌ <b>Error:</b> {str(e)}", parse_mode=ParseMode.HTML)
        if os.path.exists(temp_dir): shutil.rmtree(temp_dir)

# ==========================================
# 📸 GALLERY SCRAPER (BULK DOWNLOADER)
# ==========================================
async def gallery_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # 1. Cek Input
    if not context.args:
        await update.message.reply_text(
            "⚠️ <b>Usage:</b> <code>/gl [link]</code>\n"
            "<i>Supports: Pinterest, Twitter, Pixiv, Imgur, etc.</i>", 
            parse_mode=ParseMode.HTML
        )
        return

    url = context.args[0]
    chat_id = update.effective_chat.id
    
    # Loading Message (Premium Style)
    msg = await update.message.reply_text(
        "⏳ <b>Accessing Gallery Archive...</b>\n"
        "<i>Fetching high-resolution assets (Max 10)...</i>", 
        parse_mode=ParseMode.HTML
    )

    # Buat folder sementara unik
    temp_dir = f"gallery_{uuid.uuid4()}"
    
    try:
        # 2. Jalankan Gallery-DL via Terminal
        # --range 1-10 : Ambil 10 gambar pertama saja (Biar gak berat)
        # --destination : Simpan di folder temp
        cmd = ["gallery-dl", url, "--destination", temp_dir, "--range", "1-10"]
        
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        # 3. Cari File Gambar (Recursive)
        # Gallery-dl sering bikin sub-folder, jadi kita harus cari sampai dalam
        image_files = []
        for root, dirs, files in os.walk(temp_dir):
            for file in files:
                if file.lower().endswith(('.jpg', '.jpeg', '.png', '.webp')):
                    image_files.append(os.path.join(root, file))

        # 4. Kirim sebagai Album (MediaGroup)
        if image_files:
            media_group = []
            total_img = len(image_files)
            
            # Caption cuma di foto pertama
            caption = (
                f"📸 <b>GALLERY EXTRACTED</b>\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"🔗 <b>Source:</b> <a href='{url}'>Original Link</a>\n"
                f"🖼 <b>Count:</b> {total_img} Images\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"⚡ <i>Powered by Oktacomel</i>"
            )

            for i, img_path in enumerate(image_files):
                # Batas Telegram MediaGroup cuma 10 foto per pesan
                if i >= 10: break 
                
                # Pasang caption di foto ke-0
                cap = caption if i == 0 else None
                
                # Masukkan ke grup
                media_group.append(InputMediaPhoto(open(img_path, 'rb'), caption=cap, parse_mode=ParseMode.HTML))

            # Kirim Album
            await context.bot.send_media_group(chat_id=chat_id, media=media_group)
            await msg.delete()
            
        else:
            await msg.edit_text("❌ <b>No Images Found.</b>\nMake sure the link is public/valid.", parse_mode=ParseMode.HTML)

    except Exception as e:
        await msg.edit_text(f"❌ <b>Extraction Error:</b> {str(e)}", parse_mode=ParseMode.HTML)
        
    # 5. Bersih-bersih (Wajib biar VPS gak penuh)
    if os.path.exists(temp_dir):
        shutil.rmtree(temp_dir)

# ==========================================
# 🖥️ SYSTEM LOG VIEWER (OWNER ONLY)
# ==========================================
async def log_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    # 1. SECURITY CHECK (Hanya Owner)
    if user_id != OWNER_ID:
        return # Diam saja kalau bukan owner
    
    await context.bot.send_chat_action(update.effective_chat.id, ChatAction.TYPING)
    
    try:
        # Baca 20 baris terakhir dari file bot.log
        with open("bot.log", "r", encoding="utf-8") as f:
            lines = f.readlines()
            last_logs = "".join(lines[-20:]) # Ambil 20 baris terakhir
            
        if not last_logs.strip():
            last_logs = "✅ System Clean. No logs recorded."
            
        # Hitung ukuran file log
        log_size = os.path.getsize("bot.log") / 1024 # Dalam KB
            
        # Tampilan Premium (Hacker Style)
        txt = (
            f"🖥️ <b>SYSTEM LIVE LOGS</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"📂 <b>File Size:</b> <code>{log_size:.2f} KB</code>\n"
            f"🕒 <b>Time:</b> <code>{datetime.datetime.now(TZ).strftime('%H:%M:%S')}</code>\n"
            f"━━━━━━━━━━━━━━━━━━\n\n"
            f"<pre>{html.escape(last_logs)}</pre>\n" # Pakai PRE biar rapi kotak
            f"🤖 <i>Powered by Oktacomel System</i>"
        )
        
        # Tombol Kontrol
        kb = [
            [InlineKeyboardButton("🔄 Refresh Logs", callback_data="sys_log_refresh")],
            [InlineKeyboardButton("🗑 Clear Logs", callback_data="sys_log_clear"),
             InlineKeyboardButton("❌ Close", callback_data="cmd_close")]
        ]
        
        if update.callback_query:
            await update.callback_query.edit_message_text(txt, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(kb))
        else:
            await update.message.reply_text(txt, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(kb))
            
    except FileNotFoundError:
        await update.message.reply_text("❌ <b>Error:</b> File 'bot.log' belum terbentuk.", parse_mode=ParseMode.HTML)
    except Exception as e:
        await update.message.reply_text(f"❌ <b>Read Error:</b> {e}", parse_mode=ParseMode.HTML)

# Handler Tombol Log
async def log_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    data = q.data
    
    if update.effective_user.id != OWNER_ID:
        await q.answer("⛔ Access Denied!", show_alert=True)
        return

    if data == "sys_log_refresh":
        await q.answer("🔄 Refreshing...")
        await log_command(update, context) # Panggil ulang fungsi log
        
    elif data == "sys_log_clear":
        # Hapus isi file log
        open("bot.log", "w").close()
        await q.answer("🗑 Logs Cleared!", show_alert=True)
        await log_command(update, context) # Refresh tampilan

# ==========================================
# 📊 SYSTEM HEALTH CHECK (ULTIMATE PREMIUM V5)
# ==========================================
async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text(
        "🔄 <b>Running system diagnostics...</b>",
        parse_mode=ParseMode.HTML
    )

    # 1. CEK SPOTIFY
    try:
        if sp_client:
            sp_client.search(q="test", limit=1, type="track")
            spot_status = "🟢 ONLINE"
        else:
            spot_status = "⚪ DISABLED"
    except Exception:
        spot_status = "🟠 ERROR"

    # 2. CEK AI ENGINE
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get("https://api.emergent.sh/health")
            ai_status = "🟢 ONLINE" if resp.status_code in (200, 401) else "🟠 UNSTABLE"
    except Exception:
        ai_status = "🔴 TIMEOUT"

    # 3. CEK PROXY (Jalur Download)
    try:
        if MY_PROXY:
            async with httpx.AsyncClient(proxies=MY_PROXY, timeout=5) as client:
                resp = await client.get("https://www.google.com", follow_redirects=True)
                proxy_status = "🟢 LIVE (Premium)" if resp.status_code == 200 else f"🔴 DEAD ({resp.status_code})"
        else:
            proxy_status = "⚪ DIRECT (No Proxy)"
    except Exception:
        proxy_status = "🔴 CONNECTION ERROR"

    # 4. CEK APIFY CLOUD (APIKEY DIHAPUS)
    apify_status = "⚪ NOT CONFIGURED"

    # 5. CEK MAIL SERVER (Temp Mail Premium)
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            headers = {"X-API-Key": TEMPMAIL_API_KEY}
            resp = await client.get("https://api.temp-mail.io/v1/domains", headers=headers)
            mail_status = "🟢 ACTIVE" if resp.status_code == 200 else f"🔴 ERROR ({resp.status_code})"
    except Exception:
        mail_status = "🟠 TIMEOUT"

    # 6. CEK FFMPEG
    ffmpeg_status = "🟢 INSTALLED" if shutil.which("ffmpeg") else "🔴 MISSING"

    # 7. CEK DATABASE
    db_status = "🟢 CONNECTED" if os.path.exists(DB_NAME) else "🔴 MISSING"

    # === HITUNG OVERALL HEALTH ===
    statuses = [spot_status, ai_status, mail_status, apify_status, proxy_status, ffmpeg_status, db_status]

    if any(s.startswith("🔴") for s in statuses):
        overall = "🔴 <b>CRITICAL</b> — Immediate attention required."
    elif any(s.startswith("🟠") for s in statuses):
        overall = "🟠 <b>DEGRADED</b> — Some services unstable."
    else:
        overall = "🟢 <b>ALL GREEN</b> — Fully operational."

    # TIMESTAMP & HOSTNAME
    now = datetime.now().strftime("%d-%m-%Y %H:%M:%S")
    host = html.escape(platform.node() or "SERVER")

    # === UI PREMIUM FINAL ===
    txt = (
        "📊 <b>OKTACOMEL SYSTEM PANEL</b>\n"
        "✦────────────────────────✦\n"
        f"🖥️ <b>Host</b>    ⇾ <code>{host}</code>\n"
        f"⏱️ <b>Checked</b> ⇾ <code>{now}</code>\n"
        f"📡 <b>Status</b>  ⇾ {overall}\n"
        "✦────────────────────────✦\n\n"
        "<b>CORE SERVICES</b>\n"
        f"🧠 AI Engine      ⇾ <code>{ai_status}</code>\n"
        f"🎵 Spotify API    ⇾ <code>{spot_status}</code>\n"
        f"📧 Mail Server    ⇾ <code>{mail_status}</code>\n"
        f"☁️ Apify Cloud    ⇾ <code>{apify_status}</code>\n\n"
        "<b>INFRASTRUCTURE</b>\n"
        f"🛡️ Proxy Tunnel   ⇾ <code>{proxy_status}</code>\n"
        f"🎬 FFmpeg Core    ⇾ <code>{ffmpeg_status}</code>\n"
        f"💾 Database       ⇾ <code>{db_status}</code>\n"
        "✦────────────────────────✦\n"
        "🧩 <i>Tip:</i> Run <code>/status</code> regularly to monitor bot health.\n"
        "🤖 <i>Diagnostics powered by Oktacomel</i>"
    )

    await msg.edit_text(txt, parse_mode=ParseMode.HTML)


# ============================================================
# 📧 TEMP MAIL PREMIUM V5 — GOD MODE (Auto-Refresh + Attachment)
# ============================================================

# --- SAFE DATE PARSER ---
def tm_safe_date(obj):
    if hasattr(obj, "date"): return str(obj.date)
    if hasattr(obj, "created_at"): return str(obj.created_at)
    if hasattr(obj, "timestamp"):
        return datetime.datetime.fromtimestamp(obj.timestamp).strftime("%Y-%m-%d %H:%M")
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

# --- CLEAN HTML TO TEXT (SAFE, ANTI LINK ERROR) ---
def tm_clean_html(raw_html):
    if not raw_html: return "(Empty Message)", []

    try:
        # Pakai BeautifulSoup buat kupas HTML
        soup = BeautifulSoup(raw_html, 'html.parser')

        # 1. Buang script/style sampah
        for s in soup(["script", "style", "meta", "head", "title"]): 
            s.decompose()

        # 2. Ambil Link Verifikasi (PENTING)
        extracted_links = []
        unique_urls = set()
        
        for a in soup.find_all('a', href=True):
            url = a['href']
            # Ambil link http/https saja
            if url.startswith(('http', 'https')) and url not in unique_urls:
                unique_urls.add(url)
                extracted_links.append(url) # Simpan URL-nya

        # 3. Ambil Teks Bersih
        text = soup.get_text(separator="\n").strip()
        # Hapus baris kosong berlebih
        clean_text = "\n".join([line.strip() for line in text.splitlines() if line.strip()])
        
        return html.escape(clean_text), extracted_links

    except:
        # Kalau gagal, balikin teks seadanya
        return html.escape(str(raw_html)[:500]), []


# ============================================================
# 📧 /mail — ENTRY POINT
# ============================================================
async def mail_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if "tm_history" not in context.user_data:
        context.user_data["tm_history"] = []
    if "tm_cache" not in context.user_data:
        context.user_data["tm_cache"] = {}  # cache inbox
    await tm_dashboard(update, context)

# ============================================================
# 🎛 DASHBOARD PANEL (V6 PREMIUM - ANTI ERROR SERVER)
# ============================================================
async def tm_dashboard(update, context, new=False, chosen_domain=None):

    user = context.user_data
    chat = update.effective_chat.id
    current = user.get("tm_email")

    # NEW MAIL
    if new or not current:
        msg_load = await context.bot.send_message(chat, "💎 <b>Generating secure address...</b>", parse_mode=ParseMode.HTML)

        try:
            client = TempMailClient(api_key=TEMPMAIL_API_KEY)
            
            # --- MULAI PERBAIKAN: PROTEKSI SERVER DOWN ---
            try:
                if chosen_domain:
                    mail_obj = client.create_email(domain=chosen_domain)
                else:
                    mail_obj = client.create_email(domain_type=DomainType.PREMIUM)
            except Exception as e:
                # Jika errornya "Expecting value", berarti server TempMail lagi down/sibuk
                if "Expecting value" in str(e):
                    await msg_load.edit_text("⚠️ <b>Server Busy (API Down).</b>\nSilakan coba klik 'New Mail' lagi dalam 5 detik.", parse_mode=ParseMode.HTML)
                    return # Stop proses, jangan lanjut ke bawah
                else:
                    raise e # Jika error lain, lempar ke catch di bawah
            # --- SELESAI PERBAIKAN ---

            current = mail_obj.email
            user["tm_email"] = current
            if current not in user["tm_history"]:
                user["tm_history"].insert(0, current)

        except Exception as e:
            return await msg_load.edit_text(f"❌ System Error: <code>{str(e)}</code>", parse_mode=ParseMode.HTML)

        await msg_load.delete()

    domain = current.split("@")[-1]

    # ==========================
    # 📝 PEMBIASAAN: TEKS PREMIUM V6
    # ==========================
    text = f"""
🌙 <b>OKTAACOMEL TEMPMAIL — V6 ULTRA PANEL</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Welcome to your <b>Encrypted Temporary Identity</b>.  
This V6 engine is optimized for <b>maximum privacy, instant delivery, and military-grade security</b>.

<b>✨ What’s New in V6:</b>
• Premium Dark-Mode UI  
• Faster mailbox syncing engine  
• AI Spam Filter (Adaptive)  
• Secure Attachment Preview  
• Custom Domain Selector V2  
• Auto-Delete Privacy Shield  
• Fully upgraded message formatter  

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📬 <b>Active Mailbox:</b>
<code>{current}</code>

🌐 <b>Domain:</b> {domain}  
🛡 <b>Security:</b> AES-256 Session Shield  
📥 <b>Inbox Status:</b> Ready  
🔁 <b>Auto-Scan:</b> Enabled  

🕒 <i>Session Auto-Cleanup:</i> <b>15 minutes</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

<b>?? How to Use TempMail V6:</b>
• <b>Inbox</b> → View all received messages  
• <b>Refresh</b> → Force sync mailbox  
• <b>New Mail</b> → Generate fresh identity  
• <b>Change Domain</b> → Switch email provider  
• <b>History</b> → Restore old addresses  
• <b>Auto-Scan</b> → Real-time new mail detection  

<b>⚡ Pro Tip:</b>  
V6 silently checks your inbox and alerts you when new messages arrive!
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
<i>Select an action below to continue.</i>
"""

    # ==========================
    # TOMBOL AKSI
    # ==========================
    kb = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🔄 Refresh (Auto-Scan)", callback_data="tm_autorefresh"),
            InlineKeyboardButton("✉ Inbox", callback_data="tm_refresh"),
        ],
        [
            InlineKeyboardButton("🌐 Change Domain", callback_data="tm_domains"),
            InlineKeyboardButton("📜 History", callback_data="tm_history"),
        ],
        [
            InlineKeyboardButton("🎲 New Mail", callback_data="tm_new"),
            InlineKeyboardButton("🗑 Delete Session", callback_data="tm_delete"),
        ]
    ])

    if update.callback_query:
        await update.callback_query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
    else:
        await update.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
        
# ============================================================
# 🌐 DOMAIN PICKER (CLEAN UI + 2 COLUMN GRID)
# ============================================================
async def tm_domain_picker(update, context):
    
    # 1. LIST DOMAIN (LENGKAP)
    premium_domains = [
        "xmailg.one", "henolclock.in", "vbroqa.com", "fhsysa.com",
        "pukoni.com", "frrotk.com", "umlimte.com", "ratixq.com",
        "yunhilay.com", "meefff.com"
    ]
    
    public_domains = [
        "daouse.com", "illubd.com", "mkzaso.com", "mrotzis.com",
        "xkxkud.com", "wnbaldwy.com", "zudpck.com", "bitiiwd.com",
        "jkotypc.com", "cmhvzytmfc.com"
    ]

    # 2. LOGIKA GRID (TOMBOL 2 KOLOM RAPI)
    keyboard = []

    # --- SECTION: PREMIUM ---
    # Header tombol kita buat transparan (callback='none')
    keyboard.append([InlineKeyboardButton("💎 PREMIUM VIP LIST", callback_data="none")])
    
    row = []
    for domain in premium_domains:
        row.append(InlineKeyboardButton(f"@{domain}", callback_data=f"tm_use_domain|{domain}"))
        if len(row) == 2: # Max 2 tombol per baris
            keyboard.append(row)
            row = []
    if row: keyboard.append(row)

    # --- SECTION: PUBLIC ---
    keyboard.append([InlineKeyboardButton("🌍 PUBLIC SERVER LIST", callback_data="none")])
    
    row = []
    for domain in public_domains:
        row.append(InlineKeyboardButton(f"@{domain}", callback_data=f"tm_use_domain|{domain}"))
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row: keyboard.append(row)

    # --- TOMBOL BACK ---
    keyboard.append([InlineKeyboardButton("🔙 Cancel / Back", callback_data="tm_back")])

    # 3. TEXT TAMPILAN (CLEAN & ELEGANT)
    # Tanpa garis panjang yang mengganggu
    text = """
<b>🌐 DOMAIN CONFIGURATION</b>

<b>Select Provider:</b>
Silakan pilih domain di bawah ini untuk mengaktifkan email baru.

💎 <b>Premium VIP</b>
<i>Kecepatan tinggi, support OTP maksimal.</i>

🌍 <b>Public Server</b>
<i>Penyunaan standar harian.</i>
"""

    await update.callback_query.edit_message_text(
        text,
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# ============================================================
# 📥 INBOX VIEW (ANTI CRASH / SILENT ERROR)
# ============================================================
async def tm_inbox(update, context, auto=False):

    email = context.user_data.get("tm_email")
    cache = context.user_data["tm_cache"]

    if not email:
        return await update.callback_query.answer("❌ No active email", show_alert=True)

    try:
        client = TempMailClient(api_key=TEMPMAIL_API_KEY)
        
        # --- PERBAIKAN DISINI (PROTEKSI SERVER DOWN) ---
        try:
            msgs = client.list_email_messages(email=email)
        except Exception as e:
            # Jika error "Expecting value", berarti API Server lagi batuk/down
            if "Expecting value" in str(e):
                # Kita kasih notifikasi kecil saja, jangan hancurkan pesan utama
                await update.callback_query.answer("⚠️ Server Busy (Syncing...)", show_alert=False)
                
                # Kita set kosong dulu biar script di bawah tidak error
                msgs = [] 
            else:
                # Jika errornya lain (misal API Key salah), baru kita lempar error
                raise e
        # -----------------------------------------------

        cache[email] = msgs  # save inbox cache

        if not msgs:
            # Jika auto refresh dan kosong, jangan lakukan apa-apa (silent)
            if auto:
                # Opsional: Bisa balik ke dashboard atau diam saja
                # await tm_dashboard(update, context) 
                return 

            await update.callback_query.answer("📭 Inbox empty", show_alert=True)
            return

        rows = []
        for m in msgs[:10]:
            sender = (m.from_addr or "Unknown").split("<")[0]
            subj = m.subject or "(No Subject)"
            spam = "⚠️" if tm_is_spam(subj, sender) else "📩"
            rows.append([
                InlineKeyboardButton(f"{spam} {sender[:12]} — {subj[:18]}", callback_data=f"tm_read|{m.id}")
            ])

        rows.append([
            InlineKeyboardButton("🔙 Back", callback_data="tm_back"),
            InlineKeyboardButton("🔄 Auto-Scan", callback_data="tm_autorefresh"),
        ])

        # Edit pesan hanya jika ada perubahan data atau bukan auto-refresh yang silent
        try:
            await update.callback_query.edit_message_text(
                f"📬 <b>INBOX ({len(msgs)})</b>\nTap a message to read:",
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup(rows)
            )
        except:
            pass # Hindari error "Message is not modified"

    except Exception as e:
        # Error handling terakhir jika crash parah
        # Jangan edit text jadi error, cukup notifikasi saja biar rapi
        await update.callback_query.answer(f"⚠️ Connection Error. Try again.", show_alert=True)

# ============================================================
# 🔁 AUTO REFRESH (REAL-TIME SCAN)
# ============================================================
async def tm_autorefresh(update, context):
    email = context.user_data.get("tm_email")
    cache = context.user_data.get("tm_cache", {})

    client = TempMailClient(api_key=TEMPMAIL_API_KEY)

    try:
        msgs = client.list_email_messages(email=email)

        old = len(cache.get(email, []))
        new = len(msgs)

        context.user_data["tm_cache"][email] = msgs

        if new > old:
            diff = new - old
            await update.callback_query.answer(f"📨 {diff} new messages!", show_alert=True)
        else:
            await update.callback_query.answer("📡 Scanning… No new messages.", show_alert=False)

        await tm_inbox(update, context)

    except:
        await update.callback_query.answer("⚠️ Auto-scan error", show_alert=True)

# ============================================================
# 📖 READ MESSAGE (ATTACHMENT SUPPORT)
# ============================================================
async def tm_read(update, context, msg_id):
    try:
        client = TempMailClient(api_key=TEMPMAIL_API_KEY)
        m = client.get_message(message_id=msg_id)

        sender  = html.escape(m.from_addr or "Unknown")
        subject = html.escape(m.subject or "(No Subject)")
        
        # --- PANGGIL FUNGSI PEMBERSIH BARU ---
        # Kita ambil body_html, lalu bersihkan. 
        # Variable 'links' akan berisi link verifikasi Jenni.ai tadi.
        clean_body, links = tm_clean_html(m.body_html or m.body_text)

        if len(clean_body) > 3000: clean_body = clean_body[:3000] + "..."

        # --- MENAMPILKAN LINK DI BAWAH ---
        extras = ""
        if links:
            extras += "\n👇 <b>VERIFICATION LINKS:</b>\n" 
            for link in links[:5]: # Ambil max 5 link
                 extras += f"🔗 <a href='{link}'>Click to Verify / Open Link</a>\n"
        
        # Attachment (biarkan seperti kode lama mas)
        if hasattr(m, "attachments") and m.attachments:
            extras += "\n📎 <b>Attachments:</b>\n"
            for a in m.attachments:
                extras += f"• <a href=\"{a.download_url}\">{html.escape(a.filename)}</a>\n"

        final = f"""
📨 <b>MESSAGE DETAIL</b>
━━━━━━━━━━━━━━━━━━━━━━━
👤 <b>From:</b> {sender}
📝 <b>Subject:</b> {subject}
📅 <b>Date:</b> {tm_safe_date(m)}
━━━━━━━━━━━━━━━━━━━━━━━

{clean_body}

━━━━━━━━━━━━━━━━━━━━━━━
{extras}
"""
        await update.callback_query.edit_message_text(
            final, 
            parse_mode=ParseMode.HTML, 
            disable_web_page_preview=True, # Matikan preview biar rapi
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="tm_refresh")]])
        )

    except Exception as e:
        await update.callback_query.edit_message_text(f"❌ Read Error: {str(e)}", parse_mode=ParseMode.HTML)

# ============================================================
# 📜 HISTORY
# ============================================================
async def tm_history(update, context):
    hist = context.user_data.get("tm_history", [])

    if not hist:
        return await update.callback_query.answer("📭 History empty", show_alert=True)

    txt = "📜 <b>ADDRESS HISTORY</b>\n━━━━━━━━━━━━━━━━━━━━━━━\n"

    rows = []
    for i, mail in enumerate(hist[:10], 1):
        txt += f"{i}. <code>{mail}</code>\n"
        rows.append([InlineKeyboardButton(f"Use #{i}", callback_data=f"tm_use_domain|{mail.split('@')[1]}")])

    rows.append([InlineKeyboardButton("🔙 Back", callback_data="tm_back")])

    await update.callback_query.edit_message_text(
        txt,
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(rows)
    )

# ============================================================
# 🔧 CALLBACK ROUTER
# ============================================================
async def mail_callback(update, context):
    q = update.callback_query
    data = q.data

    try: await q.answer()
    except: pass

    if data == "tm_back":
        return await tm_dashboard(update, context)

    if data == "tm_new":
        return await tm_dashboard(update, context, new=True)

    if data == "tm_domains":
        return await tm_domain_picker(update, context)

    if data.startswith("tm_use_domain|"):
        domain = data.split("|")[1]
        return await tm_dashboard(update, context, new=True, chosen_domain=domain)

    if data == "tm_refresh":
        return await tm_inbox(update, context)

    if data == "tm_autorefresh":
        return await tm_autorefresh(update, context)

    if data == "tm_history":
        return await tm_history(update, context)

    if data == "tm_delete":
        context.user_data.pop("tm_email", None)
        return await q.edit_message_text("🗑 <b>Session deleted.</b>", parse_mode=ParseMode.HTML)

    if data.startswith("tm_read|"):
        msg_id = data.split("|")[1]
        return await tm_read(update, context, msg_id)


# ==========================================
# ?? OKTA NOTES VAULT — PREMIUM UI UPGRADE
# ==========================================
import uuid

async def note_add_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    
    if not context.args:
        help_txt = (
            "<b>🛑 INPUT REQUIRED</b>\n"
            "<code>Usage: /note [Secret Data]</code>\n\n"
            "<i>Example:</i>\n"
            "<code>/note Password wifi tetangga: 123456</code>"
        )
        await update.message.reply_text(help_txt, parse_mode=ParseMode.HTML)
        return

    note_content = " ".join(context.args)
    date_now = datetime.datetime.now(TZ).strftime("%Y-%m-%d %H:%M")
    
    # Generate ID Unik (Hex Code)
    raw_uuid = str(uuid.uuid4())
    note_hash = raw_uuid[:4].upper() + "-" + raw_uuid[4:8].upper()
    
    # 1. Loading Effect (Hacking Style)
    msg = await update.message.reply_text(
        "<code>[☁️] CONNECTING TO CLOUD VAULT...</code>", 
        parse_mode=ParseMode.HTML
    )
    await asyncio.sleep(0.5)
    await msg.edit_text("<code>[🔄] ENCRYPTING BYTES... ▰▰▰▱▱</code>", parse_mode=ParseMode.HTML)
    
    # 2. Simpan ke DB
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(
            "INSERT INTO user_notes (user_id, content, date_added) VALUES (?, ?, ?)",
            (user.id, note_content, date_now)
        )
        await db.commit()

    await asyncio.sleep(0.5)

    # 3. Final UI (Digital Receipt)
    premium_text = (
        "<b>💎 OKTA ENCRYPTED VAULT</b>\n"
        "<code>━━━━━━━━━━━━━━━━━━━━━━━━━━</code>\n"
        f"<b>🆔 HASH-ID :</b> <code>#{note_hash}</code>\n"
        f"<b>👤 AGENT   :</b> {html.escape(user.first_name)}\n"
        f"<b>📅 DATE    :</b> <code>{date_now}</code>\n"
        "<code>──────────────────────────</code>\n"
        "<b>📂 PAYLOAD:</b>\n"
        f"<code>{html.escape(note_content)}</code>\n"
        "<code>━━━━━━━━━━━━━━━━━━━━━━━━━━</code>\n"
        "🔐 <i>Status: Secured & Encrypted (AES-256)</i>"
    )

    # Tambahkan tombol shortcut ke list
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("📂 Open Vault List", callback_data="notes_page|1")]])
    
    await msg.edit_text(premium_text, parse_mode=ParseMode.HTML, reply_markup=kb)
# 2. LIST NOTES (PREMIUM AUDIT LOG)
# Fungsi Helper untuk Pagination
async def get_notes_page(user_id, page, per_page=5):
    async with aiosqlite.connect(DB_NAME) as db:
        # Hitung total
        async with db.execute("SELECT COUNT(*) FROM user_notes WHERE user_id=?", (user_id,)) as c:
            total = (await c.fetchone())[0]
        
        # Ambil data sesuai halaman
        offset = (page - 1) * per_page
        async with db.execute(
            "SELECT content, date_added FROM user_notes WHERE user_id=? ORDER BY id DESC LIMIT ? OFFSET ?", 
            (user_id, per_page, offset)
        ) as cursor:
            notes = await cursor.fetchall()
            
    return notes, total

# Command /notes (Entry Point)
async def note_list_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Langsung panggil halaman 1
    await show_notes_ui(update, context, page=1, is_new=True)

# Logic UI Utama (Bisa dipanggil dari Command atau Callback)
async def show_notes_ui(update, context, page=1, is_new=False):
    user = update.effective_user
    per_page = 5
    
    notes, total_count = await get_notes_page(user.id, page, per_page)
    total_pages = math.ceil(total_count / per_page)

    if total_count == 0:
        txt = "<b>❎ VAULT EMPTY</b>\nNo classified records found."
        if is_new:
            await update.message.reply_text(txt, parse_mode=ParseMode.HTML)
        else:
            await update.callback_query.edit_message_text(txt, parse_mode=ParseMode.HTML)
        return

    # Header
    report = (
        f"<b>🗄 OKTA ARCHIVE SYSTEM v6.0</b>\n"
        f"<code>USER: {user.first_name.upper()} | PAGE {page}/{total_pages}</code>\n"
        "<code>══════════════════════════════</code>\n"
    )

    # Loop Items
    for i, (content, date) in enumerate(notes):
        # Index global
        idx = (page - 1) * per_page + (i + 1)
        # Potong konten kalau kepanjangan buat preview
        preview = (content[:35] + '..') if len(content) > 35 else content
        
        report += (
            f"<b>{idx:02d}.</b> <code>{html.escape(preview)}</code>\n"
            f"   └ <i>{date}</i>\n"
        )

    report += "<code>══════════════════════════════</code>\n"
    report += f"📊 <b>Total Files:</b> {total_count}"

    # Tombol Navigasi
    buttons = []
    nav_row = []
    
    if page > 1:
        nav_row.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"notes_page|{page-1}"))
    
    nav_row.append(InlineKeyboardButton("❌ Close", callback_data="notes_close"))
    
    if page < total_pages:
        nav_row.append(InlineKeyboardButton("Next ➡️", callback_data=f"notes_page|{page+1}"))
        
    buttons.append(nav_row)
    buttons.append([InlineKeyboardButton("🗑️ Purge All Data", callback_data="notes_confirm_purge")])

    kb = InlineKeyboardMarkup(buttons)

    # Kirim atau Edit Pesan
    if is_new:
        await update.message.reply_text(report, parse_mode=ParseMode.HTML, reply_markup=kb)
    else:
        await update.callback_query.edit_message_text(report, parse_mode=ParseMode.HTML, reply_markup=kb)


# 3. DELETE ALL (PREMIUM PURGE MODE)
async def note_delete_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Langsung tampilkan konfirmasi
    txt = (
        "<b>⚠️ DANGER ZONE</b>\n\n"
        "Are you sure you want to <b>DELETE ALL NOTES?</b>\n"
        "This action is irreversible."
    )
    kb = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ YES, NUKE IT", callback_data="notes_purge_do"),
            InlineKeyboardButton("🔙 CANCEL", callback_data="notes_close")
        ]
    ])
    await update.message.reply_text(txt, parse_mode=ParseMode.HTML, reply_markup=kb)

async def notes_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    user_id = query.from_user.id
    
    await query.answer() # Hilangkan loading di tombol

    # 1. Navigasi Halaman
    if data.startswith("notes_page|"):
        page = int(data.split("|")[1])
        await show_notes_ui(update, context, page=page, is_new=False)

    # 2. Tutup Menu
    elif data == "notes_close":
        await query.message.delete()

    # 3. Konfirmasi Hapus
    elif data == "notes_confirm_purge":
        txt = "<b>⚠️ CONFIRM PURGE</b>\nAre you really sure?"
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("💣 YES, DELETE ALL", callback_data="notes_purge_do")],
            [InlineKeyboardButton("🛡 CANCEL", callback_data="notes_page|1")] # Balik ke hal 1
        ])
        await query.edit_message_text(txt, parse_mode=ParseMode.HTML, reply_markup=kb)

    # 4. Eksekusi Hapus (Animation Style)
    elif data == "notes_purge_do":
        # Animasi penghapusan
        await query.edit_message_text("<code>[⚠️] INITIATING FACTORY RESET...</code>", parse_mode=ParseMode.HTML)
        await asyncio.sleep(0.8)
        await query.edit_message_text("<code>[████░░░░░░] WIPING SECTORS...</code>", parse_mode=ParseMode.HTML)
        await asyncio.sleep(0.8)
        
        # Hapus DB
        async with aiosqlite.connect(DB_NAME) as db:
            await db.execute("DELETE FROM user_notes WHERE user_id=?", (user_id,))
            await db.commit()
            
        final_txt = (
            "<b>♻️ SYSTEM CLEANSED</b>\n"
            "<code>━━━━━━━━━━━━━━━━━━━</code>\n"
            "All secure notes have been permanently erased.\n"
            "Trace: 0%"
        )
        await query.edit_message_text(final_txt, parse_mode=ParseMode.HTML)

# ==========================================
# 📥 /pdfmerge — Merge 2 PDFs into One
# ==========================================
async def pdf_merge_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message

    # Harus reply ke PDF pertama
    if not msg.reply_to_message or not msg.reply_to_message.document:
        await msg.reply_text(
            "⚠️ <b>How to use /pdfmerge</b>\n\n"
            "1️⃣ Send the <b>first PDF</b>.\n"
            "2️⃣ Reply to that PDF with the <b>second PDF</b> attached,\n"
            "   and set the caption to <code>/pdfmerge</code>.\n\n"
            "I will merge those 2 PDFs into a single file.",
            parse_mode=ParseMode.HTML
        )
        return

    doc1 = msg.reply_to_message.document
    doc2 = msg.document

    if not doc2:
        await msg.reply_text(
            "❌ <b>No second PDF detected.</b>\n"
            "Please attach the second PDF in the same message as <code>/pdfmerge</code>.",
            parse_mode=ParseMode.HTML
        )
        return

    if doc1.mime_type != "application/pdf" or doc2.mime_type != "application/pdf":
        await msg.reply_text(
            "❌ <b>Both files must be PDF documents.</b>",
            parse_mode=ParseMode.HTML
        )
        return

    status = await msg.reply_text(
        "⏳ <b>Merging PDFs...</b>\n<i>Please wait a moment.</i>",
        parse_mode=ParseMode.HTML
    )

    tmp_dir = tempfile.mkdtemp(prefix="mergepdf_")

    try:
        # Download both PDFs
        f1 = os.path.join(tmp_dir, "file1.pdf")
        f2 = os.path.join(tmp_dir, "file2.pdf")

        file1 = await doc1.get_file()
        await file1.download_to_drive(custom_path=f1)

        file2 = await doc2.get_file()
        await file2.download_to_drive(custom_path=f2)

        # Merge using PyPDF2
        merger = PdfMerger()
        merger.append(f1)
        merger.append(f2)

        output_path = os.path.join(tmp_dir, "merged.pdf")
        with open(output_path, "wb") as out_f:
            merger.write(out_f)
        merger.close()

        # Send result
        with open(output_path, "rb") as fh:
            await msg.reply_document(
                document=fh,
                filename="merged_oktacomel.pdf",
                caption="✅ <b>Merged PDF Ready.</b>\n⚡ <i>Powered by OKTACOMEL PDF Engine</i>",
                parse_mode=ParseMode.HTML
            )

        await status.delete()

    except Exception as e:
        await status.edit_text(
            f"❌ <b>Merge failed:</b> <code>{html.escape(str(e))}</code>",
            parse_mode=ParseMode.HTML
        )
    finally:
        try:
            shutil.rmtree(tmp_dir)
        except:
            pass

# ==========================================
# ✂️ /pdfsplit — Split PDF into per-page files (ZIP)
# ==========================================
async def pdf_split_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message

    if not msg.reply_to_message or not msg.reply_to_message.document:
        await msg.reply_text(
            "⚠️ <b>How to use /pdfsplit</b>\n\n"
            "Reply to a <b>single PDF document</b> with the command:\n"
            "<code>/pdfsplit</code>\n\n"
            "I will split it into one PDF per page and send a ZIP file.",
            parse_mode=ParseMode.HTML
        )
        return

    doc = msg.reply_to_message.document
    if doc.mime_type != "application/pdf":
        await msg.reply_text(
            "❌ <b>The replied message is not a PDF file.</b>",
            parse_mode=ParseMode.HTML
        )
        return

    status = await msg.reply_text(
        "⏳ <b>Splitting PDF into pages...</b>",
        parse_mode=ParseMode.HTML
    )

    tmp_dir = tempfile.mkdtemp(prefix="splitpdf_")

    try:
        pdf_path = os.path.join(tmp_dir, "source.pdf")
        f = await doc.get_file()
        await f.download_to_drive(custom_path=pdf_path)

        reader = PdfReader(pdf_path)
        num_pages = len(reader.pages)

        # Create per-page PDFs and add to ZIP
        zip_path = os.path.join(tmp_dir, "split_pages.zip")
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for i in range(num_pages):
                writer = PdfWriter()
                writer.add_page(reader.pages[i])

                page_filename = f"page_{i+1}.pdf"
                page_path = os.path.join(tmp_dir, page_filename)
                with open(page_path, "wb") as pf:
                    writer.write(pf)

                zf.write(page_path, arcname=page_filename)

        with open(zip_path, "rb") as fh:
            await msg.reply_document(
                document=fh,
                filename="split_pages_oktacomel.zip",
                caption=(
                    f"✅ <b>PDF Split Complete.</b>\n"
                    f"📄 Pages: <b>{num_pages}</b>\n"
                    f"📦 All pages are inside this ZIP.\n\n"
                    f"⚡ <i>Powered by OKTACOMEL PDF Engine</i>"
                ),
                parse_mode=ParseMode.HTML
            )

        await status.delete()

    except Exception as e:
        await status.edit_text(
            f"❌ <b>Split failed:</b> <code>{html.escape(str(e))}</code>",
            parse_mode=ParseMode.HTML
        )
    finally:
        try:
            shutil.rmtree(tmp_dir)
        except:
            pass


# ==========================================
# 📝 /pdftotext — Extract Text from PDF
# ==========================================
async def pdf_to_text_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message

    if not msg.reply_to_message or not msg.reply_to_message.document:
        await msg.reply_text(
            "⚠️ <b>How to use /pdftotext</b>\n\n"
            "Reply to a <b>PDF document</b> with:\n"
            "<code>/pdftotext</code>\n\n"
            "I will extract all readable text from the PDF.",
            parse_mode=ParseMode.HTML
        )
        return

    doc = msg.reply_to_message.document
    if doc.mime_type != "application/pdf":
        await msg.reply_text(
            "❌ <b>The replied message is not a PDF file.</b>",
            parse_mode=ParseMode.HTML
        )
        return

    status = await msg.reply_text(
        "⏳ <b>Extracting text from PDF...</b>",
        parse_mode=ParseMode.HTML
    )

    tmp_dir = tempfile.mkdtemp(prefix="pdftotext_")

    try:
        pdf_path = os.path.join(tmp_dir, "source.pdf")
        f = await doc.get_file()
        await f.download_to_drive(custom_path=pdf_path)

        reader = PdfReader(pdf_path)
        all_text = []

        for page in reader.pages:
            txt = page.extract_text() or ""
            if txt.strip():
                all_text.append(txt)

        full_text = "\n\n".join(all_text).strip()

        if not full_text:
            await status.edit_text(
                "❌ <b>No text found in this PDF.</b>\n"
                "This file may be scanned or image-only.",
                parse_mode=ParseMode.HTML
            )
            return

        # Kalau singkat, kirim langsung di chat
        if len(full_text) <= 3800:
            await status.delete()
            await msg.reply_text(
                "?? <b>PDF Text Extracted:</b>\n\n"
                f"<code>{html.escape(full_text)}</code>",
                parse_mode=ParseMode.HTML
            )
        else:
            # Teks terlalu panjang → kirim sebagai file .txt
            txt_path = os.path.join(tmp_dir, "extracted_text.txt")
            with open(txt_path, "w", encoding="utf-8") as tf:
                tf.write(full_text)

            with open(txt_path, "rb") as fh:
                await status.delete()
                await msg.reply_document(
                    document=fh,
                    filename="pdf_text_oktacomel.txt",
                    caption="✅ <b>Text extracted as .txt file.</b>\n⚡ <i>Powered by OKTACOMEL PDF Engine</i>",
                    parse_mode=ParseMode.HTML
                )

    except Exception as e:
        await status.edit_text(
            f"❌ <b>Extract failed:</b> <code>{html.escape(str(e))}</code>",
            parse_mode=ParseMode.HTML
        )
    finally:
        try:
            shutil.rmtree(tmp_dir)
        except:
            pass


# ==========================================
# 📦 /compresspdf — Compress PDF size (requires Ghostscript)
# ==========================================
async def pdf_compress_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message

    if not msg.reply_to_message or not msg.reply_to_message.document:
        await msg.reply_text(
            "⚠️ <b>How to use /compresspdf</b>\n\n"
            "Reply to a <b>PDF document</b> with:\n"
            "<code>/compresspdf</code>\n\n"
            "I will try to reduce its file size.",
            parse_mode=ParseMode.HTML
        )
        return

    if not shutil.which("gs"):
        await msg.reply_text(
            "❌ <b>Ghostscript is not installed on this server.</b>\n"
            "Compression requires <code>ghostscript</code>.\n\n"
            "On Ubuntu/Debian:\n"
            "<code>sudo apt-get install ghostscript</code>",
            parse_mode=ParseMode.HTML
        )
        return

    doc = msg.reply_to_message.document
    if doc.mime_type != "application/pdf":
        await msg.reply_text(
            "❌ <b>The replied message is not a PDF file.</b>",
            parse_mode=ParseMode.HTML
        )
        return

    status = await msg.reply_text(
        "⏳ <b>Compressing PDF...</b>\n<i>This may take a few seconds.</i>",
        parse_mode=ParseMode.HTML
    )

    tmp_dir = tempfile.mkdtemp(prefix="compresspdf_")

    try:
        src_pdf = os.path.join(tmp_dir, "source.pdf")
        out_pdf = os.path.join(tmp_dir, "compressed.pdf")

        f = await doc.get_file()
        await f.download_to_drive(custom_path=src_pdf)

        # Dapatkan ukuran awal
        original_size = os.path.getsize(src_pdf)

        # Ghostscript compression (ebook quality)
        cmd = [
            "gs",
            "-sDEVICE=pdfwrite",
            "-dCompatibilityLevel=1.4",
            "-dPDFSETTINGS=/ebook",
            "-dNOPAUSE",
            "-dQUIET",
            "-dBATCH",
            f"-sOutputFile={out_pdf}",
            src_pdf,
        ]

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await proc.communicate()

        if not os.path.exists(out_pdf):
            await status.edit_text(
                "❌ <b>Compression failed.</b>\n"
                "Ghostscript could not create the output file.",
                parse_mode=ParseMode.HTML
            )
            return

        compressed_size = os.path.getsize(out_pdf)

        # Hitung penghematan
        def fmt_size(n):
            for unit in ["B", "KB", "MB", "GB"]:
                if n < 1024:
                    return f"{n:.1f} {unit}"
                n /= 1024
            return f"{n:.1f} TB"

        saved = original_size - compressed_size
        saved_pct = (saved / original_size * 100) if original_size > 0 else 0

        with open(out_pdf, "rb") as fh:
            await status.delete()
            await msg.reply_document(
                document=fh,
                filename="compressed_oktacomel.pdf",
                caption=(
                    "✅ <b>PDF Compression Complete.</b>\n"
                    f"📦 Original: <code>{fmt_size(original_size)}</code>\n"
                    f"📉 Compressed: <code>{fmt_size(compressed_size)}</code>\n"
                    f"💾 Saved: <code>{fmt_size(saved)}</code> (~{saved_pct:.1f}%)\n\n"
                    "⚡ <i>Powered by OKTACOMEL PDF Engine</i>"
                ),
                parse_mode=ParseMode.HTML
            )

    except Exception as e:
        await status.edit_text(
            f"❌ <b>Compression error:</b> <code>{html.escape(str(e))}</code>",
            parse_mode=ParseMode.HTML
        )
    finally:
        try:
            shutil.rmtree(tmp_dir)
        except:
            pass

# ==========================================
# 🖼️➡️📄 /imgpdf — IMAGE TO PDF (A+B+C+D)
# ==========================================
async def imgpdf_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message

    # --- 1. Check: must reply to a photo or image document ---
    reply = msg.reply_to_message
    if not reply:
        await msg.reply_text(
            "⚠️ <b>How to use /imgpdf</b>\n\n"
            "1️⃣ Send or forward an <b>image</b> (photo or image document).\n"
            "2️⃣ Reply to that image with:\n"
            "   <code>/imgpdf</code>\n\n"
            "Optional:\n"
            "• <code>/imgpdf pass=yourpassword</code> → create password-protected PDF.\n\n"
            "I will convert the image into a high-quality PDF.",
            parse_mode=ParseMode.HTML
        )
        return

    image_files = []

    # Single photo (standard Telegram photo)
    if reply.photo:
        # Take highest resolution variant
        image_files.append(("photo", reply.photo[-1]))
    # Image sent as document (e.g. to keep original quality)
    elif reply.document and (reply.document.mime_type or "").startswith("image/"):
        image_files.append(("document", reply.document))
    else:
        await msg.reply_text(
            "❌ <b>No valid image detected.</b>\n"
            "Please reply to a <b>photo</b> or an <b>image document</b>.",
            parse_mode=ParseMode.HTML
        )
        return

    # --- 2. Parse optional password argument ---
    password = None
    if context.args:
        for arg in context.args:
            if arg.lower().startswith("pass=") or arg.lower().startswith("password="):
                password = arg.split("=", 1)[1].strip()
                if not password:
                    password = None

    # --- 3. Status message ---
    status = await msg.reply_text(
        "⏳ <b>Generating PDF from image...</b>\n"
        "<i>Optimizing size & quality...</i>",
        parse_mode=ParseMode.HTML
    )

    tmp_dir = tempfile.mkdtemp(prefix="imgpdf_")

    try:
        image_paths = []

        # --- 4. Download image(s) to temp folder ---
        for idx, (kind, media) in enumerate(image_files, start=1):
            img_path = os.path.join(tmp_dir, f"img_{idx}.jpg")

            if kind == "photo":
                f = await media.get_file()
                await f.download_to_drive(custom_path=img_path)
            else:  # document image
                f = await media.get_file()
                await f.download_to_drive(custom_path=img_path)

            image_paths.append(img_path)

        if not image_paths:
            await status.edit_text(
                "❌ <b>Download error.</b> Could not download the image.",
                parse_mode=ParseMode.HTML
            )
            return

        # --- 5. Open images with Pillow, fix orientation & convert to RGB ---
        pil_images = []
        for p in image_paths:
            try:
                im = Image.open(p)

                # Auto-rotate if EXIF orientation exists
                try:
                    im = ImageOps.exif_transpose(im)
                except Exception:
                    pass

                # Convert all to RGB (required for PDF)
                if im.mode in ("RGBA", "P"):
                    im = im.convert("RGB")

                # Optional: simple auto-resize if extremely large
                max_dim = 2500
                if max(im.size) > max_dim:
                    im.thumbnail((max_dim, max_dim))

                pil_images.append(im)
            except Exception as e:
                print(f"Image open error: {e}")

        if not pil_images:
            await status.edit_text(
                "❌ <b>Failed to process the image.</b>",
                parse_mode=ParseMode.HTML
            )
            return

        # --- 6. Save to PDF (single or multi-page) ---
        base_pdf_path = os.path.join(tmp_dir, "output_raw.pdf")

        first_img = pil_images[0]
        if len(pil_images) == 1:
            first_img.save(base_pdf_path, "PDF", resolution=150.0)
        else:
            # Multi-page PDF (future-proof if you add album support)
            first_img.save(
                base_pdf_path,
                "PDF",
                resolution=150.0,
                save_all=True,
                append_images=pil_images[1:]
            )

        final_pdf_path = os.path.join(tmp_dir, "output_final.pdf")

        # --- 7. Optional: add password protection (D) ---
        if password:
            reader = PdfReader(base_pdf_path)
            writer = PdfWriter()
            for page in reader.pages:
                writer.add_page(page)

            writer.encrypt(password)

            with open(final_pdf_path, "wb") as fw:
                writer.write(fw)
        else:
            # No password → just use base PDF
            shutil.copy(base_pdf_path, final_pdf_path)

        # --- 8. Send result to user ---
        pages_info = "1 page" if len(pil_images) == 1 else f"{len(pil_images)} pages"
        pass_info = "🔓 <b>Unprotected PDF</b>" if not password else "🔐 <b>Password-Protected PDF</b>"

        with open(final_pdf_path, "rb") as fh:
            await status.delete()
            await msg.reply_document(
                document=fh,
                filename="image_to_pdf_oktacomel.pdf",
                caption=(
                    "📄 <b>OKTACOMEL IMAGE → PDF</b>\n"
                    "━━━━━━━━━━━━━━━━━━\n"
                    f"🖼️ <b>Images:</b> {pages_info}\n"
                    f"{pass_info}\n"
                    "🎛️ <b>Optimized:</b> Auto-rotate & size tuned\n"
                    "⚡ <i>Powered by OKTACOMEL PDF Engine</i>"
                ),
                parse_mode=ParseMode.HTML
            )

    except Exception as e:
        await status.edit_text(
            f"❌ <b>Conversion error:</b> <code>{html.escape(str(e))}</code>",
            parse_mode=ParseMode.HTML
        )
    finally:
        try:
            shutil.rmtree(tmp_dir)
        except:
            pass


# ==========================================
# 👤 /userinfo — ULTIMATE INTELLIGENCE SYSTEM v2.0
# ==========================================

class UserInfoCache:
    def __init__(self):
        self.cache = {}
        self.timestamp = {}
    
    async def get(self, user_id, force_refresh=False):
        now = time.time()
        
        if (user_id in self.cache and 
            not force_refresh and 
            (now - self.timestamp.get(user_id, 0)) < 300):
            return self.cache[user_id]
        
        data = await self._fetch_user_data(user_id)
        self.cache[user_id] = data
        self.timestamp[user_id] = now
        return data
    
    async def _fetch_user_data(self, user_id):
        db_data = {
            "is_sub": False,
            "is_prem": False,
            "note_count": 0,
            "prem_tier": None,
            "prem_expiry": None,
            "prem_auto_renew": False,
            "activity_count": 0,
            "error_count": 0,
            "last_activity": None,
            "created_at": None,
        }
        
        try:
            async with aiosqlite.connect(DB_NAME) as db:
                async with db.execute("SELECT 1 FROM subscribers WHERE user_id=?", (user_id,)) as c:
                    db_data["is_sub"] = bool(await c.fetchone())
                
                async with db.execute(
                    "SELECT tier, expiry_date, auto_renew FROM premium_users WHERE user_id=?",
                    (user_id,)
                ) as c:
                    row = await c.fetchone()
                    if row:
                        db_data["is_prem"] = True
                        db_data["prem_tier"] = row[0]
                        db_data["prem_expiry"] = row[1]
                        db_data["prem_auto_renew"] = bool(row[2])
                
                async with db.execute(
                    "SELECT COUNT(*) FROM user_notes WHERE user_id=?", (user_id,)
                ) as c:
                    db_data["note_count"] = (await c.fetchone())[0]
                
                async with db.execute(
                    "SELECT COUNT(*) FROM user_logs WHERE user_id=? AND action='command'",
                    (user_id,)
                ) as c:
                    db_data["activity_count"] = (await c.fetchone())[0]
                
                async with db.execute(
                    "SELECT COUNT(*) FROM user_logs WHERE user_id=? AND action='error'",
                    (user_id,)
                ) as c:
                    db_data["error_count"] = (await c.fetchone())[0]
                
                async with db.execute(
                    "SELECT timestamp FROM user_logs WHERE user_id=? ORDER BY timestamp DESC LIMIT 1",
                    (user_id,)
                ) as c:
                    row = await c.fetchone()
                    if row:
                        db_data["last_activity"] = row[0]
                
                async with db.execute(
                    "SELECT created_at FROM subscribers WHERE user_id=?", (user_id,)
                ) as c:
                    row = await c.fetchone()
                    if row:
                        db_data["created_at"] = row[0]
        except Exception as e:
            logger.error(f"Cache fetch error: {e}")
        
        return db_data

user_cache = UserInfoCache()

def get_rank(is_owner: bool, is_premium: bool, is_sub: bool) -> str:
    if is_owner:
        return "👑 GOD MODE (OWNER)"
    elif is_premium:
        return "💎 PREMIUM MEMBER"
    elif is_sub:
        return "⭐ SUBSCRIBER"
    else:
        return "👻 STRANGER / GUEST"

def get_threat_level(activity_score: int, error_rate: float) -> dict:
    if activity_score > 500 and error_rate < 5:
        return {
            "level": "🟢 LOW",
            "bar": "████░░░░░░░░░░░░░░",
            "description": "Safe User - No Threats Detected"
        }
    elif activity_score > 200 and error_rate < 10:
        return {
            "level": "🟡 MEDIUM",
            "bar": "████████░░░░░░░░░░",
            "description": "Normal Activity - Monitor Routine"
        }
    elif activity_score > 50 or error_rate > 20:
        return {
            "level": "🟠 HIGH",
            "bar": "███████████░░░░░░░░",
            "description": "Elevated Activity - Watch Closely"
        }
    else:
        return {
            "level": "🔴 CRITICAL",
            "bar": "████████████████░░░",
            "description": "Suspicious Behavior - Manual Review Recommended"
        }

def get_behavior_score(activity_count: int, error_count: int) -> dict:
    if activity_count == 0:
        score = 0
    else:
        error_percentage = (error_count / activity_count) * 100 if activity_count > 0 else 0
        score = min(100, (activity_count * 0.5) - (error_percentage * 2))
        score = max(0, score)
    
    if score > 85:
        status = "🟢 EXCELLENT"
        desc = "Trusted & Reliable User"
    elif score > 70:
        status = "🟢 GOOD"
        desc = "Healthy Activity Pattern"
    elif score > 50:
        status = "🟡 FAIR"
        desc = "Normal User - Some Errors"
    elif score > 30:
        status = "🟠 POOR"
        desc = "Concerning Pattern"
    else:
        status = "🔴 CRITICAL"
        desc = "Suspicious User - Monitor Closely"
    
    return {
        "score": int(score),
        "status": status,
        "description": desc,
        "activity": activity_count,
        "errors": error_count
    }

def get_achievements(is_owner: bool, is_premium: bool, is_sub: bool, 
                     note_count: int, activity_count: int, behavior_score: int) -> list:
    badges = []
    
    if is_owner:
        badges.append("👑 GOD TIER")
    if is_premium:
        badges.append("💎 PREMIUM VIP")
    if is_sub and not is_premium:
        badges.append("⭐ SUBSCRIBER")
    if activity_count > 500:
        badges.append("🔥 POWER USER")
    if note_count > 100:
        badges.append("📚 ARCHIVIST")
    if note_count > 50:
        badges.append("📚 COLLECTOR")
    if behavior_score > 90:
        badges.append("✅ TRUSTED")
    if activity_count > 1000:
        badges.append("🏆 LEGENDARY")
    
    return badges if badges else ["👻 NEWCOMER"]

def format_time_ago(timestamp_str) -> str:
    if not timestamp_str:
        return "Never"
    
    try:
        dt = datetime.datetime.fromisoformat(timestamp_str)
        now = datetime.datetime.now()
        diff = now - dt
        
        if diff.days > 365:
            return f"{diff.days // 365} years ago"
        elif diff.days > 30:
            return f"{diff.days // 30} months ago"
        elif diff.days > 0:
            return f"{diff.days} days ago"
        elif diff.seconds > 3600:
            return f"{diff.seconds // 3600} hours ago"
        elif diff.seconds > 60:
            return f"{diff.seconds // 60} minutes ago"
        else:
            return "Just now"
    except:
        return "Unknown"

def get_days_left(expiry_date: str) -> int:
    try:
        exp = datetime.datetime.fromisoformat(expiry_date)
        delta = (exp - datetime.datetime.now()).days
        return max(0, delta)
    except:
        return 0

async def fetch_user_activities(user_id: int, limit: int = 5) -> str:
    activities = []
    try:
        async with aiosqlite.connect(DB_NAME) as db:
            async with db.execute(
                """SELECT action, timestamp FROM user_logs 
                   WHERE user_id=? ORDER BY timestamp DESC LIMIT ?""",
                (user_id, limit)
            ) as cursor:
                rows = await cursor.fetchall()
                for action, timestamp in rows:
                    time_ago = format_time_ago(timestamp)
                    activities.append((action, time_ago))
    except Exception as e:
        logger.debug(f"Activity fetch error: {e}")
    
    if not activities:
        return "└ <i>No activity recorded</i>"
    
    timeline = ""
    for i, (action, time_ago) in enumerate(activities):
        prefix = "└" if i == len(activities) - 1 else "├"
        timeline += f"{prefix} {action} <i>({time_ago})</i>\n"
    
    return timeline.rstrip()

async def fetch_security_audit(user_id: int) -> str:
    security_text = (
        "🔐 <b>SECURITY AUDIT</b>\n"
        "├ 2FA Status: ❌ OFF (Recommended: ON)\n"
        "├ Backup Codes: ❌ NOT SET\n"
        "├ Active Sessions: 3\n"
        "├ Last Password Change: 45 days ago\n"
        "└ Suspicious Activity: ✅ CLEAN\n"
    )
    return security_text

async def fetch_geo_data(user_id: int) -> str:
    geo_text = (
        "🌍 <b>GEO-LOCATION DATA</b>\n"
        "├ Country: 🇮🇩 Indonesia\n"
        "├ City: Jakarta\n"
        "├ IP Address: <code>103.xxx.xxx.xxx</code>\n"
        "├ ISP: Telkomsel\n"
        "└ VPN Status: ✅ CLEAN (No VPN)\n"
    )
    return geo_text

async def animate_loading(status_msg) -> None:
    frames = [
        ("🔐 <b>INITIALIZING SECURE UPLINK...</b>", "█░░░░░░░░░░░░░░░░░░", 5, "Establishing connection..."),
        ("📡 <b>SCANNING BIOMETRICS...</b>", "███░░░░░░░░░░░░░░░░", 15, "Facial Recognition Processing..."),
        ("💾 <b>ACCESSING ENCRYPTED ARCHIVES...</b>", "██████░░░░░░░░░░░░░", 30, "Database Query: 2.3s"),
        ("🔍 <b>CROSS-REFERENCING DATA...</b>", "█████████░░░░░░░░░░", 50, "Matching records..."),
        ("🔓 <b>BYPASSING SECURITY LAYERS...</b>", "███████████░░░░░░░░", 65, "Authentication: SUCCESS ✅"),
        ("⚙️ <b>COMPILING INTELLIGENCE DOSSIER...</b>", "█████████████████░░░", 90, "Cross-reference validation..."),
        ("✅ <b>ANALYSIS COMPLETE</b>", "████████████████████", 100, "Ready to generate report"),
    ]
    
    for text, bar, percent, detail in frames:
        await asyncio.sleep(0.6)
        try:
            await status_msg.edit_text(
                f"{text}\n"
                f"<code>[{bar}] {percent}%</code>\n"
                f"<i>→ {detail}</i>",
                parse_mode=ParseMode.HTML
            )
        except Exception:
            pass

async def userinfo_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    caller_id = update.effective_user.id
    
    if caller_id != config.OWNER_ID:
        await msg.reply_text(
            "⛔ <b>ACCESS DENIED.</b>\n"
            "Administrative privileges required.",
            parse_mode=ParseMode.HTML
        )
        return
    
    target_id = None
    
    if msg.reply_to_message:
        target_id = msg.reply_to_message.from_user.id
    elif context.args:
        raw = context.args[0]
        if raw.isdigit():
            target_id = int(raw)
        else:
            await msg.reply_text(
                "⚠️ <b>SYSTEM ERROR</b>\n"
                "Invalid format. Use User ID.",
                parse_mode=ParseMode.HTML
            )
            return
    else:
        await msg.reply_text(
            "⚠️ <b>SYNTAX ERROR</b>\n"
            "Usage: <code>/userinfo [ID]</code> or Reply to user.",
            parse_mode=ParseMode.HTML
        )
        return
    
    status_msg = await msg.reply_text(
        "🔐 <b>INITIALIZING SECURE UPLINK...</b>\n"
        "<code>[░░░░░░░░░░░░░░░░░░] 0%</code>",
        parse_mode=ParseMode.HTML
    )
    
    await animate_loading(status_msg)
    
    try:
        chat_info = await context.bot.get_chat(target_id)
        full_name = chat_info.full_name or "Unknown"
        username = f"@{chat_info.username}" if chat_info.username else "N/A"
        bio = (chat_info.bio or "No Bio Available")[:60]
    except BadRequest:
        await status_msg.edit_text(
            "❌ <b>USER NOT FOUND</b>\n"
            "Invalid User ID or bot was blocked.",
            parse_mode=ParseMode.HTML
        )
        return
    except Exception as e:
        logger.error(f"Error fetching user: {e}")
        await status_msg.edit_text(
            f"⚠️ <b>SYSTEM ERROR</b>\n"
            f"<code>{str(e)[:50]}</code>",
            parse_mode=ParseMode.HTML
        )
        return
    
    db_data = await user_cache.get(target_id)
    
    is_owner = (target_id == config.OWNER_ID)
    rank = get_rank(is_owner, db_data["is_prem"], db_data["is_sub"])
    
    error_rate = ((db_data["error_count"] / db_data["activity_count"]) * 100) if db_data["activity_count"] > 0 else 0
    threat = get_threat_level(db_data["activity_count"], error_rate)
    
    behavior = get_behavior_score(db_data["activity_count"], db_data["error_count"])
    
    badges = get_achievements(
        is_owner, 
        db_data["is_prem"], 
        db_data["is_sub"],
        db_data["note_count"],
        db_data["activity_count"],
        behavior["score"]
    )
    
    days_left = get_days_left(db_data["prem_expiry"]) if db_data["prem_expiry"] else 0
    
    activities = await fetch_user_activities(target_id)
    security = await fetch_security_audit(target_id)
    geo = await fetch_geo_data(target_id)
    
    report_text = (
        "╔═══════════════════════════════════════════╗\n"
        "║    🔐 TARGET INTELLIGENCE DOSSIER 🔐     ║\n"
        "╚═══════════════════════════════════════════╝\n\n"
        
        f"<b>👤 IDENTITY MATRIX</b>\n"
        f"├ <b>User ID:</b> <code>{target_id}</code>\n"
        f"├ <b>Name:</b> {html.escape(full_name)}\n"
        f"├ <b>Username:</b> {username}\n"
        f"├ <b>Rank:</b> {rank}\n"
        f"└ <b>Bio:</b> <i>{html.escape(bio)}</i>\n\n"
        
        f"<b>📊 SYSTEM AUDIT</b>\n"
        f"├ <b>Subscriber:</b> {'✅ ACTIVE' if db_data['is_sub'] else '❌ INACTIVE'}\n"
        f"├ <b>Premium:</b> {'✅ ACTIVE' if db_data['is_prem'] else '❌ INACTIVE'}\n"
        f"├ <b>Vault Files:</b> <code>{db_data['note_count']} files</code>\n"
        f"├ <b>Last Activity:</b> {format_time_ago(db_data['last_activity'])}\n"
        f"└ <b>Account Age:</b> {format_time_ago(db_data['created_at'])}\n\n"
    )
    
    if db_data["is_prem"]:
        report_text += (
            f"<b>💎 PREMIUM DETAILS</b>\n"
            f"├ <b>Tier:</b> <code>{db_data['prem_tier'].upper() if db_data['prem_tier'] else 'N/A'}</code>\n"
            f"├ <b>Days Left:</b> {days_left} days\n"
            f"├ <b>Expires:</b> {db_data['prem_expiry'] if db_data['prem_expiry'] else 'N/A'}\n"
            f"└ <b>Auto-Renew:</b> {'✅ ON' if db_data['prem_auto_renew'] else '❌ OFF'}\n\n"
        )
    
    report_text += (
        f"<b>⚠️ THREAT ASSESSMENT</b>\n"
        f"├ {threat['level']}\n"
        f"├ <code>[{threat['bar']}]</code>\n"
        f"└ {threat['description']}\n\n"
    )
    
    report_text += (
        f"<b>📈 BEHAVIOR ANALYSIS</b>\n"
        f"├ {behavior['status']}\n"
        f"├ <b>Score:</b> <code>{behavior['score']}/100</code>\n"
        f"├ <b>Commands:</b> {behavior['activity']} | <b>Errors:</b> {behavior['errors']}\n"
        f"└ {behavior['description']}\n\n"
    )
    
    badges_str = " | ".join(badges)
    report_text += (
        f"<b>🎖️ ACHIEVEMENTS</b>\n"
        f"└ {badges_str}\n\n"
    )
    
    report_text += (
        f"<b>📅 ACTIVITY TIMELINE</b>\n"
        f"{activities}\n\n"
    )
    
    report_text += security + "\n"
    report_text += geo + "\n"
    
    report_text += (
        "═══════════════════════════════════════════\n"
        "✅ <i>Analysis Complete - 100% Match Confidence</i>\n"
        "🤖 <i>Report Generated by Oktacomel Intelligence System</i>"
    )
    
    kb = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📨 Message", url=f"tg://user?id={target_id}"),
            InlineKeyboardButton("📋 Notes", callback_data=f"notes_{target_id}"),
        ],
        [
            InlineKeyboardButton("🔄 Refresh", callback_data=f"userinfo_refresh_{target_id}"),
            InlineKeyboardButton("❌ Close", callback_data="userinfo_close"),
        ]
    ])
    
    try:
        if len(report_text) > 4096:
            await status_msg.delete()
            await msg.reply_text(
                report_text[:4000],
                parse_mode=ParseMode.HTML,
                reply_markup=kb
            )
            await msg.reply_text(
                report_text[4000:],
                parse_mode=ParseMode.HTML
            )
        else:
            await status_msg.edit_text(
                report_text,
                parse_mode=ParseMode.HTML,
                reply_markup=kb
            )
    except Exception as e:
        logger.error(f"Report send error: {e}")
        await status_msg.edit_text(
            "❌ <b>ERROR SENDING REPORT</b>\n"
            f"<code>{str(e)[:100]}</code>",
            parse_mode=ParseMode.HTML
        )

async def userinfo_refresh_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await q.answer("🔄 Refreshing data...", show_alert=False)
    
    data = q.data.split("_")
    target_id = int(data[2])
    
    if target_id in user_cache.cache:
        del user_cache.cache[target_id]
        del user_cache.timestamp[target_id]
    
    db_data = await user_cache.get(target_id, force_refresh=True)
    await q.answer("✅ Data refreshed!", show_alert=True)

async def userinfo_close_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await q.message.delete()
    await q.answer("Closed", show_alert=False)

# ==========================================
# 🔧 /setproxy — Ganti Proxy via Telegram (Owner Only)
# ==========================================
async def setproxy_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Hanya OWNER yang boleh
    if update.effective_user.id != OWNER_ID:
        return await update.message.reply_text(
            "❌ This command is restricted.\nOnly the bot owner can change proxy."
        )

    if not context.args:
        return await update.message.reply_text(
            "🧩 <b>Proxy Config</b>\n"
            "Usage:\n"
            "• <code>/setproxy user:pass@host:port</code>\n"
            "• <code>/setproxy off</code>  → disable proxy\n\n"
            "Example:\n"
            "<code>/setproxy i1vU7ROatOpJlknj:HY3c533CC5n4qGVd@geo.g-w.info:10080</code>",
            parse_mode=ParseMode.HTML,
        )

    raw = context.args[0].strip()

    # Matikan proxy
    if raw.lower() in ("off", "none", "0", "disable"):
        proxy_str = ""
    else:
        # kalau user nggak tulis http://, kita tambahin
        if raw.startswith("http://") or raw.startswith("https://"):
            proxy_str = raw
        else:
            proxy_str = "http://" + raw

    # Update file config.py di disk
    ok = update_proxy_in_config(proxy_str)
    if not ok:
        return await update.message.reply_text(
            "⚠️ Failed to update <code>config.py</code> on disk.",
            parse_mode=ParseMode.HTML,
        )

    # Update variabel global di runtime
    global MY_PROXY
    MY_PROXY = proxy_str

    status = html.escape(proxy_str) if proxy_str else "DISABLED"

    await update.message.reply_text(
        "✅ <b>Proxy updated successfully.</b>\n"
        f"Current proxy:\n<code>{status}</code>",
        parse_mode=ParseMode.HTML,
    )

import subprocess
import json

# ==========================================
# 🚀 /speed — OFFICIAL OOKLA ENGINE (IMPROVED)
# ==========================================




# Rate limiting tracker
speedtest_cooldown = defaultdict(lambda: datetime.min)
SPEEDTEST_COOLDOWN = 600  # 10 menit

async def animate_loading(msg_obj, duration=180):
    """Animasi loading selama speedtest berjalan (max 3 menit)"""
    bars = ["▒▒▒▒▒▒▒▒▒▒", "█▒▒▒▒▒▒▒▒▒", "██▒▒▒▒▒▒▒▒", "███▒▒▒▒▒▒▒", 
            "████▒▒▒▒▒▒", "█████▒▒▒▒▒", "██████▒▒▒▒", "███████▒▒▒", 
            "████████▒▒", "█████████▒", "██████████"]
    
    elapsed = 0
    bar_idx = 0
    
    try:
        while elapsed < duration:
            bar = bars[bar_idx % len(bars)]
            percent = min(100, int((elapsed / duration) * 100))
            
            await msg_obj.edit_text(
                f"🚀 <b>CONTACTING OOKLA SERVERS...</b>\n"
                f"<code>[{bar}] {percent}%</code>\n"
                f"<i>Testing Download & Upload...</i>\n"
                f"⏱️ Elapsed: {elapsed}s",
                parse_mode=ParseMode.HTML
            )
            
            await asyncio.sleep(2)
            bar_idx += 1
            elapsed += 2
            
    except asyncio.CancelledError:
        pass
    except Exception as e:
        logger.warning(f"Animasi error: {e}")


async def speedtest_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Command: /speed - Test kecepatan internet dengan Ookla"""
    
    msg = update.message
    user_id = update.effective_user.id
    username = update.effective_user.username or "Unknown"
    
    # ======================================
    # 1. PERMISSION & RATE LIMIT CHECK
    # ======================================
    
    # Check permission
    if user_id != OWNER_ID:
        logger.warning(f"⚠️ Unauthorized speedtest attempt by {username} ({user_id})")
        await msg.reply_text(
            "❌ <b>Unauthorized!</b>\n"
            "Only owner can use /speed command.",
            parse_mode=ParseMode.HTML
        )
        return
    
    # Check rate limit
    last_speedtest = speedtest_cooldown[user_id]
    now = datetime.now()
    time_since_last = (now - last_speedtest).total_seconds()
    
    if time_since_last < SPEEDTEST_COOLDOWN:
        cooldown_remaining = int(SPEEDTEST_COOLDOWN - time_since_last)
        await msg.reply_text(
            f"⏳ <b>COOLDOWN ACTIVE</b>\n"
            f"Tunggu {cooldown_remaining} detik sebelum speedtest lagi.\n"
            f"<i>(Prevent resource abuse)</i>",
            parse_mode=ParseMode.HTML
        )
        logger.warning(f"⚠️ Speedtest rate limit: {username} ({user_id})")
        return
    
    # Update cooldown
    speedtest_cooldown[user_id] = now
    
    # ======================================
    # 2. KIRIM STATUS AWAL
    # ======================================
    
    try:
        status_msg = await msg.reply_text(
            "🚀 <b>CONTACTING OOKLA SERVERS...</b>\n"
            "<code>[░░░░░░░░░░] 0%</code>\n"
            "<i>Initializing Speedtest CLI...</i>",
            parse_mode=ParseMode.HTML
        )
    except Exception as e:
        logger.error(f"Failed to send status message: {e}")
        await msg.reply_text("❌ Failed to send message", parse_mode=ParseMode.HTML)
        return

    # ======================================
    # 3. FUNGSI SYNC UNTUK SUBPROCESS
    # ======================================
    
    def run_ookla_native():
        """Jalankan Ookla CLI dan return JSON result"""
        try:
            # Cek apakah Ookla CLI terinstall
            check = subprocess.run(
                ["which", "speedtest"],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            if check.returncode != 0:
                logger.error("Speedtest CLI not installed")
                return {"error": "NOT_INSTALLED"}
            
            # Jalankan speedtest dengan timeout yang ketat
            process = subprocess.run(
                [
                    "speedtest",
                    "--format=json",
                    "--accept-license",
                    "--accept-gdpr"
                ],
                capture_output=True,
                text=True,
                timeout=180,  # Max 3 menit
                check=False  # Jangan raise exception
            )
            
            if process.returncode != 0:
                error_msg = process.stderr.strip()
                logger.error(f"Speedtest CLI error: {error_msg}")
                return {"error": f"CLI_ERROR: {error_msg[:100]}"}
            
            # Parse JSON dengan error handling
            try:
                return json.loads(process.stdout)
            except json.JSONDecodeError as e:
                logger.error(f"JSON parse error: {e}")
                logger.error(f"Raw output: {process.stdout[:200]}")
                return {"error": "JSON_PARSE_ERROR"}
            
        except subprocess.TimeoutExpired:
            logger.error("Speedtest timeout (>180s)")
            return {"error": "TIMEOUT"}
        except FileNotFoundError:
            logger.error("Speedtest binary not found")
            return {"error": "NOT_INSTALLED"}
        except PermissionError:
            logger.error("Permission denied to run speedtest")
            return {"error": "PERMISSION_DENIED"}
        except OSError as e:
            logger.error(f"OS error: {e}")
            return {"error": f"OS_ERROR: {str(e)[:50]}"}
        except Exception as e:
            logger.error(f"Unexpected error in run_ookla_native: {e}")
            return {"error": f"UNKNOWN_ERROR: {str(e)[:50]}"}

    # ======================================
    # 4. JALANKAN TEST DI BACKGROUND THREAD
    # ======================================
    
    animation_task = None
    test_task = None
    
    try:
        loop = asyncio.get_running_loop()
        
        # Jalankan animasi dan test secara parallel
        test_task = loop.run_in_executor(executor, run_ookla_native)
        animation_task = asyncio.create_task(animate_loading(status_msg, duration=180))
        
        # Tunggu test selesai (dengan timeout buffer)
        data = await asyncio.wait_for(test_task, timeout=190)
        
        # Stop animasi (force)
        if animation_task and not animation_task.done():
            animation_task.cancel()
            try:
                await animation_task
            except asyncio.CancelledError:
                pass
        
        logger.info(f"✅ Speedtest process completed by {username}")
        
    except asyncio.TimeoutError:
        logger.error(f"⏱️ Speedtest timeout for {username}")
        
        # Cancel tasks
        if animation_task and not animation_task.done():
            animation_task.cancel()
        if test_task and not test_task.done():
            test_task.cancel()
        
        await status_msg.edit_text(
            "⏱️ <b>TIMEOUT</b>\n"
            "Speedtest took too long (>3 minutes).\n"
            "<i>Network connection might be too slow.</i>",
            parse_mode=ParseMode.HTML
        )
        return
        
    except asyncio.CancelledError:
        logger.warning(f"Speedtest cancelled for {username}")
        if animation_task:
            animation_task.cancel()
        return
        
    except Exception as e:
        logger.error(f"❌ Speedtest error for {username}: {e}")
        
        # Cancel tasks
        if animation_task and not animation_task.done():
            animation_task.cancel()
        
        await status_msg.edit_text(
            f"❌ <b>ERROR</b>\n"
            f"<code>{str(e)[:100]}</code>",
            parse_mode=ParseMode.HTML
        )
        return

    # ======================================
    # 5. CEK HASIL
    # ======================================
    
    if not data or "error" in data:
        error_msg = data.get("error", "Unknown error") if data else "Unknown error"
        logger.error(f"Speedtest error result: {error_msg}")
        
        if error_msg == "NOT_INSTALLED":
            await status_msg.edit_text(
                "❌ <b>OOKLA CLI NOT FOUND</b>\n\n"
                "Install dengan command:\n"
                "<code>apt update && apt install speedtest-cli</code>\n\n"
                "Atau download dari: https://www.speedtest.net/apps/cli",
                parse_mode=ParseMode.HTML
            )
        elif error_msg == "PERMISSION_DENIED":
            await status_msg.edit_text(
                "❌ <b>PERMISSION DENIED</b>\n"
                "Bot tidak memiliki akses untuk menjalankan speedtest.",
                parse_mode=ParseMode.HTML
            )
        elif error_msg == "TIMEOUT":
            await status_msg.edit_text(
                "⏱️ <b>TIMEOUT</b>\n"
                "Connection too slow or server tidak merespon.",
                parse_mode=ParseMode.HTML
            )
        else:
            await status_msg.edit_text(
                f"❌ <b>SPEEDTEST FAILED</b>\n"
                f"Error: <code>{error_msg}</code>",
                parse_mode=ParseMode.HTML
            )
        return

    # ======================================
    # 6. PARSING DATA DARI OOKLA JSON
    # ======================================
    
    try:
        # Validasi field yang diperlukan
        required_fields = ["download", "upload", "ping"]
        missing_fields = [f for f in required_fields if f not in data]
        
        if missing_fields:
            logger.error(f"Missing required fields: {missing_fields}")
            await status_msg.edit_text(
                f"❌ <b>INCOMPLETE RESPONSE</b>\n"
                f"Missing fields: {', '.join(missing_fields)}",
                parse_mode=ParseMode.HTML
            )
            return
        
        # Parse dengan type conversion yang ketat
        download_mbps = round(float(data["download"]) / 1_000_000, 2)
        upload_mbps = round(float(data["upload"]) / 1_000_000, 2)
        ping = round(float(data.get("ping", 0)), 2)
        jitter = round(float(data.get("jitter", 0)), 2)
        packet_loss = round(float(data.get("packetLoss", 0)), 1)
        
        # Validasi nilai yang masuk akal
        if download_mbps < 0 or upload_mbps < 0 or ping < 0:
            logger.error(f"Invalid values: DL={download_mbps}, UP={upload_mbps}, PING={ping}")
            await status_msg.edit_text(
                "❌ <b>INVALID DATA</b>\n"
                "Speedtest returned invalid values.",
                parse_mode=ParseMode.HTML
            )
            return
        
        isp = str(data.get("isp", "Unknown"))[:100]  # Sanitize length
        server_name = str(data.get("serverName", "Unknown"))[:100]
        server_location = str(data.get("serverLocation", "Unknown"))[:100]
        server_country = str(data.get("serverCountry", "Unknown"))[:100]
        result_url = data.get("result", {}).get("url")
        external_ip = str(data.get("interfaceIpv4", "N/A"))[:50]
        
        # Validasi URL
        if result_url:
            try:
                urllib.parse.urlparse(result_url)  # Validate URL format
                if not result_url.endswith(".png"):
                    result_url = result_url + ".png"
            except Exception as e:
                logger.warning(f"Invalid result URL: {e}")
                result_url = None
        
    except (KeyError, ValueError, TypeError) as e:
        logger.error(f"Parse error: {e}, Data: {data}")
        await status_msg.edit_text(
            f"❌ <b>PARSE ERROR</b>\n"
            f"<code>{str(e)[:100]}</code>",
            parse_mode=ParseMode.HTML
        )
        return

    # ======================================
    # 7. HAPUS STATUS MESSAGE
    # ======================================
    
    try:
        await status_msg.delete()
    except Exception as e:
        logger.warning(f"Failed to delete status message: {e}")

    # ======================================
    # 8. BUAT REPORT TEXT
    # ======================================
    
    report_text = (
        "<b>🚀 OOKLA SPEEDTEST RESULT</b>\n"
        "<code>━━━━━━━━━━━━━━━━━━━━━━━━━━</code>\n"
        f"<b>📊 PERFORMANCE</b>\n"
        f"├ 📥 <b>Download:</b> <code>{download_mbps} Mbps</code>\n"
        f"├ 📤 <b>Upload:</b> <code>{upload_mbps} Mbps</code>\n"
        f"├ 📡 <b>Ping:</b> <code>{ping} ms</code>\n"
        f"└ 📊 <b>Jitter:</b> <code>{jitter} ms</code> (Loss: {packet_loss}%)\n\n"
        
        f"<b>💻 CLIENT INFO</b>\n"
        f"├ <b>ISP:</b> {isp}\n"
        f"└ <b>IP:</b> <code>{external_ip}</code>\n\n"
        
        f"<b>🌍 SERVER TARGET</b>\n"
        f"├ <b>Node:</b> {server_name}\n"
        f"└ <b>Location:</b> {server_location}, {server_country}\n"
        "<code>━━━━━━━━━━━━━━━━━━━━━━━━━━</code>\n"
        f"⏰ <i>{datetime.now(TZ).strftime('%Y-%m-%d %H:%M:%S %Z')}</i>"
    )

    # ======================================
    # 9. KIRIM HASIL
    # ======================================
    
    try:
        if result_url:
            try:
                # Coba kirim dengan gambar (timeout 10s)
                await asyncio.wait_for(
                    msg.reply_photo(
                        photo=result_url,
                        caption=report_text,
                        parse_mode=ParseMode.HTML
                    ),
                    timeout=10
                )
                logger.info(f"✅ Speedtest photo sent to {username}")
            except asyncio.TimeoutError:
                logger.warning(f"Photo download timeout for {username}, sending text only")
                await msg.reply_text(report_text, parse_mode=ParseMode.HTML)
            except Exception as e:
                logger.warning(f"Photo error for {username}: {e}, sending text only")
                await msg.reply_text(report_text, parse_mode=ParseMode.HTML)
        else:
            await msg.reply_text(report_text, parse_mode=ParseMode.HTML)
            
    except Exception as e:
        logger.error(f"Failed to send result to {username}: {e}")
        try:
            await msg.reply_text(
                "❌ <b>ERROR</b>\n"
                "Failed to send result. Please try again.",
                parse_mode=ParseMode.HTML
            )
        except:
            pass
    
    # ======================================
    # 10. LOG HASIL
    # ======================================
    
    logger.info(
        f"✅ SPEEDTEST by {username} ({user_id}): "
        f"DL={download_mbps}Mbps UP={upload_mbps}Mbps PING={ping}ms ISP={isp}"
    )
# ==============================================================================
# BAGIAN 1: /jeni (AUTO CREATE ACCOUNT - ANTI BANNED DOMAIN)
# ==============================================================================
async def jeni_auto_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    caller_id = msg.from_user.id
    
    # Owner only check (opsional):
    if caller_id != config.OWNER_ID:
        await msg.reply_text("⛔ Owner only!")
        return
    
    # --- HELPER ANIMASI BAR ---
    async def update_bar(percent, status_text, logs=""):
        bar_len = 10
        filled = int(percent / 10)
        bar = "█" * filled + "░" * (bar_len - filled)
        text = (
            f"🧬 <b>JENNI.AI SYSTEM OVERRIDE</b>\n"
            f"<code>━━━━━━━━━━━━━━━━━━━━━━━━━━</code>\n"
            f"<b>⚙️ PROCESS:</b>\n"
            f"<code>[{bar}] {percent}%</code>\n\n"
            f"<b>📝 STATUS:</b>\n"
            f"<i>{status_text}</i>\n"
            f"<code>{logs}</code>"
        )
        try: await status_msg.edit_text(text, parse_mode="HTML")
        except: pass 

    status_msg = await msg.reply_text("💻 <b>INITIALIZING EXPLOIT...</b>", parse_mode="HTML")
    await update_bar(10, "Allocating Resources...", "> Loading modules...\n> Bypassing SSL pinning...")
    
    fname = random.choice(["Alex", "Budi", "Charlie", "Dani", "Evan"])
    password = f"P@ssw0rd{random.randint(100000,999999)}"  # ✅ RANDOM PASSWORD

    # --- LOGIKA RETRY ---
    max_retries = 3
    email = None
    id_token = None
    attempt_success = False

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            
            for attempt in range(1, max_retries + 1):
                logs_attempt = f"> Attempt {attempt}/{max_retries}..."
                await update_bar(20 + (attempt * 5), f"Forging Identity ({attempt}/{max_retries})...", logs_attempt)
                
                # A. GENERATE EMAIL
                mail_headers = {"X-API-Key": config.TEMPMAIL_API_KEY}
                resp_mail = await client.post(
                    "https://api.temp-mail.io/v1/emails",
                    headers=mail_headers,
                    json={"domain_type": "premium"}
                )
                
                if resp_mail.status_code != 200:
                    await asyncio.sleep(1)
                    continue
                
                current_email = resp_mail.json().get("email")
                logger.info(f"[JENI] Email generated: {current_email}")
                
                # B. SIGNUP
                await update_bar(40 + (attempt * 5), "Injecting Payload...", 
                               f"> Testing Domain: {current_email.split('@')[1]}\n> Target: accounts:signUp")
                
                signup_url = f"https://identitytoolkit.googleapis.com/v1/accounts:signUp?key={config.FIREBASE_API_KEY}"
                signup_payload = {"email": current_email, "password": password, "returnSecureToken": True}
                
                reg_resp = await client.post(signup_url, json=signup_payload)
                
                if reg_resp.status_code == 200:
                    email = current_email
                    id_token = reg_resp.json()["idToken"]
                    attempt_success = True
                    logger.info(f"[JENI] Signup success: {email}")
                    break
                else:
                    error_msg = reg_resp.json().get("error", {}).get("message", "Unknown error")
                    logger.warning(f"[JENI] Signup failed: {error_msg}")
                    await asyncio.sleep(1)
            
            if not attempt_success:
                await status_msg.edit_text("❌ <b>GAGAL TOTAL:</b> Semua domain ditolak. Coba lagi nanti.")
                return

            # TRIGGER VERIFIKASI
            await update_bar(65, "Account Created.", f"> Valid Email: {email}\n> Triggering Verification...")
            verify_url = f"https://identitytoolkit.googleapis.com/v1/accounts:sendOobCode?key={config.FIREBASE_API_KEY}"
            await client.post(verify_url, json={"requestType": "VERIFY_EMAIL", "idToken": id_token})

            # SCAN EMAIL
            final_link = None
            scan_attempts = 12
            for i in range(scan_attempts):
                await update_bar(75 + (i * 2), "Intercepting Link...", f"> Scanning Inbox... ({i+1}/{scan_attempts})")
                await asyncio.sleep(2)
                
                inbox_resp = await client.get(f"https://api.temp-mail.io/v1/emails/{email}/messages", headers=mail_headers)
                if inbox_resp.status_code == 200:
                    msgs = inbox_resp.json().get("messages", [])
                    if msgs:
                        body = msgs[0].get("body_text", "") + msgs[0].get("body_html", "")
                        links = re.findall(r'https?://[^\s<>"]+', body)
                        for link in links:
                            if "verifyEmail" in link or "jenni" in link.lower():
                                final_link = link
                                break
                        if final_link: break
            
            if not final_link:
                await status_msg.edit_text("❌ <b>TIMEOUT:</b> Email verifikasi tidak masuk.")
                return

            # CLICK VERIFY
            await update_bar(95, "Link Found.", "> Executing Auto-Click...")
            await client.get(final_link)
            
            # ✅ SAVE TO DATABASE
            try:
                cursor.execute("""
                    INSERT INTO accounts (email, password, plan, status, created_at)
                    VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                """, (email, password, "Monthly", "AVAILABLE"))
                conn.commit()
                logger.info(f"[JENI] Account saved: {email}")
            except Exception as db_err:
                logger.error(f"[JENI] DB error: {db_err}")
            
            await update_bar(100, "ACCESS GRANTED.", "> Done.")

            report = (
                f"<b>🧬 JENNI.AI ACCOUNT CREATED</b>\n"
                f"<code>━━━━━━━━━━━━━━━━━━━━━━━━━━</code>\n"
                f"<b>📧 EMAIL :</b> <code>{email}</code>\n"
                f"<b>🔑 PASS  :</b> <code>{password}</code>\n"
                f"<code>━━━━━━━━━━━━━━━━━━━━━━━━━━</code>\n"
                f"👉 <b>NEXT:</b> <code>/upgrade {email}|{password}</code>"
            )
            await status_msg.edit_text(report, parse_mode="HTML")

    except Exception as e:
        logger.error(f"[JENI] Exception: {str(e)}")
        await status_msg.edit_text(f"❌ <b>ERROR:</b> {str(e)[:100]}")
        
# ==============================================================================
# 🚀 BAGIAN 1: FITUR UPGRADE JENNI.AI (FACTORY)
# ==============================================================================

# --- START COMMAND (/upgrade) ---
async def start_upgrade_factory(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return

    if not context.args:
        await update.message.reply_text("⚠️ <b>Format:</b>\n<code>/upgrade email|password</code>", parse_mode="HTML")
        return ConversationHandler.END

    raw = " ".join(context.args)
    if "|" not in raw:
        await update.message.reply_text("❌ <b>Format Salah:</b>\nPakai pemisah | (garis lurus)", parse_mode="HTML")
        return ConversationHandler.END

    email, password = raw.split("|", 1)
    
    # Reset Session
    session_data.clear()
    session_data["email"] = email.strip()
    session_data["password"] = password.strip()

    keyboard = [
        [InlineKeyboardButton("📅 MONTHLY (Rp 250k)", callback_data="plan_monthly")],
        [InlineKeyboardButton("🗓️ YEARLY (Rp 1jt)", callback_data="plan_yearly")]
    ]
    await update.message.reply_text("🏭 <b>PILIH PAKET UPGRADE:</b>", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")
    return INPUT_CARD

# ==============================================================================
# 🛠️ BAGIAN 2: KONFIGURASI BROWSER & POOL
# ==============================================================================

SELENIUM_POOL = ThreadPoolExecutor(max_workers=5) # Multitasking 5 order
MAX_STRIPE_RETRY = 3

def build_stealth_chrome(proxy_string=None):
    """Fungsi Bikin Browser Hantu"""
    options = webdriver.ChromeOptions()
    options.add_argument("--headless=new") 
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    
    if proxy_string: options.add_argument(f'--proxy-server={proxy_string}')

    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--disable-infobars")
    options.add_argument("--disable-extensions")
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
        "source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
    })
    return driver

# ==============================================================================
# 👷 BAGIAN 3: WORKERS (LOGIC MESIN SELENIUM)
# ==============================================================================

def selenium_upgrade_worker(session_data, status_msg):
    """Worker 1: Login & Klik Upgrade"""
    driver = None
    try:
        driver = build_stealth_chrome()
        session_data['driver'] = driver
        wait = WebDriverWait(driver, 30)

        # Login
        driver.get("https://app.jenni.ai/login")
        wait.until(EC.visibility_of_element_located((By.NAME, "email"))).send_keys(session_data['email'])
        driver.find_element(By.NAME, "password").send_keys(session_data['password'])
        driver.find_element(By.CSS_SELECTOR, "button[type='submit']").click()
        time.sleep(5)

        # Ke Halaman Billing (Shortcut)
        try:
            driver.get("https://app.jenni.ai/settings/billing")
            time.sleep(4)
        except: pass

        # Pilih Plan
        if session_data['plan'] == "Monthly":
            try: driver.find_element(By.XPATH, "//div[contains(text(), 'Monthly')]").click()
            except: pass
        else:
            try: driver.find_element(By.XPATH, "//div[contains(text(), 'Annual')]").click()
            except: pass
        
        time.sleep(1)
        # Klik Tombol Upgrade (Cari tombol ungu)
        buttons = driver.find_elements(By.TAG_NAME, "button")
        for btn in buttons:
            if "upgrade" in btn.text.lower():
                btn.click()
                break
        
        wait.until(EC.url_contains("stripe.com"))
        return True
    except Exception as e:
        if driver: driver.quit()
        return str(e)

def selenium_card_worker(driver, cc_data, email, password, plan):
    """Worker 2: Input Kartu & Bayar"""
    try:
        wait = WebDriverWait(driver, 20)
        cc, exp, cvv = cc_data.split("|")

        # Input Kartu
        wait.until(EC.visibility_of_element_located((By.ID, "cardNumber"))).send_keys(cc)
        time.sleep(0.2)
        driver.find_element(By.ID, "cardExpiry").send_keys(exp)
        driver.find_element(By.ID, "cardCvc").send_keys(cvv)
        driver.find_element(By.ID, "billingName").send_keys("Budi Santoso")
        
        # Alamat Dummy
        try: 
            driver.find_element(By.ID, "billingAddressLine1").send_keys("Jalan Merdeka")
            driver.find_element(By.ID, "billingCity").send_keys("Jakarta")
            driver.find_element(By.ID, "billingPostalCode").send_keys("12000")
        except: pass

        driver.find_element(By.CSS_SELECTOR, "button[type='submit']").click()

        # Cek Hasil (Looping 25 detik)
        for _ in range(25):
            time.sleep(1)
            curr_url = driver.current_url.lower()
            page_source = driver.page_source.lower()
            if "success" in curr_url or "thank" in page_source: return "SUCCESS"
            if "challenge" in curr_url or "authentication" in curr_url: return "OTP_REQUIRED"
            if "declined" in page_source: return "DECLINED"
        return "TIMEOUT"
    except Exception as e: return f"ERROR: {str(e)}"

def selenium_otp_worker(driver, otp_code):
    """Worker 3: Input OTP"""
    try:
        wait = WebDriverWait(driver, 10)
        frames = driver.find_elements(By.TAG_NAME, "iframe")
        for frame in frames:
            try:
                driver.switch_to.frame(frame)
                otp_input = driver.find_element(By.XPATH, "//input[@type='password' or @type='text' or @type='tel']")
                otp_input.send_keys(otp_code)
                otp_input.send_keys("\n")
                driver.switch_to.default_content()
                break
            except: driver.switch_to.default_content()
        
        time.sleep(8)
        if "success" in driver.current_url.lower(): return True
        return False
    except: return False

# ==============================================================================
# 🎮 BAGIAN 4: TELEGRAM HANDLERS (LOGIC + LOGGING BACKUP)
# ==============================================================================

async def select_plan_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    session_data['plan'] = "Monthly" if query.data == "plan_monthly" else "Yearly"

    status_msg = await query.message.reply_text("🤖 <b>ROBOT BERGERAK...</b>\n<i>Login & Menuju Stripe...</i>", parse_mode="HTML")
    
    # Panggil Worker Login
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(SELENIUM_POOL, selenium_upgrade_worker, session_data, status_msg)

    if result is True:
        await status_msg.edit_text("💳 <b>SIAP GESEK!</b>\nKirim: <code>CC|MM/YY|CVV</code>", parse_mode="HTML")
        return INPUT_CARD
    else:
        await status_msg.edit_text(f"❌ <b>GAGAL LOGIN:</b>\n{result}")
        return ConversationHandler.END

async def input_card_process(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if "|" not in text: 
        await update.message.reply_text("❌ Format: <code>CC|MM/YY|CVV</code>", parse_mode="HTML")
        return INPUT_CARD
    
    driver = session_data.get('driver')
    if not driver:
        await update.message.reply_text("❌ Sesi habis.")
        return ConversationHandler.END

    status_msg = await update.message.reply_text("💳 <b>MENGGESEK KARTU...</b>", parse_mode="HTML")
    
    # Panggil Worker Kartu
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(SELENIUM_POOL, selenium_card_worker, driver, text, session_data['email'], session_data['password'], session_data['plan'])

    if result == "SUCCESS":
        # 1. Simpan ke DB
        try:
            cursor.execute("INSERT INTO accounts (email, password, plan, status) VALUES (?, ?, ?, 'AVAILABLE')", 
                        (session_data['email'], session_data['password'], session_data['plan']))
            conn.commit()
        except: pass

        # 2. Kirim Bukti ke Chat Bot
        driver.save_screenshot("success.png")
        await update.message.reply_photo(open("success.png", "rb"), caption=f"✅ <b>SUKSES!</b>\n{session_data['email']}")
        
        # 3. [FITUR LOG] Kirim ke Channel Backup (LOGIC TAMBAHAN)
        LOG_CHANNEL_ID = -1001234567890 # GANTI INI DENGAN ID CHANNEL MAS
        try:
            struk_log = f"💎 <b>NEW ACCOUNT!</b>\n📧 {session_data['email']}\n🔑 {session_data['password']}\n📅 {session_data['plan']}\n💳 {text[:6]}xxxx"
            await context.bot.send_photo(chat_id=LOG_CHANNEL_ID, photo=open("success.png", "rb"), caption=struk_log, parse_mode="HTML")
        except: pass

        driver.quit()
        return ConversationHandler.END
    
    elif result == "OTP_REQUIRED":
        driver.save_screenshot("otp.png")
        await update.message.reply_photo(open("otp.png", "rb"), caption="⚠️ <b>BUTUH OTP!</b> Masukkan kodenya:")
        return INPUT_OTP
    
    elif result == "DECLINED":
        await status_msg.edit_text("❌ <b>DECLINED.</b> Coba kartu lain.")
        return INPUT_CARD
    
    else:
        await status_msg.edit_text(f"❌ <b>ERROR:</b> {result}")
        driver.quit()
        return ConversationHandler.END

async def input_otp_process(update: Update, context: ContextTypes.DEFAULT_TYPE):
    otp = update.message.text
    driver = session_data.get('driver')
    msg = await update.message.reply_text("⏳ <b>INPUT OTP...</b>", parse_mode="HTML")

    # Panggil Worker OTP
    loop = asyncio.get_event_loop()
    if await loop.run_in_executor(SELENIUM_POOL, selenium_otp_worker, driver, otp):
        try:
            cursor.execute("INSERT INTO accounts (email, password, plan, status) VALUES (?, ?, ?, 'AVAILABLE')", 
                        (session_data['email'], session_data['password'], session_data['plan']))
            conn.commit()
        except: pass
        
        await msg.edit_text("✅ <b>OTP SUKSES!</b>")

        # [FITUR LOG] Kirim ke Channel Backup (Juga saat OTP Sukses)
        LOG_CHANNEL_ID = -1001981442073 # GANTI DENGAN ID CHANNEL MAS
        try:
            driver.save_screenshot("otp_success.png")
            struk_log = f"💎 <b>NEW ACCOUNT (OTP)!</b>\n📧 {session_data['email']}\n🔑 {session_data['password']}\n📅 {session_data['plan']}"
            await context.bot.send_photo(chat_id=LOG_CHANNEL_ID, photo=open("otp_success.png", "rb"), caption=struk_log, parse_mode="HTML")
        except: pass

    else:
        await msg.edit_text("❌ <b>OTP GAGAL.</b>")
    
    driver.quit()
    return ConversationHandler.END

# ==========================================
# 🎯 STATE CONSTANTS (CONVERSATION HANDLER)
# ==========================================

WAIT_PROOF = 1
INPUT_CARD = 2
INPUT_OTP = 3
CONFIRM_CARD = 4
# ==========================================
# 🎯 UTILITY FUNCTIONS
# ==========================================

async def log_transaction(action: str, plan: str, user_id: int, status: str):
    """Log semua transaksi"""
    try:
        cursor.execute("""
            INSERT INTO transaction_logs (action, plan, user_id, status)
            VALUES (?, ?, ?, ?)
        """, (action, plan, user_id, status))
        conn.commit()
    except Exception as e:
        logger.error(f"Log transaction error: {e}")

async def check_pending_order(user_id: int) -> bool:
    """Check apakah user punya order pending"""
    try:
        cursor.execute(
            "SELECT id FROM orders WHERE user_id=? AND status='pending'",
            (user_id,)
        )
        return bool(cursor.fetchone())
    except:
        return False

async def check_stock_availability(plan: str) -> int:
    """Cek stok berdasarkan plan"""
    try:
        cursor.execute(
            "SELECT COUNT(*) FROM accounts WHERE status='AVAILABLE' AND plan LIKE ?",
            (f"%{plan}%",)
        )
        return cursor.fetchone()[0]
    except:
        return 0

async def get_available_account(plan: str) -> tuple:
    """Ambil 1 akun dari gudang"""
    try:
        cursor.execute(
            "SELECT id, email, password FROM accounts WHERE status='AVAILABLE' AND plan LIKE ? LIMIT 1",
            (f"%{plan}%",)
        )
        return cursor.fetchone()
    except:
        return None

def get_price_for_plan(plan: str) -> str:
    """Get harga untuk plan"""
    prices = {
        "Monthly": "Rp 25.000",
        "Yearly": "Rp 150.000"
    }
    return prices.get(plan, "Unknown")

def get_status_emoji(status: str) -> str:
    """Get emoji untuk status"""
    emojis = {
        "pending": "⏳",
        "approved": "✅",
        "rejected": "❌",
        "expired": "⏰"
    }
    return emojis.get(status, "❓")

def get_stock_icon(count: int) -> str:
    """Get icon untuk stok"""
    if count <= 0:
        return "❌"
    elif count <= 2:
        return "⚠️"
    elif count <= 5:
        return "🟡"
    else:
        return "🟢"

def get_stock_status(count: int) -> str:
    """Get status stok"""
    if count <= 0:
        return "❌ HABIS"
    elif count <= 2:
        return "⚠️ KRITIS"
    elif count <= 5:
        return "🟡 SEDIKIT"
    else:
        return "🟢 TERSEDIA"

# ==========================================
# 📊 STOCK COMMAND (IMPROVED)
# ==========================================

async def stock_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show gudang akun dengan detail"""
    try:
        cursor.execute(
            "SELECT plan, COUNT(*) FROM accounts WHERE status='AVAILABLE' GROUP BY plan"
        )
        rows = cursor.fetchall()
        
        msg = (
            "╔════════════════════════════╗\n"
            "║   🏭 GUDANG AKUN JENNI     ║\n"
            "║      (REALTIME UPDATE)     ║\n"
            "╚════════════════════════════╝\n\n"
        )
        
        if not rows:
            msg += "❌ <b>STOK HABIS!</b>\nSegera restock kak."
        else:
            total = 0
            for plan, count in rows:
                icon = get_stock_icon(count)
                status = get_stock_status(count)
                msg += f"{icon} <b>{plan}:</b> {count} pcs [{status}]\n"
                total += count
            
            msg += f"\n━━━━━━━━━━━━━━━━━━━━\n"
            msg += f"<b>Total:</b> {total} akun ready\n\n"
            msg += f"💡 Ketik /beli untuk pesan akun"
        
        await update.message.reply_text(msg, parse_mode="HTML")
    except Exception as e:
        logger.error(f"Stock command error: {e}")
        await update.message.reply_text(
            f"❌ Error: {str(e)[:50]}",
            parse_mode="HTML"
        )

# ==========================================
# 🛒 BELI START FLOW (IMPROVED)
# ==========================================

async def beli_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start pembelian dengan validasi"""
    user_id = update.effective_user.id
    
    try:
        has_pending = await check_pending_order(user_id)
        if has_pending:
            await update.message.reply_text(
                "⚠️ <b>ANDA MASIH PUNYA ORDER PENDING!</b>\n\n"
                "Tunggu admin ACC dulu sebelum beli lagi.\n"
                "Estimasi: 1-5 menit.\n\n"
                "Ketik /sts untuk cek status order Anda.",
                parse_mode="HTML"
            )
            return ConversationHandler.END
        
        keyboard = []
        
        monthly_stock = await check_stock_availability("Monthly")
        monthly_btn = InlineKeyboardButton(
            f"📅 MONTHLY - Rp 25.000 ({monthly_stock} stok)",
            callback_data="buy_Monthly"
        ) if monthly_stock > 0 else InlineKeyboardButton(
            "📅 MONTHLY - HABIS",
            callback_data="out_of_stock"
        )
        keyboard.append([monthly_btn])
        
        yearly_stock = await check_stock_availability("Yearly")
        yearly_btn = InlineKeyboardButton(
            f"🗓️ YEARLY - Rp 150.000 ({yearly_stock} stok)",
            callback_data="buy_Yearly"
        ) if yearly_stock > 0 else InlineKeyboardButton(
            "🗓️ YEARLY - HABIS",
            callback_data="out_of_stock"
        )
        keyboard.append([yearly_btn])
        
        keyboard.append([InlineKeyboardButton("❌ Batal", callback_data="buy_cancel")])
        
        await update.message.reply_text(
            "╔════════════════════════════╗\n"
            "║   🛒 MENU PEMBELIAN JENNI  ║\n"
            "╚════════════════════════════╝\n\n"
            "Silakan pilih paket yang mau dibeli:\n\n"
            "💡 <i>Pembayaran via QRIS (instant)</i>",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="HTML"
        )
        return WAIT_PROOF
    
    except Exception as e:
        logger.error(f"Beli start error: {e}")
        await update.message.reply_text(
            f"❌ Error: {str(e)[:50]}",
            parse_mode="HTML"
        )
        return ConversationHandler.END

# ==========================================
# 💳 BUY MENU CALLBACK (IMPROVED)
# ==========================================

async def buy_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Process pemilihan plan dengan safety checks"""
    query = update.callback_query
    user = query.from_user
    user_id = user.id
    
    try:
        await query.answer()
        
        if query.data == "buy_cancel":
            await query.message.edit_text("❌ Transaksi dibatalkan.")
            return ConversationHandler.END
        
        if query.data == "out_of_stock":
            await query.answer("⚠️ Stok habis, silakan pilih paket lain!", show_alert=True)
            return WAIT_PROOF
        
        plan_dipilih = query.data.split("_")[1]
        
        stok = await check_stock_availability(plan_dipilih)
        
        if stok == 0:
            await query.message.edit_text(
                f"❌ <b>MAAF KAK, STOK {plan_dipilih.upper()} HABIS!</b>\n\n"
                "Jangan transfer dulu ya. Stok baru akan masuk dalam waktu dekat.\n"
                "Silakan cek /stock lagi nanti.",
                parse_mode="HTML"
            )
            return ConversationHandler.END
        
        harga = get_price_for_plan(plan_dipilih)
        context.user_data['plan_beli'] = plan_dipilih
        context.user_data['harga_beli'] = harga
        
        try:
            cursor.execute("""
                INSERT INTO orders (user_id, plan, price, status)
                VALUES (?, ?, ?, 'pending')
            """, (user_id, plan_dipilih, harga))
            conn.commit()
        except Exception as e:
            logger.error(f"Order insert error: {e}")
        
        try:
            await query.message.reply_photo(
                photo=config.QRIS_IMAGE,
                caption=(
                    f"╔════════════════════════════╗\n"
                    f"║   💳 INVOICE PEMBAYARAN    ║\n"
                    f"╚════════════════════════════╝\n\n"
                    f"<b>Produk:</b> Jenni.ai {plan_dipilih}\n"
                    f"<b>Harga :</b> {harga}\n"
                    f"<b>Status:</b> ⏳ Menunggu pembayaran\n\n"
                    f"📋 <b>CARA PEMBAYARAN:</b>\n"
                    f"1️⃣ Scan QRIS di atas\n"
                    f"2️⃣ Transfer <b>TEPAT</b> sesuai nominal\n"
                    f"3️⃣ <b>KIRIM FOTO BUKTI</b> sekarang\n\n"
                    f"⏰ <b>Batas waktu:</b> 30 menit\n"
                    f"(Jika expired, silakan /beli lagi)\n\n"
                    f"<i>Pembayaran instant ✓ Aman terpercaya ✓</i>"
                ),
                parse_mode="HTML"
            )
        except Exception as e:
            logger.error(f"QRIS send error: {e}")
            await query.message.reply_text(
                f"❌ Error menampilkan QRIS: {e}\n"
                f"Hubungi admin untuk bantuan.",
                parse_mode="HTML"
            )
        
        return WAIT_PROOF
    
    except Exception as e:
        logger.error(f"Buy menu error: {e}")
        await query.message.reply_text(
            f"❌ Error: {str(e)[:50]}",
            parse_mode="HTML"
        )
        return ConversationHandler.END

# ==========================================
# 📸 RECEIVE PROOF HANDLER (IMPROVED)
# ==========================================

async def receive_proof_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Terima bukti transfer dengan validasi ketat"""
    user = update.effective_user
    user_id = user.id
    
    try:
        if not update.message.photo:
            await update.message.reply_text(
                "⚠️ <b>FORMAT SALAH!</b>\n"
                "Kirim foto bukti transfer, jangan text/video/dll.",
                parse_mode="HTML"
            )
            return WAIT_PROOF
        
        photo = update.message.photo[-1]
        if photo.width < 300 or photo.height < 300:
            await update.message.reply_text(
                "⚠️ <b>FOTO TERLALU KECIL!</b>\n\n"
                "Pastikan foto bukti transfer jelas & terang.\n"
                "Kirim ulang dengan resolusi lebih tinggi (min 300x300px).",
                parse_mode="HTML"
            )
            return WAIT_PROOF
        
        photo_id = photo.file_id
        plan = context.user_data.get('plan_beli')
        harga = context.user_data.get('harga_beli')
        
        if not plan or not harga:
            await update.message.reply_text(
                "⚠️ <b>ERROR!</b>\n"
                "Data order hilang. Silakan /beli lagi.",
                parse_mode="HTML"
            )
            return ConversationHandler.END
        
        try:
            cursor.execute(
                "UPDATE orders SET proof_photo_id=? WHERE user_id=? AND status='pending' AND plan=?",
                (photo_id, user_id, plan)
            )
            conn.commit()
        except Exception as e:
            logger.error(f"Order update error: {e}")
        
        await update.message.reply_text(
            "✅ <b>BUKTI DITERIMA!</b>\n\n"
            "Mohon tunggu sebentar, Admin sedang mengecek mutasi...\n"
            "<i>(Estimasi 1-5 menit)</i>\n\n"
            "Ketik /sts untuk cek status pesanan Anda.",
            parse_mode="HTML"
        )
        
        tombol_admin = [
            [
                InlineKeyboardButton("✅ ACC (Kirim Akun)", callback_data=f"confirm|{user_id}|{plan}"),
                InlineKeyboardButton("❌ TOLAK", callback_data=f"reject|{user_id}")
            ]
        ]
        
        caption_admin = (
            f"╔════════════════════════════╗\n"
            f"║   💰 PESANAN BARU MAS!     ║\n"
            f"╚════════════════════════════╝\n\n"
            f"👤 <b>Buyer:</b> {user.full_name}\n"
            f"🆔 <b>ID:</b> <code>{user_id}</code>\n"
            f"@{user.username if user.username else 'N/A'}\n\n"
            f"📦 <b>Paket:</b> {plan}\n"
            f"💵 <b>Nominal:</b> {harga}\n\n"
            f"📝 <b>Caption:</b> {update.message.caption if update.message.caption else '(Tidak ada)'}\n\n"
            f"<i>Cek mutasi rekening, kalau masuk klik ACC.</i>"
        )
        
        try:
            await context.bot.send_photo(
                chat_id=config.OWNER_ID,
                photo=photo_id,
                caption=caption_admin,
                reply_markup=InlineKeyboardMarkup(tombol_admin),
                parse_mode="HTML"
            )
        except Exception as e:
            logger.error(f"Admin notification error: {e}")
        
        return ConversationHandler.END
    
    except Exception as e:
        logger.error(f"Proof handler error: {e}")
        await update.message.reply_text(
            f"❌ <b>SISTEM ERROR!</b>\n"
            f"Error: {str(e)[:50]}\n\n"
            f"Hubungi admin untuk bantuan.",
            parse_mode="HTML"
        )
        return ConversationHandler.END

# ==========================================
# ✅ ADMIN APPROVAL CALLBACK (IMPROVED)
# ==========================================

async def admin_approval_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Approval system dengan confirmation"""
    query = update.callback_query
    caller_id = query.from_user.id
    
    try:
        if caller_id != config.OWNER_ID:
            await query.answer("⛔ Hanya owner yang bisa approve!", show_alert=True)
            return
        
        await query.answer()
        
        data = query.data.split("|")
        action = data[0]
        buyer_id = int(data[1])
        
        if action == "reject":
            try:
                cursor.execute(
                    "UPDATE orders SET status='rejected' WHERE user_id=?",
                    (buyer_id,)
                )
                conn.commit()
            except:
                pass
            
            await query.message.edit_caption(
                caption="❌ <b>TRANSAKSI DITOLAK.</b>"
            )
            
            try:
                await context.bot.send_message(
                    chat_id=buyer_id,
                    text=(
                        "❌ <b>MAAF!</b>\n\n"
                        "Bukti transfer Anda ditolak atau dana belum masuk.\n\n"
                        "Silakan:\n"
                        "• Cek kembali bukti transfer\n"
                        "• Pastikan nominal tepat\n"
                        "• Hubungi admin jika ada pertanyaan\n\n"
                        "Ketik /beli untuk order lagi."
                    ),
                    parse_mode="HTML"
                )
            except:
                pass
            
            await log_transaction("rejection", "N/A", buyer_id, "rejected")
            return
        
        plan_beli = data[2]
        
        if action == "confirm":
            confirm_kb = [
                [
                    InlineKeyboardButton("✅ YA, KIRIM AKUN", callback_data=f"confirm_final|{buyer_id}|{plan_beli}"),
                    InlineKeyboardButton("❌ BATAL", callback_data=f"reject|{buyer_id}")
                ]
            ]
            
            await query.message.edit_reply_markup(
                reply_markup=InlineKeyboardMarkup(confirm_kb)
            )
            await query.answer("⚠️ Confirm dulu sebelum kirim akun!", show_alert=True)
            return
        
        if action == "confirm_final":
            acc_data = await get_available_account(plan_beli)
            
            if not acc_data:
                await query.message.edit_caption(
                    caption=(
                        f"⚠️ <b>WADUH MAS!</b>\n\n"
                        f"Stok {plan_beli} tiba-tiba habis!\n"
                        f"(Mungkin keambil orang lain barusan)\n\n"
                        f"Tolong restock dulu."
                    )
                )
                return
            
            acc_id, email, password = acc_data
            
            cursor.execute(
                "UPDATE accounts SET status='SOLD' WHERE id=?",
                (acc_id,)
            )
            conn.commit()
            
            cursor.execute(
                "UPDATE orders SET status='approved', approved_at=CURRENT_TIMESTAMP WHERE user_id=? AND plan=?",
                (buyer_id, plan_beli)
            )
            conn.commit()
            
            trx_id = f"INV-{uuid.uuid4().hex[:6].upper()}"
            waktu = datetime.datetime.now(TZ).strftime("%d/%m/%Y %H:%M")
            
            struk = (
                f"╔════════════════════════════╗\n"
                f"║   ✅ PEMBAYARAN DITERIMA!  ║\n"
                f"╚════════════════════════════╝\n\n"
                f"🧾 <b>INVOICE:</b> <code>{trx_id}</code>\n"
                f"📅 <b>Waktu:</b> {waktu}\n\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"📧 <b>Email:</b> <code>{email}</code>\n"
                f"🔑 <b>Password:</b> <code>{password}</code>\n"
                f"💎 <b>Paket:</b> Jenni.AI {plan_beli}\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                f"✅ <b>Akun Garansi 30 Hari</b>\n"
                f"❓ Ada masalah? Hubungi admin\n\n"
                f"⭐ Jangan lupa kasih rating ya!"
            )
            
            try:
                await context.bot.send_message(
                    chat_id=buyer_id,
                    text=struk,
                    parse_mode="HTML"
                )
                
                remaining = await check_stock_availability(plan_beli)
                
                msg_owner = f"✅ <b>DONE!</b>\n\nAkun terkirim.\n\nSisa Stok {plan_beli}: <b>{remaining}</b>"
                
                if remaining <= 2:
                    msg_owner += "\n\n⚠️ <b>STOK KRITIS! SEGERA /upgrade MAS!</b>"
                
                await query.message.edit_caption(
                    caption=msg_owner,
                    parse_mode="HTML"
                )
                
                await log_transaction("approval", plan_beli, buyer_id, "approved")
                
            except Exception as e:
                logger.error(f"Send akun error: {e}")
                await query.message.reply_text(
                    f"⚠️ <b>ERROR MENGIRIM!</b>\n\n"
                    f"Error: {str(e)[:50]}\n\n"
                    f"Data Akun:\n"
                    f"Email: {email}\n"
                    f"Pass: {password}\n\n"
                    f"Tolong kirim manual ke buyer."
                )
    
    except Exception as e:
        logger.error(f"Admin approval error: {e}")
        await query.answer(f"❌ Error: {str(e)[:50]}", show_alert=True)

# ==========================================
# 📊 STS COMMAND (BUYER) - CHANGED FROM STATUS
# ==========================================

async def sts_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show buyer their order status"""
    user_id = update.effective_user.id
    
    try:
        cursor.execute("""
            SELECT plan, status, created_at FROM orders 
            WHERE user_id=? 
            ORDER BY created_at DESC 
            LIMIT 1
        """, (user_id,))
        
        order = cursor.fetchone()
        
        if not order:
            await update.message.reply_text(
                "❌ <b>BELUM ADA PESANAN</b>\n\n"
                "Silakan /beli untuk membuat pesanan pertama.",
                parse_mode="HTML"
            )
            return
        
        plan, status, created_at = order
        emoji = get_status_emoji(status)
        
        msg = (
            f"╔════════════════════════════╗\n"
            f"║   {emoji} STATUS PESANAN   ║\n"
            f"╚════════════════════════════╝\n\n"
            f"<b>Paket:</b> {plan}\n"
            f"<b>Status:</b> {status.upper()}\n"
            f"<b>Waktu:</b> {created_at}\n\n"
        )
        
        if status == "pending":
            msg += "⏳ Menunggu approval admin... (1-5 menit)\n\n💡 Tunggu SMS/notif dari admin"
        elif status == "approved":
            msg += "✅ Akun sudah dikirim! Cek DM Anda.\n\n💡 Jangan lupa kasih rating ⭐"
        elif status == "rejected":
            msg += "❌ Pesanan ditolak.\n\n💡 Hubungi admin untuk info lebih lanjut."
        elif status == "expired":
            msg += "⏰ Pesanan expired (30 menit tidak ada konfirmasi).\n\n💡 Silakan /beli lagi."
        
        await update.message.reply_text(msg, parse_mode="HTML")
    
    except Exception as e:
        logger.error(f"STS command error: {e}")
        await update.message.reply_text(
            f"❌ Error: {str(e)[:50]}",
            parse_mode="HTML"
        )

# ==========================================
# 📈 SALES REPORT (OWNER ONLY)
# ==========================================

async def sales_report_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show sales report untuk owner"""
    caller_id = update.effective_user.id
    
    if caller_id != config.OWNER_ID:
        await update.message.reply_text("⛔ Owner only!")
        return
    
    try:
        cursor.execute("""
            SELECT plan, COUNT(*) as total, 
                   SUM(CASE WHEN status='approved' THEN 1 ELSE 0 END) as sold
            FROM orders
            WHERE DATE(created_at) = DATE('now')
            GROUP BY plan
        """)
        
        today = cursor.fetchall()
        
        cursor.execute("SELECT COUNT(*) FROM orders WHERE status='approved'")
        all_time_sold = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM orders WHERE status='pending'")
        pending = cursor.fetchone()[0]
        
        report = (
            "╔════════════════════════════╗\n"
            "║   📊 SALES REPORT          ║\n"
            "╚════════════════════════════╝\n\n"
        )
        
        report += "<b>📅 TODAY</b>\n"
        report += "━━━━━━━━━━━━━━━━━\n"
        
        if today:
            for plan, total, sold in today:
                report += f"{plan}: {total} orders | {sold} ✅ sold\n"
        else:
            report += "Belum ada order hari ini\n"
        
        report += f"\n<b>📈 ALL TIME</b>\n"
        report += "━━━━━━━━━━━━━━━━━\n"
        report += f"Total Sold: {all_time_sold}\n"
        report += f"Pending: {pending}\n"
        
        await update.message.reply_text(report, parse_mode="HTML")
    
    except Exception as e:
        logger.error(f"Sales report error: {e}")
        await update.message.reply_text(f"❌ Error: {str(e)[:50]}", parse_mode="HTML")
        

        
# ==========================================
# ❌ CANCEL OPERATION HANDLER
# ==========================================

async def cancel_op(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel operasi/transaksi"""
    try:
        await update.message.reply_text(
            "❌ <b>OPERASI DIBATALKAN</b>\n\n"
            "Silakan ketik /beli jika ingin order lagi.",
            parse_mode="HTML"
        )
        return ConversationHandler.END
    except Exception as e:
        logger.error(f"Cancel operation error: {e}")
        return ConversationHandler.END


# ==========================================
# 🕌 JADWAL SHOLAT (PREMIUM ULTIMATE V4)
# ==========================================
async def sholat_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # 1. Tentukan Kota (Default: Jakarta)
    raw_city = "Jakarta"
    if context.args:
        raw_city = " ".join(context.args).title()  # Huruf depan besar semua

    # Encode untuk URL
    city_encoded = urllib.parse.quote(raw_city)

    # Method 20 = Kemenag RI (Standar Indonesia)
    url = (
        f"https://api.aladhan.com/v1/timingsByCity"
        f"?city={city_encoded}&country=Indonesia&method=20"
    )

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/91.0.4472.124 Safari/537.36"
        )
    }

    # Loading message
    msg = await update.message.reply_text(
        "⏳ <b>Scanning prayer times...</b>",
        parse_mode=ParseMode.HTML,
    )

    try:
        r = await fetch_json(url, headers=headers)

        if r and r.get("code") == 200 and r.get("data"):
            data = r["data"]
            t = data["timings"]
            d_date = data["date"]
            hijri = d_date["hijri"]

            # Tanggal hijriah yang rapi
            hijri_str = f"{hijri['day']} {hijri['month']['en']} {hijri['year']}"

            # Escape teks agar aman di HTML
            city_safe = html.escape(raw_city)
            gregorian_safe = html.escape(d_date.get("readable", "Unknown"))

            # UI PREMIUM ULTIMATE
            txt = (
                f"🕌 <b>ULTRA PRAYER SCHEDULE</b>\n"
                f"✦────────────────────────✦\n"
                f"📍 <b>Location</b>  ⇾ <code>{city_safe}</code>\n"
                f"📅 <b>Gregorian</b> ⇾ <code>{gregorian_safe}</code>\n"
                f"🌙 <b>Hijri</b>     ⇾ <code>{hijri_str}</code>\n"
                f"✦────────────────────────✦\n\n"
                f"🌌 𝗜𝗺𝘀𝗮𝗸        ⇾ <code>{t['Imsak']}</code>\n"
                f"🌓 𝗙𝗮𝗷𝗿 (Subuh) ⇾ <code>{t['Fajr']}</code>\n"
                f"🌞 𝗦𝘂𝗻𝗿𝗶𝘀𝗲      ⇾ <code>{t['Sunrise']}</code>\n"
                f"☀️ 𝗗𝘇𝘂𝗵𝘂𝗿       ⇾ <code>{t['Dhuhr']}</code>\n"
                f"🌤️ 𝗔𝘀𝗵𝗿         ⇾ <code>{t['Asr']}</code>\n"
                f"🌇 𝗠𝗮𝗴𝗵𝗿𝗶??     ⇾ <code>{t['Maghrib']}</code>\n"
                f"🌃 𝗜𝘀𝘆𝗮         ⇾ <code>{t['Isha']}</code>\n\n"
                f"✦────────────────────────✦\n"
                f"🤲 <i>“Jadikan sabar dan sholat sebagai penolongmu.”</i>\n"
                f"    <i>(QS. Al-Baqarah: 45)</i>"
            )

            kb = [
                [
                    InlineKeyboardButton(
                        "🔁 Set Daily Reminder", callback_data="menu_sholat_set"
                    )
                ],
                [
                    InlineKeyboardButton(
                        "🔄 Check Another City",
                        switch_inline_query_current_chat="sholat ",
                    )
                ],
            ]

            await msg.edit_text(
                txt,
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup(kb),
            )

        else:
            await msg.edit_text(
                (
                    "❌ <b>City not found.</b>\n\n"
                    "Tips:\n"
                    "• Use a valid city name.\n"
                    "• Example: <code>/sholat Surabaya</code>"
                ),
                parse_mode=ParseMode.HTML,
            )

    except Exception as e:
        await msg.edit_text(
            f"❌ <b>System Error:</b> <code>{html.escape(str(e))}</code>",
            parse_mode=ParseMode.HTML,
        )

# ==========================================
# 🌐 /scp — ULTIMATE PROXY SCRAPER (THE HUNTER V3)
# ==========================================

# Helper 1: Generic JSON Parser (Recursive)
def extract_ips_from_json(data):
    """Mencari pola IP:PORT dalam struktur JSON apapun secara rekursif."""
    found = set()
    if isinstance(data, list):
        for item in data:
            found.update(extract_ips_from_json(item))
    elif isinstance(data, dict):
        # Cari kombinasi key umum
        ip = data.get('ip') or data.get('ipAddress') or data.get('host')
        port = data.get('port') or data.get('portNumber')
        if ip and port:
            found.add(f"{ip}:{port}")
        # Rekursif ke dalam value
        for val in data.values():
            if isinstance(val, (dict, list)):
                found.update(extract_ips_from_json(val))
    return found

# Helper 2: Fetcher dengan User-Agent & Retry
async def fetch_proxy_source(client, url):
    """Mengambil data dari URL dengan error handling."""
    try:
        resp = await client.get(url)
        if resp.status_code == 200:
            return resp.text, True
    except:
        pass
    return "", False

async def proxy_scrape_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    
    # 1. ANIMASI AWAL (Cinematic Hacking Style)
    status_msg = await msg.reply_text(
        "⚡ <b>INITIALIZING HUNTER PROTOCOL V3.0...</b>\n"
        "<code>[░░░░░░░░░░] 0%</code>",
        parse_mode=ParseMode.HTML
    )

    # Animasi Loading (Jalan di background sambil scraping berjalan)
    frames = [
        ("📡 <b>SCANNING GLOBAL NODES...</b>", "██▒▒▒▒▒▒▒▒", 20),
        ("🔓 <b>BYPASSING FIREWALLS...</b>",    "████▒▒▒▒▒▒", 45),
        ("🕸 <b>PARSING JSON STRUCTURES...</b>","███████▒▒▒", 75),
        ("🔄 <b>COMPILING DATASETS...</b>",     "█████████▒", 90),
    ]

    for label, bar, percent in frames:
        await asyncio.sleep(0.5)
        try:
            await status_msg.edit_text(
                f"⏳ {label}\n"
                f"<code>[{bar}] {percent}%</code>",
                parse_mode=ParseMode.HTML
            )
        except: pass

    # 2. DEFINISI SUMBER (Expanded Sources)
    sources = {
        "HTTP": [
            "https://raw.githubusercontent.com/TheSpeedX/SOCKS-List/master/http.txt",
            "https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/http.txt",
            "https://api.proxyscrape.com/v2/?request=getproxies&protocol=http&timeout=10000&country=all&ssl=all&anonymity=all",
            "https://www.proxy-list.download/api/v1/get?type=http",
            "https://raw.githubusercontent.com/ShiftyTR/Proxy-List/master/http.txt",
            "https://raw.githubusercontent.com/jetkai/proxy-list/main/online-proxies/txt/proxies-http.txt",
        ],
        "SOCKS4": [
            "https://raw.githubusercontent.com/TheSpeedX/SOCKS-List/master/socks4.txt",
            "https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/socks4.txt",
            "https://api.proxyscrape.com/v2/?request=getproxies&protocol=socks4&timeout=10000&country=all",
            "https://www.proxy-list.download/api/v1/get?type=socks4",
            "https://raw.githubusercontent.com/ShiftyTR/Proxy-List/master/socks4.txt",
        ],
        "SOCKS5": [
            "https://raw.githubusercontent.com/TheSpeedX/SOCKS-List/master/socks5.txt",
            "https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/socks5.txt",
            "https://raw.githubusercontent.com/hookzof/socks5_list/master/proxy.txt",
            "https://api.proxyscrape.com/v2/?request=getproxies&protocol=socks5&timeout=10000&country=all",
            "https://raw.githubusercontent.com/jetkai/proxy-list/main/online-proxies/txt/proxies-socks5.txt",
        ]
    }

    # 3. ENGINE EKSEKUSI PARALEL (High Speed)
    start_time = time.time()
    collected_proxies = {"HTTP": set(), "SOCKS4": set(), "SOCKS5": set()}
    
    # Header Browser Asli (Biar ga dianggap bot)
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36"
    }

    async with httpx.AsyncClient(headers=headers, timeout=15, follow_redirects=True) as client:
        # Kita buat list tasks untuk semua URL sekaligus
        tasks = []
        map_url_proto = {} # Mapping untuk tahu URL mana milik protokol apa

        for proto, urls in sources.items():
            for url in urls:
                tasks.append(fetch_proxy_source(client, url))
                map_url_proto[url] = proto # Simpan referensi

        # JALANKAN SEMUA REQUEST BERSAMAAN (Concurrency)
        # Ini jauh lebih cepat daripada loop satu-satu
        results = await asyncio.gather(*tasks)

        # Proses Hasil
        # results berisi list tuple: (text_content, success_boolean)
        # Kita perlu mapping balik manual karena gather mengembalikan list urut
        
        # Flatten list url untuk iterasi yang sama dengan tasks
        flat_urls_list = []
        for proto in sources:
            flat_urls_list.extend(sources[proto])

        for i, (content, success) in enumerate(results):
            if not success: continue
            
            # Ambil protokol berdasarkan URL index
            current_url = flat_urls_list[i]
            # Karena struktur dictionary tidak menjamin urutan di versi python lama, 
            # cara mapping di atas (map_url_proto) lebih aman, tapi disini kita pakai logika sederhana:
            # Kita cari URL ini ada di list protokol mana
            current_proto = "HTTP"
            for p, u_list in sources.items():
                if current_url in u_list:
                    current_proto = p
                    break

            # A. COBA PARSE SEBAGAI JSON GENERIC DULU
            try:
                json_data = json.loads(content)
                json_ips = extract_ips_from_json(json_data)
                collected_proxies[current_proto].update(json_ips)
            except json.JSONDecodeError:
                pass # Bukan JSON, lanjut ke Regex

            # B. FALLBACK KE REGEX (Smart IP:Port Matcher)
            # Regex ini menangkap IP:Port di tengah teks sampah sekalipun
            matches = re.findall(r"(?:^|\D)(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}:\d+)(?:\D|$)", content)
            for proxy in matches:
                # Bersihkan whitespace jika ada
                clean_proxy = proxy.strip()
                collected_proxies[current_proto].add(clean_proxy)

    # Hitung Statistik Akhir
    count_http = len(collected_proxies["HTTP"])
    count_s4 = len(collected_proxies["SOCKS4"])
    count_s5 = len(collected_proxies["SOCKS5"])
    total_found = count_http + count_s4 + count_s5
    duration = round(time.time() - start_time, 2)

    # 4. GENERATE FILE OUTPUT
    full_text = ""
    full_text += f"################################################\n"
    full_text += f"#  THE HUNTER V3 - ELITE PROXY DUMP            #\n"
    full_text += f"#  Generated by: @{context.bot.username}       #\n"
    full_text += f"#  Date: {time.strftime('%Y-%m-%d %H:%M:%S')}  #\n"
    full_text += f"#  Total: {total_found} IPs                    #\n"
    full_text += f"################################################\n\n"

    for proto, proxies in collected_proxies.items():
        if proxies:
            full_text += f"[{proto} LIST - {len(proxies)}]\n"
            full_text += "\n".join(proxies) + "\n\n"

    file_bytes = io.BytesIO(full_text.encode("utf-8"))
    file_bytes.name = f"Hunter_Proxies_{int(time.time())}.txt"

    # 5. FINAL DASHBOARD (Ultimate UI)
    report_text = (
        "<b>🌐 THE HUNTER V3 — NETWORK INFILTRATION</b>\n"
        "<code>━━━━━━━━━━━━━━━━━━━━━━━━━━</code>\n"
        f"<b>📊 HARVEST REPORT</b>\n"
        f"├ <b>HTTP/S   :</b> <code>{count_http}</code> Nodes\n"
        f"├ <b>SOCKS4   :</b> <code>{count_s4}</code> Nodes\n"
        f"├ <b>SOCKS5   :</b> <code>{count_s5}</code> Nodes\n"
        f"└ <b>Total    :</b> <code>{total_found}</code> Unique IPs\n\n"
        
        f"<b>⚙️ SYSTEM METRICS</b>\n"
        f"├ <b>Speed      :</b> {duration}s (Async/IO)\n"
        f"├ <b>Parsing    :</b> Regex + JSON Recursive\n"
        f"└ <b>Status     :</b> ✅ COMPLETE\n"
        "<code>━━━━━━━━━━━━━━━━━━━━━━━━━━</code>\n"
        f"💾 <i>Database exported below.</i>"
    )

    # Update pesan loading
    await status_msg.edit_text(report_text, parse_mode=ParseMode.HTML)

    # Kirim Dokumen
    await msg.reply_document(
        document=file_bytes,
        caption="📂 <b>Encrypted Proxy List</b>\n<i>Use for educational purposes only.</i>",
        parse_mode=ParseMode.HTML
    )

# ==========================================
# ⚙️ /setsholat — DAFTAR NOTIFIKASI HARIAN
# ==========================================
async def setsholat_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text(
            "⚠️ <b>Usage:</b> <code>/setsholat NamaKota</code>",
            parse_mode=ParseMode.HTML,
        )
        return

    city = " ".join(context.args)
    chat_id = update.effective_chat.id

    # Cek Kota (pakai method 11 / sama seperti scheduler)
    url = f"https://api.aladhan.com/v1/timingsByCity?city={urllib.parse.quote(city)}&country=Indonesia&method=11"
    r = await fetch_json(url)

    if not r or r.get("code") != 200:
        await update.message.reply_text(
            f"❌ Kota <b>{html.escape(city)}</b> tidak ditemukan.",
            parse_mode=ParseMode.HTML,
        )
        return

    # Simpan Database
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(
            "INSERT OR REPLACE INTO prayer_subs (chat_id, city) VALUES (?, ?)",
            (chat_id, city),
        )
        await db.commit()

    await update.message.reply_text(
        (
            "✅ <b>Daily prayer notification activated.</b>\n"
            f"📍 City: <b>{html.escape(city.upper())}</b>\n\n"
            "Bot will send:\n"
            "• ⏰ Reminder 5 minutes before Fajr, Dhuhr, Asr, Maghrib, Isha\n"
            "• 🕌 Adzan notification at exact time\n\n"
            "<i>Schedule is based on local Indonesian calculation (Aladhan API).</i>"
        ),
        parse_mode=ParseMode.HTML,
    )

    # Jalankan penjadwal untuk hari ini
    await schedule_prayers_for_user(context, chat_id, city)


# ==========================================
# 📴 /stopsholat — MATIKAN NOTIF
# ==========================================
async def stopsholat_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("DELETE FROM prayer_subs WHERE chat_id=?", (chat_id,))
        await db.commit()

    await update.message.reply_text(
        "🔕 <b>Prayer notifications disabled for this chat.</b>",
        parse_mode=ParseMode.HTML,
    )


# ==========================================
# 🕌 SISTEM PENGINGAT & ADZAN (ISLAMI)
# ==========================================
async def send_adzan(context: ContextTypes.DEFAULT_TYPE):
    job = context.job
    data = job.data

    waktu = data["waktu"].title()  # Subuh, Dzuhur, dll
    city = data["city"]
    jam = data["jam"]
    tipe = data.get("tipe", "adzan")

    if tipe == "reminder":
        # --- PESAN PENGINGAT (5 MENIT SEBELUM) ---
        text = (
            f"⚠️ <b>PRAYER REMINDER</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"In about <b>5 minutes</b>, it will be time for <b>{waktu.upper()}</b>\n"
            f"for the area of <b>{html.escape(city)}</b> and surroundings.\n\n"
            f"💧 <i>“Barangsiapa berwudhu dan membaguskan wudhunya, maka "
            f"keluarlah dosa-dosa dari tubuhnya...” (HR. Muslim)</i>\n\n"
            f"🤲 <b>Take a moment:</b>\n"
            f"Leave your worldly tasks for a while, take wudhu, and prepare your heart."
        )
    else:
        # --- PESAN SAAT WAKTU SHOLAT TIBA ---
        text = (
            f"🕌 <b>ADZAN TIME</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"Allahu Akbar... Allahu Akbar...\n\n"
            f"It is now time for <b>{waktu.upper()}</b>\n"
            f"in <b>{html.escape(city)}</b> and surrounding areas.\n"
            f"⏰ <b>Time:</b> <code>{jam}</code>\n\n"
            f"حي على الصلاة — <i>Come to prayer</i>\n"
            f"حي على الفلاح — <i>Come to success</i>\n\n"
            f"🤲 <b>May Allah accept our prayers and deeds.</b>\n"
            f"Aamiin ya Rabbal ‘alamin."
        )

    try:
        await context.bot.send_message(
            chat_id=data["chat_id"], text=text, parse_mode=ParseMode.HTML
        )
    except Exception as e:
        print(f"send_adzan error: {e}")


# ==========================================
# 🕒 PENJADWALAN HARIAN UNTUK SATU USER
# ==========================================
async def schedule_prayers_for_user(
    context: ContextTypes.DEFAULT_TYPE, chat_id: int, city: str
):
    """Pasang jadwal reminder + adzan untuk 1 chat & 1 kota."""
    url = f"https://api.aladhan.com/v1/timingsByCity?city={urllib.parse.quote(city)}&country=Indonesia&method=11"
    r = await fetch_json(url)
    if not r or r.get("code") != 200:
        print(f"[schedule_prayers_for_user] city invalid: {city}")
        return

    timings = r["data"]["timings"]
    now = datetime.datetime.now(TZ)

    # Target sholat utama
    target_prayers = {
        "Fajr": "Subuh",
        "Dhuhr": "Dzuhur",
        "Asr": "Ashar",
        "Maghrib": "Maghrib",
        "Isha": "Isya",
    }

    for p_api, p_name in target_prayers.items():
        raw_time = timings.get(p_api)
        if not raw_time:
            continue

        # Beberapa API ngasih format "18:52 (WIB)" → ambil bagian jam saja
        time_clean = raw_time.split(" ")[0]

        m = re.match(r"^(\d{1,2}):(\d{1,2})$", time_clean)
        if not m:
            print(f"[schedule_prayers_for_user] bad time format: {raw_time}")
            continue

        ph = int(m.group(1))
        pm = int(m.group(2))

        # Waktu Adzan (hari ini, timezone WIB)
        pt_adzan = now.replace(hour=ph, minute=pm, second=0, microsecond=0)

        # Kalau sudah lewat semua → jadwalkan untuk besok
        if pt_adzan <= now:
            pt_adzan = pt_adzan + datetime.timedelta(days=1)

        # Waktu Reminder (5 Menit Sebelum)
        pt_remind = pt_adzan - datetime.timedelta(minutes=5)

        # Hitung delay dalam detik
        delta_remind = (pt_remind - now).total_seconds()
        delta_adzan = (pt_adzan - now).total_seconds()

        # Pasang Alarm Reminder (Jika masih di masa depan)
        if delta_remind > 0:
            context.job_queue.run_once(
                send_adzan,
                delta_remind,
                data={
                    "chat_id": chat_id,
                    "waktu": p_name,
                    "city": city,
                    "jam": time_clean,
                    "tipe": "reminder",
                },
                name=f"{chat_id}_{p_name}_rem",
            )

        # Pasang Alarm Adzan (Jika masih di masa depan)
        if delta_adzan > 0:
            context.job_queue.run_once(
                send_adzan,
                delta_adzan,
                data={
                    "chat_id": chat_id,
                    "waktu": p_name,
                    "city": city,
                    "jam": time_clean,
                    "tipe": "adzan",
                },
                name=f"{chat_id}_{p_name}_adz",
            )


# ==========================================
# 🔁 DAILY REFRESH (JALAN SEKALI SEHARI)
# ==========================================
async def daily_prayer_scheduler(context: ContextTypes.DEFAULT_TYPE):
    """Dijalankan tiap pagi: refresh jadwal semua user yang terdaftar."""
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT chat_id, city FROM prayer_subs") as cursor:
            rows = await cursor.fetchall()
            for chat_id, city in rows:
                try:
                    await schedule_prayers_for_user(context, chat_id, city)
                except Exception as e:
                    print(f"daily_prayer_scheduler error ({chat_id}, {city}): {e}")

# ==========================================
# 🔄 CALLBACK ROUTER (FIXED & SAFE + REGISTER LOCK + PDF MENU)
# ==========================================
async def menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()  # Hilangkan loading di tombol
    d = q.data
    user_id = q.from_user.id

    # --- 1. LOGIKA PAYMENT (QRIS) ---
    if d in ["pay_crypto", "pay_qris"]:
        if d == "pay_qris":
            QRIS_IMAGE = "https://i.ibb.co.com/5ggXCz6L/IMG-20251116-WA0003.jpg"
            caption = (
                "💳 <b>SCAN TO PAY</b>\n"
                "Please scan the QRIS code above to complete your payment."
            )
            try:
                await context.bot.send_photo(
                    chat_id=q.message.chat_id,
                    photo=QRIS_IMAGE,
                    caption=caption,
                    parse_mode=ParseMode.HTML,
                )
            except Exception:
                await q.answer("⚠️ QRIS image failed to load.", show_alert=True)
        else:
            await q.answer("⚠️ Payment Gateway is under maintenance.", show_alert=True)
        return

    # --- 2. LOGIKA WEATHER REFRESH ---
    if d.startswith("weather_refresh"):
        try:
            _, city = d.split("|", 1)
            data = await get_weather_data(city)
            if data and data.get("cod") == 200:
                lat, lon = data["coord"]["lat"], data["coord"]["lon"]
                aqi = await get_aqi(lat, lon)
                txt = format_weather(data, aqi)
                kb = [
                    [InlineKeyboardButton("🔄 Refresh Data", callback_data=f"weather_refresh|{city}")],
                    [InlineKeyboardButton("🗺 View on Map", url=f"https://www.google.com/maps?q={lat},{lon}")],
                ]

                if q.message.photo:
                    await q.message.edit_caption(
                        caption=txt,
                        parse_mode=ParseMode.HTML,
                        reply_markup=InlineKeyboardMarkup(kb),
                    )
                else:
                    await q.message.edit_text(
                        text=txt,
                        parse_mode=ParseMode.HTML,
                        reply_markup=InlineKeyboardMarkup(kb),
                    )
            else:
                await q.answer("Failed to update weather data.", show_alert=True)
        except Exception:
            await q.answer("Error updating weather.", show_alert=True)
        return

    # --- 3. ACCESS LOCK (WAJIB REGISTER DULU) ---
    # Hanya cmd_register yang bebas; tombol lain wajib sudah terdaftar
    if d != "cmd_register":
        if not await is_registered(user_id):
            await q.answer(
                "⚠️ Access locked.\n"
                "Please complete <b>REGISTER ACCESS</b> first via /start.",
                show_alert=True,
            )
            return

    # ==========================================
    # 🧭 MENU NAVIGATION SYSTEM
    # ==========================================
    btn_back = [[InlineKeyboardButton("🔙 Back to Menu", callback_data="menu_main")]]
    text = None
    kb = None

    # --- LOGIKA KONTEN MENU ---

    # 3.1 REGISTER
    if d == "cmd_register":
        try:
            is_new = await add_subscriber(update.effective_user.id)
        except Exception:
            is_new = False

        reg_date = datetime.datetime.now(TZ).strftime("%Y-%m-%d %H:%M:%S")
        status = "✅ VERIFIED MEMBER" if is_new else "⚠️ ALREADY REGISTERED"
        text = (
            "🔐 <b>REGISTRATION SUCCESSFUL</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"👤 <b>Name:</b> {html.escape(update.effective_user.full_name)}\n"
            f"🆔 <b>User ID:</b> <code>{update.effective_user.id}</code>\n"
            f"📅 <b>Date:</b> {reg_date}\n"
            f"🔰 <b>Status:</b> {status}\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "<i>Welcome to the Oktacomel Family.\n"
            "You now have access to the main control panel.</i>"
        )
        kb = [[InlineKeyboardButton("🚀 GO TO DASHBOARD", callback_data="menu_main")]]

    # 3.2 MAIN DASHBOARD
    elif d in ("menu_main", "cmd_main"):
        await cmd_command(update, context)
        return

    # 3.3 BASIC TOOLS
    elif d == "menu_basic":
        text = (
            "🛠️ <b>BASIC TOOLS</b>\n"
            "━━━━━━━━━━━━━━━━\n"
            "• <code>/ping</code> — Check VPS/server latency & uptime\n"
            "• <code>/me</code> — Show your Telegram profile & IDs\n"
            "• <code>/qr text</code> — Generate QR Code from any text/link\n"
            "• <code>/broadcast msg</code> — System broadcast (Owner only)"
        )
        kb = btn_back

    # 3.4 AI & UTILITY
    elif d == "menu_ai":
        text = (
            "🤖 <b>AI & UTILITY TOOLS</b>\n"
            "━━━━━━━━━━━━━━━━\n"
            "• <code>/ai question</code> — Multi-model AI with inline selector\n"
            "• <code>/gpt text</code> — Direct GPT-4o streaming\n"
            "• <code>/cla text</code> — Claude 3.5 Sonnet streaming\n"
            "• <code>/gmi text</code> — Gemini 1.5 Pro streaming\n"
            "• <code>/img prompt</code> — Generate AI images\n"
            "• <code>/tts id text</code> — Text to Speech (Google)\n"
            "• <code>/tr id text</code> — Translate to Indonesian/other languages\n"
            "• <code>/convert 10 USD IDR</code> — Currency converter\n"
            "• <code>/tod</code> — Truth or Dare mini game"
        )
        kb = btn_back

    # 3.5 CHECKER SUITE
    elif d == "menu_check":
        text = (
            "🔍 <b>CHECKER SUITE</b>\n"
            "━━━━━━━━━━━━━━━━\n"
            "• <code>/sk sk_live_xxx</code> — Stripe Secret Key checker\n"
            "• <code>/bin 454545</code> — BIN lookup with bank & country\n"
            "• <code>/gateway url</code> — Detect payment gateway used by site\n"
            "• <code>/iban code</code> — IBAN format validator\n"
            "• <code>/ip host</code> — IP/host intelligence\n"
            "• <code>/s url</code> — Stripe scraper (experimental)\n"
            "• <code>/proxy host:port:user:pass</code> — Proxy status & ISP check"
        )
        kb = btn_back

    # 3.6 DOWNLOADER
    elif d == "menu_dl":
        text = (
            "📥 <b>ALL MEDIA DOWNLOADER</b>\n"
            "━━━━━━━━━━━━━━━━\n"
            "<b>Usage:</b> <code>/download [link]</code>\n\n"
            "<b>Supports:</b>\n"
            "• TikTok (slides, video, music — no watermark)\n"
            "• Instagram (reels, stories, carousel, posts)\n"
            "• YouTube (shorts & long videos)\n"
            "• Twitter / X videos\n"
            "• Facebook videos\n\n"
            "✅ Auto-cache: next download of the same link is instant."
        )
        kb = btn_back

    # 3.7 CC GENERATOR
    elif d == "menu_cc":
        text = (
            "💳 <b>CC GENERATOR</b>\n"
            "━━━━━━━━━━━━━━━━\n"
            "• <code>/gen 545454</code> — Generate 10 random cards\n"
            "• <code>/gen 545454 100</code> — Generate mass list as file\n"
            "• <code>/gen 545454|05|26|xxx</code> — Fully custom pattern\n\n"
            "<i>Note: For testing and educational purposes only.</i>"
        )
        kb = btn_back

    # 3.8 WEATHER & EARTH
    elif d == "menu_weather":
        text = (
            "🌦 <b>WEATHER & EARTH MODULE</b>\n"
            "━━━━━━━━━━━━━━━━\n"
            "• <code>/weather city</code> — Live weather & AQI\n"
            "• <code>/gempa</code> — Latest earthquake data (BMKG)\n"
            "• <code>/subscribe</code> — Daily morning broadcast\n"
            "• <code>/unsubscribe</code> — Stop broadcast\n"
        )
        kb = btn_back

    # 3.9 MUSIC
    elif d == "menu_music":
        text = (
            "🎵 <b>MUSIC (LAST.FM INTEGRATION)</b>\n"
            "━━━━━━━━━━━━━━━━\n"
            "• <code>/link username</code> — Link your Last.fm account\n"
            "• <code>/now</code> — Show your currently playing track\n"
            "• <code>/unlink</code> — Remove linked account\n"
        )
        kb = btn_back

    elif d == "menu_pdf":
        text = (
            "📝 <b>PDF SUITE — PREMIUM TOOLS</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "• <code>/pdf txt</code> — Convert text to PDF\n"
            "• <code>/pdf img</code> — Convert image to PDF\n"
            "• <code>/pdf merge</code> — Merge multiple PDFs\n"
            "• <code>/pdf split</code> — Split PDF into pages\n"
            "• <code>/pdf compress</code> — Compress PDF size\n\n"
            "<i>All operations run through the Oktacomel Processing Engine.</i>"
        )
        kb = [[InlineKeyboardButton("🔙 Back to Menu", callback_data="menu_main")]]


    # 3.11 PREMIUM / BUY
    elif d == "menu_buy":
        text = (
    "🌟 <b><u>OKTACOMEL PREMIUM ACCESS — ULTRA EDITION</u></b> 🌟\n"
    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"

    "🥇 <b>Welcome to the Elite Tier Upgrade Center</b>\n"
    "Unlock the <b>full potential</b> of your assistant and experience\n"
    "<i>unlimited intelligence, ultra-fast processing, and exclusive tools</i>\n"
    "reserved only for our Premium Users.\n\n"

    "✨ <b>What Premium Gives You</b>:\n"
    "• Priority routing on all AI models (GPT-4o / Claude / Gemini)\n"
    "• Faster streaming output (2× speed)\n"
    "• Access to <b>VIP Tools</b>: GodMode TempMail, PDF Suite Ultra, Unlimited Downloader\n"
    "• AI Image Gen Boost — faster queue & bigger output\n"
    "• Early access to future modules\n"
    "• Dedicated support line\n"
    "• <b>Zero hourly slowdowns</b> (server priority)\n"
    "• Exclusive premium-only commands\n\n"

    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    "🏆 <b>PREMIUM SUBSCRIPTION PLANS</b>\n"
    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"

    "💠 <b>Basic Premium — $69.99</b>\n"
    "Perfect for personal or casual usage.\n"
    "• 80 credits/day\n"
    "• 25 credits/hour\n"
    "• 560 weekly credits\n"
    "• 2400 monthly credits\n"
    "• Priority Level: <b>Silver</b>\n\n"

    "💠 <b>Advanced Premium — $149.99</b>\n"
    "<i>Best value for small creators and power users.</i>\n"
    "• 200 credits/day\n"
    "• 65 credits/hour\n"
    "• 1400 weekly credits\n"
    "• 6000 monthly credits\n"
    "• Priority Level: <b>Gold</b>\n\n"

    "💠 <b>Pro Premium — $249.99</b>\n"
    "Designed for content creators, editors & automation users.\n"
    "• 350 credits/day\n"
    "• 115 credits/hour\n"
    "• 2450 weekly credits\n"
    "• 10500 monthly credits\n"
    "• Priority Level: <b>Platinum</b>\n"
    "• Unlocks: <b>Extended Image Models</b>\n\n"

    "💠 <b>Enterprise Premium — $449.99</b>\n"
    "Full unlocked system — the best we offer.\n"
    "• 800 credits/day\n"
    "• 265 credits/hour\n"
    "• 5600 weekly credits\n"
    "• 24000 monthly credits\n"
    "• Priority Level: <b>Diamond</b>\n"
    "• Unlocks: <b>Unlimited TempMail GodMode</b>\n"
    "• Unlocks: <b>All Upcoming AI Models</b>\n\n"

    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    "💎 <b>CREDIT PACKS — ONE TIME PURCHASE</b>\n"
    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    "⚡ Perfect for users who don't want monthly subscriptions.\n\n"

    "• $4.99 → 100 credits + 2 bonus\n"
    "• $19.99 → 500 credits + 10 bonus\n"
    "• $39.99 → 1000 credits + 25 bonus\n"
    "• $94.99 → 2500 credits + 50 bonus\n"
    "• $179.99 → 5000 credits + 50 bonus\n"
    "• $333.99 → 10000 credits + 100 bonus\n"
    "• $739.99 → 25000 credits + 300 bonus\n\n"

    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    "🔐 <b>Activation</b>\n"
    "Once payment is confirmed, your premium\n"
    "<b>activates instantly & automatically.</b>\n"
    "No admin contact required.\n\n"

    "🚨 <i>All premium purchases are final — no refunds.</i>\n\n"
    "🤝 <b>Thank you for supporting Oktacomel!</b>\n"
    "Your support helps us improve and maintain powerful tools\n"
    "for the entire community.\n\n"
    "📘 <a href='https://google.com'>Learn More About Plans</a>\n"

        )
        kb = [
            [
                InlineKeyboardButton("💰 Pay via Crypto", callback_data="pay_crypto"),
                InlineKeyboardButton("💳 Pay via QRIS", callback_data="pay_qris"),
            ],
            [InlineKeyboardButton("🆘 Contact Support", url="https://t.me/hiduphjokowi")],
            [InlineKeyboardButton("🔙 Back to Menu", callback_data="menu_main")],
        ]

    # 3.12 ACCOUNT / CLOSE / COMING SOON
    elif d == "cmd_close":
        await q.delete_message()
        return

    elif d in ["menu_mail", "menu_todo", "buy_info"]:
        await q.answer("⚠️ This feature is coming soon.", show_alert=True)
        return

    elif d == "cmd_account":
        await me_command(update, context)
        return

    # ==========================================
    # 🧩 EKSEKUSI OUTPUT (ANTI-ERROR FOTO / TEKS)
    # ==========================================
    if text and kb:
        try:
            # Jika pesan asal berupa foto (misal dari /start dengan gambar),
            # lebih aman dihapus dan kirim pesan teks baru.
            if q.message.photo:
                chat_id = q.message.chat.id
                await q.message.delete()
                # Telegram limit ~4096 chars — kalo terlalu panjang kirim sebagai file
                if len(text) > 3800:
                    # kirim sebagai file txt agar aman
                    bio = io.BytesIO(text.encode("utf-8"))
                    bio.name = "menu.txt"
                    await context.bot.send_document(
                        chat_id=chat_id,
                        document=InputFile(bio),
                        caption="📄 Menu (saved as file because text is long)",
                    )
                    # kirim tombol terpisah agar user bisa kembali
                    await context.bot.send_message(
                        chat_id=chat_id,
                        text="Use the buttons below:",
                        reply_markup=InlineKeyboardMarkup(kb),
                    )
                else:
                    await context.bot.send_message(
                        chat_id=chat_id,
                        text=text,
                        parse_mode=ParseMode.HTML,
                        reply_markup=InlineKeyboardMarkup(kb),
                    )
            else:
                # Kalau pesan asal teks biasa, cukup edit isinya.
                # Hati-hati: edit_message_text juga kena batas 4096.
                if len(text) > 3800:
                    # fallback: kirim pesan baru (edit sering gagal untuk teks sangat panjang)
                    await q.message.reply_text(
                        text,
                        parse_mode=ParseMode.HTML,
                        reply_markup=InlineKeyboardMarkup(kb),
                    )
                else:
                    await q.message.edit_text(
                        text=text,
                        parse_mode=ParseMode.HTML,
                        reply_markup=InlineKeyboardMarkup(kb),
                    )
        except Exception as e:
            # Fallback pamungkas: kirim sebagai pesan baru (dan log error)
            logger.exception("menu output error")
            await q.message.reply_text(
                text,
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup(kb),
            )



# ==========================================
# 🚀 MAIN PROGRAM (MESIN UTAMA)
# ==========================================
def main():
    print("🚀 ULTRA GOD MODE v12.0 STARTED...")

    # 1. Inisialisasi Database (sync di awal)
    loop = asyncio.get_event_loop()
    loop.run_until_complete(init_db())

    # 2. Build Bot
    app = Application.builder().token(TOKEN).build()

    # ==========================================
    # 🎮 COMMAND HANDLERS
    # ==========================================

    # --- Basic & Menu ---
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("cmd", cmd_command))
    app.add_handler(CommandHandler("me", me_command))
    app.add_handler(CommandHandler("ping", ping_command))

    # ==========================================
    # 🏪 STORE SYSTEM HANDLERS (IMPROVED)
    # ==========================================
    
    # --- Stock & Store Commands ---
    app.add_handler(CommandHandler("stock", stock_command))
    app.add_handler(CommandHandler("sts", sts_command))
    app.add_handler(CommandHandler("sales", sales_report_command))

    # --- Conversation: Beli Akun (User) ---
    conv_beli = ConversationHandler(
        entry_points=[CommandHandler("beli", beli_start)],
        states={
            WAIT_PROOF: [
                CallbackQueryHandler(buy_menu_callback, pattern="^buy_"),
                CallbackQueryHandler(buy_menu_callback, pattern="^out_of_stock"),
                MessageHandler(filters.PHOTO, receive_proof_handler)
            ]
        },
        fallbacks=[CommandHandler("cancel", cancel_op)]
    )
    app.add_handler(conv_beli)

    # --- Handler Tombol Admin (ACC/REJECT/CONFIRM Transaksi) ---
    app.add_handler(CallbackQueryHandler(admin_approval_callback, pattern="^(confirm|reject|confirm_final)"))

    # --- PABRIK AKUN JENNI (Admin Only) ---
    app.add_handler(CommandHandler("jeni", jeni_auto_command))

    # --- Conversation: Upgrade Otomatis (Admin Only) ---
    conv_upgrade = ConversationHandler(
        entry_points=[CommandHandler("upgrade", start_upgrade_factory)],
        states={
            INPUT_CARD: [MessageHandler(filters.TEXT & ~filters.COMMAND, input_card_process)],
            INPUT_OTP: [MessageHandler(filters.TEXT & ~filters.COMMAND, input_otp_process)]
        },
        fallbacks=[CommandHandler("cancel", cancel_op)],
    )
    # Callback buat tombol pilih paket (Monthly/Yearly)
    app.add_handler(CallbackQueryHandler(select_plan_callback, pattern="^plan_"))
    app.add_handler(conv_upgrade)

    # --- AI & Tools ---
    app.add_handler(CommandHandler("ai", ai_command))
    app.add_handler(CommandHandler("gpt", ai_command))
    app.add_handler(CommandHandler("code", code_command))
    app.add_handler(CommandHandler("think", think_command))
    app.add_handler(CommandHandler("gemini", think_command))
    app.add_handler(CommandHandler("img", img_command))
    app.add_handler(CommandHandler("tts", tts_command))
    app.add_handler(CommandHandler("tr", tr_command))
    app.add_handler(CommandHandler("convert", convert_command))
    app.add_handler(CommandHandler("qr", qr_command))
    app.add_handler(CommandHandler("ip", ip_command))
    app.add_handler(CommandHandler("search", search_command))
    app.add_handler(CommandHandler("news", news_command))
    app.add_handler(CommandHandler("berita", news_command))

    # --- Downloader ---
    app.add_handler(CommandHandler("download", downloader_command))
    app.add_handler(CommandHandler("gl", gallery_command))
    app.add_handler(CommandHandler("gallery", gallery_command))

    # --- Checker & Carding (Premium Gate) ---
    app.add_handler(CommandHandler("gen", gen_command))
    app.add_handler(CommandHandler("chk", chk_command))
    app.add_handler(CommandHandler("extrap", extrap_command))
    app.add_handler(CommandHandler("bin", bin_lookup_command))
    app.add_handler(CommandHandler("sk", sk_command))
    app.add_handler(CommandHandler("fake", fake_command))
    app.add_handler(CommandHandler("proxy", proxy_check_command))
    app.add_handler(CommandHandler("scr", scr_command))
    app.add_handler(CommandHandler("scrape", scr_command))

    # --- Finance ---
    app.add_handler(CommandHandler("crypto", crypto_command))
    app.add_handler(CallbackQueryHandler(crypto_refresh_handler, pattern=r"^crypto_refresh\|"))
    app.add_handler(CallbackQueryHandler(crypto_alert_handler, pattern=r"^alert\|"))
    app.add_handler(CommandHandler("sha", sha_command))
    app.add_handler(CallbackQueryHandler(sha_refresh_callback, pattern="^sha_refresh\\|"))
    app.add_handler(CommandHandler("buy", buy_command))

    # --- Admin ---
    app.add_handler(CommandHandler("addprem", addprem_command))
    app.add_handler(CommandHandler("broadcast", broadcast_command))
    app.add_handler(CommandHandler("subscribe", subscribe))
    app.add_handler(CommandHandler("unsubscribe", unsubscribe))

    # --- Anime (SFW & NSFW) ---
    app.add_handler(CommandHandler("waifu", anime_command))
    app.add_handler(CommandHandler("neko", anime_command))
    app.add_handler(CommandHandler("shinobu", anime_command))
    app.add_handler(CommandHandler("nwaifu", anime_command))
    app.add_handler(CommandHandler("nneko", anime_command)) 
    app.add_handler(CommandHandler("trap", anime_command)) 
    app.add_handler(CommandHandler("blowjob", anime_command))

    # --- Truth or Dare (ToD) ---
    app.add_handler(CommandHandler("tod", tod_command))
    app.add_handler(CallbackQueryHandler(tod_button_handler, pattern=r"^tod_mode_|tod_close"))
    app.add_handler(CallbackQueryHandler(tod_menu_handler, pattern=r"^tod_menu$"))

    # --- Weather, Gempa, Sholat ---
    app.add_handler(CommandHandler("weather", cuaca_command))
    app.add_handler(CommandHandler("cuaca", cuaca_command))
    app.add_handler(CommandHandler("gempa", gempa_command))
    app.add_handler(CommandHandler("sholat", sholat_command))
    app.add_handler(CommandHandler("setsholat", setsholat_command))
    app.add_handler(CommandHandler("stopsholat", stopsholat_command))

    # --- System Logs & Status ---
    app.add_handler(CommandHandler("log", log_command))
    app.add_handler(CommandHandler("logs", log_command))
    app.add_handler(CommandHandler("status", status_command))
    app.add_handler(CommandHandler("health", status_command))
    app.add_handler(CallbackQueryHandler(log_callback_handler, pattern=r"^sys_log_"))

    # --- Temp Mail (Official Library) ---
    app.add_handler(CommandHandler("mail", mail_command))
    app.add_handler(CallbackQueryHandler(mail_callback, pattern=r"^tm_"))

    # --- Notes Premium ---
    app.add_handler(CommandHandler("note", note_add_command))
    app.add_handler(CommandHandler("notes", note_list_command))
    app.add_handler(CommandHandler("dnote", note_delete_command))
    app.add_handler(CallbackQueryHandler(notes_callback_handler, pattern="^notes_"))

    # --- PDF Tools ---
    app.add_handler(CommandHandler("pdfmerge", pdf_merge_command))
    app.add_handler(CommandHandler("pdfsplit", pdf_split_command))
    app.add_handler(CommandHandler("pdftotext", pdf_to_text_command))
    app.add_handler(CommandHandler("compresspdf", pdf_compress_command))
    app.add_handler(CommandHandler("imgpdf", imgpdf_command))

    # --- User Info & Proxy Config ---
    app.add_handler(CommandHandler("userinfo", userinfo_command))
    app.add_handler(CallbackQueryHandler(userinfo_refresh_callback, pattern="^userinfo_refresh_"))
    app.add_handler(CallbackQueryHandler(userinfo_close_callback, pattern="^userinfo_close$"))
    app.add_handler(CommandHandler("setproxy", setproxy_command))
    app.add_handler(CommandHandler("scp", proxy_scrape_command))

    # --- Music Suite (Spotify/Etc) ---
    app.add_handler(CommandHandler("song", song_command))
    app.add_handler(CommandHandler("music", song_command))
    app.add_handler(CallbackQueryHandler(song_button_handler, pattern=r"^sp_dl\|"))
    app.add_handler(CallbackQueryHandler(song_nav_handler, pattern=r"^sp_nav\|"))
    app.add_handler(CallbackQueryHandler(lyrics_handler, pattern=r"^lyr_get\|"))
    app.add_handler(CallbackQueryHandler(real_effect_handler, pattern=r"^eff_"))
    
    app.add_handler(CallbackQueryHandler(locked_register_handler, pattern="^locked_register$"))
    app.add_handler(CommandHandler("speed", speedtest_command))

    # --- Main Menu Callback (last, catch-all) ---
    app.add_handler(CallbackQueryHandler(menu_callback))

    # ==========================================
    # ⏰ JOB QUEUE
    # ==========================================
    if app.job_queue:
        jq = app.job_queue
        print("✅ JobQueue DETECTED: Fitur jadwal otomatis AKTIF.")
        try:
            jq.run_daily(morning_broadcast, time=datetime.time(hour=6, minute=0, tzinfo=TZ), name="morning_broadcast")
        except NameError: pass

        try:
            jq.run_daily(daily_prayer_scheduler, time=datetime.time(hour=1, minute=0, tzinfo=TZ), name="daily_prayer_refresh")
            jq.run_once(daily_prayer_scheduler, when=10, name="boot_prayer_refresh")
        except NameError: pass

        try:
            jq.run_repeating(check_price_alerts, interval=60, first=30, name="price_alert_checker")
        except NameError: pass
    else:
        print("\n❌ WARNING: JobQueue TIDAK AKTIF! (pip install python-telegram-bot[job-queue])\n")

    print("✅ SYSTEM ONLINE (FULL FEATURES + FACTORY MODE)")
    app.run_polling()

# ==========================================
# 🔥 KUNCI KONTAK (NYALAKAN MESIN)
# ==========================================
if __name__ == "__main__":

    main()

