# ============================================================
# ENDPOINT: POST /auth/verificar
# Servicio: ServicioDoctor
# Acción: PASO 2 del login con 2FA
#         El doctor ingresa el código recibido por email.
#         Si es válido y no expiró, se entrega el JWT.
# Tablas BD: doctores.doctores, doctores.codigos_2fa
# ============================================================

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database import SessionLocal, Base

from auth.jwt_config import crear_token

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import Column, Integer, String, Boolean, DateTime
from pydantic import BaseModel
from datetime import datetime

router = APIRouter()

# ── Modelos ORM ───────────────────────────────────────────────────────────────
class Doctor(Base):
    __tablename__  = "doctores"
    __table_args__ = {"schema": "doctores", "extend_existing": True}

    id                 = Column(Integer, primary_key=True)
    nombres            = Column(String(100))
    apellidos          = Column(String(100))
    especialidad       = Column(String(100))
    numero_colegiatura = Column(String(50))
    activo             = Column(Boolean, default=True)

class Codigo2FA(Base):
    """Mapea doctores.codigos_2fa"""
    __tablename__  = "codigos_2fa"
    __table_args__ = {"schema": "doctores", "extend_existing": True}

    id        = Column(Integer,   primary_key=True)
    doctor_id = Column(Integer,   nullable=False)
    codigo    = Column(String(6), nullable=False)
    expira_en = Column(DateTime,  nullable=False)
    usado     = Column(Boolean,   default=False)
    creado_en = Column(DateTime,  default=datetime.utcnow)

# ── Schemas Pydantic ──────────────────────────────────────────────────────────
class VerificarRequest(BaseModel):
    """CONTRATO DE ENTRADA — lo que el doctor envía para verificar el código"""
    doctor_id: int    # Viene de la respuesta del PASO 1 (login)
    codigo:    str    # El código de 6 dígitos recibido por email

class VerificarResponse(BaseModel):
    """
    CONTRATO DE SALIDA del PASO 2
    Devuelve el JWT completo — idéntico al login original sin 2FA.
    """
    access_token:       str
    token_type:         str
    doctor_id:          int
    nombre:             str
    especialidad:       str
    numero_colegiatura: str
    expira_en_minutos:  int

# ── Dependencia BD ────────────────────────────────────────────────────────────
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# ── ENDPOINT ──────────────────────────────────────────────────────────────────
@router.post(
    "/auth/verificar",
    response_model = VerificarResponse,
    status_code    = 200,
    tags           = ["Autenticación"],
    summary        = "Verificar código 2FA — PASO 2 (entrega el JWT)",
    description    = """
    PASO 2 del login con doble autenticación.
    El doctor ingresa el código de 6 dígitos recibido por email.
    Si el código es válido y no expiró (5 minutos), se devuelve el JWT
    para acceder a los endpoints protegidos.
    """
)
def post_auth_verificar(
    datos: VerificarRequest,
    db:    Session = Depends(get_db)
):
    # ── PASO 1: Buscar el código en la BD ─────────────────────────────────────
    registro = db.query(Codigo2FA).filter(
        Codigo2FA.doctor_id == datos.doctor_id,
        Codigo2FA.codigo    == datos.codigo.strip(),
        Codigo2FA.usado     == False
    ).first()

    if not registro:
        raise HTTPException(
            status_code = status.HTTP_401_UNAUTHORIZED,
            detail      = "Código de verificación incorrecto o ya fue usado."
        )

    # ── PASO 2: Verificar que no expiró ──────────────────────────────────────
    if datetime.utcnow() > registro.expira_en:
        # Limpiar el código expirado
        db.delete(registro)
        db.commit()
        raise HTTPException(
            status_code = status.HTTP_401_UNAUTHORIZED,
            detail      = "El código de verificación expiró. "
                          "Vuelve a iniciar sesión para recibir uno nuevo."
        )

    # ── PASO 3: Marcar el código como usado (no puede reutilizarse) ──────────
    registro.usado = True
    db.commit()

    # ── PASO 4: Obtener los datos del doctor para el token ────────────────────
    doctor = db.query(Doctor).filter(Doctor.id == datos.doctor_id).first()

    if not doctor or not doctor.activo:
        raise HTTPException(
            status_code = status.HTTP_401_UNAUTHORIZED,
            detail      = "Doctor no encontrado o inactivo."
        )

    # ── PASO 5: Crear el token JWT ────────────────────────────────────────────
    token_payload = {
        "sub"          : doctor.numero_colegiatura,
        "doctor_id"    : doctor.id,
        "nombre"       : f"Dr. {doctor.nombres} {doctor.apellidos}",
        "especialidad" : doctor.especialidad,
    }

    token = crear_token(data=token_payload)

    print(f"[2FA] LOGIN_COMPLETO → Dr. {doctor.nombres} {doctor.apellidos} "
          f"| Colegiatura: {doctor.numero_colegiatura} | ID: {doctor.id}")

    return VerificarResponse(
        access_token       = token,
        token_type         = "bearer",
        doctor_id          = doctor.id,
        nombre             = f"Dr. {doctor.nombres} {doctor.apellidos}",
        especialidad       = doctor.especialidad,
        numero_colegiatura = doctor.numero_colegiatura,
        expira_en_minutos  = 60
    )