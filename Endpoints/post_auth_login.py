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

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import Column, Integer, String, Boolean, DateTime
from pydantic import BaseModel
from passlib.context import CryptContext
from datetime import datetime, timedelta

router = APIRouter()

# ── Configuración de bcrypt ───────────────────────────────────────────────────
# Mismo contexto que en registro para que los hashes sean compatibles
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


# ── Modelos ORM ───────────────────────────────────────────────────────────────

class Doctor(Base):
    """Mapea doctores.doctores — para obtener nombre y especialidad del doctor"""
    __tablename__  = "doctores"
    __table_args__ = {"schema": "doctores", "extend_existing": True}

    id           = Column(Integer, primary_key=True)
    nombres      = Column(String(100))
    apellidos    = Column(String(100))
    especialidad = Column(String(100))
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


# ── Schemas Pydantic ──────────────────────────────────────────────────────────

class LoginRequest(BaseModel):
    """
    CONTRATO DE ENTRADA
    Lo que el doctor envía para hacer login
    """
    # El número de colegiatura como usuario (ej: "CMP-001")
    numero_colegiatura: str

    # La contraseña en texto plano (solo viaja en HTTPS, nunca se guarda así)
    password: str


class LoginResponse(BaseModel):
    """
    CONTRATO DE SALIDA
    Lo que devolvemos al doctor cuando el login es exitoso
    """
    # El token JWT — el doctor debe guardarlo y enviarlo en cada request
    access_token: str

    # Siempre "bearer" — es el tipo estándar de token
    token_type: str

    # Información del doctor autenticado (para que el frontend la muestre)
    doctor_id:          int
    nombre:             str
    especialidad:       str
    numero_colegiatura: str

    # Cuántos minutos dura el token
    expira_en_minutos: int


# ── Dependencia BD ────────────────────────────────────────────────────────────
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ── ENDPOINT ──────────────────────────────────────────────────────────────────
@router.post(
    "/auth/login",
    response_model = LoginResponse,
    status_code    = 200,
    tags           = ["Autenticación"],
    summary        = "Login del doctor",
    description    = """
    El doctor inicia sesión con su número de colegiatura y contraseña.
    Si las credenciales son correctas, recibe un token JWT.
    Ese token debe enviarse en el header de los endpoints protegidos:
        Authorization: Bearer <token>
    """
)
def post_auth_login(
    datos: LoginRequest,
    db:    Session = Depends(get_db)
):
    # Limpiamos el número de colegiatura (quitamos espacios, ponemos mayúsculas)
    colegiatura = datos.numero_colegiatura.strip().upper()

    # ── PASO 1: Buscar las credenciales por número de colegiatura ────────────
    credencial = db.query(DoctorCredencial).filter(
        DoctorCredencial.numero_colegiatura == colegiatura
    ).first()

    # IMPORTANTE: Si las credenciales no existen O la contraseña es incorrecta,
    # devolvemos el MISMO error. Esto es intencional por seguridad:
    # no queremos revelar si el usuario existe o no.
    if not credencial:
        raise HTTPException(
            status_code = status.HTTP_401_UNAUTHORIZED,
            detail      = "Número de colegiatura o contraseña incorrectos",
            headers     = {"WWW-Authenticate": "Bearer"}
        )

    # ── PASO 2: Verificar que las credenciales estén activas ─────────────────
    if not credencial.activo:
        raise HTTPException(
            status_code = status.HTTP_401_UNAUTHORIZED,
            detail      = "Esta cuenta está desactivada. Contacta al administrador.",
            headers     = {"WWW-Authenticate": "Bearer"}
        )

    # ── PASO 3: Verificar la contraseña con bcrypt ───────────────────────────
    # pwd_context.verify() compara la contraseña en texto plano
    # contra el hash guardado en la BD — NUNCA desencripta el hash
    # Retorna True si coinciden, False si no
    password_correcta = pwd_context.verify(datos.password, credencial.password_hash)

    if not password_correcta:
        # Mismo error que arriba (no revelamos si fue el usuario o la contraseña)
        raise HTTPException(
            status_code = status.HTTP_401_UNAUTHORIZED,
            detail      = "Número de colegiatura o contraseña incorrectos",
            headers     = {"WWW-Authenticate": "Bearer"}
        )

    # ── PASO 4: Obtener los datos del doctor para el token ───────────────────
    doctor = db.query(Doctor).filter(
        Doctor.id == credencial.doctor_id
    ).first()

    if not doctor or not doctor.activo:
        raise HTTPException(
            status_code = status.HTTP_401_UNAUTHORIZED,
            detail      = "Doctor no encontrado o inactivo.",
            headers     = {"WWW-Authenticate": "Bearer"}
        )

    # ── PASO 5: Crear el token JWT ───────────────────────────────────────────
    # El payload es lo que quedará DENTRO del token (se puede leer pero no modificar)
    # "sub" (subject) es el campo estándar del JWT para identificar al usuario
    token_payload = {
        "sub"          : colegiatura,          # identificador principal
        "doctor_id"    : doctor.id,            # ID en la BD
        "nombre"       : f"Dr. {doctor.nombres} {doctor.apellidos}",
        "especialidad" : doctor.especialidad,
    }

    # Creamos el token con la función de jwt_config.py
    token = crear_token(data=token_payload)

    # ── Registrar en consola (para auditoría en desarrollo) ───────────────────
    print(f"[AUTH] LOGIN_EXITOSO → "
          f"Dr. {doctor.nombres} {doctor.apellidos} | "
          f"Colegiatura: {colegiatura} | "
          f"ID: {doctor.id}")

    return LoginResponse(
        access_token       = token,
        token_type         = "bearer",
        doctor_id          = doctor.id,
        nombre             = f"Dr. {doctor.nombres} {doctor.apellidos}",
        especialidad       = doctor.especialidad,
        numero_colegiatura = colegiatura,
        expira_en_minutos  = 60
    )