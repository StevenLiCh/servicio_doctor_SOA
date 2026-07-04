# ============================================================
# ENDPOINT: POST /auth/login
# Servicio: ServicioDoctor
# Acción: El doctor inicia sesión con colegiatura + contraseña
# Retorna: Token JWT que debe usar en los demás endpoints
# Tabla BD: doctores.doctor_credenciales + doctores.doctores
# ============================================================

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database import SessionLocal, Base
from auth.jwt_config import crear_token
from auth.twofa import crear_codigo_para_doctor
from auth.email_service import enviar_codigo_verificacion

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import Column, Integer, String, Boolean, DateTime
from pydantic import BaseModel
from passlib.context import CryptContext
from datetime import datetime, timedelta

router = APIRouter()

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class Doctor(Base):
    """Mapea doctores.doctores — para obtener nombre y especialidad del doctor"""
    __tablename__  = "doctores"
    __table_args__ = {"schema": "doctores", "extend_existing": True}

    id           = Column(Integer, primary_key=True)
    nombres      = Column(String(100))
    apellidos    = Column(String(100))
    especialidad = Column(String(100))
    email        = Column(String(100))
    activo       = Column(Boolean, default=True)


class DoctorCredencial(Base):
    """Mapea doctores.doctor_credenciales — para verificar la contraseña"""
    __tablename__  = "doctor_credenciales"
    __table_args__ = {"schema": "doctores", "extend_existing": True}

    id                 = Column(Integer,     primary_key=True)
    doctor_id          = Column(Integer,     nullable=False)
    numero_colegiatura = Column(String(50),  nullable=False)
    password_hash      = Column(String(255), nullable=False)
    activo             = Column(Boolean,     default=True)


class LoginRequest(BaseModel):
    """CONTRATO DE ENTRADA: lo que el doctor envía para hacer login"""
    numero_colegiatura: str
    password: str


class LoginResponse(BaseModel):
    """
    CONTRATO DE SALIDA
    Ahora el login NO entrega el JWT directamente.
    Primero se envía un código de verificación al correo del doctor.
    El JWT se entrega recién en POST /auth/verificar-codigo
    """
    mensaje:            str
    requiere_codigo:    bool
    doctor_id:          int
    numero_colegiatura: str
    email_enmascarado:  str  # ej: st***@gmail.com (no exponemos el correo completo)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def enmascarar_email(email: str) -> str:
    """Convierte 'steven.li.chocano@gmail.com' en 'st***@gmail.com'"""
    if not email or "@" not in email:
        return "***"
    usuario, dominio = email.split("@", 1)
    visible = usuario[:2]
    return f"{visible}***@{dominio}"


@router.post(
    "/auth/login",
    response_model = LoginResponse,
    status_code    = 200,
    tags           = ["Autenticación"],
    summary        = "Login del doctor",
    description    = """
    PASO 1 del login (verificación en dos pasos).
    El doctor envía su número de colegiatura y contraseña.
    Si son correctos, se envía un código de 6 dígitos al correo del doctor
    y se le pide que lo confirme en POST /auth/verificar-codigo.
    El JWT recién se entrega en ese segundo endpoint.
    """
)
def post_auth_login(
    datos: LoginRequest,
    db:    Session = Depends(get_db)
):
    colegiatura = datos.numero_colegiatura.strip().upper()

    credencial = db.query(DoctorCredencial).filter(
        DoctorCredencial.numero_colegiatura == colegiatura
    ).first()

    if not credencial:
        raise HTTPException(
            status_code = status.HTTP_401_UNAUTHORIZED,
            detail      = "Número de colegiatura o contraseña incorrectos",
            headers     = {"WWW-Authenticate": "Bearer"}
        )

    if not credencial.activo:
        raise HTTPException(
            status_code = status.HTTP_401_UNAUTHORIZED,
            detail      = "Esta cuenta está desactivada. Contacta al administrador.",
            headers     = {"WWW-Authenticate": "Bearer"}
        )

    password_correcta = pwd_context.verify(datos.password, credencial.password_hash)

    if not password_correcta:
        raise HTTPException(
            status_code = status.HTTP_401_UNAUTHORIZED,
            detail      = "Número de colegiatura o contraseña incorrectos",
            headers     = {"WWW-Authenticate": "Bearer"}
        )

    doctor = db.query(Doctor).filter(
        Doctor.id == credencial.doctor_id
    ).first()

    if not doctor or not doctor.activo:
        raise HTTPException(
            status_code = status.HTTP_401_UNAUTHORIZED,
            detail      = "Doctor no encontrado o inactivo.",
            headers     = {"WWW-Authenticate": "Bearer"}
        )

    if not doctor.email:
        raise HTTPException(
            status_code = status.HTTP_400_BAD_REQUEST,
            detail      = "El doctor no tiene un correo registrado. No se puede enviar el código de verificación."
        )

    # ── Genera el código y lo guarda en doctores.codigos_2fa ─────────────────
    codigo = crear_codigo_para_doctor(db, doctor.id)

    # ── Envía el correo con el código ─────────────────────────────────────────
    enviado = enviar_codigo_verificacion(
        destinatario  = doctor.email,
        nombre_doctor = f"Dr. {doctor.nombres} {doctor.apellidos}",
        codigo        = codigo
    )

    if not enviado:
        raise HTTPException(
            status_code = status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail      = "No se pudo enviar el código de verificación. Intenta nuevamente."
        )

    print(f"[AUTH] PASSWORD_OK_CODIGO_ENVIADO → "
          f"Dr. {doctor.nombres} {doctor.apellidos} | "
          f"Colegiatura: {colegiatura} | "
          f"ID: {doctor.id}")

    return LoginResponse(
        mensaje            = "Contraseña correcta. Se envió un código de verificación a tu correo.",
        requiere_codigo    = True,
        doctor_id          = doctor.id,
        numero_colegiatura = colegiatura,
        email_enmascarado  = enmascarar_email(doctor.email)
    )