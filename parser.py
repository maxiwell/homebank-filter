import numpy as np
import pyparsing as pp
import sys
import csv
import json, ast
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
    raise ValueError(f"Invalid date format: {date}")

def build_parse():
    field = pp.oneOf("memo amount category date tags account acc_type")

    operator = pp.oneOf("= >= <= < > == != <> ~ is")
    not_op = pp.oneOf("NOT not !")
    and_op = pp.oneOf("AND and")
    or_op  = pp.oneOf("OR or")

    value_str = pp.QuotedString("'")
    value_num = pp.Word(pp.nums + ".").setParseAction(lambda t: float(t[0]))
    value_list = pp.Suppress("[") + pp.Group(pp.delimitedList(pp.QuotedString("'"))) + pp.Suppress("]") 

    value = value_str | value_num | value_list

    exp = pp.Group(field + operator + value)

    cond = pp.infixNotation(exp, [
        (not_op, 1, pp.opAssoc.RIGHT),
        (and_op, 2, pp.opAssoc.LEFT),
        (or_op, 2, pp.opAssoc.LEFT),
        (operator, 2, pp.opAssoc.LEFT)
    ], lpar=pp.Suppress("("), rpar=pp.Suppress(")"))

    return cond

def parse_string(query):
    parser = build_parse()
    try:
        parsed_query = parser.parseString(query, parseAll=True)[0]
        return parsed_query
    except pp.ParseException as e:
        print(f"Erro ao interpretar query: {e}")
        sys.exit(1)



def get_contexto(transacao, root):
    memo = transacao.get("wording", "").lower()
    amount = transacao.get("amount", "")
    account = transacao.get("account", "")
    category = transacao.get("category", "")
    date = transacao.get("date", "")
    tags = transacao.get("tags", "")
    acc_type = ""

    date = ts_to_date(int(date), "%d/%m/%Y")

    cat = root.find(f".//cat[@key='{category}']")
    if cat is not None:
        category = cat.get("name")
        parent = cat.get("parent", None)
        if parent is not None:
            category = root.find(f".//cat[@key='{parent}']").get("name") + ":" + category

    acc = root.find(f".//account[@key='{account}']")
    if acc is not None:
        account = acc.get("name")
        acc_type = acc.get("type", "")

    # account type is hard coded in the homebank source code
    if acc_type is not None:
        if acc_type == "1":
            acc_type = "bank"
        elif acc_type == "2":
            acc_type = "cash"
        elif acc_type == "3":
            acc_type = "asset"
        elif acc_type == "4":
            acc_type = "credit card"
        elif acc_type == "5":
            acc_type = "liability"
        elif acc_type == "6":
            acc_type = "checking"

    return {"date": date,
            "account": account,
            "acc_type": acc_type,
            "category": category,
            "memo": memo,
            "amount": amount,
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
            op_left, operator, op_right = parsed
        elif (len(parsed) == 2):
            operator, op_right = parsed

        # special operators
        if operator.upper() == "NOT" or operator == "!":
            return not avaliar(op_right)
        elif operator.upper() == "AND":
            return avaliar(op_left) and avaliar(op_right)
        elif operator.upper() == "OR":
            return avaliar(op_left) or avaliar(op_right)

        # right_value has the right side value from homebank file
        right_value = contexto.get(op_left, "")

        # semantic exceptions
        if (op_left == "date"):
            right_value = date_to_ts(right_value)
            op_right    = date_to_ts(op_right)
        elif (isinstance(op_right, float)):
            right_value = float(right_value)
        elif operator == 'is':
            # convert the string "['word1', 'word2']"" to a real array
            op_right = ast.literal_eval(str(op_right))
        else:
            right_value = right_value.lower()
            op_right = op_right.lower()


        if operator == "~":
            return op_right in right_value
        elif operator == "=" or operator == "==":
            return right_value == op_right
        elif operator == "!=" or operator == "<>":
            return right_value != op_right
        elif operator == ">=":
            return right_value >= op_right
        elif operator == "<=":
            return right_value <= op_right
        elif operator == ">":
            return right_value > op_right
        elif operator == "<":
            return right_value < op_right
        elif operator == "is":
            if right_value in op_right:
                return True

        return False

    return avaliar(parsed_query)