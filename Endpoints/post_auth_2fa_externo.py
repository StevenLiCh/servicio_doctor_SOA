# ============================================================
# ENDPOINT: POST /auth/2fa/{perfil}/enviar
#           POST /auth/2fa/{perfil}/verificar
# Servicio: ServicioDoctor
# Acción: Maneja el 2FA para perfiles externos (paciente, clínica)
#         que no tienen 2FA propio.
#         - /enviar   → recibe el email y envía el código
#         - /verificar → valida el código y confirma el acceso
#
# FLUJO:
#   1. El portal llama a POST /paciente/login (ServicioPaciente)
#   2. Si el login es exitoso, el portal llama a /auth/2fa/paciente/enviar
#   3. ServicioDoctor genera el código y lo envía al email
#   4. El usuario ingresa el código en el portal
#   5. El portal llama a /auth/2fa/paciente/verificar
#   6. ServicioDoctor valida el código y confirma
# ============================================================

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from auth.email_config import enviar_codigo_2fa

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, EmailStr
from typing import Optional
from datetime import datetime, timedelta
import random

router = APIRouter()

# ── Almacenamiento temporal de códigos en memoria ────────────────────────────
# NOTA: En producción usar Redis o una tabla en BD.
# Para este proyecto académico, un dict en memoria es suficiente.
# Estructura: { "email": { "codigo": "123456", "expira": datetime, "token": "..." } }
_codigos_temporales: dict = {}

# ── Schemas Pydantic ──────────────────────────────────────────────────────────
class EnviarCodigoRequest(BaseModel):
    """
    Lo que el portal envía para iniciar el 2FA de un usuario externo
    """
    # Email al que enviar el código
    # ── AJUSTAR: según lo que devuelva el login de cada servicio ──
    email: str

    # Token provisional obtenido del login del servicio externo
    # Se guarda temporalmente y se devuelve cuando el código es válido
    token: str

    # Nombre del usuario (opcional, para personalizar el email)
    nombre: Optional[str] = "Usuario"

class EnviarCodigoResponse(BaseModel):
    mensaje:          str
    codigo_enviado:   bool
    email_destino:    str   # Email enmascarado
    expira_en_minutos: int

class VerificarCodigoRequest(BaseModel):
    """Lo que el portal envía para verificar el código 2FA"""
    email:  str    # El mismo email usado en /enviar
    codigo: str    # El código de 6 dígitos ingresado por el usuario
    token:  str    # El token provisional (para verificar que es la misma sesión)

class VerificarCodigoResponse(BaseModel):
    """Confirmación de que el código es válido"""
    verificado:   bool
    access_token: str   # El token provisional que se devuelve al portal

# ── Función helper: enmascarar email ─────────────────────────────────────────
def enmascarar_email(email: str) -> str:
    try:
        usuario, dominio = email.split("@")
        return f"{usuario[0]}**@{dominio}"
    except Exception:
        return "***@***.com"

# ── ENDPOINT: Enviar código 2FA ───────────────────────────────────────────────
@router.post(
    "/auth/2fa/{perfil}/enviar",
    response_model = EnviarCodigoResponse,
    tags           = ["Autenticación"],
    summary        = "Enviar código 2FA para perfil externo (paciente/clínica)",
    description    = """
    Genera y envía un código de verificación 2FA al email del usuario
    de un servicio externo (paciente o clínica) que no tiene 2FA propio.
    El código expira en 5 minutos.
    """
)
async def enviar_codigo_2fa_externo(
    perfil: str,
    datos:  EnviarCodigoRequest
):
    # Validar perfil
    perfiles_validos = ["paciente", "clinica"]
    if perfil not in perfiles_validos:
        raise HTTPException(
            status_code = 400,
            detail      = f"Perfil inválido. Opciones: {perfiles_validos}"
        )

    # Generar código de 6 dígitos
    codigo  = str(random.randint(100000, 999999))
    expira  = datetime.utcnow() + timedelta(minutes=5)

    # Guardar en memoria (reemplaza código anterior del mismo email)
    _codigos_temporales[datos.email] = {
        "codigo" : codigo,
        "expira" : expira,
        "token"  : datos.token,
        "perfil" : perfil
    }

    # Nombre para personalizar el email
    nombre = datos.nombre or f"Usuario ({perfil.capitalize()})"

    # Enviar el código por email
    enviado = enviar_codigo_2fa(
        email_destino = datos.email,
        nombre_doctor = nombre,
        codigo        = codigo
    )

    if not enviado:
        raise HTTPException(
            status_code = 500,
            detail      = "No se pudo enviar el código de verificación. "
                          "Verifica que el email sea correcto."
        )

    print(f"[2FA-EXTERNO] CÓDIGO_ENVIADO → Perfil: {perfil} | Email: {datos.email}")

    return EnviarCodigoResponse(
        mensaje           = "Código enviado exitosamente",
        codigo_enviado    = True,
        email_destino     = enmascarar_email(datos.email),
        expira_en_minutos = 5
    )

# ── ENDPOINT: Verificar código 2FA ────────────────────────────────────────────
@router.post(
    "/auth/2fa/{perfil}/verificar",
    response_model = VerificarCodigoResponse,
    tags           = ["Autenticación"],
    summary        = "Verificar código 2FA para perfil externo (paciente/clínica)",
    description    = """
    Verifica el código 2FA ingresado por el usuario.
    Si es válido, devuelve el token provisional del servicio externo
    para que el portal pueda completar el acceso.
    """
)
async def verificar_codigo_2fa_externo(
    perfil: str,
    datos:  VerificarCodigoRequest
):
    # Buscar el código almacenado para este email
    registro = _codigos_temporales.get(datos.email)

    if not registro:
        raise HTTPException(
            status_code = status.HTTP_401_UNAUTHORIZED,
            detail      = "No hay un código activo para este correo. "
                          "Vuelve a iniciar sesión."
        )

    # Verificar que el perfil coincide
    if registro["perfil"] != perfil:
        raise HTTPException(
            status_code = status.HTTP_401_UNAUTHORIZED,
            detail      = "Código no válido para este perfil."
        )

    # Verificar que no expiró
    if datetime.utcnow() > registro["expira"]:
        del _codigos_temporales[datos.email]
        raise HTTPException(
            status_code = status.HTTP_401_UNAUTHORIZED,
            detail      = "El código expiró. Vuelve a iniciar sesión."
        )

    # Verificar que el código coincide
    if registro["codigo"] != datos.codigo.strip():
        raise HTTPException(
            status_code = status.HTTP_401_UNAUTHORIZED,
            detail      = "Código de verificación incorrecto."
        )

    # Verificar que el token coincide (seguridad extra)
    if registro["token"] != datos.token:
        raise HTTPException(
            status_code = status.HTTP_401_UNAUTHORIZED,
            detail      = "Sesión inválida. Vuelve a iniciar sesión."
        )

    # Eliminar el código (no puede reutilizarse)
    token_valido = registro["token"]
    del _codigos_temporales[datos.email]

    print(f"[2FA-EXTERNO] VERIFICADO → Perfil: {perfil} | Email: {datos.email}")

    return VerificarCodigoResponse(
        verificado   = True,
        access_token = token_valido
    )