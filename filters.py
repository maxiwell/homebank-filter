def get_query_by_filter_name(filter_name):

    if (filter_name == "filtro_a"):
        query = "((descricao ~ 'pix' AND valor >= 150) AND valor <= 200)"

    elif (filter_name == "filtro_b"):
        query = "(descricao ~ 'pix' AND (valor == 15 OR valor == 200)) AND ! descricao ~ 'guilher'"

    elif (filter_name == "filtro_c"):
        query = "descricao ~ 'MOBILE PAG TIT BANCO 481' AND data < '01/2025'"

    return query
