import requests
import xml.etree.ElementTree as ET

# ==============================
# CONFIGURACIÓN
# ==============================
URL_PROD = "https://cpea-ws.afip.gob.ar/wscpe/services/soap"

# Leer token y sign desde archivos generados por WSAA
with open("token.txt", "r", encoding="utf-8") as ft:
    TOKEN = ft.read().strip()

with open("sign.txt", "r", encoding="utf-8") as fs:
    SIGN = fs.read().strip()

CUIT = "30716004720"   # tu CUIT

# Datos de la CPE a consultar
TIPO_CPE = 74          # Automotor
SUCURSAL = 1           # sucursal sin ceros a la izquierda
NRO_ORDEN = 25209      # número de orden sin ceros a la izquierda
NRO_CTG = "010225047780"  # CTG con 12 dígitos

# ==============================
# ARMAR REQUEST SOAP
# ==============================
soap_body = f"""<?xml version="1.0" encoding="UTF-8"?>
<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
                  xmlns:wsc="https://serviciosjava.afip.gob.ar/wscpe/">
  <soapenv:Header/>
  <soapenv:Body>
    <wsc:ConsultarCPEAutomotorReq>
      <auth>
        <token>{TOKEN}</token>
        <sign>{SIGN}</sign>
        <cuitRepresentada>{CUIT}</cuitRepresentada>
      </auth>
      <solicitud>
        <nroCTG>{NRO_CTG}</nroCTG>
      </solicitud>
    </wsc:ConsultarCPEAutomotorReq>
  </soapenv:Body>
</soapenv:Envelope>
"""

headers = {
    "Content-Type": "text/xml; charset=utf-8",
    "SOAPAction": "https://serviciosjava.afip.gob.ar/wscpe/consultarCPEAutomotor"
}

# Guardar request
with open("request.xml", "w", encoding="utf-8") as f:
    f.write(soap_body)

# ==============================
# ENVIAR REQUEST
# ==============================
resp = requests.post(URL_PROD, data=soap_body.encode("utf-8"), headers=headers, timeout=60)

# Guardar response
with open("response.xml", "w", encoding="utf-8") as f:
    f.write(resp.text)

print("=== Archivos generados ===")
print("request.xml  → XML enviado al WS")
print("response.xml → XML recibido del WS")

# ==============================
# PROCESAR RESPUESTA EN DICCIONARIO
# ==============================
if resp.status_code == 200:
    root = ET.fromstring(resp.text)
    ns = {
        "soap": "http://schemas.xmlsoap.org/soap/envelope/",
        "wsc": "http://impl.service.ws.cpe.afip.gov.ar/"
    }
    respuesta = root.find(".//wsc:respuesta", ns)
    if respuesta is not None:
        datos_cpe = {}
        for elem in respuesta.iter():
            if elem.text and elem.text.strip():
                tag = elem.tag.split("}")[-1]
                datos_cpe[tag] = elem.text.strip()

        print("\n=== DATOS DE LA CPE ===")
        for k, v in datos_cpe.items():
            print(f"{k}: {v}")
    else:
        print("No se encontró el bloque <respuesta> en la respuesta del WS")
        print(resp.text)
else:
    print("Error HTTP:", resp.status_code)
    print(resp.text)
