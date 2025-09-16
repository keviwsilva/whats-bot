from flask import Flask, request
from twilio.twiml.messaging_response import MessagingResponse
import sqlite3
import os
import datetime
import re
import json
import random
import numpy as np
from datetime import datetime, timedelta
from collections import defaultdict
import math

app = Flask(__name__)
db_file = "gastos_ml.db"

# Inicializa o banco com tabelas para ML
def init_db():
    conn = sqlite3.connect(db_file)
    c = conn.cursor()
    
    # Tabela de gastos
    c.execute("""CREATE TABLE IF NOT EXISTS gastos (
                 id INTEGER PRIMARY KEY AUTOINCREMENT,
                 valor REAL,
                 descricao TEXT,
                 categoria TEXT,
                 data TEXT,
                 localizacao TEXT,
                 metodo_pagamento TEXT,
                 tags TEXT
                 )""")
    
    # Tabela de orçamentos
    c.execute("""CREATE TABLE IF NOT EXISTS orcamentos (
                 id INTEGER PRIMARY KEY AUTOINCREMENT,
                 categoria TEXT,
                 limite_mensal REAL,
                 mes_ano TEXT
                 )""")
    
    # Tabela de metas financeiras
    c.execute("""CREATE TABLE IF NOT EXISTS metas (
                 id INTEGER PRIMARY KEY AUTOINCREMENT,
                 objetivo TEXT,
                 valor_alvo REAL,
                 valor_atual REAL,
                 data_limite TEXT,
                 concluida INTEGER DEFAULT 0
                 )""")
    
    # Tabela de contexto da conversa
    c.execute("""CREATE TABLE IF NOT EXISTS contexto (
                 id INTEGER PRIMARY KEY AUTOINCREMENT,
                 numero TEXT,
                 ultima_intencao TEXT,
                 dados_contexto TEXT,
                 timestamp TEXT
                 )""")
    
    # Tabela para aprendizado de ML
    c.execute("""CREATE TABLE IF NOT EXISTS ml_model (
                 id INTEGER PRIMARY KEY AUTOINCREMENT,
                 tipo TEXT,
                 parametros TEXT,
                 precisao REAL,
                 data_treinamento TEXT
                 )""")
    
    # Tabela para padrões de gastos do usuário
    c.execute("""CREATE TABLE IF NOT EXISTS padroes_usuario (
                 id INTEGER PRIMARY KEY AUTOINCREMENT,
                 padrao_type TEXT,
                 padrao_dados TEXT,
                 confianca REAL,
                 ultima_atualizacao TEXT
                 )""")
    
    conn.commit()
    conn.close()

init_db()

# Sistema de ML para categorização
class CategorizadorML:
    def __init__(self):
        self.palavras_chave = defaultdict(lambda: defaultdict(int))
        self.categorias_padrao = defaultdict(int)
        self.modelo_treinado = False
        
    def treinar_com_dados(self, conn):
        c = conn.cursor()
        c.execute("SELECT descricao, categoria FROM gastos WHERE categoria IS NOT NULL")
        dados = c.fetchall()
        
        for descricao, categoria in dados:
            palavras = descricao.lower().split()
            for palavra in palavras:
                if len(palavra) > 2:  # Ignora palavras muito curtas
                    self.palavras_chave[palavra][categoria] += 1
            self.categorias_padrao[categoria] += 1
        
        self.modelo_treinado = True
        return len(dados)
    
    def prever_categoria(self, descricao):
        if not self.modelo_treinado:
            return "outros"
        
        palavras = descricao.lower().split()
        scores = defaultdict(float)
        
        for palavra in palavras:
            if palavra in self.palavras_chave:
                total = sum(self.palavras_chave[palavra].values())
                for categoria, count in self.palavras_chave[palavra].items():
                    scores[categoria] += count / total
        
        if scores:
            return max(scores.items(), key=lambda x: x[1])[0]
        else:
            # Fallback para categorias mais comuns
            if self.categorias_padrao:
                return max(self.categorias_padrao.items(), key=lambda x: x[1])[0]
            return "outros"

# Sistema de previsão de gastos
class PredictorML:
    def __init__(self):
        self.historico_gastos = []
        self.media_movel = 0
        self.tendencia = 0
        
    def analisar_historico(self, conn):
        c = conn.cursor()
        c.execute("SELECT valor, data FROM gastos ORDER BY data")
        dados = c.fetchall()
        
        self.historico_gastos = []
        for valor, data_str in dados:
            try:
                data = datetime.strptime(data_str.split('T')[0], "%Y-%m-%d")
                self.historico_gastos.append((data, valor))
            except:
                continue
        
        if len(self.historico_gastos) < 7:
            return False
            
        # Calcula média móvel dos últimos 7 dias
        ultimos_7_dias = [v for d, v in self.historico_gastos[-7:]]
        self.media_movel = sum(ultimos_7_dias) / len(ultimos_7_dias)
        
        # Calcula tendência (últimos 7 dias vs anteriores 7 dias)
        if len(self.historico_gastos) >= 14:
            anteriores_7_dias = [v for d, v in self.historico_gastos[-14:-7]]
            media_anteriores = sum(anteriores_7_dias) / len(anteriores_7_dias)
            self.tendencia = ((self.media_movel - media_anteriores) / media_anteriores) * 100 if media_anteriores > 0 else 0
        
        return True
    
    def prever_proximos_dias(self, dias=7):
        if not self.historico_gastos:
            return None
            
        previsao = self.media_movel * dias
        return previsao, self.tendencia

# Sistema de recomendação inteligente
class RecomendadorML:
    def __init__(self):
        self.padroes_gastos = defaultdict(list)
        self.recomendacoes = []
        
    def analisar_padroes(self, conn):
        c = conn.cursor()
        
        # Padrões por dia da semana
        c.execute("SELECT valor, data FROM gastos")
        for valor, data_str in dados:
            try:
                data = datetime.strptime(data_str.split('T')[0], "%Y-%m-%d")
                dia_semana = data.weekday()
                self.padroes_gastos['dia_semana'].append((dia_semana, valor))
            except:
                continue
        
        # Padrões por categoria
        c.execute("SELECT categoria, valor FROM gastos WHERE categoria IS NOT NULL")
        for categoria, valor in c.fetchall():
            self.padroes_gastos['categoria'].append((categoria, valor))
        
        # Gera recomendações baseadas em padrões
        self._gerar_recomendacoes()
        
    def _gerar_recomendacoes(self):
        self.recomendacoes = []
        
        # Análise de gastos por dia da semana
        if 'dia_semana' in self.padroes_gastos:
            gastos_por_dia = defaultdict(list)
            for dia, valor in self.padroes_gastos['dia_semana']:
                gastos_por_dia[dia].append(valor)
            
            dias_nomes = ['Segunda', 'Terça', 'Quarta', 'Quinta', 'Sexta', 'Sábado', 'Domingo']
            for dia, gastos in gastos_por_dia.items():
                if len(gastos) > 3:  # Padrão significativo
                    media = sum(gastos) / len(gastos)
                    self.recomendacoes.append(
                        f"💡 Você gasta em média R$ {media:.2f} às {dias_nomes[dia]}s-feiras"
                    )
        
        # Análise de gastos por categoria
        if 'categoria' in self.padroes_gastos:
            gastos_por_categoria = defaultdict(list)
            for categoria, valor in self.padroes_gastos['categoria']:
                gastos_por_categoria[categoria].append(valor)
            
            for categoria, gastos in gastos_por_categoria.items():
                if len(gastos) > 5:  # Padrão significativo
                    total = sum(gastos)
                    self.recomendacoes.append(
                        f"💡 Você já gastou R$ {total:.2f} com {categoria} este mês"
                    )
    
    def obter_recomendacoes(self, limite=3):
        return random.sample(self.recomendacoes, min(limite, len(self.recomendacoes))) if self.recomendacoes else []

# Instâncias dos modelos ML
categorizador_ml = CategorizadorML()
predictor_ml = PredictorML()
recomendador_ml = RecomendadorML()

# Função para formatar data
def formatar_data(data_str):
    try:
        if 'T' in data_str:
            dt = datetime.fromisoformat(data_str.replace('Z', '+00:00'))
            return dt.strftime("%d/%m/%Y")
        else:
            dt = datetime.strptime(data_str, "%Y-%m-%d")
            return dt.strftime("%d/%m/%Y")
    except (ValueError, AttributeError):
        return data_str

# Sistema de NLP avançado com ML
def analisar_intencao_com_ml(mensagem, historico=None):
    mensagem = mensagem.lower().strip()
    
    # Padrões com pesos baseados em aprendizado
    padroes = {
        'saudacao': (r'\b(oi|olá|ola|eae|hey|hello|como vai|tudo bem)\b', 0.95),
        'adicionar_gasto': (r'\b(gastei|gasto|gastar|adicionar|add|registrar|comprei|paguei|investi|r\$|reais|valor|preço)\b', 0.90),
        'consultar_gastos': (r'\b(ver|mostrar|listar|consultar|visualizar|gastos|despesas|compras)\b', 0.85),
        'resumo_financeiro': (r'\b(total|soma|resumo|quanto gastei|extrato|finanças|financeiro)\b', 0.88),
        'buscar_gastos': (r'\b(buscar|procurar|encontrar|filtrar|pesquisar|onde gastei)\b', 0.82),
        'definir_orcamento': (r'\b(orçamento|orcamento|limite|definir|estabelecer|máximo|controlar)\b', 0.80),
        'definir_meta': (r'\b(meta|objetivo|poupar|economizar|guardar|sonho|conseguir|alcançar)\b', 0.78),
        'analise_categoria': (r'\b(categoria|categorias|por tipo|por área|onde mais gasto)\b', 0.75),
        'previsao_gastos': (r'\b(previsão|previsao|futuro|próximo|próximos|esperar|projeção)\b', 0.77),
        'comparativo_mensal': (r'\b(comparar|mês|meses|variação|variaçao|evolução|evolucao)\b', 0.76),
        'recomendacao': (r'\b(dica|sugestão|sugestao|recomendação|recomendacao|como economizar|economia)\b', 0.72),
        'remover_gasto': (r'\b(remover|excluir|deletar|apagar|eliminar|retirar|cancelar)\b', 0.85),
        'configuracao': (r'\b(configurar|preferências|preferencias|alterar|mudar|personalizar)\b', 0.70),
        'treinar_ml': (r'\b(treinar|aprender|melhorar|atualizar|inteligencia|ia|ml|machine learning)\b', 0.65),
        'ajuda': (r'\b(ajuda|help|comandos|o que você faz|funcionalidades|como usar)\b', 0.90)
    }
    
    # Verifica correspondências com pesos
    correspondencias = []
    for intencao, (padrao, peso) in padroes.items():
        if re.search(padrao, mensagem, re.IGNORECASE):
            # Ajusta peso baseado no histórico do usuário
            peso_ajustado = peso
            if historico and intencao in historico:
                # Aumenta peso para intenções frequentes
                peso_ajustado *= 1.2
            
            correspondencias.append((intencao, peso_ajustado))
    
    if correspondencias:
        # Retorna a intenção com maior peso
        return max(correspondencias, key=lambda x: x[1])[0]
    
    # Fallback: detecta se há valor numérico (provavelmente adicionar gasto)
    if any(char.isdigit() for char in mensagem) and ('r$' in mensagem or 'reais' in mensagem):
        return "adicionar_gasto"
    
    return "desconhecido"

# Funções de extração de dados
def extrair_valor(texto):
    padroes = [
        r'r\$\s*(\d+[\.,]?\d*)',
        r'(\d+[\.,]?\d*)\s*reais',
        r'valor.*?(\d+[\.,]?\d*)',
        r'gastei.*?(\d+[\.,]?\d*)',
        r'(\d+[\.,]?\d*)\s*no|\s*na|\s*com',
        r'custa.*?(\d+[\.,]?\d*)'
    ]
    
    for padrao in padroes:
        correspondencias = re.findall(padrao, texto, re.IGNORECASE)
        if correspondencias:
            try:
                valor_str = correspondencias[0].replace(',', '.')
                return float(valor_str)
            except:
                continue
    return None

def extrair_descricao(texto):
    texto_limpo = re.sub(r'\d+[\.,]?\d*', '', texto)
    texto_limpo = re.sub(r'r\$|reais|valor|gastei|gasto|adicionar|add|registrar', '', texto_limpo, flags=re.IGNORECASE)
    texto_limpo = re.sub(r'\s+', ' ', texto_limpo).strip()
    
    palavras_remover = ['no', 'na', 'em', 'de', 'do', 'da', 'com', 'por', 'para', 'um', 'uma']
    palavras = [p for p in texto_limpo.split() if p.lower() not in palavras_remover]
    
    return ' '.join(palavras) if palavras else None

def extrair_id_remocao(texto):
    padroes = [
        r'remover\s+(\d+)',
        r'excluir\s+(\d+)',
        r'deletar\s+(\d+)',
        r'apagar\s+(\d+)',
        r'id\s+(\d+)',
        r'#(\d+)',
        r'(\d+)$'
    ]
    
    for padrao in padroes:
        correspondencias = re.findall(padrao, texto, re.IGNORECASE)
        if correspondencias:
            try:
                return int(correspondencias[0])
            except:
                continue
    return None

# Funções de contexto
def salvar_contexto(numero, intencao, dados=None):
    conn = sqlite3.connect(db_file)
    c = conn.cursor()
    
    dados_json = json.dumps(dados) if dados else None
    
    c.execute("SELECT id FROM contexto WHERE numero = ?", (numero,))
    existe = c.fetchone()
    
    if existe:
        c.execute("UPDATE contexto SET ultima_intencao = ?, dados_contexto = ?, timestamp = ? WHERE numero = ?",
                 (intencao, dados_json, datetime.now().isoformat(), numero))
    else:
        c.execute("INSERT INTO contexto (numero, ultima_intencao, dados_contexto, timestamp) VALUES (?, ?, ?, ?)",
                 (numero, intencao, dados_json, datetime.now().isoformat()))
    
    conn.commit()
    conn.close()

def recuperar_contexto(numero):
    conn = sqlite3.connect(db_file)
    c = conn.cursor()
    
    c.execute("SELECT ultima_intencao, dados_contexto FROM contexto WHERE numero = ?", (numero,))
    resultado = c.fetchone()
    
    conn.close()
    
    if resultado:
        intencao, dados_json = resultado
        dados = json.loads(dados_json) if dados_json else None
        return intencao, dados
    return None, None

# Funções de gerenciamento de gastos
def listar_gastos_para_remocao(conn, limite=10):
    c = conn.cursor()
    c.execute("SELECT id, valor, descricao, categoria, data FROM gastos ORDER BY data DESC, id DESC LIMIT ?", (limite,))
    return c.fetchall()

def remover_gasto(conn, id_gasto):
    c = conn.cursor()
    c.execute("SELECT id, valor, descricao FROM gastos WHERE id = ?", (id_gasto,))
    gasto = c.fetchone()
    
    if gasto:
        c.execute("DELETE FROM gastos WHERE id = ?", (id_gasto,))
        conn.commit()
        return True, gasto
    return False, None

# Sistema de análise com ML
def gerar_insights_ml(conn, numero):
    c = conn.cursor()
    
    # Atualiza modelos ML
    dados_treinados = categorizador_ml.treinar_com_dados(conn)
    predictor_ml.analisar_historico(conn)
    recomendador_ml.analisar_padroes(conn)
    
    # Insights básicos
    mes_atual = datetime.now().strftime("%Y-%m")
    c.execute("SELECT SUM(valor) FROM gastos WHERE substr(data,1,7)=?", (mes_atual,))
    total_mes = c.fetchone()[0] or 0
    
    c.execute("SELECT categoria, SUM(valor) FROM gastos WHERE substr(data,1,7)=? GROUP BY categoria ORDER BY SUM(valor) DESC", 
             (mes_atual,))
    gastos_por_categoria = c.fetchall()
    
    insights = []
    
    if gastos_por_categoria:
        categoria_maior = gastos_por_categoria[0]
        insights.append(f"💡 Sua maior despesa este mês foi em {categoria_maior[0]}: R$ {categoria_maior[1]:.2f}")
    
    # Previsão com ML
    if predictor_ml.analisar_historico(conn):
        previsao, tendencia = predictor_ml.prever_proximos_dias(7)
        if previsao:
            if tendencia > 5:
                insights.append(f"📈 Tendência de alta: seus gastos aumentaram {tendencia:.1f}% na última semana")
            elif tendencia < -5:
                insights.append(f"📉 Tendência de baixa: seus gastos diminuíram {abs(tendencia):.1f}% na última semana")
            
            insights.append(f"🔮 Previsão para próxima semana: R$ {previsao:.2f}")
    
    # Recomendações com ML
    recomendacoes_ml = recomendador_ml.obter_recomendacoes(2)
    insights.extend(recomendacoes_ml)
    
    return insights

@app.route("/whatsapp", methods=["POST"])
def whatsapp_bot():
    try:
        msg_recebida = request.form.get('Body')
        numero = request.form.get('From')
        resposta = MessagingResponse()

        conn = sqlite3.connect(db_file)
        c = conn.cursor()
        
        # Recupera histórico de intenções para ML contextual
        c.execute("SELECT ultima_intencao FROM contexto WHERE numero = ? ORDER BY timestamp DESC LIMIT 10", (numero,))
        historico_intencoes = [row[0] for row in c.fetchall() if row[0]]
        
        # Processa a mensagem com ML
        intencao = analisar_intencao_com_ml(msg_recebida, historico_intencoes)
        ultima_intencao, contexto = recuperar_contexto(numero)
        
        # Extrai dados da mensagem
        valor = extrair_valor(msg_recebida)
        descricao = extrair_descricao(msg_recebida)
        
        # Sistema de diálogo com ML
        if intencao == "saudacao":
            saudacoes = ["Olá! 👋", "Oi! 😊", "E aí! 👍", "Hello! 👋"]
            resposta.message(f"{random.choice(saudacoes)} Sou seu assistente financeiro com IA. Como posso ajudar?")
            
        elif intencao == "adicionar_gasto":
            if valor:
                # Usa ML para categorização
                categoria = categorizador_ml.prever_categoria(descricao) if descricao else "outros"
                
                if not descricao:
                    salvar_contexto(numero, "aguardando_descricao", {"valor": valor})
                    resposta.message(f"💵 Valor identificado: R$ {valor:.2f}. Por favor, digite a descrição deste gasto.")
                else:
                    hoje = datetime.now().isoformat()
                    c.execute("INSERT INTO gastos (valor, descricao, categoria, data) VALUES (?, ?, ?, ?)",
                             (valor, descricao, categoria, hoje))
                    conn.commit()
                    
                    # Atualiza modelos ML com novo dado
                    categorizador_ml.treinar_com_dados(conn)
                    
                    insights = gerar_insights_ml(conn, numero)
                    msg_insights = "\n".join(insights) if insights else ""
                    
                    resposta.message(f"✅ Gasto de R$ {valor:.2f} adicionado em {categoria}: {descricao}\n\n{msg_insights}")
            else:
                resposta.message("Não consegui identificar o valor. Por favor, digite algo como:\n'Gastei 50 reais no almoço'")
        
        elif intencao == "consultar_gastos":
            c.execute("SELECT id, valor, descricao, categoria, data FROM gastos ORDER BY data DESC, id DESC LIMIT 10")
            gastos = c.fetchall()
            
            if gastos:
                msg = "📋 Seus últimos 10 gastos:\n\n"
                total = 0
                
                for id_gasto, v, d, cat, dt in gastos:
                    data_formatada = formatar_data(dt)
                    msg += f"• #{id_gasto} | {data_formatada} | {cat} | R$ {v:.2f} - {d}\n"
                    total += v
                
                msg += f"\n💰 Total: R$ {total:.2f}"
                msg += f"\n\n🗑️ Para remover um gasto, digite 'remover X' (onde X é o número do gasto)"
                resposta.message(msg)
            else:
                resposta.message("Nenhum gasto registrado ainda.")
        
        elif intencao == "resumo_financeiro":
            # Gera relatório com insights de ML
            insights = gerar_insights_ml(conn, numero)
            
            mes_atual = datetime.now().strftime("%Y-%m")
            c.execute("SELECT SUM(valor) FROM gastos WHERE substr(data,1,7)=?", (mes_atual,))
            total_mes = c.fetchone()[0] or 0
            
            c.execute("SELECT categoria, SUM(valor) FROM gastos WHERE substr(data,1,7)=? GROUP BY categoria", 
                     (mes_atual,))
            gastos_categorias = c.fetchall()
            
            msg = f"📊 Resumo Financeiro - {mes_atual}\n\n"
            msg += f"💰 Total gasto: R$ {total_mes:.2f}\n\n"
            
            if gastos_categorias:
                msg += "📈 Por categoria:\n"
                for cat, val in gastos_categorias:
                    percentual = (val / total_mes * 100) if total_mes > 0 else 0
                    msg += f"• {cat}: R$ {val:.2f} ({percentual:.1f}%)\n"
            
            if insights:
                msg += f"\n🔍 Insights de IA:\n" + "\n".join(insights)
            
            resposta.message(msg)
        
        elif intencao == "previsao_gastos":
            if predictor_ml.analisar_historico(conn):
                previsao_7_dias, tendencia = predictor_ml.prever_proximos_dias(7)
                previsao_30_dias, _ = predictor_ml.prever_proximos_dias(30)
                
                msg = "🔮 Previsão de Gastos (Machine Learning)\n\n"
                msg += f"📊 Próximos 7 dias: R$ {previsao_7_dias:.2f}\n"
                msg += f"📅 Próximos 30 dias: R$ {previsao_30_dias:.2f}\n"
                
                if tendencia > 5:
                    msg += f"📈 Tendência: Alta ({tendencia:.1f}%)\n"
                elif tendencia < -5:
                    msg += f"📉 Tendência: Baixa ({abs(tendencia):.1f}%)\n"
                else:
                    msg += f"📊 Tendência: Estável ({tendencia:.1f}%)\n"
                
                # Adiciona recomendações baseadas na previsão
                if previsao_30_dias > 1000:
                    msg += "\n💡 Recomendação: Considere revisar gastos não essenciais"
                elif previsao_30_dias < 500:
                    msg += "\n💡 Recomendação: Bom controle financeiro!"
                
                resposta.message(msg)
            else:
                resposta.message("📊 Preciso de mais dados para fazer previsões precisas. Continue registrando seus gastos!")
        
        elif intencao == "treinar_ml":
            dados_treinados = categorizador_ml.treinar_com_dados(conn)
            predictor_ml.analisar_historico(conn)
            recomendador_ml.analisar_padroes(conn)
            
            resposta.message(f"🤖 Modelos de ML treinados com {dados_treinados} registros!\n\nSistema de IA atualizado e melhorado.")
        
        elif intencao == "buscar_gastos":
            termos = re.sub(r'(buscar|procurar|encontrar|filtrar|pesquisar)', '', msg_recebida, flags=re.IGNORECASE)
            termos = termos.strip()
            
            if termos:
                c.execute("SELECT id, valor, descricao, categoria, data FROM gastos WHERE descricao LIKE ? OR categoria LIKE ? ORDER BY data DESC", 
                         (f'%{termos}%', f'%{termos}%'))
                gastos = c.fetchall()
                
                if gastos:
                    msg = f"🔍 Gastos encontrados com '{termos}':\n\n"
                    total = 0
                    
                    for id_gasto, v, d, cat, dt in gastos:
                        data_formatada = formatar_data(dt)
                        msg += f"• #{id_gasto} | {data_formatada} | {cat} | R$ {v:.2f} - {d}\n"
                        total += v
                    
                    msg += f"\n💰 Total: R$ {total:.2f}"
                    msg += f"\n\n🗑️ Para remover um gasto, digite 'remover X' (onde X é o número do gasto)"
                    resposta.message(msg)
                else:
                    resposta.message(f"Nenhum gasto encontrado com '{termos}'.")
            else:
                resposta.message("Por favor, digite o que deseja buscar. Ex: 'buscar gastos com mercado'")
        
        elif intencao == "remover_gasto":
            id_gasto = extrair_id_remocao(msg_recebida)
            
            if id_gasto:
                sucesso, gasto = remover_gasto(conn, id_gasto)
                
                if sucesso:
                    id_removido, valor_removido, descricao_removida = gasto
                    resposta.message(f"🗑️ Gasto removido com sucesso!\n\nID: #{id_removido}\nValor: R$ {valor_removido:.2f}\nDescrição: {descricao_removida}")
                else:
                    resposta.message(f"❌ Não foi encontrado nenhum gasto com o ID #{id_gasto}.\n\nDigite 'listar' para ver seus gastos disponíveis.")
            else:
                gastos = listar_gastos_para_remocao(conn)
                
                if gastos:
                    msg = "📋 Seus últimos gastos (com IDs):\n\n"
                    
                    for id_gasto, v, d, cat, dt in gastos:
                        data_formatada = formatar_data(dt)
                        msg += f"• #{id_gasto} | {data_formatada} | {cat} | R$ {v:.2f} - {d}\n"
                    
                    msg += f"\n🗑️ Para remover um gasto, digite 'remover X' (onde X é o número do gasto)"
                    resposta.message(msg)
                else:
                    resposta.message("Nenhum gasto registrado para remover.")
        
        elif intencao == "ajuda":
            resposta.message(
                "🤖 *Assistente Financeiro com IA* 🤖\n\n"
                "💳 *Registrar Gastos:*\n"
                "- 'Gastei 50 no almoço'\n- 'Adicionar 30 de transporte'\n\n"
                "📊 *Consultas e Análises:*\n"
                "- 'Mostrar meus gastos'\n- 'Resumo financeiro'\n- 'Previsão de gastos'\n\n"
                "🔮 *Machine Learning:*\n"
                "- 'Previsão próxima semana'\n- 'Treinar IA'\n- 'Onde gastei mais?'\n\n"
                "🗑️ *Gerenciar Gastos:*\n"
                "- 'Remover gasto 5'\n- 'Excluir gasto 3'\n\n"
                "🎯 *Controle Financeiro:*\n"
                "- 'Definir orçamento para alimentação'\n- 'Criar meta de viagem'\n\n"
                "💡 *Dica:* Quanto mais você usar, mais inteligente eu fico!"
            )
        
        else:
            respostas_nao_reconhecidas = [
                "Desculpe, não entendi. Pode reformular?",
                "Não consegui processar sua solicitação. Pode tentar de outra forma?",
                "Hmm, não sei como ajudar com isso. Que tal um comando diferente?",
            ]
            resposta.message(f"{random.choice(respostas_nao_reconhecidas)}\n\nDigite 'ajuda' para ver o que posso fazer.")
        
        # Salva o contexto da conversa
        salvar_contexto(numero, intencao)
        
        conn.close()
        return str(resposta)
    
    except Exception as e:
        print(f"Erro: {str(e)}")
        resposta = MessagingResponse()
        resposta.message("😕 Ocorreu um erro inesperado. Por favor, tente novamente.")
        return str(resposta)

if __name__ == "__main__":
    # Treina modelos ML inicialmente
    conn = sqlite3.connect(db_file)
    categorizador_ml.treinar_com_dados(conn)
    predictor_ml.analisar_historico(conn)
    recomendador_ml.analisar_padroes(conn)
    conn.close()
    
    app.run(debug=True, port=5000)
