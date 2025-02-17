#!/bin/env python3
# -*- coding: utf-8 -*-

import click
import xml.etree.ElementTree as ET
import json
import sys

from parser import criar_parser, avaliar_expressao, get_contexto
from datetime import datetime, timedelta

def carregar_dados(arquivo):
    try:
        tree = ET.parse(arquivo)
        root = tree.getroot()
        return root
    except Exception as e:
        print(f"Erro ao carregar arquivo: {e}")
        return None

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
    totalizers = {}
    for trans in root.findall("ope"):
        if avaliar_expressao(trans, root, parsed_query):
            context = get_contexto(trans, root)
            all_transactions.append(context)

            totalizers['transacao'] = totalizers.get('transacao', 0) + 1
            totalizers['valor'] = totalizers.get('valor', 0) + float(context['valor'])

            totalizers['categoria'] = calculate_totalizer('categoria', context, totalizers)
            totalizers['account'] = calculate_totalizer('account', context, totalizers)

    return all_transactions, totalizers

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

def get_query_by_filter_name(filter_name):
    json_file = "filters.json"
    filters = {}

    try:
        with open(json_file, "r") as f:
            filters = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        printf(f"Error loading filters from {json_file}: {e}")

    return filters.get(filter_name, filters) 

@click.command()
@click.option('-l', "--list", default=None, is_flag=True, help="List all saved filters")
@click.option('-f', "--filter", help="Saved filter to apply")
@click.option('-q', "--query", help="JQL like query to filter transactions")
@click.option('-a', "--append", help="Append more conditions in the filter called by '-f'")
@click.option('-c', "--columns", help="Columns to show in the output")
@click.option('--csv', help="Save the output in a csv file")
def commands(list, filter, append, query, columns, csv):

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

    if append:
        if not filter:
            raise click.UsageError("Mandatory '-f' with '-a'")
            sys.exit(1)

        query = '(' + query + ')' + append

    root = load_xhb_file("Gastos.xhb")

    print('query:', query)
    trans, totalizers = run_query(root, query)
    trans = select_columns(trans, columns)

    if csv is not None:
        convert_to_csv(trans, csv)
    else:
        for i in trans:
            print(i)

    print("Totalizers:")
    print(json.dumps(totalizers, indent=4, ensure_ascii=False))


if __name__ == '__main__':
    if (len(sys.argv) < 2):
        print("usage: main.py --help")
        sys.exit(1)

    commands()
