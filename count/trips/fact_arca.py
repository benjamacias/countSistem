import subprocess
import base64
import requests
import xmltodict
from datetime import datetime, timedelta, timezone
from zeep import Client
import os
import ssl
from requests import Session
from zeep import Client
from requests.adapters import HTTPAdapter
from lxml import etree
from pathlib import Path
from zeep.transports import Transport

TA_PATH = "ta.xml"

BASE_DIR = Path(__file__).resolve().parent
CERT_PATH = BASE_DIR / "MaciasBenjaPrueba.crt"
KEY_PATH = BASE_DIR / "private.key"

CUIT = 20431255570
SERVICE = "wsfe"
#WSDL_FE = "https://servicios1.afip.gov.ar/wsfev1/service.asmx?WSDL"
#WSAA_URL = "https://wsaa.afip.gov.ar/ws/services/LoginCms"
TA_FILE = "ta.xml"
WSDL_FE = "https://wswhomo.afip.gov.ar/wsfev1/service.asmx?WSDL"
WSAA_URL = "https://wsaahomo.afip.gov.ar/ws/services/LoginCms?WSDL"
WSDL_CGT = "https://fwshomo.afip.gov.ar/ctg/services/CTGService?wsdl"


ssl_context = ssl.create_default_context()
ssl_context.set_ciphers("DEFAULT@SECLEVEL=1")

class SSLAdapter(HTTPAdapter):
    def init_poolmanager(self, *args, **kwargs):
        ctx = ssl.create_default_context()
        ctx.set_ciphers("DEFAULT@SECLEVEL=1")
        kwargs["ssl_context"] = ctx
        return super().init_poolmanager(*args, **kwargs)
    
def cargar_ta_desde_xml(path):
    if not os.path.exists(path):
        raise Exception("TA no encontrado")

    tree = etree.parse(path)

    expiration_str = tree.findtext(".//expirationTime")
    token = tree.findtext(".//token")
    sign = tree.findtext(".//sign")

    if not expiration_str or not token or not sign:
        raise Exception("TA inválido: falta uno o más campos obligatorios")

    expiration_dt = datetime.fromisoformat(expiration_str)
    now = datetime.now(expiration_dt.tzinfo or timezone.utc)

    if expiration_dt < now:
        raise Exception("TA vencido")

    return {"Token": token, "Sign": sign, "Cuit": CUIT}



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

def guardar_ta(xml_string, filename=TA_FILE):
    """
    Guarda el XML del TA como archivo.

    Parámetros:
        xml_string (str): contenido XML a guardar
        filename (str): ruta del archivo destino
    """
    with open(filename, "w", encoding="utf-8") as f:
        f.write(xml_string)


def obtener_token_sign_desde_cache():
    """
    Devuelve (token, sign) reutilizando el TA si sigue vigente,
    o generando uno nuevo si está vencido o no existe.
    """
    ta_dict = cargar_ta()

    if ta_dict and ta_vigente(ta_dict):
        token = ta_dict["credentials"]["token"]
        sign = ta_dict["credentials"]["sign"]
    else:
        generar_ticket_request()
        xml = obtener_token_y_sign()
        guardar_ta(xml)
        ta_dict = xmltodict.parse(xml)["loginTicketResponse"]
        token = ta_dict["credentials"]["token"]
        sign = ta_dict["credentials"]["sign"]

    return token, sign



def emitir_factura_dinamica(cliente_cuit, condicion_iva_id, tipo_cbte, imp_total, punto_venta):
    """Emitir factura electrónica utilizando los datos proporcionados."""

    # Configurar sesión segura
    session = requests.Session()
    session.mount("https://", SSLAdapter())
    transport = Transport(session=session)

    token, sign = obtener_token_sign_desde_cache()
    # Crear cliente WSFE
    client = Client(WSDL_FE, transport=transport)

    auth = {'Token': token, 'Sign': sign, 'Cuit': CUIT}

    # Obtener el último comprobante autorizado para calcular el próximo número
    ultimo = client.service.FECompUltimoAutorizado(Auth=auth, PtoVta=punto_venta, CbteTipo=tipo_cbte)
    proximo_numero = ultimo.CbteNro + 1

    # Calcular importes neto e IVA (21%)
    imp_neto = round(imp_total / 1.21, 2)
    imp_iva = round(imp_total - imp_neto, 2)

    detalle = [{
        'Concepto': 1,
        'DocTipo': 96,
        'DocNro': cliente_cuit,
        'CbteDesde': proximo_numero,
        'CbteHasta': proximo_numero,
        'CbteFch': datetime.now().strftime('%Y%m%d'),
        'ImpTotal': imp_total,
        'ImpTotConc': 0.0,
        'ImpNeto': imp_neto,
        'ImpOpEx': 0.0,
        'ImpIVA': imp_iva,
        'ImpTrib': 0.0,
        'MonId': 'PES',
        'MonCotiz': 1.0,
        'CondicionIVAReceptorId': condicion_iva_id,
        'Iva': [{
            'AlicIva': {
                'Id': condicion_iva_id,
                'BaseImp': imp_neto,
                'Importe': imp_iva
            }
        }],
    }]

    fe_req = {
        'FeCabReq': {
            'CantReg': 1,
            'PtoVta': punto_venta,
            'CbteTipo': tipo_cbte
        },
        'FeDetReq': {'FECAEDetRequest': detalle}
    }

    respuesta = client.service.FECAESolicitar(Auth=auth, FeCAEReq=fe_req)
    return respuesta


def obtener_carta_porte(ctg_numero):
    """Consulta una Carta de Porte electrónica usando el servicio CGT."""

    session = requests.Session()
    session.mount("https://", SSLAdapter())
    transport = Transport(session=session)

    token, sign = obtener_token_sign_desde_cache()
    client = Client(WSDL_CGT, transport=transport)
    auth = {'Token': token, 'Sign': sign, 'Cuit': CUIT}

    respuesta = client.service.consultarCTG(Auth=auth, Ctg=ctg_numero)

    def _get(obj, name):
        if isinstance(obj, dict):
            return obj.get(name)
        return getattr(obj, name, None)

    pdf_b64 = _get(respuesta, "pdf")
    pdf = base64.b64decode(pdf_b64) if pdf_b64 else None

    return {
        "estado": _get(respuesta, "estado"),
        "origen": _get(respuesta, "origen"),
        "destino": _get(respuesta, "destino"),
        "patente": _get(respuesta, "patente"),
        "pdf": pdf,
    }
