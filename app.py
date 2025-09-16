from flask import Flask, request
from twilio.twiml.messaging_response import MessagingResponse
import sqlite3
import os
import datetime
import re
import json
import random
from datetime import datetime, timedelta

app = Flask(__name__)
db_file = "gastos_avancado.db"

# Inicializa o banco com mais tabelas
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
                 metodo_pagamento TEXT
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
    
    conn.commit()
    conn.close()

init_db()

# Sistema de categorização automática
CATEGORIAS = {
    'alimentação': ['comida', 'restaurante', 'lanche', 'mercado', 'supermercado', 'padaria', 
                   'almoço', 'janta', 'jantar', 'café', 'ifood', 'uber eats'],
    'transporte': ['ônibus', 'busão', 'metro', 'uber', '99', 'taxi', 'gasolina', 'combustível', 
                  'estacionamento', 'pedágio', 'manutenção', 'oficina'],
    'moradia': ['aluguel', 'condomínio', 'luz', 'energia', 'água', 'internet', 'telefone', 
               'netflix', 'spotify', 'streaming', 'assinatura'],
    'saúde': ['farmacia', 'farmácia', 'remédio', 'médico', 'dentista', 'plano de saúde', 
             'hospital', 'clinica', 'academia', 'suplemento'],
    'entretenimento': ['cinema', 'shopping', 'bar', 'balada', 'show', 'festival', 'viagem', 
                      'hobby', 'jogo', 'livro', 'curso'],
    'vestuário': ['roupa', 'calça', 'camisa', 'tenis', 'sapato', 'loja', 'shopping', 'moda'],
    'educação': ['livro', 'curso', 'faculdade', 'escola', 'material', 'aula', 'workshop']
}

# Função para categorizar automaticamente
def categorizar_gasto(descricao):
    descricao = descricao.lower()
    for categoria, palavras_chave in CATEGORIAS.items():
        for palavra in palavras_chave:
            if palavra in descricao:
                return categoria
    return "outros"

# Função para formatar data (trata tanto datas simples quanto ISO completas)
def formatar_data(data_str):
    try:
        # Tenta parse como data ISO completa (com hora)
        if 'T' in data_str:
            dt = datetime.fromisoformat(data_str.replace('Z', '+00:00'))
            return dt.strftime("%d/%m/%Y")
        else:
            # Tenta parse como data simples (YYYY-MM-DD)
            dt = datetime.strptime(data_str, "%Y-%m-%d")
            return dt.strftime("%d/%m/%Y")
    except (ValueError, AttributeError):
        # Se falhar, retorna a string original
        return data_str

# Sistema de NLP avançado com múltiplas intenções
def analisar_intencao(mensagem):
    mensagem = mensagem.lower().strip()
    
    # Padrões complexos com regex
    padroes = {
        'saudacao': r'\b(oi|olá|ola|eae|hey|hello|como vai|tudo bem)\b',
        'adicionar_gasto': r'\b(gastei|gasto|gastar|adicionar|add|registrar|comprei|paguei|investi|r\$|reais|valor|preço)\b',
        'consultar_gastos': r'\b(ver|mostrar|listar|consultar|visualizar|gastos|despesas|compras)\b',
        'resumo_financeiro': r'\b(total|soma|resumo|quanto gastei|extrato|finanças|financeiro)\b',
        'buscar_gastos': r'\b(buscar|procurar|encontrar|filtrar|pesquisar|onde gastei)\b',
        'definir_orcamento': r'\b(orçamento|orcamento|limite|definir|estabelecer|máximo|controlar)\b',
        'definir_meta': r'\b(meta|objetivo|poupar|economizar|guardar|sonho|conseguir|alcançar)\b',
        'analise_categoria': r'\b(categoria|categorias|por tipo|por área|onde mais gasto)\b',
        'previsao_gastos': r'\b(previsão|previsao|futuro|próximo|próximos|esperar|projeção)\b',
        'comparativo_mensal': r'\b(comparar|mês|meses|variação|variaçao|evolução|evolucao)\b',
        'recomendacao': r'\b(dica|sugestão|sugestao|recomendação|recomendacao|como economizar|economia)\b',
        'configuracao': r'\b(configurar|preferências|preferencias|alterar|mudar|personalizar)\b',
        'remover_gasto': r'\b(remover|excluir|deletar|apagar|eliminar|retirar|cancelar)\b',
        'ajuda': r'\b(ajuda|help|comandos|o que você faz|funcionalidades|como usar)\b'
    }
    
    # Verifica qual padrão corresponde
    for intencao, padrao in padroes.items():
        if re.search(padrao, mensagem, re.IGNORECASE):
            return intencao
    
    # Extrai valor para detectar intenção implícita de adicionar gasto
    if extrair_valor(mensagem):
        return "adicionar_gasto"
    
    return "desconhecido"

# Função para extrair valor (mais avançada)
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

# Função para extrair descrição
def extrair_descricao(texto):
    # Remove números, palavras relacionadas a valor e comandos
    texto_limpo = re.sub(r'\d+[\.,]?\d*', '', texto)
    texto_limpo = re.sub(r'r\$|reais|valor|gastei|gasto|adicionar|add|registrar', '', texto_limpo, flags=re.IGNORECASE)
    texto_limpo = re.sub(r'\s+', ' ', texto_limpo).strip()
    
    # Remove preposições e artigos comuns
    palavras_remover = ['no', 'na', 'em', 'de', 'do', 'da', 'com', 'por', 'para', 'um', 'uma']
    palavras = [p for p in texto_limpo.split() if p.lower() not in palavras_remover]
    
    return ' '.join(palavras) if palavras else None

# Função para extrair ID de gasto para remoção
def extrair_id_remocao(texto):
    # Procura por padrões como "remover 1", "excluir id 5", etc.
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

# Função para salvar contexto da conversa
def salvar_contexto(numero, intencao, dados=None):
    conn = sqlite3.connect(db_file)
    c = conn.cursor()
    
    dados_json = json.dumps(dados) if dados else None
    
    # Verifica se já existe contexto para este número
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

# Função para recuperar contexto
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

# Função para listar gastos com IDs para remoção
def listar_gastos_para_remocao(conn, limite=10):
    c = conn.cursor()
    c.execute("SELECT id, valor, descricao, categoria, data FROM gastos ORDER BY data DESC, id DESC LIMIT ?", (limite,))
    gastos = c.fetchall()
    return gastos

# Função para remover gasto por ID
def remover_gasto(conn, id_gasto):
    c = conn.cursor()
    
    # Primeiro verifica se o gasto existe
    c.execute("SELECT id, valor, descricao FROM gastos WHERE id = ?", (id_gasto,))
    gasto = c.fetchone()
    
    if gasto:
        # Remove o gasto
        c.execute("DELETE FROM gastos WHERE id = ?", (id_gasto,))
        conn.commit()
        return True, gasto
    else:
        return False, None

# Sistema de análise e insights
def gerar_insights(conn, numero):
    c = conn.cursor()
    
    # Gastos do mês atual
    mes_atual = datetime.now().strftime("%Y-%m")
    c.execute("SELECT SUM(valor) FROM gastos WHERE substr(data,1,7)=?", (mes_atual,))
    total_mes = c.fetchone()[0] or 0
    
    # Gastos por categoria
    c.execute("SELECT categoria, SUM(valor) FROM gastos WHERE substr(data,1,7)=? GROUP BY categoria ORDER BY SUM(valor) DESC", 
             (mes_atual,))
    gastos_por_categoria = c.fetchall()
    
    # Comparativo com mês anterior
    mes_anterior = (datetime.now().replace(day=1) - timedelta(days=1)).strftime("%Y-%m")
    c.execute("SELECT SUM(valor) FROM gastos WHERE substr(data,1,7)=?", (mes_anterior,))
    total_mes_anterior = c.fetchone()[0] or 0
    
    # Geração de insights
    insights = []
    
    if gastos_por_categoria:
        categoria_maior = gastos_por_categoria[0]
        insights.append(f"💡 Sua maior despesa este mês foi em {categoria_maior[0]}: R$ {categoria_maior[1]:.2f}")
    
    if total_mes_anterior > 0:
        variacao = ((total_mes - total_mes_anterior) / total_mes_anterior) * 100
        if variacao > 0:
            insights.append(f"📈 Seus gastos aumentaram {variacao:.1f}% em relação ao mês anterior")
        else:
            insights.append(f"📉 Seus gastos diminuíram {abs(variacao):.1f}% em relação ao mês anterior")
    
    # Verifica orçamentos
    c.execute("SELECT categoria, limite_mensal FROM orcamentos WHERE mes_ano=?", (mes_atual,))
    orcamentos = c.fetchall()
    
    for categoria, limite in orcamentos:
        c.execute("SELECT SUM(valor) FROM gastos WHERE categoria=? AND substr(data,1,7)=?", 
                 (categoria, mes_atual))
        gasto_categoria = c.fetchone()[0] or 0
        
        if gasto_categoria > limite:
            percentual = (gasto_categoria / limite) * 100
            insights.append(f"⚠️ Você excedeu o orçamento de {categoria} em {percentual:.1f}%!")
        elif gasto_categoria > limite * 0.8:
            insights.append(f"🔔 Você está perto de atingir o limite de {categoria}")
    
    return insights

# Sistema de recomendações personalizadas
def gerar_recomendacoes(conn, numero):
    c = conn.cursor()
    
    # Análise de padrões de gastos
    c.execute("SELECT categoria, SUM(valor) FROM gastos GROUP BY categoria ORDER BY SUM(valor) DESC")
    categorias = c.fetchall()
    
    recomendacoes = []
    
    if categorias:
        categoria_maior = categorias[0][0]
        recomendacoes.append(f"💡 Considere reduzir gastos com {categoria_maior}, sua maior categoria de despesas")
    
    # Verifica gastos frequentes
    c.execute("SELECT descricao, COUNT(*) as freq FROM gastos GROUP BY descricao HAVING freq > 3 ORDER BY freq DESC")
    gastos_frequentes = c.fetchall()
    
    if gastos_frequentes:
        recomendacoes.append("💡 Você tem alguns gastos muito frequentes. Avalie si são realmente necessários")
    
    # Sugestões genéricas
    sugestoes = [
        "💡 Experimente definir orçamentos por categoria para controlar melhor seus gastos",
        "💡 Estabeleça metas financeiras para manter o foco em seus objetivos",
        "💡 Revise assinaturas e serviços recorrentes - você realmente usa todos?",
        "💡 Compare preços antes de compras importantes para economizar"
    ]
    
    recomendacoes.extend(random.sample(sugestoes, 2))
    
    return recomendacoes

@app.route("/whatsapp", methods=["POST"])
def whatsapp_bot():
    try:
        msg_recebida = request.form.get('Body')
        numero = request.form.get('From')
        resposta = MessagingResponse()

        conn = sqlite3.connect(db_file)
        c = conn.cursor()
        
        # Processa a mensagem com NLP avançado
        intencao = analisar_intencao(msg_recebida)
        ultima_intencao, contexto = recuperar_contexto(numero)
        
        # Extrai valor e descrição se relevantes
        valor = extrair_valor(msg_recebida)
        descricao = extrair_descricao(msg_recebida)
        
        # Sistema de diálogo contextual
        if intencao == "saudacao":
            saudacoes = ["Olá! 👋", "Oi! 😊", "E aí! 👍", "Hello! 👋"]
            resposta.message(f"{random.choice(saudacoes)} Sou seu assistente financeiro inteligente. Como posso ajudar?")
            
        elif intencao == "adicionar_gasto":
            if valor:
                categoria = categorizar_gasto(descricao) if descricao else "outros"
                
                if not descricao:
                    # Pede descrição se não foi fornecida
                    salvar_contexto(numero, "aguardando_descricao", {"valor": valor})
                    resposta.message(f"💵 Valor identificado: R$ {valor:.2f}. Por favor, digite a descrição deste gasto.")
                else:
                    # Adiciona o gasto completo
                    hoje = datetime.now().isoformat()
                    c.execute("INSERT INTO gastos (valor, descricao, categoria, data) VALUES (?, ?, ?, ?)",
                             (valor, descricao, categoria, hoje))
                    conn.commit()
                    
                    # Gera insights após adicionar gasto
                    insights = gerar_insights(conn, numero)
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
            # Resumo do mês atual
            mes_atual = datetime.now().strftime("%Y-%m")
            c.execute("SELECT SUM(valor) FROM gastos WHERE substr(data,1,7)=?", (mes_atual,))
            total_mes = c.fetchone()[0] or 0
            
            # Gastos por categoria
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
            
            # Adiciona insights
            insights = gerar_insights(conn, numero)
            if insights:
                msg += f"\n🔍 Insights:\n" + "\n".join(insights)
            
            resposta.message(msg)
        
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
        
        elif intencao == "analise_categoria":
            c.execute("SELECT categoria, SUM(valor) FROM gastos GROUP BY categoria ORDER BY SUM(valor) DESC")
            categorias = c.fetchall()
            
            if categorias:
                msg = "📊 Análise por Categoria:\n\n"
                total_geral = sum(val for _, val in categorias)
                
                for cat, val in categorias:
                    percentual = (val / total_geral * 100) if total_geral > 0 else 0
                    msg += f"• {cat}: R$ {val:.2f} ({percentual:.1f}%)\n"
                
                resposta.message(msg)
            else:
                resposta.message("Nenhum gasto registrado para análise.")
        
        elif intencao == "remover_gasto":
            # Tenta extrair o ID do gasto a ser removido
            id_gasto = extrair_id_remocao(msg_recebida)
            
            if id_gasto:
                # Tenta remover o gasto
                sucesso, gasto = remover_gasto(conn, id_gasto)
                
                if sucesso:
                    id_removido, valor_removido, descricao_removida = gasto
                    resposta.message(f"🗑️ Gasto removido com sucesso!\n\nID: #{id_removido}\nValor: R$ {valor_removido:.2f}\nDescrição: {descricao_removida}")
                else:
                    resposta.message(f"❌ Não foi encontrado nenhum gasto com o ID #{id_gasto}.\n\nDigite 'listar' para ver seus gastos disponíveis.")
            else:
                # Se não encontrou ID, lista os gastos para o usuário escolher
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
        
        elif intencao == "definir_orcamento":
            # Extrai categoria e valor do orçamento
            partes = msg_recebida.split()
            try:
                valor_orcamento = extrair_valor(msg_recebida)
                categoria = None
                
                # Tenta identificar a categoria
                for cat in CATEGORIAS.keys():
                    if cat in msg_recebida.lower():
                        categoria = cat
                        break
                
                if not categoria:
                    categoria = "outros"
                
                mes_ano = datetime.now().strftime("%Y-%m")
                
                # Verifica se já existe orçamento para esta categoria no mês
                c.execute("SELECT id FROM orcamentos WHERE categoria=? AND mes_ano=?", (categoria, mes_ano))
                existe = c.fetchone()
                
                if existe:
                    c.execute("UPDATE orcamentos SET limite_mensal=? WHERE categoria=? AND mes_ano=?", 
                             (valor_orcamento, categoria, mes_ano))
                else:
                    c.execute("INSERT INTO orcamentos (categoria, limite_mensal, mes_ano) VALUES (?, ?, ?)",
                             (categoria, valor_orcamento, mes_ano))
                
                conn.commit()
                resposta.message(f"✅ Orçamento de R$ {valor_orcamento:.2f} definido para {categoria} neste mês.")
            except Exception as e:
                resposta.message("Formato inválido. Use: 'definir orçamento de 500 reais para alimentação'")
        
        elif intencao == "definir_meta":
            # Implementação simplificada para metas
            valor_meta = extrair_valor(msg_recebida)
            
            if valor_meta:
                # Extrai descrição da meta
                desc_meta = re.sub(r'\d+[\.,]?\d*|r\$|reais|meta|objetivo', '', msg_recebida, flags=re.IGNORECASE)
                desc_meta = desc_meta.strip()
                
                if not desc_meta:
                    desc_meta = "Economia"
                
                data_limite = (datetime.now() + timedelta(days=30)).isoformat()  # 30 dias padrão
                
                c.execute("INSERT INTO metas (objetivo, valor_alvo, valor_atual, data_limite) VALUES (?, ?, ?, ?)",
                         (desc_meta, valor_meta, 0, data_limite))
                conn.commit()
                
                resposta.message(f"🎯 Meta definida: {desc_meta} - R$ {valor_meta:.2f}\n\nVocê pode acompanhar seu progresso a qualquer momento!")
            else:
                resposta.message("Por favor, especifique o valor da meta. Ex: 'quero economizar 1000 reais para uma viagem'")
        
        elif intencao == "recomendacao":
            recomendacoes = gerar_recomendacoes(conn, numero)
            msg = "💡 Recomendações Personalizadas:\n\n" + "\n".join(recomendacoes)
            resposta.message(msg)
        
        elif intencao == "ajuda":
            resposta.message(
                "🤖 *Assistente Financeiro Inteligente* 🤖\n\n"
                "💳 *Registrar Gastos:*\n"
                "- 'Gastei 50 no almoço'\n- 'Adicionar 30 de transporte'\n- 'Comprei um livro por 25 reais'\n\n"
                "📊 *Consultas e Análises:*\n"
                "- 'Mostrar meus gastos'\n- 'Resumo financeiro'\n- 'Quanto gastei esse mês?'\n"
                "- 'Onde gastei mais?'\n- 'Buscar gastos com mercado'\n\n"
                "🗑️ *Gerenciar Gastos:*\n"
                "- 'Remover gasto 5'\n- 'Excluir gasto 3'\n- 'Listar gastos'\n\n"
                "🎯 *Controle Financeiro:*\n"
                "- 'Definir orçamento de 500 para alimentação'\n- 'Criar meta de 1000 reais'\n"
                "- 'Recomendações para economizar'\n\n"
                "💡 *Dica:* Você pode conversar naturalmente comigo!"
            )
        
        else:
            # Resposta para mensagens não reconhecidas
            respostas_nao_reconhecidas = [
                "Desculpe, não entendi. Pode reformular?",
                "Não consegui processar sua solicitação. Pode tentar de outra forma?",
                "Hmm, não sei como ajudar com isso. Que tal um comando diferente?",
                "Interessante! Mas não tenho essa funcionalidade ainda."
            ]
            resposta.message(f"{random.choice(respostas_nao_reconhecidas)}\n\nDigite 'ajuda' para ver o que posso fazer.")
        
        # Salva o contexto da conversa
        salvar_contexto(numero, intencao)
        
        conn.close()
        return str(resposta)
    
    except Exception as e:
        # Log do erro para debugging
        print(f"Erro: {str(e)}")
        resposta = MessagingResponse()
        resposta.message("😕 Ocorreu um erro inesperado. Por favor, tente novamente.")
        return str(resposta)

if __name__ == "__main__":
    app.run(debug=True, port=5000)
