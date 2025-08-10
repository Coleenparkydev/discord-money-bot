import discord
from discord.ext import commands
import sqlite3
from datetime import datetime, timedelta
import asyncio
import os
from threading import Thread
from http.server import HTTPServer, BaseHTTPRequestHandler

# Simple HTTP server for health checks
class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/plain')
        self.end_headers()
        self.wfile.write(b'Bot is alive!')
    
    def log_message(self, format, *args):
        pass  # Suppress server logs

def run_health_server():
    port = int(os.environ.get('PORT', 8000))
    server = HTTPServer(('0.0.0.0', port), HealthHandler)
    server.serve_forever()

# Bot setup
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

# Constants
MONEY_PER_MESSAGE = 5
DAILY_LIMIT = 300

class MoneyBot:
    def __init__(self):
        self.init_database()
    
    def init_database(self):
        """Initialize the SQLite database"""
        conn = sqlite3.connect('money_bot.db')
        cursor = conn.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                wallet_money INTEGER DEFAULT 0,
                daily_earned INTEGER DEFAULT 0,
                last_earn_date TEXT DEFAULT ""
            )
        ''')
        
        conn.commit()
        conn.close()
    
    def get_user_data(self, user_id):
        """Get user's money data from database"""
        conn = sqlite3.connect('money_bot.db')
        cursor = conn.cursor()
        
        cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
        result = cursor.fetchone()
        
        if not result:
            # Create new user
            cursor.execute('''
                INSERT INTO users (user_id, wallet_money, daily_earned, last_earn_date)
                VALUES (?, 0, 0, "")
            ''', (user_id,))
            conn.commit()
            result = (user_id, 0, 0, "")
        
        conn.close()
        return result
    
    def update_user_data(self, user_id, wallet=None, daily_earned=None, last_date=None):
        """Update user's money data"""
        conn = sqlite3.connect('money_bot.db')
        cursor = conn.cursor()
        
        # Get current data first
        current = self.get_user_data(user_id)
        
        # Use provided values or keep current ones
        new_wallet = wallet if wallet is not None else current[1]
        new_daily = daily_earned if daily_earned is not None else current[2]
        new_date = last_date if last_date is not None else current[3]
        
        cursor.execute('''
            UPDATE users 
            SET wallet_money = ?, daily_earned = ?, last_earn_date = ?
            WHERE user_id = ?
        ''', (new_wallet, new_daily, new_date, user_id))
        
        conn.commit()
        conn.close()
    
    def can_earn_money(self, user_id):
        """Check if user can earn money today"""
        user_data = self.get_user_data(user_id)
        today = datetime.now().strftime("%Y-%m-%d")
        
        # If it's a new day, reset daily earnings
        if user_data[3] != today:
            self.update_user_data(user_id, daily_earned=0, last_date=today)
            return True
        
        # Check if under daily limit
        return user_data[2] < DAILY_LIMIT
    
    def add_money(self, user_id):
        """Add money to user's wallet if under daily limit"""
        if not self.can_earn_money(user_id):
            return False
        
        user_data = self.get_user_data(user_id)
        today = datetime.now().strftime("%Y-%m-%d")
        
        new_wallet = user_data[1] + MONEY_PER_MESSAGE
        new_daily = user_data[2] + MONEY_PER_MESSAGE
        
        self.update_user_data(user_id, wallet=new_wallet, daily_earned=new_daily, last_date=today)
        return True

# Initialize the money system
money_system = MoneyBot()

@bot.event
async def on_ready():
    print(f'{bot.user} has connected to Discord!')
    print('Money & Banking Bot is ready!')

@bot.event
async def on_message(message):
    # Don't respond to bot messages
    if message.author.bot:
        return
    
    # Process commands first (this prevents earning money from commands)
    await bot.process_commands(message)
    
    # Don't give money for messages in #money channel
    if message.channel.name.lower() == "money":
        return
    
    # Don't give money for command messages (messages starting with !)
    if message.content.startswith('!'):
        return
    
    # Add money for regular messages in other channels
    money_system.add_money(message.author.id)

@bot.command(name='balance', aliases=['bal', 'money'])
async def balance(ctx):
    """Check your wallet balance (only works in #money channel)"""
    # Check if command is used in "money" channel
    if ctx.channel.name.lower() != "money":
        await ctx.send("❌ This command can only be used in the #money channel!")
        return
    
    user_data = money_system.get_user_data(ctx.author.id)
    wallet = user_data[1]
    daily_earned = user_data[2]
    
    embed = discord.Embed(title=f"💰 {ctx.author.display_name}'s Wallet", color=0x00ff00)
    embed.add_field(name="🪙 Balance", value=f"${wallet:,}", inline=True)
    embed.add_field(name="📅 Daily Progress", value=f"${daily_earned}/{DAILY_LIMIT}", inline=True)
    
    await ctx.send(embed=embed)

@bot.command(name='help_money', aliases=['money_help'])
async def help_money(ctx):
    """Show money system help"""
    embed = discord.Embed(title="💰 Money System Commands", color=0xffd700)
    embed.description = "Earn $5 for every message you send (up to $300/day)!"
    
    embed.add_field(name="!balance", value="Check your wallet balance (only in #money channel)", inline=False)
    embed.add_field(name="Rules", value="• No money earned in #money channel\n• No money for using commands\n• Only regular chat messages earn $5", inline=False)
    
    embed.set_footer(text="💡 Tip: Just keep chatting in other channels to earn money!")
    
    await ctx.send(embed=embed)

# Get token from environment variable for security
if __name__ == "__main__":
    TOKEN = os.getenv('DISCORD_TOKEN')
    if not TOKEN:
        print("Error: DISCORD_TOKEN environment variable not set!")
        exit(1)
    
    # Start health check server in background
    health_thread = Thread(target=run_health_server, daemon=True)
    health_thread.start()
    print("Health server started on port", os.environ.get('PORT', 8000))
    
    # Start the Discord bot
    bot.run(TOKEN)
