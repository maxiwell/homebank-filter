def get_query_by_filter_name(filter_name):
    filters = {
        "filtro_a": "((descricao ~ 'pix' AND valor >= 150) AND valor <= 200)",
        "filtro_b": "(descricao ~ 'pix' AND (valor == 15 OR valor == 200)) AND ! descricao ~ 'guilher'",
        "filtro_c": "descricao ~ 'MOBILE PAG TIT BANCO 481' AND data < '01/2025'"
    }    

    return filters.get(filter_name, filters) 
