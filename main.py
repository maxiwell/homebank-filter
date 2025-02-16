#!/bin/env python3
# -*- coding: utf-8 -*-

import click
import xml.etree.ElementTree as ET
import numpy as np
import pyparsing as pp
import sys
import csv
import json

from filters import get_query_by_filter_name

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


def comparar_datas(data1: str, data2: str) -> str:
    formato = "%d/%m/%Y"
    dt1 = datetime.strptime(data1, formato)
    dt2 = datetime.strptime(data2, formato)

    """
    data2 > data1 = positivo
    data1 > data2 = negativo
    data1 = data2 = igual
    """
    return (dt2 - dt1).days

def carregar_dados(arquivo):
    try:
        tree = ET.parse(arquivo)
        root = tree.getroot()
        return root
    except Exception as e:
        print(f"Erro ao carregar arquivo: {e}")
        return None

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

def calculate_totalizer(key, context, totalizer):
    total_by_key = totalizer.get(key, {})
    key_value = context[key]
    total_by_key[key_value] = total_by_key.get(key_value, 0) + float(context['valor'])
    return total_by_key

def run_query(root, query):
    parser = criar_parser()
    try:
        parsed_query = parser.parseString(query, parseAll=True)[0]
    except pp.ParseException as e:
        print(f"Erro ao interpretar query: {e}")
        return [], {}

    all_transactions = []
    totalizer = {}
    for trans in root.findall("ope"):
        if avaliar_expressao(trans, root, parsed_query):
            context = get_contexto(trans, root)
            all_transactions.append(context)

            totalizer['total_transacoes'] = totalizer.get('total_transacoes', 0) + 1
            totalizer['total_valor'] = totalizer.get('total_valor', 0) + float(context['valor'])

            totalizer['total_categoria'] = calculate_totalizer('categoria', context, totalizer)
            totalizer['total_account'] = calculate_totalizer('account', context, totalizer)

    return all_transactions, totalizer

def convert_to_csv(dados, arquivo_csv):
    # Escrevendo os dados no arquivo CSV
    with open(arquivo_csv, mode='w', newline='', encoding='utf-8') as arquivo:
        escritor_csv = csv.DictWriter(arquivo, fieldnames=dados[0].keys())
        escritor_csv.writeheader()
        escritor_csv.writerows(dados)

    print(f"Arquivo '{arquivo_csv}' gerado com sucesso!")

def select_columns(all_transactions, columns):
    ret_trans = []
    columns_to_show = columns.split(",") if columns else None
    if columns_to_show:
        for i in all_transactions:
            i_selected_columns = {}
            for col in columns_to_show:
                try:
                    col = col.strip()
                    i_selected_columns[col] = i[col]
                except KeyError:
                    print(f"Columns'{col}' not found!")
                    sys.exit(1)

            ret_trans.append(i_selected_columns)
    else:
        ret_trans = all_transactions

    return ret_trans


def load_xhb_file(file):
    root = carregar_dados(file)

    if root is None:
        print("homebank xhb file is empty")
        sys.exit(1)

    return root

@click.command()
@click.option('-l', "--list", default=None, is_flag=True, help="List all saved filters")
@click.option('-f', "--filter", help="Saved filter to apply")
@click.option('-q', "--query", help="JQL like query to filter transactions")
@click.option('-c', "--columns", help="Columns to show in the output")
@click.option('--csv', help="Save the output in a csv file")
def commands(list, filter, query, columns, csv):

    if filter is not None:
        query = get_query_by_filter_name(filter)

    if query is not None:
        query = query

    if list is not None:
        for key, value in get_query_by_filter_name(None).items():
            print(f"{key}:\n    {value}\n")
        sys.exit(0)

    if columns:
        if not query and not filter:
            raise click.UsageError("Mandatory '-f' or '-q' with '-c'")
            sys.exit(1)

    root = load_xhb_file("Gastos.xhb")

    print('query:', query)
    trans, amount_totalized = run_query(root, query)
    trans = select_columns(trans, columns)

    if csv is not None:
        convert_to_csv(trans, csv)
    else:
        for i in trans:
            print(i)

    print(json.dumps(amount_totalized, indent=4, ensure_ascii=False))


if __name__ == '__main__':
    if (len(sys.argv) < 2):
        print("usage: main.py --help")
        sys.exit(1)

    commands()
