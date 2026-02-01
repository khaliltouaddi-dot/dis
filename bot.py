import discord
from discord.ext import commands
from discord.ui import View, Select, Button
import os
import asyncio

# ====================== CONFIG ======================
intents = discord.Intents.all()
bot = commands.Bot(command_prefix="+", intents=intents)

TICKET_CATEGORY_NAME = "Tickets"

TICKET_CATEGORIES = {
    "Middleman": {"emoji": "💰", "role": "Middleman Trusted", "description": "Expliquez clairement votre trade."},
    "Owner": {"emoji": "🛡️", "role": "Gestion Owner", "description": "Problème important, un Owner va vous répondre."},
    "Partenariat": {"emoji": "🤝", "role": "Gérant partenariat", "description": "Merci de détailler votre demande de partenariat."},
    "Abuse": {"emoji": "🚨", "role": "Gestion abuse", "description": "Décrivez précisément l'abus rencontré."},
}

claimed_tickets = {}  # {ticket_channel_id: staff_user_name}

# ====================== UTILITAIRES ======================
def is_ticket(channel):
    return channel.category is not None and channel.category.name == TICKET_CATEGORY_NAME

def has_ticket_role(member, channel):
    for role in channel.overwrites:
        if role != channel.guild.default_role and role in member.roles:
            return True
    return False

# ====================== PANEL ======================
@bot.command()
@commands.has_permissions(administrator=True)
async def setuppanel(ctx):
    guild = ctx.guild
    category = discord.utils.get(guild.categories, name=TICKET_CATEGORY_NAME)
    if not category:
        category = await guild.create_category(TICKET_CATEGORY_NAME)

    embed = discord.Embed(
        title="📄 Centre de Support",
        description="Besoin d'aide ? Sélectionnez la catégorie ci-dessous.",
        color=0x2f3136
    )

    for name, info in TICKET_CATEGORIES.items():
        role = discord.utils.get(guild.roles, name=info["role"])
        role_mention = role.mention if role else f"@{info['role']}"
        embed.add_field(
            name=f"{info['emoji']} {name}",
            value=f"{info['description']}\nRôle pingable : {role_mention}",
            inline=False
        )

    embed.set_footer(text="⚡ Merci de ne pas ouvrir plusieurs tickets.")
    view = TicketMenu()
    await ctx.send(embed=embed, view=view)
    await ctx.message.delete()
    await ctx.send(f"✅ Panel envoyé par {ctx.author.mention}", delete_after=10)

# ====================== MENU ======================
class TicketMenu(View):
    def __init__(self):
        super().__init__(timeout=None)
        options = [
            discord.SelectOption(
                label=name,
                description=info["description"][:100],
                emoji=info["emoji"]
            )
            for name, info in TICKET_CATEGORIES.items()
        ]
        self.add_item(TicketSelect(options=options))

class TicketSelect(Select):
    def __init__(self, options):
        super().__init__(
            placeholder="Sélectionnez la catégorie...",
            min_values=1,
            max_values=1,
            options=options
        )

    async def callback(self, interaction: discord.Interaction):
        guild = interaction.guild
        category_name = self.values[0]
        category = discord.utils.get(guild.categories, name=TICKET_CATEGORY_NAME)

        for channel in category.text_channels:
            if channel.name.startswith(f"ticket-{interaction.user.id}"):
                await interaction.response.send_message(
                    "⚠️ Vous avez déjà un ticket ouvert !",
                    ephemeral=True
                )
                return

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            interaction.user: discord.PermissionOverwrite(read_messages=True, send_messages=True)
        }

        role_name = TICKET_CATEGORIES[category_name]["role"]
        role = discord.utils.get(guild.roles, name=role_name)
        if role:
            overwrites[role] = discord.PermissionOverwrite(read_messages=True, send_messages=True)

        ticket_channel = await guild.create_text_channel(
            name=f"ticket-{interaction.user.id}",
            category=category,
            overwrites=overwrites
        )

        embed = discord.Embed(
            title=f"🎫 Ticket {category_name}",
            description=(
                f"{interaction.user.mention}, bienvenue ! "
                f"Un membre du support **{category_name}** va vous répondre bientôt."
            ),
            color=0x00ff00
        )

        view = ClaimButton(role, interaction.user.id)
        await ticket_channel.send(
            content=f"{role.mention if role else ''}",
            embed=embed,
            view=view
        )

        await interaction.response.send_message(
            f"✅ Ticket créé : {ticket_channel.mention}",
            ephemeral=True
        )

# ====================== BOUTON CLAIM ======================
class ClaimButton(View):
    def __init__(self, role, creator_id):
        super().__init__(timeout=None)
        self.add_item(Claim(role, creator_id))

class Claim(Button):
    def __init__(self, role, creator_id):
        super().__init__(label="Claim", style=discord.ButtonStyle.green)
        self.role = role
        self.creator_id = creator_id

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id == self.creator_id:
            await interaction.response.send_message(
                "⚠️ Vous ne pouvez pas claim votre propre ticket !",
                ephemeral=True
            )
            return

        if self.role and self.role not in interaction.user.roles:
            await interaction.response.send_message(
                "⚠️ Seuls les membres du staff peuvent claim.",
                ephemeral=True
            )
            return

        claimed_tickets[interaction.channel.id] = interaction.user.name
        await interaction.response.send_message(
            f"✅ {interaction.user.mention} a pris en charge le ticket !"
        )

# ====================== COMMANDES ======================
async def staff_only(ctx):
    if not is_ticket(ctx.channel):
        await ctx.send("⚠️ Ce salon n'est pas un ticket.")
        return False

    if has_ticket_role(ctx.author, ctx.channel):
        overwrites = ctx.channel.overwrites
        if ctx.author.id in [u.id for u, perm in overwrites.items() if perm.read_messages]:
            if not any(role for role in ctx.author.roles if role in overwrites):
                await ctx.send("⚠️ Vous n'avez pas la permission d'utiliser cette commande.")
                return False
        return True

    await ctx.send("⚠️ Vous n'avez pas la permission d'utiliser cette commande.")
    return False

@bot.command()
async def add(ctx, member: discord.Member):
    if not await staff_only(ctx):
        return
    await ctx.channel.set_permissions(member, read_messages=True, send_messages=True)
    await ctx.send(f"{member.mention} a été ajouté au ticket.")

@bot.command()
async def rename(ctx, *, new_name):
    if not await staff_only(ctx):
        return
    await ctx.channel.edit(name=new_name.lower())
    await ctx.send(f"Le ticket a été renommé en : {new_name}")

@bot.command()
async def fermer(ctx):
    if not await staff_only(ctx):
        return
    await ctx.send("⏳ Le ticket sera supprimé dans 5 secondes...")
    await asyncio.sleep(5)
    await ctx.channel.delete()

# ====================== LANCEMENT ======================
TOKEN = os.getenv("DISCORD_TOKEN")

if not TOKEN:
    raise ValueError("❌ DISCORD_TOKEN manquant dans les variables d'environnement.")

bot.run(TOKEN)
