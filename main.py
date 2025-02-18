#!/bin/env python3
# -*- coding: utf-8 -*-

import click
import xml.etree.ElementTree as ET
import json
import sys
import calendar
import csv
import re

from parser import parse_string, avaliar_expressao, get_contexto
from datetime import datetime, timedelta

def load_data(file):
    try:
        tree = ET.parse(file)
        root = tree.getroot()
        return root
    except Exception as e:
        print(f"Error on load data from {file}: {e}")
        return None

def calculate_totalizer(key, context, totalizer):
    total_by_key = totalizer.get(key, {})
    key_value = context[key]
    total_by_key[key_value] = total_by_key.get(key_value, 0) + float(context['amount'])
    return total_by_key

def run_query(root, query):
    parsed_query = parse_string(query)

    all_transactions = []
    totalizers = {}
    for trans in root.findall("ope"):
        if avaliar_expressao(trans, root, parsed_query):
            context = get_contexto(trans, root)
            all_transactions.append(context)

            totalizers['transactions'] = totalizers.get('transactions', 0) + 1
            totalizers['amount'] = totalizers.get('amount', 0) + float(context['amount'])

            totalizers['category'] = calculate_totalizer('category', context, totalizers)
            totalizers['account'] = calculate_totalizer('account', context, totalizers)

    all_transactions = sorted(all_transactions, key=lambda x: datetime.strptime(x['date'], "%d/%m/%Y"))
    return all_transactions, totalizers

def convert_to_csv(dados, arquivo_csv):
    if dados is None or len(dados) == 0:
        print("Nenhum dado para ser escrito no arquivo CSV!")
        return

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
    root = load_data(file)

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
        print(f"Error loading filters from {json_file}: {e}")

    if filter_name is None:
        return filters

    query = filters.get(filter_name, None)
    if query is None:
        print(f"Filter '{filter_name}' not found!")
        sys.exit(1)

    return query

def dt_format(dt):
    return dt.strftime("%d/%m/%Y")

def magic_words(query):
    today = datetime.today()

    first_day_this_month = today.replace(day=1)
    last_day_this_month  = today.replace(day=calendar.monthrange(today.year, today.month)[1])

    first_day_last_month = (first_day_this_month - timedelta(days=1)).replace(day=1)
    last_day_last_month  = first_day_this_month - timedelta(days=1)

    first_day_this_year = today.replace(month=1, day=1)
    last_day_this_year  = today.replace(month=12, day=31)

    first_day_last_year = today.replace(year=today.year-1, month=1, day=1)
    last_day_last_year = today.replace(year=today.year-1, month=12, day=31)

    replace_magic_words = {
        'today'     : f"date = '{dt_format(today)}'",
        'yesterday' : f"date = '{dt_format(today - timedelta(days=1))}'",
        'tomorrow'  : f"date = '{dt_format(today + timedelta(days=1))}'",
        'this_month': f"date >= '{dt_format(first_day_this_month)}' and date <= '{dt_format(last_day_this_month)}'",
        'last_month': f"date >= '{dt_format(first_day_last_month)}' and date <= '{dt_format(last_day_last_month)}'",
        'last_30_days': f"date >= '{dt_format(today - timedelta(days=30))}' and date <= '{dt_format(today)}'",
        'this_year' : f"date >= '{dt_format(first_day_this_year)}' and date <= '{dt_format(last_day_this_year)}'",
        'last_year' : f"date >= '{dt_format(first_day_last_year)}' and date <= '{dt_format(last_day_last_year)}'",
    }

    for key, value in replace_magic_words.items():
        query = query.replace('{' + key + '}', value)

    return query

@click.command()
@click.option('-l', "--list", default=None, is_flag=True, help="List all saved filters")
@click.option('-f', "--filter", help="Saved filter to apply")
@click.option('-q', "--query", help="JQL like query to filter transactions")
@click.option('-a', "--append", help="Append more conditions in the filter called by '-f'")
@click.option('-c', "--columns", help="Columns to show in the output")
@click.option('-r', "--replace", help="Replace the first magic work")
@click.option('--csv', help="Save the output in a csv file")
def commands(list, filter, append, query, columns, replace, csv):

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

        query = '(' + query + ') ' + append

    if replace:
        if not filter:
            raise click.UsageError("Mandatory '-f' with '-r'")
            sys.exit(1)
        query = re.sub(r'{.*}', replace, query)

    root = load_xhb_file("Gastos.xhb")

    query = magic_words(query)

    print('query:', query)
    trans, totalizers = run_query(root, query)
    trans = select_columns(trans, columns)

    if csv is not None:
        convert_to_csv(trans, csv)
    else:
        for i in trans:
            print(i)

    print("Totalizers:")

    try:
        sorted_category = dict(sorted(totalizers["category"].items(), key=lambda x: x[0]))
        rounded_sorted_category = {k: round(v, 2) for k, v in sorted_category.items()}
        rounded_account = {k: round(v, 2) for k, v in totalizers["account"].items()}
        rounded_amount  = round(totalizers["amount"], 2)

        totalizers["category"] = rounded_sorted_category
        totalizers["account"]  = rounded_account
        totalizers["amount"]   = rounded_amount
    except KeyError:
        totalizers = {}

    json_dump = json.dumps(totalizers, indent=4, ensure_ascii=False)
    print(json_dump)


if __name__ == '__main__':
    if (len(sys.argv) < 2):
        print("usage: main.py --help")
        sys.exit(1)

    commands()
