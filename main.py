from flask import Flask, request
import telebot
import os
import time
import json
import threading
import random

# =======================================
# CONFIGURAÇÕES INICIAIS
# =======================================
TOKEN = os.getenv("BOT_TOKEN")  # ou coloque seu token direto aqui
bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

GRUPO_ID = -100123456789  # ID do grupo
DONO_ID = 1481389775
MATEUS_ID = 7889195722
AUTORIZADOS = {DONO_ID, MATEUS_ID}

# =======================================
# VARIÁVEIS DE CONTROLE
# =======================================
desafio_ativo = None
respostas_pendentes = {}  # {pid: {"pergunta": {}, "respostas": {}, "limites": {}, "revelar_em": float}}
pontuacoes = {}
mensagens_privadas = {}  # {user_id: [msg_ids]}
perguntas_feitas = []

# =======================================
# FUNÇÕES AUXILIARES
# =======================================
def carregar_perguntas():
    with open("perguntas.json", "r", encoding="utf-8") as f:
        return json.load(f)

def salvar_perguntas_feitas():
    with open("perguntas_feitas.json", "w", encoding="utf-8") as f:
        json.dump(perguntas_feitas, f)

def escolher_pergunta():
    perguntas = carregar_perguntas()
    usadas = {p["id"] for p in perguntas_feitas}
    disponiveis = [p for p in perguntas if p["id"] not in usadas]
    return random.choice(disponiveis) if disponiveis else None

# =======================================
# ENVIO DE PERGUNTA NO PRIVADO
# =======================================
def enviar_pergunta_privada(user_id, pid, pergunta):
    global mensagens_privadas

    # apaga perguntas antigas no privado
    if user_id in mensagens_privadas:
        for msg_id in mensagens_privadas[user_id]:
            try:
                bot.delete_message(user_id, msg_id)
            except:
                pass
    mensagens_privadas[user_id] = []

    # monta opções
    markup = telebot.types.InlineKeyboardMarkup()
    for i, opc in enumerate(pergunta["opcoes"]):
        markup.add(telebot.types.InlineKeyboardButton(opc, callback_data=f"{pid}|{i}"))

    msg = bot.send_message(
        user_id,
        f"⏳ Você tem *10 segundos* para responder:\n\n❓ {pergunta['pergunta']}",
        parse_mode="Markdown",
        reply_markup=markup,
    )
    mensagens_privadas[user_id].append(msg.message_id)

    # timer individual
    respostas_pendentes[pid]["limites"][user_id] = time.time() + 10

    def timeout():
        time.sleep(10)
        if user_id not in respostas_pendentes[pid]["respostas"]:
            nome = bot.get_chat(user_id).first_name or bot.get_chat(user_id).username or "Alguém"
            bot.send_message(user_id, "⏰ Seu tempo expirou! Você não pode mais responder.")
            bot.send_message(GRUPO_ID, f"⏰ {nome} perdeu a vez. Aguarde resultado final.")

    threading.Thread(target=timeout).start()

# =======================================
# CALLBACK: NOVO DESAFIO
# =======================================
@bot.callback_query_handler(func=lambda c: c.data == "novo_desafio")
def desafio_callback(call):
    global desafio_ativo

    agora = time.time()

    # Se já existe desafio ativo → só manda pergunta ao jogador
    if desafio_ativo is not None:
        pid = desafio_ativo
        pend = respostas_pendentes.get(pid)
        if pend and agora < pend["revelar_em"]:
            return enviar_pergunta_privada(call.from_user.id, pid, pend["pergunta"])
        else:
            return bot.answer_callback_query(call.id, "⏳ Aguarde o próximo desafio.")

    # Se não existe desafio → cria um novo
    pergunta = escolher_pergunta()
    if not pergunta:
        return bot.send_message(call.from_user.id, "❌ Não há perguntas disponíveis.")

    pid = str(time.time())
    respostas_pendentes[pid] = {
        "pergunta": pergunta,
        "respostas": {},
        "limites": {},
        "revelar_em": agora + 300
    }
    desafio_ativo = pid

    perguntas_feitas.append({"id": pergunta["id"], "tempo": agora})
    salvar_perguntas_feitas()

    def revelar():
        time.sleep(300)
        revelar_resposta(pid)

    threading.Thread(target=revelar).start()

    return enviar_pergunta_privada(call.from_user.id, pid, pergunta)

# =======================================
# CALLBACK: RESPOSTA DO JOGADOR
# =======================================
@bot.callback_query_handler(func=lambda c: "|" in c.data)
def resposta_callback(call):
    global respostas_pendentes

    pid, idx = call.data.split("|")
    idx = int(idx)

    if pid not in respostas_pendentes:
        return bot.answer_callback_query(call.id, "⏳ Esse desafio já encerrou.")

    pend = respostas_pendentes[pid]
    agora = time.time()
    limite = pend["limites"].get(call.from_user.id, 0)

    # expirou
    if agora > limite:
        return bot.send_message(call.from_user.id, "⏰ Seu tempo expirou! Você não pode mais responder.")

    # já respondeu
    if call.from_user.id in pend["respostas"]:
        return bot.answer_callback_query(call.id, "⚠️ Você já respondeu!")

    # registra resposta
    pend["respostas"][call.from_user.id] = idx
    nome = call.from_user.first_name or call.from_user.username or "Alguém"

    bot.send_message(call.from_user.id, f"✅ Você respondeu: {pend['pergunta']['opcoes'][idx]}\n\n👀 Aguarde 5 minutos para saber se acertou!")
    bot.send_message(GRUPO_ID, f"✍️ {nome} respondeu.")

# =======================================
# REVELAR RESPOSTA
# =======================================
def revelar_resposta(pid):
    global desafio_ativo, respostas_pendentes, pontuacoes

    if pid not in respostas_pendentes:
        return

    pend = respostas_pendentes[pid]
    pergunta = pend["pergunta"]
    corretas = []
    for uid, resp in pend["respostas"].items():
        if resp == pergunta["correta"]:
            pontuacoes[uid] = pontuacoes.get(uid, 0) + 1
            nome = bot.get_chat(uid).first_name or bot.get_chat(uid).username or "Alguém"
            corretas.append(nome)

    texto = f"📢 Desafio encerrado!\n\n❓ Pergunta: {pergunta['pergunta']}\n✅ Resposta correta: {pergunta['opcoes'][pergunta['correta']]}\n\n📖 Explicação: {pergunta['explicacao']}\n\n🏆 Quem acertou: {', '.join(corretas) if corretas else 'Ninguém 😢'}"

    # ranking
    ranking = sorted(pontuacoes.items(), key=lambda x: x[1], reverse=True)
    if ranking:
        texto += "\n\n📊 Ranking:\n"
        for i, (uid, pts) in enumerate(ranking, start=1):
            nome = bot.get_chat(uid).first_name or bot.get_chat(uid).username or "Alguém"
            texto += f"{i}. {nome} — {pts} ponto(s)\n"

    markup = telebot.types.InlineKeyboardMarkup()
    markup.add(telebot.types.InlineKeyboardButton("🆕 Novo Desafio", callback_data="novo_desafio"))

    bot.send_message(GRUPO_ID, texto, reply_markup=markup)

    # limpa estado
    del respostas_pendentes[pid]
    desafio_ativo = None

# =======================================
# COMANDO /quiz (apenas autorizados)
# =======================================
@bot.message_handler(commands=["quiz"])
def comando_quiz(message):
    if message.from_user.id in AUTORIZADOS:
        markup = telebot.types.InlineKeyboardMarkup()
        markup.add(telebot.types.InlineKeyboardButton("🆕 Novo Desafio", callback_data="novo_desafio"))
        bot.send_message(GRUPO_ID, "🎮 Iniciando desafio!", reply_markup=markup)
    else:
        bot.reply_to(message, "🚫 Você não tem permissão para iniciar desafios.")

# =======================================
# FLASK ENDPOINT
# =======================================
@app.route(f"/{TOKEN}", methods=["POST"])
def webhook():
    update = telebot.types.Update.de_json(request.stream.read().decode("utf-8"))
    bot.process_new_updates([update])
    return "OK"

@app.route("/")
def index():
    return "Bot ativo!"

# =======================================
# MAIN
# =======================================
if __name__ == "__main__":
    bot.remove_webhook()
    bot.polling(none_stop=True)
