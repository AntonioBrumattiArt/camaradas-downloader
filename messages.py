# -*- coding: utf-8 -*-
"""Todas as frases que o camarada lê. Edite à vontade, sem mexer na lógica."""

INVALID_URL = "Camarada, isso não é um link. Até a revolução precisa de endereço."
NO_INTERNET = "Trabalhadores do mundo, uni-vos! Mas conectem-se primeiro."
PRIVATE = "A propriedade é um roubo. Esse vídeo é propriedade privada."
LOGIN_HINT = "Entre na sua conta no navegador e escolha ele em Login do navegador, nos três pontinhos."
REMOVED = "Tudo que é sólido desmancha no ar."
UNSUPPORTED = "A luta continua, mas esse site ainda não aderiu."
GEO_BLOCKED = "Fronteiras são invenção da burguesia, mas o servidor discorda."
RATE_LIMIT = "O capital impõe limites. Aguarde alguns minutos, camarada."
DRM = "Os meios de produção estão sob guarda do patronato."
DISK = "Acumulação primitiva de arquivos detectada."
GENERIC = "Um passo à frente, dois passos atrás."
UNKNOWN = "A história se repete, primeiro como tragédia, depois como farsa."
SUCCESS = "Hasta la victoria siempre! Vídeo expropriado."

# {browser} vira o nome do navegador escolhido (Chrome, Edge, Firefox)
COOKIES = "O {browser} guarda a carteirinha a sete chaves. Tente o {others}."

# Textos do splash e da barra de progresso
SPLASH = "Convocando o Comitê Central..."
PROGRESS_DOWNLOAD = "Baixando seu vídeo..."
PROGRESS_CONVERT = "Convertendo seu vídeo..."

BROWSER_NAMES = {"firefox": "Firefox", "edge": "Edge", "chrome": "Chrome"}


def cookies_message(browser):
    """Frase da carteirinha com o navegador usado e as outras duas opções."""
    name = BROWSER_NAMES.get(browser, "navegador")
    others = [v for k, v in BROWSER_NAMES.items() if k != browser]
    return COOKIES.format(browser=name, others=" ou o ".join(others))
