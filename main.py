import discord
from discord.ext import commands
import requests
import json
import os
from dotenv import load_dotenv
from flask import Flask, request
import asyncio
import uuid
import base64
import io
from hypercorn.config import Config
from hypercorn.asyncio import serve

# --- CONFIGURAÇÕES E CARREGAMENTO DE VARIÁVEIS ---
load_dotenv()
TOKEN_DISCORD = os.getenv('TOKEN_DISCORD')
ACCESS_TOKEN_MERCADO_PAGO = os.getenv('ACCESS_TOKEN_MERCADO_PAGO')
ID_DO_SEU_SERVIDOR = 1416871057058697321
ID_CARGO_VIP = 1416905674008428674
ID_CANAL_LOGS = 1416906306404618271

# --- BOT DO DISCORD ---
intents = discord.Intents.default()
intents.members = True
intents.message_content = True
bot = commands.Bot(command_prefix="/", intents=intents)

# --- SERVIDOR WEB (FLASK) PARA RECEBER WEBHOOKS ---
app = Flask(__name__)

@app.route('/webhook/mercadopago', methods=['POST'])
def webhook_mercadopago():
    data = request.json
    if data and data.get('type') == 'payment' and data['data'].get('id'):
        payment_id = data['data']['id']
        print(f"Webhook recebido para o pagamento ID: {payment_id}")
        headers = {"Authorization": f"Bearer {ACCESS_TOKEN_MERCADO_PAGO}"}
        response = requests.get(f"https://api.mercadopago.com/v1/payments/{payment_id}", headers=headers)
        if response.status_code == 200:
            payment_data = response.json()
            if payment_data.get('status') == 'approved' and payment_data.get('external_reference'):
                user_id = int(payment_data['external_reference'])
                print(f"Pagamento aprovado para o usuário ID: {user_id}")
                asyncio.run_coroutine_threadsafe(entregar_produto(user_id, payment_data), bot.loop)
    return "OK", 200

async def entregar_produto(user_id, payment_data):
    try:
        guild = bot.get_guild(ID_DO_SEU_SERVIDOR)
        member = await guild.fetch_member(user_id)
        role = guild.get_role(ID_CARGO_VIP)
        if member and role:
            await member.add_roles(role)
            await member.send(f"✅ Pagamento confirmado! Você recebeu o cargo **{role.name}** no servidor **{guild.name}**.")
            log_channel = bot.get_channel(ID_CANAL_LOGS)
            if log_channel:
                embed = discord.Embed(title="🎉 Venda Realizada!", description=f"O usuário **{member.mention}** comprou o cargo **{role.name}**.", color=0x00ff00)
                embed.add_field(name="Valor Pago", value=f"R$ {payment_data.get('transaction_amount', 'N/A')}")
                embed.add_field(name="ID do Pagamento", value=payment_data.get('id', 'N/A'))
                embed.set_footer(text=f"ID do Usuário: {user_id}")
                await log_channel.send(embed=embed)
    except Exception as e:
        print(f"Ocorreu um erro ao entregar o produto para o usuário {user_id}: {e}")

# --- COMANDOS DO BOT ---
@bot.event
async def on_ready():
    print(f'Bot {bot.user} está online e pronto!')
    await bot.tree.sync()

@bot.tree.command(name="comprar", description="Gera um pagamento Pix para adquirir o acesso VIP.")
async def comprar(interaction: discord.Interaction):
    WEBHOOK_URL = "https://neoBot.up.railway.app/webhook/mercadopago" # Lembre-se de colocar sua URL aqui
    
    payload = {
        "transaction_amount": 1.00, "description": "Acesso VIP no Servidor", "payment_method_id": "pix",
        "notification_url": WEBHOOK_URL, "external_reference": str(interaction.user.id),
        "payer": {"email": f"{interaction.user.id}@discord.com", "first_name": interaction.user.name}
    }
    headers = {
        "Authorization": f"Bearer {ACCESS_TOKEN_MERCADO_PAGO}", "Content-Type": "application/json",
        "X-Idempotency-Key": str(uuid.uuid4())
    }
    response = requests.post("https://api.mercadopago.com/v1/payments", data=json.dumps(payload), headers=headers)
    if response.status_code == 201:
        data = response.json()
        qr_code_base64 = data['point_of_interaction']['transaction_data']['qr_code_base64']
        qr_code_text = data['point_of_interaction']['transaction_data']['qr_code']
        image_data = base64.b64decode(qr_code_base64)
        image_file = io.BytesIO(image_data)
        discord_file = discord.File(fp=image_file, filename="qr_code.png")
        embed = discord.Embed(title="✨ Pagamento VIP via Pix", description="Para concluir a compra, escaneie o QR Code abaixo com o app do seu banco ou use o 'Copia e Cola'.", color=0x3498db)
        embed.set_image(url="attachment://qr_code.png")
        embed.set_footer(text="Após o pagamento, você receberá seu cargo automaticamente.")
        await interaction.response.send_message(embed=embed, file=discord_file, ephemeral=True)
        await interaction.followup.send(f"**Pix Copia e Cola:**\n```{qr_code_text}```", ephemeral=True)
    else:
        print("Erro na API do Mercado Pago:", response.text)
        await interaction.response.send_message("❌ Desculpe, ocorreu um erro ao gerar seu pagamento. Tente novamente mais tarde.", ephemeral=True)

# --- INICIALIZAÇÃO DE DEBUG ---
async def main():
    print("[DEBUG] Etapa 1: Função main iniciada.")
    if not TOKEN_DISCORD:
        print("[ERRO FATAL] TOKEN_DISCORD não encontrado nas Variables! Parando.")
        return

    print("[DEBUG] Etapa 2: TOKEN_DISCORD encontrado.")
    
    port = int(os.environ.get("PORT", 8080))
    config = Config()
    config.bind = [f"0.0.0.0:{port}"]
    print(f"[DEBUG] Etapa 3: Servidor web configurado para rodar na porta {port}.")
    
    print("[DEBUG] Etapa 4: Preparando para iniciar bot.start e serve com asyncio.gather.")
    try:
        # Roda o bot e o servidor web ao mesmo tempo
        await asyncio.gather(
            bot.start(TOKEN_DISCORD),
            serve(app, config)
        )
    except discord.errors.LoginFailure:
        print("[ERRO FATAL] Falha no login. O TOKEN_DISCORD está incorreto ou foi revogado.")
    except Exception as e:
        print(f"[ERRO FATAL] Uma exceção ocorreu durante o asyncio.gather: {e}")

if __name__ == '__main__':
    print("[DEBUG] Ponto de entrada: Bloco __main__ executado.")
    try:
        asyncio.run(main())
    except Exception as e:
        print(f"[ERRO FATAL] Uma exceção geral foi capturada no __main__: {e}")
