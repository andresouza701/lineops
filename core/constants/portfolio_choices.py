import unicodedata


def normalize_portfolio_name(value):
    """Normalize portfolio name by removing diacritics and converting to lowercase."""
    if not value:
        return ""
    normalized = unicodedata.normalize("NFKD", str(value))
    without_diacritics = "".join(
        char for char in normalized if not unicodedata.combining(char)
    )
    return " ".join(without_diacritics.strip().lower().split())


B2B_SUPERVISORS = [
    ("Alex", "Alex"),
    ("Barbara", "Barbara"),
    ("Eduardo", "Eduardo"),
    ("Gislaine", "Gislaine"),
    ("Jane", "Jane"),
    ("Jessica", "Jessica"),
    ("Paloma", "Paloma"),
    ("Quezia", "Quezia"),
    ("Rodrigo", "Rodrigo"),
    ("Rosimeri", "Rosimeri"),
    ("Textil", "Textil"),
]

B2B_PORTFOLIOS = [
    ("Alimentos", "Alimentos"),
    ("Andina", "Andina"),
    ("BackOffice", "BackOffice"),
    ("BAT", "BAT"),
    ("Chilli Beans", "Chilli Beans"),
    ("Femsa", "Femsa"),
    ("Heineki", "Heineki"),
    ("Industria", "Industria"),
    ("Manual Dellys", "Manual Dellys"),
    ("MV - Martins", "MV - Martins"),
    ("MV - Pepsico Repique", "MV - Pepsico Repique"),
    ("MV - Pepsico", "MV - Pepsico"),
    ("MV - Transportes", "MV - Transportes"),
    ("MV - Ações", "MV - Ações"),
    ("MV - Mix", "MV - Mix"),
    ("MV - Dellys", "MV - Dellys"),
    ("MV - Potencial", "MV - Potencial"),
    ("MV - Represado", "MV - Represado"),
    ("Pepsico", "Pepsico"),
    ("Pesquisa", "Pesquisa"),
    ("Sascar", "Sascar"),
    ("Souza", "Souza"),
    ("Tabacos", "Tabacos"),
    ("Textil", "Textil"),
]

B2C_SUPERVISORS = [
    ("Camila", "Camila"),
    ("Alex", "Alex"),
    ("Leonardo", "Leonardo"),
]

B2C_PORTFOLIOS = [
    ("Ambiental", "Ambiental"),
    ("Natura", "Natura"),
    ("ViaSat", "ViaSat"),
    ("Opera", "Opera"),
    ("Valid", "Valid"),
]

B2B_PORTFOLIO_NAMES = {
    normalize_portfolio_name(portfolio) for portfolio, _ in B2B_PORTFOLIOS
}
B2C_PORTFOLIO_NAMES = {
    normalize_portfolio_name(portfolio) for portfolio, _ in B2C_PORTFOLIOS
}
