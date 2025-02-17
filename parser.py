import numpy as np
import pyparsing as pp
import sys
import csv
import json
from datetime import datetime, timedelta

# Converte um timestamp baseado em dias desde 0000-01-01 para uma data no formato YYYY-MM-DD.
def ts_to_date(timestamp: int, formato) -> str:

    # O Python começa em 0001-01-01
    base_date = datetime(1, 1, 1)

    # -1 para compesar a diferenca entre o padrao do MATLAB e do Python
    converted_date = base_date + timedelta(days=timestamp - 1)
    return converted_date.strftime(formato)


def date_to_ts(date) -> int:
    # O Python começa em 0001-01-01
    base_date = datetime(1, 1, 1)

    formatos = ["%d/%m/%Y", "%m/%Y", "%Y"]
    for formato in formatos:
        try:
            ts = datetime.strptime(date, formato)
            # -1 para compesar a diferenca entre o padrao do MATLAB e do Python
            converted_date = (ts - base_date).days - 1
            return converted_date
        except ValueError:
            continue
    raise ValueError(f"Formato de data inválido: {date}")


def criar_parser():
    campo = pp.oneOf("descricao valor categoria data tags account")

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
    account = transacao.get("account", "")
    categoria = transacao.get("category", "")
    date = transacao.get("date", "")
    tags = transacao.get("tags", "")

    date = ts_to_date(int(date), "%d/%m/%Y")

    cat = root.find(f".//cat[@key='{categoria}']")
    if cat is not None:
        categoria = cat.get("name")
        parent = cat.get("parent", None)
        if parent is not None:
            categoria = root.find(f".//cat[@key='{parent}']").get("name") + ":" + categoria

    acc = root.find(f".//account[@key='{account}']")
    if acc is not None:
        account = acc.get("name")

    return {"data": date,
            "account": account,
            "categoria": categoria,
            "descricao": descricao_trans,
            "valor": valor,
            "tags": tags}


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
        if operador.upper() == "NOT" or operador == "!":
            return not avaliar(op_dir)
        elif operador.upper() == "AND":
            return avaliar(op_esq) and avaliar(op_dir)
        elif operador.upper() == "OR":
            return avaliar(op_esq) or avaliar(op_dir)

        # campo_valor has the right side value from homebank file
        campo_valor = contexto.get(op_esq, "")

        # semantic exceptions
        if (op_esq == "data"):
            campo_valor = date_to_ts(campo_valor)
            op_dir      = date_to_ts(op_dir)
        elif (isinstance(op_dir, float)):
            campo_valor = float(campo_valor)
        else:
            campo_valor = campo_valor.lower()
            op_dir = op_dir.lower()

        if operador == "~":
            return op_dir in campo_valor
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