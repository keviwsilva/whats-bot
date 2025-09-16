from flask import Flask, request
from twilio.twiml.messaging_response import MessagingResponse
import sqlite3
import os
import datetime

app = Flask(__name__)
db_file = "gastos.db"  # arquivo de banco de dados local

# Inicializa o banco
def init_db():
    if not os.path.exists(db_file):
        conn = sqlite3.connect(db_file)
        c = conn.cursor()
        c.execute("""CREATE TABLE IF NOT EXISTS gastos (
                     id INTEGER PRIMARY KEY AUTOINCREMENT,
                     valor REAL,
                     descricao TEXT,
                     data TEXT
                     )""")
        conn.commit()
        conn.close()

init_db()

@app.route("/whatsapp", methods=["POST"])
def whatsapp_bot():
    msg_recebida = request.form.get('Body').lower()
    resposta = MessagingResponse()

    conn = sqlite3.connect(db_file)
    c = conn.cursor()

    # Comando: adicionar gasto
    if msg_recebida.startswith("adicionar"):
        try:
            partes = msg_recebida.split()
            valor = float(partes[1])
            descricao = " ".join(partes[2:])
            hoje = datetime.date.today().isoformat()
            c.execute("INSERT INTO gastos (valor, descricao, data) VALUES (?, ?, ?)",
                      (valor, descricao, hoje))
            conn.commit()
            resposta.message(f"Gasto de R$ {valor:.2f} adicionado: {descricao}")
        except:
            resposta.message("Formato inválido. Use: adicionar <valor> <descrição>")

    # Comando: total geral
    elif msg_recebida == "total":
        c.execute("SELECT SUM(valor) FROM gastos")
        total = c.fetchone()[0] or 0
        resposta.message(f"💰 Total de gastos: R$ {total:.2f}")

    # Comando: listar todos os gastos
    elif msg_recebida == "listar":
        c.execute("SELECT valor, descricao, data FROM gastos")
        linhas = c.fetchall()
        if linhas:
            msg = "📝 Lista de gastos:\n"
            for v, d, dt in linhas:
                msg += f"- {dt} R$ {v:.2f} : {d}\n"
            resposta.message(msg)
        else:
            resposta.message("Nenhum gasto registrado.")

    # Comando: total por mês
    elif msg_recebida.startswith("total mês"):
        try:
            mes = msg_recebida.split()[2]  # formato: AAAA-MM
            c.execute("SELECT SUM(valor) FROM gastos WHERE substr(data,1,7)=?", (mes,))
            total = c.fetchone()[0] or 0
            resposta.message(f"💰 Total de gastos em {mes}: R$ {total:.2f}")
        except:
            resposta.message("Formato inválido. Use: total mês AAAA-MM")

    # Comando: listar gastos por mês
    elif msg_recebida.startswith("listar mês"):
        try:
            mes = msg_recebida.split()[2]  # formato: AAAA-MM
            c.execute("SELECT valor, descricao, data FROM gastos WHERE substr(data,1,7)=?", (mes,))
            linhas = c.fetchall()
            if linhas:
                msg = f"📝 Lista de gastos em {mes}:\n"
                for v, d, dt in linhas:
                    msg += f"- {dt} R$ {v:.2f} : {d}\n"
                resposta.message(msg)
            else:
                resposta.message(f"Nenhum gasto registrado em {mes}.")
        except:
            resposta.message("Formato inválido. Use: listar mês AAAA-MM")

    # Mensagem padrão
    else:
        resposta.message(
            "Comandos disponíveis:\n"
            "- adicionar <valor> <descrição>\n"
            "- total\n"
            "- listar\n"
            "- total mês AAAA-MM\n"
            "- listar mês AAAA-MM"
        )

    conn.close()
    return str(resposta)

if __name__ == "__main__":
    app.run(debug=True)
