import subprocess
import base64
import requests
import xmltodict
from datetime import datetime, timedelta, timezone
from zeep import Client
import os
import ssl
from requests import Session
from zeep import Client, Transport
from requests.adapters import HTTPAdapter

CERT_PATH = "benjamaciasPC_63935779e4755fe7.crt"
KEY_PATH = "private.key"
CUIT = 20431255570
SERVICE = "wsfe"
WSDL_FE = "https://servicios1.afip.gov.ar/wsfev1/service.asmx?WSDL"
WSAA_URL = "https://wsaa.afip.gov.ar/ws/services/LoginCms"
TA_FILE = "ta.xml"

ssl_context = ssl.create_default_context()
ssl_context.set_ciphers("DEFAULT@SECLEVEL=1")


class SSLAdapter(HTTPAdapter):
    def __init__(self, ssl_context=None, **kwargs):
        self.ssl_context = ssl_context
        super().__init__(**kwargs)

    def init_poolmanager(self, *args, **kwargs):
        kwargs['ssl_context'] = self.ssl_context
        return super().init_poolmanager(*args, **kwargs)

    def proxy_manager_for(self, *args, **kwargs):
        kwargs['ssl_context'] = self.ssl_context
        return super().proxy_manager_for(*args, **kwargs)

# === AUTENTICACIÓN Y FIRMA ===

def generar_ticket_request():
    """
    Genera el archivo `request.xml` con el LoginTicketRequest y lo firma con OpenSSL,
    generando el archivo `request.cms`.

    No recibe parámetros. 
    Lanza excepción si la firma falla.
    """
    now = datetime.now(timezone.utc).replace(microsecond=0)
    generacion = (now - timedelta(minutes=10)).isoformat().replace("+00:00", "Z")
    expiracion = (now + timedelta(minutes=10)).isoformat().replace("+00:00", "Z")
    unique_id = int(datetime.now().timestamp())

    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
        <loginTicketRequest version="1.0">
            <header>
                <uniqueId>{unique_id}</uniqueId>
                <generationTime>{generacion}</generationTime>
                <expirationTime>{expiracion}</expirationTime>
            </header>
            <service>{SERVICE}</service>
        </loginTicketRequest>"""

    with open("request.xml", "w", encoding="utf-8") as f:
        f.write(xml)

    res = subprocess.run([
        "openssl", "smime", "-sign",
        "-signer", CERT_PATH,
        "-inkey", KEY_PATH,
        "-outform", "DER",
        "-nodetach",
        "-out", "request.cms",
        "-in", "request.xml"
    ], capture_output=True)

    if res.returncode != 0:
        raise Exception("Error firmando con OpenSSL: " + res.stderr.decode())

def obtener_token_y_sign():
    """
    Envia el request firmado al WSAA y obtiene el token y sign.

    Retorna el XML completo como string (`loginCmsReturn`).
    Lanza excepción si la respuesta del WSAA contiene errores.
    """
    with open("request.cms", "rb") as f:
        cms_b64 = base64.b64encode(f.read()).decode()

    soap_request = f"""<?xml version="1.0"?>
<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
                  xmlns:ser="http://wsaa.view.sua.dvadac.desein.afip.gov.ar">
    <soapenv:Header/>
    <soapenv:Body>
        <ser:loginCms>
            <ser:in0>{cms_b64}</ser:in0>
        </ser:loginCms>
    </soapenv:Body>
</soapenv:Envelope>"""

    headers = {
        "Content-Type": "text/xml",
        "SOAPAction": "http://wsaa.view.sua.dvadac.desein.afip.gov.ar/loginCms"
    }

    response = requests.post(WSAA_URL, data=soap_request.encode("utf-8"), headers=headers)

    if response.status_code != 200:
        raise Exception(f"Error en WSAA: status {response.status_code}")

    data = xmltodict.parse(response.content)

    if "soapenv:Fault" in data.get("soapenv:Envelope", {}).get("soapenv:Body", {}):
        fault = data["soapenv:Envelope"]["soapenv:Body"]["soapenv:Fault"]
        faultstring = fault.get("faultstring", "Error no especificado")
        raise Exception(f"WSAA Fault: {faultstring}")

    return data["soapenv:Envelope"]["soapenv:Body"]["loginCmsResponse"]["loginCmsReturn"]

# === TA (Ticket de Acceso) ===

def guardar_ta(xml_string, filename=TA_FILE):
    """
    Guarda el XML del TA como archivo.

    Parámetros:
        xml_string (str): contenido XML a guardar
        filename (str): ruta del archivo destino
    """
    with open(filename, "w", encoding="utf-8") as f:
        f.write(xml_string)

def cargar_ta(filename=TA_FILE):
    """
    Carga el archivo TA desde disco y lo convierte a dict.

    Retorna el dict del TA o None si no existe.
    """
    if not os.path.exists(filename):
        return None
    with open(filename, "r", encoding="utf-8") as f:
        return xmltodict.parse(f.read())["loginTicketResponse"]

def ta_vigente(ta_dict):
    """
    Verifica si el TA actual está vigente.

    Parámetro:
        ta_dict (dict): estructura ya parseada del TA

    Retorna True si el TA está vigente, False si está vencido o inválido.
    """
    try:
        exp_str = ta_dict["header"]["expirationTime"]
        exp = datetime.fromisoformat(exp_str)
        now = datetime.now(exp.tzinfo or timezone.utc)
        return exp > now
    except Exception:
        return False

# === FACTURACIÓN ===

def emitir_factura(token, sign):
    """
    Solicita autorización de una factura tipo B (CbteTipo 6).

    Parámetros:
        token (str): token del TA
        sign (str): sign del TA

    Retorna una tupla: (resultado del WS, importe total)
    """
    client = Client(WSDL_FE, transport=transport)
    auth = {'Token': token, 'Sign': sign, 'Cuit': CUIT}
    ultimo = client.service.FECompUltimoAutorizado(Auth=auth, PtoVta=1, CbteTipo=6)
    proximo_numero = ultimo.CbteNro + 1

    detalle = [{
        'Concepto': 1,
        'DocTipo': 96,
        'DocNro': 27225103441,
        'CbteDesde': proximo_numero,
        'CbteHasta': proximo_numero,
        'CbteFch': datetime.now().strftime('%Y%m%d'),
        'ImpTotal': 121.0,
        'ImpTotConc': 0.0,
        'ImpNeto': 100.0,
        'ImpOpEx': 0.0,
        'ImpIVA': 21.0,
        'ImpTrib': 0.0,
        'MonId': 'PES',
        'MonCotiz': 1.0,
        'CondicionIVAReceptorId': 5,
        'Iva': [{
            'AlicIva': {
                'Id': 5,
                'BaseImp': 100.0,
                'Importe': 21.0
            }
        }],
    }]

    fe_req = {
        'FeCabReq': {
            'CantReg': 1,
            'PtoVta': 1,
            'CbteTipo': 6
        },
        'FeDetReq': {'FECAEDetRequest': detalle}
    }

    result = client.service.FECAESolicitar(Auth=auth, FeCAEReq=fe_req)
    return result, 121.0

def consultar_ultimo_comprobante(token, sign):
    """
    Consulta el último comprobante autorizado para el punto de venta 1 y tipo 6.

    Retorna el dict con los datos del comprobante.
    """
    client = Client(WSDL_FE, transport=transport)
    auth = {'Token': token, 'Sign': sign, 'Cuit': CUIT}
    return client.service.FECompUltimoAutorizado(Auth=auth, PtoVta=1, CbteTipo=6)

def consultar_tipos_iva(token, sign):
    """
    Devuelve el listado de tipos de IVA disponibles.

    Retorna el resultado del método `FEParamGetTiposIva`.
    """
    client = Client(WSDL_FE, transport=transport)
    auth = {'Token': token, 'Sign': sign, 'Cuit': CUIT}
    return client.service.FEParamGetTiposIva(Auth=auth)

# === PADRÓN A13 ===

def get_padron_token_sign():
    """
    Cambia temporalmente el servicio a 'ws_sr_padron_a13',
    genera un nuevo TA para el padrón, y luego vuelve a 'wsfe'.

    Retorna (token, sign) válidos para consultar el padrón.
    """
    global SERVICE
    SERVICE = "ws_sr_padron_a13"
    generar_ticket_request()
    cred = obtener_token_y_sign()
    SERVICE = "wsfe"
    return cred['token'], cred['sign']

def consultar_condicion_iva(cuit_cliente, token, sign):
    """
    Consulta la condición frente al IVA de un CUIT mediante el padrón A13.

    Parámetros:
        cuit_cliente (int): CUIT del cliente
        token (str): token válido para padrón
        sign (str): sign válido para padrón

    Retorna el ID de la condición frente al IVA o None si hay error.
    """
    WSDL_PADRON = "https://aws.afip.gov.ar/sr-padron/webservices/personaServiceA13?WSDL"
    client = Client(WSDL_PADRON)
    auth = {'token': token, 'sign': sign, 'cuitRepresentada': CUIT}

    try:
        response = client.service.getPersona_v2(auth, cuit_cliente)
        return int(response['persona']['idCondicionIva'])
    except Exception:
        return None

# === EJECUCIÓN ===

def main():
    global transport
    ta_dict = cargar_ta()
    ssl_context = ssl.create_default_context()
    ssl_context.set_ciphers("DEFAULT@SECLEVEL=1")

    session = Session()
    session.mount("https://", SSLAdapter(ssl_context=ssl_context))
    transport = Transport(session=session)
    if not ta_dict or not ta_vigente(ta_dict):
        generar_ticket_request()
        xml_resp = obtener_token_y_sign()
        guardar_ta(xml_resp)
        ta_dict = xmltodict.parse(xml_resp)["loginTicketResponse"]

    token = ta_dict["credentials"]["token"]
    sign = ta_dict["credentials"]["sign"]

    resultado = emitir_factura(token, sign)
    ultimo_cbte = consultar_ultimo_comprobante(token, sign)
    tipos_iva = consultar_tipos_iva(token, sign)
    print("Resultado de emisión:", resultado)
    print("Último comprobante autorizado:", ultimo_cbte)    
    print("Tipos de IVA disponibles:", tipos_iva)

if __name__ == "__main__":
    main()
