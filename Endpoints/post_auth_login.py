# ============================================================
# ENDPOINT: POST /auth/login
# Servicio: ServicioDoctor
# Acción: PASO 1 del login con 2FA
#         Verifica colegiatura + password y si son correctos,
#         envía un código de 6 dígitos al email del doctor.
#         El JWT se entrega solo cuando el doctor verifica el código
#         en el endpoint POST /auth/verificar (PASO 2).
# Tablas BD: doctores.doctores, doctores.doctor_credenciales,
#            doctores.codigos_2fa
# ============================================================

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database import SessionLocal, Base

from auth.email_config import enviar_codigo_2fa

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import Column, Integer, String, Boolean, DateTime
from pydantic import BaseModel
from passlib.context import CryptContext
from datetime import datetime, timedelta
import random

router = APIRouter()

# ── Configuración de bcrypt ───────────────────────────────────────────────────
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# ── Modelos ORM ───────────────────────────────────────────────────────────────
class Doctor(Base):
    __tablename__  = "doctores"
    __table_args__ = {"schema": "doctores", "extend_existing": True}

    id           = Column(Integer, primary_key=True)
    nombres      = Column(String(100))
    apellidos    = Column(String(100))
    especialidad = Column(String(100))
    email        = Column(String(100))
    activo       = Column(Boolean, default=True)

class DoctorCredencial(Base):
    __tablename__  = "doctor_credenciales"
    __table_args__ = {"schema": "doctores", "extend_existing": True}

    id                 = Column(Integer,     primary_key=True)
    doctor_id          = Column(Integer,     nullable=False)
    numero_colegiatura = Column(String(50),  nullable=False)
    password_hash      = Column(String(255), nullable=False)
    activo             = Column(Boolean,     default=True)

class Codigo2FA(Base):
    """Mapea doctores.codigos_2fa — códigos temporales de verificación"""
    __tablename__  = "codigos_2fa"
    __table_args__ = {"schema": "doctores", "extend_existing": True}

    id        = Column(Integer,   primary_key=True)
    doctor_id = Column(Integer,   nullable=False)
    codigo    = Column(String(6), nullable=False)
    expira_en = Column(DateTime,  nullable=False)
    usado     = Column(Boolean,   default=False)
    creado_en = Column(DateTime,  default=datetime.utcnow)

# ── Schemas Pydantic ──────────────────────────────────────────────────────────
class LoginRequest(BaseModel):
    """CONTRATO DE ENTRADA — lo que el doctor envía para iniciar sesión"""
    numero_colegiatura: str
    password:           str

class LoginResponse(BaseModel):
    """
    CONTRATO DE SALIDA del PASO 1
    Ya NO devuelve el JWT — devuelve confirmación de que el código fue enviado.
    El JWT se entrega en POST /auth/verificar (PASO 2).
    """
    mensaje:            str
    codigo_enviado:     bool
    email_destino:      str   # Solo los primeros caracteres (por seguridad)
    doctor_id:          int
    expira_en_minutos:  int

# ── Dependencia BD ────────────────────────────────────────────────────────────
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# ── FUNCIÓN: Enmascarar email ─────────────────────────────────────────────────
def enmascarar_email(email: str) -> str:
    """
    Muestra el email parcialmente por seguridad.
    Ej: ana.torres@hospital.com → a**@hospital.com
    """
    try:
        usuario, dominio = email.split("@")
        usuario_oculto = usuario[0] + "**"
        return f"{usuario_oculto}@{dominio}"
    except Exception:
        return "***@***.com"

# ── ENDPOINT ──────────────────────────────────────────────────────────────────
@router.post(
    "/auth/login",
    response_model = LoginResponse,
    status_code    = 200,
    tags           = ["Autenticación"],
    summary        = "Login del doctor — PASO 1 (envía código 2FA al email)",
    description    = """
    PASO 1 del login con doble autenticación.
    Verifica las credenciales del doctor y si son correctas,
    envía un código de 6 dígitos al email registrado.

    El token JWT se entrega en el PASO 2:
        POST /auth/verificar → con el código recibido por email.
    """
)
def post_auth_login(
    datos: LoginRequest,
    db:    Session = Depends(get_db)
):
    colegiatura = datos.numero_colegiatura.strip().upper()

    # ── PASO 1: Buscar credenciales ───────────────────────────────────────────
    credencial = db.query(DoctorCredencial).filter(
        DoctorCredencial.numero_colegiatura == colegiatura
    ).first()

    # Mismo error si no existe o si la contraseña es incorrecta (seguridad)
    if not credencial or not credencial.activo:
        raise HTTPException(
            status_code = status.HTTP_401_UNAUTHORIZED,
            detail      = "Número de colegiatura o contraseña incorrectos",
            headers     = {"WWW-Authenticate": "Bearer"}
        )

    # ── PASO 2: Verificar contraseña ──────────────────────────────────────────
    if not pwd_context.verify(datos.password[:72], credencial.password_hash):
        raise HTTPException(
            status_code = status.HTTP_401_UNAUTHORIZED,
            detail      = "Número de colegiatura o contraseña incorrectos",
            headers     = {"WWW-Authenticate": "Bearer"}
        )

    # ── PASO 3: Obtener datos del doctor ──────────────────────────────────────
    doctor = db.query(Doctor).filter(Doctor.id == credencial.doctor_id).first()

    if not doctor or not doctor.activo:
        raise HTTPException(
            status_code = status.HTTP_401_UNAUTHORIZED,
            detail      = "Doctor no encontrado o inactivo."
        )

    if not doctor.email:
        raise HTTPException(
            status_code = status.HTTP_400_BAD_REQUEST,
            detail      = "El doctor no tiene email registrado. "
                          "Contacta al administrador para agregarlo."
        )

    # ── PASO 4: Generar código 2FA de 6 dígitos ───────────────────────────────
    # Generamos un número entre 100000 y 999999 (siempre 6 dígitos)
    codigo = str(random.randint(100000, 999999))
    expira = datetime.utcnow() + timedelta(minutes=5)

    # ── PASO 5: Invalidar códigos anteriores del mismo doctor ─────────────────
    # Para que no acumule códigos viejos en la tabla
    db.query(Codigo2FA).filter(
        Codigo2FA.doctor_id == doctor.id,
        Codigo2FA.usado     == False
    ).delete()

    # ── PASO 6: Guardar el nuevo código en la BD ──────────────────────────────
    nuevo_codigo = Codigo2FA(
        doctor_id = doctor.id,
        codigo    = codigo,
        expira_en = expira,
        usado     = False
    )
    db.add(nuevo_codigo)
    db.commit()

    # ── PASO 7: Enviar el código por email ────────────────────────────────────
    enviado = enviar_codigo_2fa(
        email_destino = doctor.email,
        nombre_doctor = f"Dr. {doctor.nombres} {doctor.apellidos}",
        codigo        = codigo
    )

    if not enviado:
        raise HTTPException(
            status_code = 500,
            detail      = "No se pudo enviar el código de verificación. "
                          "Verifica tu email o contacta al administrador."
        )

    print(f"[2FA] LOGIN_PASO1 → Dr. {doctor.nombres} {doctor.apellidos} "
          f"| Colegiatura: {colegiatura} "
          f"| Código enviado a: {doctor.email}")

    return LoginResponse(
        mensaje           = "Código de verificación enviado a tu correo electrónico",
        codigo_enviado    = True,
        email_destino     = enmascarar_email(doctor.email),
        doctor_id         = doctor.id,
        expira_en_minutos = 5
    )