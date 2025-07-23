from flask import Flask, request
import telebot
import os
import random
import json
import threading
import time
from datetime import datetime

### 🔐 INÍCIO DAS CONFIGURAÇÕES GERAIS - NÃO ALTERAR SEM CONHECIMENTO 🔐
GRUPO_ID = -1002363575666
DONO_ID = 1481389775
TOKEN = os.getenv("TELEGRAM_TOKEN")
RENDER_URL = os.getenv("RENDER_EXTERNAL_URL")
PERGUNTAS_PATH = "perguntas.json"
RANKING_PATH = "ranking.json"

bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)
respostas_pendentes = {}
perguntas_feitas = []
ultimo_pedido_membro = 0  # Timestamp do último pedido de novo desafio por um membro
### 🔐 FIM DAS CONFIGURAÇÕES GERAIS 🔐

# 🔐 CARREGAMENTO DOS ARQUIVOS (RANKING E PERGUNTAS FEITAS)
try:
    perguntas = json.load(open(PERGUNTAS_PATH, encoding="utf-8"))
except:
    perguntas = []
try:
    ranking = json.load(open(RANKING_PATH, encoding="utf-8"))
except:
    ranking = {}

def salvar_ranking():
    with open(RANKING_PATH, "w", encoding="utf-8") as f:
        json.dump(ranking, f, ensure_ascii=False, indent=2)

def salvar_perguntas_feitas():
    with open("perguntas_feitas.json", "w", encoding="utf-8") as f:
        json.dump(perguntas_feitas, f)

def carregar_perguntas_feitas():
    global perguntas_feitas
    try:
        with open("perguntas_feitas.json", "r", encoding="utf-8") as f:
            perguntas_feitas = json.load(f)
    except:
        perguntas_feitas = []

# 🔐 LÓGICA PARA ESCOLHER PERGUNTA QUE NÃO SE REPITA EM 5 DIAS

def escolher_pergunta():
    agora = time.time()
    ultimos_5_dias = agora - (5 * 86400)
    recentes = [p for p in perguntas_feitas if p["tempo"] > ultimos_5_dias]
    ids_recentes = [p["id"] for p in recentes]
    candidatas = [p for p in perguntas if p["id"] not in ids_recentes]
    if not candidatas:
        return None
    return random.choice(candidatas)

# 🌐 ENVIA UMA NOVA PERGUNTA PARA O GRUPO
def mandar_pergunta():
    hora = datetime.now().hour
    if not (6 <= hora <= 23):
        return

    pergunta = escolher_pergunta()
    if not pergunta:
        return

    pid = str(time.time())
    respostas_pendentes[pid] = {"pergunta": pergunta, "respostas": {}}

    markup = telebot.types.InlineKeyboardMarkup()
    for i, opc in enumerate(pergunta["opcoes"]):
        markup.add(telebot.types.InlineKeyboardButton(opc, callback_data=f"{pid}|{i}"))

    # 📋 Remove a penúltima pergunta enviada
    try:
        bot.delete_message(GRUPO_ID, respostas_pendentes["ultimo_id"])
    except:
        pass

    msg = bot.send_message(GRUPO_ID, f"❓ *Pergunta:* {pergunta['pergunta']}", parse_mode="Markdown", reply_markup=markup)
    respostas_pendentes["ultimo_id"] = msg.message_id

    # 🔹 Botão adicional de novo desafio
    botao_markup = telebot.types.InlineKeyboardMarkup()
    botao_markup.add(telebot.types.InlineKeyboardButton("🧠 Novo desafio", callback_data="pedir_nova_pergunta"))
    bot.send_message(GRUPO_ID, "_Se quiser mais uma pergunta, toque abaixo!_", parse_mode="Markdown", reply_markup=botao_markup)

    perguntas_feitas.append({"id": pergunta["id"], "tempo": time.time()})
    salvar_perguntas_feitas()

    timer = threading.Timer(450, revelar_resposta, args=[pid])
    respostas_pendentes[pid]["timer"] = timer
    timer.start()

# 🔎 COMANDO /forcar
@bot.message_handler(commands=["forcar"])
def forcar_pergunta(m):
    if m.from_user.id != DONO_ID:
        return bot.reply_to(m, "Você não tem permissão pra isso.")

    if respostas_pendentes:
        pid_ativo = next(iter(respostas_pendentes))
        if pid_ativo != "ultimo_id":
            bot.send_message(GRUPO_ID, "⏳ Enviando resposta da pergunta anterior...")
            revelar_resposta(pid_ativo)

    bot.send_message(GRUPO_ID, "🚨 Enviando nova pergunta agora!")
    mandar_pergunta()

# 🔹 CLIQUE NA RESPOSTA
@bot.callback_query_handler(func=lambda c: "|" in c.data)
def responder_quiz(call):
    pid, opcao = call.data.split("|")
    if pid not in respostas_pendentes:
        return bot.answer_callback_query(call.id, "Pergunta expirada.")

    pend = respostas_pendentes[pid]
    user = call.from_user.id
    nome = call.from_user.first_name or call.from_user.username or "Alguém"

    if user in pend["respostas"]:
        return bot.answer_callback_query(call.id, "Você já respondeu.")

    pend["respostas"][user] = int(opcao)
    bot.answer_callback_query(call.id, "✅ Resposta registrada!")
    bot.send_message(GRUPO_ID, f"✅ {nome} respondeu.")

# 🔹 BOTÃO: NOVO DESAFIO
@bot.callback_query_handler(func=lambda call: call.data == "pedir_nova_pergunta")
def membro_pediu_nova(call):
    global ultimo_pedido_membro
    agora = time.time()

    if call.from_user.id == DONO_ID:
        pid_ativo = next(iter(respostas_pendentes), None)
        if pid_ativo and pid_ativo != "ultimo_id":
            revelar_resposta(pid_ativo)
        mandar_pergunta()
        return bot.answer_callback_query(call.id, "✅ Nova pergunta enviada!")

    tempo_restante = int(600 - (agora - ultimo_pedido_membro))
    if tempo_restante > 0:
        minutos = tempo_restante // 60
        segundos = tempo_restante % 60
        bot.send_message(GRUPO_ID, f"⏳ Calma! Já pediram recentemente. Tente de novo em {minutos}m {segundos}s.")
        return bot.answer_callback_query(call.id, "Aguarde antes de pedir outra.")

    ultimo_pedido_membro = agora
    pid_ativo = next(iter(respostas_pendentes), None)
    if pid_ativo and pid_ativo != "ultimo_id":
        revelar_resposta(pid_ativo)
    mandar_pergunta()
    bot.answer_callback_query(call.id, "🧠 Novo desafio enviado!")

# 🎉 REVELA A RESPOSTA

def revelar_resposta(pid):
    pend = respostas_pendentes.pop(pid, None)
    if not pend:
        return

    pergunta = pend["pergunta"]
    corretos = [u for u, o in pend["respostas"].items() if o == pergunta["correta"]]
    acertadores = []

    for u in corretos:
        ranking[u] = ranking.get(u, 0) + 1
        try:
            user = bot.get_chat(u)
            nome = user.first_name or user.username or str(u)
        except:
            nome = str(u)
        acertadores.append(nome)

    salvar_ranking()

    resp = f"✅ *Resposta correta:* {pergunta['opcoes'][pergunta['correta']]}\n\n"

    if acertadores:
        resp += "🎉 *Quem acertou:*\n" + "\n".join(f"• {nome}" for nome in acertadores) + "\n"
    else:
        resp += "😢 Ninguém acertou dessa vez.\n"

    if ranking:
        resp += "\n🏆 *Ranking atual:*\n"
        top = sorted(ranking.items(), key=lambda x: x[1], reverse=True)
        for i, (u, p) in enumerate(top[:10], start=1):
            try:
                user = bot.get_chat(u)
                nome = user.first_name or user.username or str(u)
            except:
                nome = str(u)
            resp += f"{i}º – {nome}: {p} ponto(s)\n"

    bot.send_message(GRUPO_ID, resp, parse_mode="Markdown")

# 🏠 WEBHOOK FLASK
@app.route(f"/{TOKEN}", methods=["POST"])
def webhook():
    bot.process_new_updates([telebot.types.Update.de_json(request.stream.read().decode("utf-8"))])
    return "OK", 200

@app.route("/", methods=["GET"])
def home():
    url = f"{RENDER_URL}/{TOKEN}"
    if bot.get_webhook_info().url != url:
        bot.remove_webhook()
        bot.set_webhook(url=url)
    return "✅", 200

# 🌟 THREAD DE MANUTENÇÃO

def manter_vivo():
    import requests
    while True:
        try:
            requests.get(RENDER_URL)
        except:
            pass
        time.sleep(600)

def ciclo_perguntas():
    while True:
        agora = datetime.now()
        if 6 <= agora.hour < 24:
            mandar_pergunta()
        time.sleep(3600)  # A cada 1h

if __name__ == "__main__":
    carregar_perguntas_feitas()
    threading.Thread(target=ciclo_perguntas).start()
    threading.Thread(target=manter_vivo).start()
    port = int(os.getenv("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
