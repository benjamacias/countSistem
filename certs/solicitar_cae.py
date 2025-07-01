import requests
from lxml import etree
from datetime import datetime, timedelta
import subprocess
import base64

# === Configuración general ===
CUIT_EMISOR = "20431255570"
PTO_VTA = 1
CBTE_TIPO = 6  # Factura B

# === Paso 1: Crear TRA.xml ===
def crear_TRA(service='wsfe', cuit=CUIT_EMISOR):
    tra = etree.Element("loginTicketRequest", version="1.0")
    header = etree.SubElement(tra, "header")
    etree.SubElement(header, "uniqueId").text = str(int(datetime.now().timestamp()))
    etree.SubElement(header, "generationTime").text = (datetime.now() - timedelta(minutes=10)).isoformat()
    etree.SubElement(header, "expirationTime").text = (datetime.now() + timedelta(minutes=10)).isoformat()
    etree.SubElement(tra, "service").text = service

    xml_string = etree.tostring(tra, pretty_print=True, xml_declaration=True, encoding="UTF-8")
    with open("TRA.xml", "wb") as f:
        f.write(xml_string)

# === Paso 2: Firmar TRA ===
def firmar_tra(consola_openssl_path="openssl", cert="cert.pem", key="private.key"):
    try:
        subprocess.run(
            [
                consola_openssl_path,
                "smime", "-sign",
                "-signer", cert,
                "-inkey", key,
                "-in", "TRA.xml",
                "-out", "TRA.tmp",
                "-outform", "DER",
                "-nodetach"
            ],
            check=True,
            capture_output=True
        )
        print("✔️ TRA firmado correctamente.")
    except subprocess.CalledProcessError as e:
        print("❌ Error al firmar el TRA:")
        print(e.stderr.decode())

# === Paso 3: Obtener token y sign desde WSAA ===
from pathlib import Path
from lxml import etree
from datetime import datetime
import requests
import base64

def obtener_token_sign():
    from pathlib import Path

    def token_sigue_valido(xml_string):
        try:
            xml = etree.fromstring(xml_string.encode("utf-8"))
            exp = xml.find("header/expirationTime").text
            expiration = datetime.fromisoformat(exp)
            return datetime.now() < expiration
        except Exception as e:
            print("⚠️ Error al validar expiración del token:", e)
            return False

    token_file = Path("token.xml")
    if token_file.exists():
        with open(token_file, "r", encoding="utf-8") as f:
            login_response = f.read()
        if token_sigue_valido(login_response):
            print("♻️ Reutilizando TA vigente.")
            xml = etree.fromstring(login_response.encode("utf-8"))
            token = xml.find("credentials/token").text
            sign = xml.find("credentials/sign").text
            return token, sign
        else:
            print("⏰ El TA expiró. Se generará uno nuevo.")

    # Generar nuevo TA
    with open("TRA.tmp", "rb") as f:
        cms = base64.b64encode(f.read()).decode("utf-8")

    url = "https://wsaahomo.afip.gov.ar/ws/services/LoginCms"
    headers = {
        "Content-Type": "text/xml; charset=utf-8",
        "SOAPAction": "loginCms"
    }

    soap_body = f"""<?xml version="1.0" encoding="UTF-8"?>
    <soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
                      xmlns:wsaa="http://wsaa.view.sua.dvadac.desein.afip.gov.ar/">
      <soapenv:Header/>
      <soapenv:Body>
        <wsaa:loginCms>
          <wsaa:in0>{cms}</wsaa:in0>
        </wsaa:loginCms>
      </soapenv:Body>
    </soapenv:Envelope>"""

    try:
        response = requests.post(url, data=soap_body.encode("utf-8"), headers=headers)
        if response.status_code == 200:
            tree = etree.fromstring(response.content)
            login_cms_return = tree.find(".//{http://wsaa.view.sua.dvadac.desein.afip.gov.ar/}loginCmsReturn").text
            # Procesar la respuesta exitosa
            login_response = base64.b64decode(login_cms_return).decode("utf-8")
            xml = etree.fromstring(login_response.encode("utf-8"))
            token = xml.find("credentials/token").text
            sign = xml.find("credentials/sign").text
            # Guardar para futuras ejecuciones
            with open("token.xml", "w", encoding="utf-8") as f:
                f.write(login_response)
            return token, sign
        elif response.status_code == 500 and "El CEE ya posee un TA valido" in response.text:
            print("Ya existe un token de autenticación válido. Reutilizando...")
            # Reutilizar el token de autenticación existente
            with open("token.xml", "r", encoding="utf-8") as f:
                login_response = f.read()
            xml = etree.fromstring(login_response.encode("utf-8"))
            token = xml.find("credentials/token").text
            sign = xml.find("credentials/sign").text
            return token, sign
        else:
            raise Exception(f"Error HTTP: {response.status_code}\n{response.text}")
    except requests.exceptions.RequestException as e:
        print("Error al conectar con la URL:", e)



# === Paso 4: Consultar último comprobante autorizado ===
def consultar_ultimo_cbte(cuit_emisor, token, sign, pto_vta, cbte_tipo):
    url = "https://wswhomo.afip.gov.ar/wsfev1/service.asmx"
    headers = {
        "Content-Type": "text/xml; charset=utf-8",
        "SOAPAction": "http://ar.gov.afip.dif.FEV1/FECompUltimoAutorizado"
    }

    body = f"""
    <soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
                      xmlns:ar="http://ar.gov.afip.dif.FEV1/">
      <soapenv:Header/>
      <soapenv:Body>
        <ar:FECompUltimoAutorizado>
          <ar:Auth>
            <ar:Token>{token}</ar:Token>
            <ar:Sign>{sign}</ar:Sign>
            <ar:Cuit>{cuit_emisor}</ar:Cuit>
          </ar:Auth>
          <ar:PtoVta>{pto_vta}</ar:PtoVta>
          <ar:CbteTipo>{cbte_tipo}</ar:CbteTipo>
        </ar:FECompUltimoAutorizado>
      </soapenv:Body>
    </soapenv:Envelope>
    """

    response = requests.post(url, data=body.encode("utf-8"), headers=headers)
    if response.status_code != 200:
        raise Exception(f"Error HTTP: {response.status_code}\n{response.text}")
    
    print("Respuesta del servidor:")
    print(response.text)
    tree = etree.fromstring(response.content)
    ult_cbte = tree.find(".//{http://ar.gov.afip.dif.FEV1/}CbteNro")
    if ult_cbte is not None:
        return int(ult_cbte.text)
    else:
        print("⚠️ No hay comprobantes autorizados para el punto de venta y tipo de comprobante especificados.")
        return 0
# === Paso 5: Solicitar CAE ===
def solicitar_cae(cuit_emisor, token, sign, pto_vta, cbte_tipo, cbte_numero):
    fecha_cbte = datetime.now().strftime("%Y%m%d")

    url = "https://wswhomo.afip.gov.ar/wsfev1/service.asmx"
    headers = {"Content-Type": "text/xml; charset=utf-8", "SOAPAction": "http://ar.gov.afip.dif.FEV1/FECAESolicitar"}
    ult_cbte = consultar_ultimo_cbte(CUIT_EMISOR, token, sign, PTO_VTA, CBTE_TIPO)
    siguiente_cbte = ult_cbte + 1
    soap_body = f"""
    <soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
                      xmlns:ar="http://ar.gov.afip.dif.FEV1/">
      <soapenv:Header/>
      <soapenv:Body>
        <ar:FECAESolicitar>
          <ar:Auth>
            <ar:Token>{token}</ar:Token>
            <ar:Sign>{sign}</ar:Sign>
            <ar:Cuit>{cuit_emisor}</ar:Cuit>
          </ar:Auth>
          <ar:FeCAEReq>
            <ar:FeCabReq>
              <ar:CantReg>1</ar:CantReg>
              <ar:PtoVta>{pto_vta}</ar:PtoVta>
              <ar:CbteTipo>{cbte_tipo}</ar:CbteTipo>
            </ar:FeCabReq>
            <ar:FeDetReq>
           <ar:FECAEDetRequest>
              <ar:Concepto>1</ar:Concepto>
              <ar:DocTipo>80</ar:DocTipo>
              <ar:DocNro>20111111112</ar:DocNro>
              <ar:CondicionIVA>5</ar:CondicionIVA>
              <ar:CbteDesde>{siguiente_cbte}</ar:CbteDesde>
              <ar:CbteHasta>{siguiente_cbte}</ar:CbteHasta>
              <ar:CbteFch>20250630</ar:CbteFch>
              <ar:ImpTotal>121.00</ar:ImpTotal>
              <ar:ImpTotConc>0.00</ar:ImpTotConc>
              <ar:ImpNeto>100.00</ar:ImpNeto>
              <ar:ImpIVA>21.00</ar:ImpIVA>
              <ar:ImpOpEx>0.00</ar:ImpOpEx>
              <ar:ImpTrib>0.00</ar:ImpTrib>
              <ar:FchServDesde></ar:FchServDesde>
              <ar:FchServHasta></ar:FchServHasta>
              <ar:FchVtoPago></ar:FchVtoPago>
              <ar:MonId>PES</ar:MonId>
              <ar:MonCotiz>1.000</ar:MonCotiz>
              <ar:Iva>
                <ar:AlicIva>
                  <ar:Id>5</ar:Id>
                  <ar:BaseImp>100.00</ar:BaseImp>
                  <ar:Importe>21.00</ar:Importe>
                </ar:AlicIva>
              </ar:Iva>
              </ar:FECAEDetRequest>
          </ar:FeDetReq>
          </ar:FeCAEReq>
        </ar:FECAESolicitar>
      </soapenv:Body>
    </soapenv:Envelope>
    """
    print("XML enviado para solicitar CAE:\n", soap_body)
    response = requests.post(url, data=soap_body.encode("utf-8"), headers=headers)
    print("Status:", response.status_code)

    tree = etree.fromstring(response.content)
    cae_element = tree.find(".//CAE")
    if cae_element is not None:
        cae = cae_element.text
        print(f"✅ CAE obtenido: {cae}")
        return cae
    else:
        print("⚠️ No se encontró el CAE.")
        print(response.text)
        return None

# === Ejecución del flujo completo ===
def main():
    crear_TRA()
    firmar_tra(cert="MaciasBenjaPrueba.crt", key="private.key")
    token, sign = obtener_token_sign()
    ult_cbte = consultar_ultimo_cbte(CUIT_EMISOR, token, sign, PTO_VTA, CBTE_TIPO)
    siguiente_cbte = ult_cbte + 1
    solicitar_cae(CUIT_EMISOR, token, sign, PTO_VTA, CBTE_TIPO, siguiente_cbte)

if __name__ == "__main__":
    main()
