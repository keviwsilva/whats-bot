from flask import Flask, request, jsonify
from twilio.twiml.messaging_response import MessagingResponse
from twilio.rest import Client
from datetime import datetime, timedelta
import json
import os
import csv
from pathlib import Path
import logging
import sqlite3
import atexit

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configurações
app = Flask(__name__)

# Suas credenciais do Twilio (usar variáveis de ambiente no Render)
account_sid = os.environ.get('TWILIO_ACCOUNT_SID', 'SEU_ACCOUNT_SID')
auth_token = os.environ.get('TWILIO_AUTH_TOKEN', 'SEU_AUTH_TOKEN')
twilio_whatsapp_number = os.environ.get('TWILIO_WHATSAPP_NUMBER', 'whatsapp:+14155238886')

# Inicializar cliente Twilio
try:
    client = Client(account_sid, auth_token)
    logger.info("Cliente Twilio inicializado com sucesso")
except Exception as e:
    logger.error(f"Erro ao inicializar cliente Twilio: {e}")
    client = None

# Configuração do banco de dados SQLite
DB_PATH = os.environ.get('DATABASE_URL', 'sqlite:///financas.db').replace('sqlite:///', '')
if DB_PATH.startswith('/'):
    DB_PATH = DB_PATH[1:]

def init_db():
    """Inicializa o banco de dados com as tabelas necessárias"""
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        
        # Criar tabela de usuários
        c.execute('''
            CREATE TABLE IF NOT EXISTS usuarios (
                id TEXT PRIMARY KEY,
                categorias_receitas TEXT DEFAULT '["salário", "freelance", "investimentos", "presente"]',
                categorias_despesas TEXT DEFAULT '["alimentação", "transporte", "moradia", "lazer", "saúde", "educação"]'
            )
        ''')
        
        # Criar tabela de transações
        c.execute('''
            CREATE TABLE IF NOT EXISTS transacoes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                usuario_id TEXT,
                tipo TEXT,
                valor REAL,
                descricao TEXT,
                categoria TEXT,
                data TEXT,
                FOREIGN KEY (usuario_id) REFERENCES usuarios (id)
            )
        ''')
        
        conn.commit()
        conn.close()
        logger.info("Banco de dados inicializado com sucesso")
    except Exception as e:
        logger.error(f"Erro ao inicializar banco de dados: {e}")

# Inicializar banco de dados ao iniciar
init_db()

# Fechar conexão ao sair
@atexit.register
def close_db():
    """Fecha conexões com o banco de dados ao encerrar a aplicação"""
    logger.info("Encerrando aplicação e fechando conexões com banco de dados")

# Dicionário para sessões de usuário (em memória)
user_sessions = {}

# Funções de acesso ao banco de dados
def get_usuario(sender):
    """Obtém ou cria um usuário no banco de dados"""
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        
        # Verificar se usuário existe
        c.execute("SELECT * FROM usuarios WHERE id = ?", (sender,))
        usuario = c.fetchone()
        
        if not usuario:
            # Criar novo usuário
            c.execute(
                "INSERT INTO usuarios (id) VALUES (?)", 
                (sender,)
            )
            conn.commit()
            
            # Retornar dados do novo usuário
            return {
                "id": sender,
                "categorias_receitas": ["salário", "freelance", "investimentos", "presente"],
                "categorias_despesas": ["alimentação", "transporte", "moradia", "lazer", "saúde", "educação"]
            }
        else:
            # Retornar usuário existente
            return {
                "id": usuario[0],
                "categorias_receitas": json.loads(usuario[1]),
                "categorias_despesas": json.loads(usuario[2])
            }
    except Exception as e:
        logger.error(f"Erro ao obter usuário: {e}")
        return None
    finally:
        conn.close()

def get_transacoes(usuario_id):
    """Obtém todas as transações de um usuário"""
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        
        c.execute(
            "SELECT tipo, valor, descricao, categoria, data FROM transacoes WHERE usuario_id = ? ORDER BY datetime(data) DESC", 
            (usuario_id,)
        )
        
        transacoes = []
        for row in c.fetchall():
            transacoes.append({
                "tipo": row[0],
                "valor": row[1],
                "descricao": row[2],
                "categoria": row[3],
                "data": row[4]
            })
        
        return transacoes
    except Exception as e:
        logger.error(f"Erro ao obter transações: {e}")
        return []
    finally:
        conn.close()

def add_transacao(usuario_id, tipo, valor, descricao, categoria):
    """Adiciona uma nova transação para o usuário"""
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        
        data_atual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        c.execute(
            "INSERT INTO transacoes (usuario_id, tipo, valor, descricao, categoria, data) VALUES (?, ?, ?, ?, ?, ?)",
            (usuario_id, tipo, valor, descricao, categoria, data_atual)
        )
        
        conn.commit()
        return True
    except Exception as e:
        logger.error(f"Erro ao adicionar transação: {e}")
        return False
    finally:
        conn.close()

def add_categoria(usuario_id, tipo, categoria):
    """Adiciona uma nova categoria para o usuário"""
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        
        # Obter categorias atuais
        coluna = "categorias_receitas" if tipo == "receita" else "categorias_despesas"
        c.execute(f"SELECT {coluna} FROM usuarios WHERE id = ?", (usuario_id,))
        resultado = c.fetchone()
        
        if resultado:
            categorias = json.loads(resultado[0])
            if categoria not in categorias:
                categorias.append(categoria)
                
                # Atualizar categorias
                c.execute(
                    f"UPDATE usuarios SET {coluna} = ? WHERE id = ?",
                    (json.dumps(categorias), usuario_id)
                )
                conn.commit()
        
        return True
    except Exception as e:
        logger.error(f"Erro ao adicionar categoria: {e}")
        return False
    finally:
        conn.close()

@app.route('/')
def home():
    return "Bot de Finanças Pessoais está funcionando! Use o WhatsApp para interagir."

@app.route('/webhook', methods=['POST'])
def webhook():
    """Endpoint para receber mensagens do WhatsApp via Twilio"""
    try:
        incoming_msg = request.values.get('Body', '').lower().strip()
        sender = request.values.get('From', '')
        
        logger.info(f"Mensagem recebida de {sender}: {incoming_msg}")
        
        # Inicializar resposta
        resp = MessagingResponse()
        msg = resp.message()
        
        # Processar mensagem
        response_text = processar_mensagem(incoming_msg, sender)
        msg.body(response_text)
        
        return str(resp)
    except Exception as e:
        logger.error(f"Erro no webhook: {e}")
        return "Erro interno do servidor", 500

def processar_mensagem(mensagem, sender):
    """Processa a mensagem e retorna uma resposta"""
    try:
        # Obter dados do usuário
        usuario = get_usuario(sender)
        if not usuario:
            return "❌ Erro ao carregar seus dados. Tente novamente."
        
        transacoes = get_transacoes(sender)
        
        # Verificar se é a primeira interação nesta sessão
        if sender not in user_sessions:
            user_sessions[sender] = {"estado": "menu_principal"}
        
        session = user_sessions[sender]
        
        # Comandos principais
        if mensagem in ['menu', 'inicio', 'voltar', 'ajuda']:
            session["estado"] = "menu_principal"
            return mostrar_menu_principal()
        
        elif session["estado"] == "menu_principal":
            return processar_menu_principal(mensagem, session, usuario, transacoes, sender)
        
        elif session["estado"].startswith("registrar_"):
            return processar_registro(mensagem, session, usuario, sender)
        
        else:
            return "Desculpe, não entendi. Digite 'menu' para ver as opções."
    except Exception as e:
        logger.error(f"Erro ao processar mensagem: {e}")
        return "Ocorreu um erro interno. Por favor, tente novamente."

def mostrar_menu_principal():
    return (
        "💰 *BOT DE FINANÇAS PESSOAIS* 💰\n\n"
        "Escolha uma opção:\n\n"
        "1️⃣ - Registrar receita\n"
        "2️⃣ - Registrar despesa\n"
        "3️⃣ - Ver saldo atual\n"
        "4️⃣ - Extrato recente\n"
        "5️⃣ - Relatório por categoria\n"
        "6️⃣ - Minhas categorias\n\n"
        "Digite o número ou nome da opção desejada."
    )

def processar_menu_principal(mensagem, session, usuario, transacoes, sender):
    opcoes = {
        '1': 'registrar_receita',
        'receita': 'registrar_receita',
        '2': 'registrar_despesa', 
        'despesa': 'registrar_despesa',
        '3': 'mostrar_saldo',
        'saldo': 'mostrar_saldo',
        '4': 'extrato_recente',
        'extrato': 'extrato_recente',
        '5': 'relatorio_categoria',
        'categoria': 'relatorio_categoria',
        '6': 'mostrar_categorias',
        'categorias': 'mostrar_categorias'
    }
    
    if mensagem in opcoes:
        session["estado"] = opcoes[mensagem]
        return executar_acao(session["estado"], usuario, transacoes, sender)
    else:
        return "Opção não reconhecida. Digite 'menu' para ver as opções disponíveis."

def executar_acao(acao, usuario, transacoes, sender):
    if acao == "registrar_receita":
        return "💵 *Registrar Receita*\n\nDigite o valor da receita:"
    
    elif acao == "registrar_despesa":
        return "💸 *Registrar Despesa*\n\nDigite o valor da despesa:"
    
    elif acao == "mostrar_saldo":
        saldo = calcular_saldo(transacoes)
        return f"💰 *Seu Saldo Atual*\n\nSaldo: R$ {saldo:,.2f}"
    
    elif acao == "extrato_recente":
        return mostrar_extrato_recente(transacoes)
    
    elif acao == "relatorio_categoria":
        return "📊 *Relatório por Categoria*\n\nFuncionalidade em desenvolvimento. Em breve!"
    
    elif acao == "mostrar_categorias":
        return mostrar_categorias(usuario)
    
    return "Ação não implementada."

def processar_registro(mensagem, session, usuario, sender):
    if session["estado"] == "registrar_receita":
        try:
            valor = float(mensagem.replace(',', '.'))
            session["estado"] = "registrar_receita_descricao"
            session["valor"] = valor
            return "💵 Digite uma descrição para esta receita:"
        except ValueError:
            return "❌ Valor inválido. Digite um número válido:"
    
    elif session["estado"] == "registrar_receita_descricao":
        descricao = mensagem
        session["estado"] = "registrar_receita_categoria"
        session["descricao"] = descricao
        categorias = usuario["categorias_receitas"]
        return f"📁 Escolha a categoria:\n\n" + "\n".join([f"{i+1} - {cat}" for i, cat in enumerate(categorias)])
    
    elif session["estado"] == "registrar_receita_categoria":
        try:
            categorias = usuario["categorias_receitas"]
            categoria = ""
            
            if mensagem.isdigit() and 1 <= int(mensagem) <= len(categorias):
                categoria = categorias[int(mensagem)-1]
            else:
                categoria = mensagem
                # Adicionar nova categoria
                add_categoria(sender, "receita", categoria)
            
            # Adicionar transação
            success = add_transacao(sender, "receita", session["valor"], session["descricao"], categoria)
            
            if success:
                session["estado"] = "menu_principal"
                return f"✅ Receita de R$ {session['valor']:,.2f} registrada com sucesso!\nDigite 'menu' para mais opções."
            else:
                return "❌ Erro ao registrar receita. Tente novamente."
        
        except (ValueError, IndexError):
            return "❌ Categoria inválida. Tente novamente."
    
    elif session["estado"] == "registrar_despesa":
        try:
            valor = float(mensagem.replace(',', '.'))
            session["estado"] = "registrar_despesa_descricao"
            session["valor"] = valor
            return "💸 Digite uma descrição para esta despesa:"
        except ValueError:
            return "❌ Valor inválido. Digite um número válido:"
    
    elif session["estado"] == "registrar_despesa_descricao":
        descricao = mensagem
        session["estado"] = "registrar_despesa_categoria"
        session["descricao"] = descricao
        categorias = usuario["categorias_despesas"]
        return f"📁 Escolha a categoria:\n\n" + "\n".join([f"{i+1} - {cat}" for i, cat in enumerate(categorias)])
    
    elif session["estado"] == "registrar_despesa_categoria":
        try:
            categorias = usuario["categorias_despesas"]
            categoria = ""
            
            if mensagem.isdigit() and 1 <= int(mensagem) <= len(categorias):
                categoria = categorias[int(mensagem)-1]
            else:
                categoria = mensagem
                # Adicionar nova categoria
                add_categoria(sender, "despesa", categoria)
            
            # Adicionar transação
            success = add_transacao(sender, "despesa", session["valor"], session["descricao"], categoria)
            
            if success:
                session["estado"] = "menu_principal"
                return f"✅ Despesa de R$ {session['valor']:,.2f} registrada com sucesso!\nDigite 'menu' para mais opções."
            else:
                return "❌ Erro ao registrar despesa. Tente novamente."
        
        except (ValueError, IndexError):
            return "❌ Categoria inválida. Tente novamente."
    
    return "Estado não reconhecido."

def calcular_saldo(transacoes):
    saldo = 0
    for transacao in transacoes:
        if transacao["tipo"] == "receita":
            saldo += transacao["valor"]
        else:
            saldo -= transacao["valor"]
    return saldo

def mostrar_extrato_recente(transacoes):
    if not transacoes:
        return "📋 Você ainda não tem transações registradas."
    
    # Ordenar por data (mais recente primeiro)
    transacoes_ordenadas = sorted(
        transacoes, 
        key=lambda x: datetime.strptime(x["data"], "%Y-%m-%d %H:%M:%S"), 
        reverse=True
    )[:10]
    
    resposta = "📋 *Últimas 10 transações:*\n\n"
    for i, trans in enumerate(transacoes_ordenadas, 1):
        tipo = "✅" if trans["tipo"] == "receita" else "❌"
        data_formatada = datetime.strptime(trans["data"], "%Y-%m-%d %H:%M:%S").strftime("%d/%m %H:%M")
        resposta += f"{i}. {tipo} {data_formatada} - {trans['descricao']}: R$ {trans['valor']:,.2f}\n"
    
    saldo = calcular_saldo(transacoes)
    resposta += f"\n💰 Saldo atual: R$ {saldo:,.2f}"
    
    return resposta

def mostrar_categorias(usuario):
    resposta = "📁 *Suas Categorias:*\n\n"
    resposta += "💵 *Receitas:*\n" + "\n".join([f"• {cat}" for cat in usuario["categorias_receitas"]]) + "\n\n"
    resposta += "💸 *Despesas:*\n" + "\n".join([f"• {cat}" for cat in usuario["categorias_despesas"]])
    return resposta

def send_message(to, body):
    """Função para enviar mensagens proactively"""
    if not client:
        return None
        
    try:
        message = client.messages.create(
            body=body,
            from_=twilio_whatsapp_number,
            to=to
        )
        return message.sid
    except Exception as e:
        logger.error(f"Erro ao enviar mensagem: {e}")
        return None

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)