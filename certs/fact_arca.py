import subprocess
import base64
import requests
import xmltodict
from datetime import datetime, timedelta, timezone
from zeep import Client
import os

CERT_PATH = "MaciasBenjaPrueba.crt"
KEY_PATH = "private.key"
CUIT = 20431255570  # tu CUIT
SERVICE = "wsfe"
WSDL_FE = "https://wswhomo.afip.gov.ar/wsfev1/service.asmx?WSDL"
WSAA_URL = "https://wsaahomo.afip.gov.ar/ws/services/LoginCms"
TA_FILE = "ta.xml"

def generar_ticket_request():

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
        print("Error firmando con OpenSSL:", res.stderr.decode())
        raise Exception("Error en la firma OpenSSL")
    else:
        print("Firma generada correctamente")

def obtener_token_y_sign():
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

    print("=== Enviando solicitud WSAA ===")
    print(soap_request[:1000])  # imprimir solo los primeros 1000 caracteres para no saturar

    response = requests.post(WSAA_URL, data=soap_request.encode("utf-8"), headers=headers)

    print(f"=== Respuesta WSAA: status {response.status_code} ===")
    print(response.text)

    if response.status_code != 200:
        raise Exception(f"Error en WSAA: status {response.status_code}")

    data = xmltodict.parse(response.content)

    if "soapenv:Fault" in data.get("soapenv:Envelope", {}).get("soapenv:Body", {}):
        fault = data["soapenv:Envelope"]["soapenv:Body"]["soapenv:Fault"]
        faultstring = fault.get("faultstring", "Error no especificado")
        raise Exception(f"WSAA Fault: {faultstring}")

    ticket = data["soapenv:Envelope"]["soapenv:Body"]["loginCmsResponse"]["loginCmsReturn"]
    return ticket


def guardar_ta(xml_string, filename=TA_FILE):
    with open(filename, "w", encoding="utf-8") as f:
        f.write(xml_string)

def cargar_ta(filename=TA_FILE):
    if not os.path.exists(filename):
        return None
    with open(filename, "r", encoding="utf-8") as f:
        return xmltodict.parse(f.read())["loginTicketResponse"]
    
def ta_vigente(ta_dict):
    try:
        from datetime import datetime, timezone
        exp_str = ta_dict["header"]["expirationTime"]
        exp = datetime.fromisoformat(exp_str)
        now = datetime.now(exp.tzinfo or timezone.utc)
        return exp > now
    except Exception:
        return False

def emitir_factura(token, sign):
    auth = {
        'Token': token,
        'Sign': sign,
        'Cuit': CUIT
    }
    client = Client(WSDL_FE)
    ultimo = client.service.FECompUltimoAutorizado(Auth=auth, PtoVta=1, CbteTipo=6)
    proximo_numero = ultimo.CbteNro + 1
    AlicIvaType = client.get_type('ns0:AlicIva')
    alicuota_iva = AlicIvaType(Id=5, BaseImp=100.0, Importe=21.0)

    auth = {
        'Token': token,
        'Sign': sign,
        'Cuit': CUIT
    }

    cabecera = {
        'CantReg': 1,
        'PtoVta': 1,
        'CbteTipo': 6  # Factura B
    }

    hoy = datetime.now().strftime('%Y%m%d')
    detalle = [{
        'Concepto': 1,
        'DocTipo': 96,
        'DocNro': 27225103441,  # CUIT del cliente
        'CbteDesde': proximo_numero,
        'CbteHasta': proximo_numero,
        'CbteFch': hoy,
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
        'FeCabReq': cabecera,
        'FeDetReq': {'FECAEDetRequest': detalle}
    }
    result = client.service.FECAESolicitar(Auth=auth, FeCAEReq=fe_req)
    return result

def consultar_ultimo_comprobante(token, sign):
    client = Client(WSDL_FE)
    auth = {'Token': token, 'Sign': sign, 'Cuit': CUIT}
    return client.service.FECompUltimoAutorizado(Auth=auth, PtoVta=1, CbteTipo=6)

def get_padron_token_sign():
    global SERVICE
    SERVICE = "ws_sr_padron_a13"  # Cambiar temporalmente
    generar_ticket_request()
    cred = obtener_token_y_sign()
    SERVICE = "wsfe"  # Volver a "wsfe" para facturación
    return cred['token'], cred['sign']


def consultar_condicion_iva(cuit_cliente, token, sign):
    WSDL_PADRON = "https://aws.afip.gov.ar/sr-padron/webservices/personaServiceA13?WSDL"
    client = Client(WSDL_PADRON)
    
    auth = {
        'token': token,
        'sign': sign,
        'cuitRepresentada': CUIT  # tu CUIT
    }

    try:
        response = client.service.getPersona_v2(auth, cuit_cliente)
        actividades = response.get('persona', {}).get('actividad', [])
        iva = response['persona']['idCondicionIva']
        return int(iva)
    except Exception as e:
        print("Error consultando padrón:", e)
        return None

def consultar_tipos_iva(token, sign):
    client = Client(WSDL_FE)
    auth = {'Token': token, 'Sign': sign, 'Cuit': CUIT}
    return client.service.FEParamGetTiposIva(Auth=auth)

def main():
    ta_dict = cargar_ta()

    if not ta_dict or not ta_vigente(ta_dict):
        print("TA no existe o vencido, generando nuevo...")
        generar_ticket_request()
        xml_resp = obtener_token_y_sign()
        guardar_ta(xml_resp)
        ta_dict = xmltodict.parse(xml_resp)["loginTicketResponse"]
    else:
        print("Usando TA guardado y vigente")
    
    token = ta_dict["credentials"]["token"]
    sign = ta_dict["credentials"]["sign"]

    print("Emitiendo factura...")
    resultado = emitir_factura(token, sign)
    print("Resultado emisión factura:", resultado)

    print("Consultando último comprobante autorizado...")
    ultimo_cbte = consultar_ultimo_comprobante(token, sign)
    print("Último comprobante autorizado:", ultimo_cbte)

    print("Consultando tipos de IVA...")
    tipos_iva = consultar_tipos_iva(token, sign)
    print("Tipos de IVA:", tipos_iva)

if __name__ == "__main__":
    main()
