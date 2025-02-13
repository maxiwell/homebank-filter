import xml.etree.ElementTree as ET
import numpy as np
import pyparsing as pp
import sys

def carregar_dados(arquivo):
    try:
        tree = ET.parse(arquivo)
        root = tree.getroot()
        return root
    except Exception as e:
        print(f"Erro ao carregar arquivo: {e}")
        return None

def criar_parser():
    campo = pp.oneOf("descricao valor categoria")
    operador = pp.oneOf("= >= <= < > == != <> ~")
    not_op = pp.oneOf("NOT not !")
    and_op = pp.oneOf("AND and")
    or_op = pp.oneOf("OR or")
    valor_str = pp.QuotedString("'")
    valor_num = pp.Word(pp.nums + ".").setParseAction(lambda t: float(t[0]))
    valor = valor_str | valor_num
    expressao = pp.Group(campo + operador + valor)

    condicao = pp.infixNotation(expressao, [
        (not_op, 1, pp.opAssoc.RIGHT),
        (and_op, 2, pp.opAssoc.LEFT),
        (or_op, 2, pp.opAssoc.LEFT),
        (operador, 2, pp.opAssoc.LEFT)
    ], lpar=pp.Suppress("("), rpar=pp.Suppress(")"))

    return condicao


def get_contexto(transacao, root):
    descricao_trans = transacao.get("wording", "").lower()
    valor = transacao.get("amount", "")
    categoria = transacao.get("category", "")

    cat = root.find(f".//cat[@key='{categoria}']")
    if cat is not None:
        categoria = cat.get("name")

    return {"categoria": categoria,
            "descricao": descricao_trans,
            "valor": valor}


def avaliar_expressao(transacao, root, parsed_query):
    contexto = get_contexto(transacao, root)

    def avaliar(parsed):

        # stop condition
        if (np.isscalar(parsed)):
            return parsed

        while (len(parsed) > 3):
            parsed = parsed[0:2] + [avaliar(parsed[2:])]

        if (len(parsed) == 3):
            op_esq, operador, op_dir = parsed
        elif (len(parsed) == 2):
            operador, op_dir = parsed

        # special operators
        if operador.upper == "NOT" or operador == "!":
            return not avaliar(op_dir)
        elif operador.upper() == "AND":
            return avaliar(op_esq) and avaliar(op_dir)
        elif operador.upper() == "OR":
            return avaliar(op_esq) or avaliar(op_dir)

        campo_valor = contexto.get(op_esq, "")
        if (isinstance(op_dir, float)):
            campo_valor = float(campo_valor)

        if operador == "~":
            return op_dir.lower() in campo_valor
        elif operador == "=" or operador == "==":
            return campo_valor == op_dir
        elif operador == "!=" or operador == "<>":
            return campo_valor != op_dir
        elif operador == ">=":
            return campo_valor >= op_dir
        elif operador == "<=":
            return campo_valor <= op_dir
        elif operador == ">":
            return campo_valor > op_dir
        elif operador == "<":
            return campo_valor < op_dir

        return False

    return avaliar(parsed_query)

def buscar_transacoes(root, query):
    parser = criar_parser()
    try:
        parsed_query = parser.parseString(query, parseAll=True)[0]
    except pp.ParseException as e:
        print(f"Erro ao interpretar query: {e}")
        return []

    transacoes = []
    for transacao in root.findall("ope"):
        if avaliar_expressao(transacao, root, parsed_query):
            transacoes.append(get_contexto(transacao, root))

    return transacoes

if __name__ == "__main__":
    query = sys.argv[1]
    arquivo = "Gastos.xhb"  # Substitua pelo caminho correto do arquivo
    root = carregar_dados(arquivo)

    if root is not None:
        # Exemplo de consulta JQL-like
        #query = "((descricao ~ 'pix' AND valor >= 150) AND valor <= 200)"
        #query = "(descricao ~ 'pix' AND (valor == 15 OR valor == 200)) AND NOT descricao ~ 'guilher'"
        resultado = buscar_transacoes(root, query)
        for r in resultado:
            print(r)
