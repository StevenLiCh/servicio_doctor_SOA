# ============================================================
# ENDPOINT: POST /auth/verificar-codigo
# Servicio: ServicioDoctor
# Acción: PASO 2 del login (verificación en dos pasos)
#         El doctor envía el código de 6 dígitos que le llegó al correo.
#         Si es correcto, recién aquí se entrega el JWT.
# Tabla BD: doctores.codigos_2fa + doctores.doctores
# ============================================================

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database import SessionLocal, Base
from auth.jwt_config import crear_token
from auth.twofa import validar_codigo, crear_codigo_para_doctor
from auth.email_service import enviar_codigo_verificacion

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import Column, Integer, String, Boolean, DateTime
from pydantic import BaseModel, field_validator

router = APIRouter()


class Doctor(Base):
    """Mapea doctores.doctores"""
    __tablename__  = "doctores"
    __table_args__ = {"schema": "doctores", "extend_existing": True}

    id           = Column(Integer, primary_key=True)
    nombres      = Column(String(100))
    apellidos    = Column(String(100))
    especialidad = Column(String(100))
    email        = Column(String(100))
    activo       = Column(Boolean, default=True)


class VerificarCodigoRequest(BaseModel):
    """Lo que envía el doctor en el paso 2"""
    doctor_id:          int
    numero_colegiatura: str
    codigo:             str

    @field_validator("codigo")
    @classmethod
    def validar_formato_codigo(cls, v):
        v = v.strip()
        if not v.isdigit() or len(v) != 6:
            raise ValueError("El código debe tener exactamente 6 dígitos")
        return v


class VerificarCodigoResponse(BaseModel):
    """Lo que devolvemos si el código es correcto: el JWT real"""
    access_token:       str
    token_type:         str
    doctor_id:          int
    nombre:             str
    especialidad:       str
    numero_colegiatura: str
    expira_en_minutos:  int


class ReenviarCodigoRequest(BaseModel):
    doctor_id: int


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.post(
    "/auth/verificar-codigo",
    response_model = VerificarCodigoResponse,
    status_code    = 200,
    tags           = ["Autenticación"],
    summary        = "Verificar código 2FA y obtener el token JWT",
    description    = """
    PASO 2 del login (verificación en dos pasos).
    El doctor ingresa el código de 6 dígitos que recibió por correo.
    Si es correcto y no ha expirado (5 minutos), se entrega el JWT.
    """
)
def post_auth_verificar_codigo(
    datos: VerificarCodigoRequest,
    db:    Session = Depends(get_db)
):
    colegiatura = datos.numero_colegiatura.strip().upper()

    codigo_valido = validar_codigo(db, datos.doctor_id, datos.codigo)

    if not codigo_valido:
        raise HTTPException(
            status_code = status.HTTP_401_UNAUTHORIZED,
            detail      = "Código inválido o expirado. Solicita uno nuevo."
        )

    doctor = db.query(Doctor).filter(
        Doctor.id == datos.doctor_id
    ).first()

    if not doctor or not doctor.activo:
        raise HTTPException(
            status_code = status.HTTP_401_UNAUTHORIZED,
            detail      = "Doctor no encontrado o inactivo."
        )

    token_payload = {
        "sub"          : colegiatura,
        "doctor_id"    : doctor.id,
        "nombre"       : f"Dr. {doctor.nombres} {doctor.apellidos}",
        "especialidad" : doctor.especialidad,
    }
    token = crear_token(data=token_payload)

    print(f"[AUTH] LOGIN_2FA_EXITOSO → "
          f"Dr. {doctor.nombres} {doctor.apellidos} | "
          f"Colegiatura: {colegiatura} | "
          f"ID: {doctor.id}")

    return VerificarCodigoResponse(
        access_token       = token,
        token_type         = "bearer",
        doctor_id          = doctor.id,
        nombre             = f"Dr. {doctor.nombres} {doctor.apellidos}",
        especialidad       = doctor.especialidad,
        numero_colegiatura = colegiatura,
        expira_en_minutos  = 60
    )


@router.post(
    "/auth/reenviar-codigo",
    status_code = 200,
    tags        = ["Autenticación"],
    summary     = "Reenviar el código de verificación",
    description = "Genera y envía un nuevo código de 6 dígitos al correo del doctor."
)
def post_auth_reenviar_codigo(
    datos: ReenviarCodigoRequest,
    db:    Session = Depends(get_db)
):
    doctor = db.query(Doctor).filter(
        Doctor.id == datos.doctor_id
    ).first()

    if not doctor or not doctor.activo:
        raise HTTPException(
            status_code = status.HTTP_404_NOT_FOUND,
            detail      = "Doctor no encontrado o inactivo."
        )

    if not doctor.email:
        raise HTTPException(
            status_code = status.HTTP_400_BAD_REQUEST,
            detail      = "El doctor no tiene un correo registrado."
        )

    codigo  = crear_codigo_para_doctor(db, doctor.id)
    enviado = enviar_codigo_verificacion(
        destinatario  = doctor.email,
        nombre_doctor = f"Dr. {doctor.nombres} {doctor.apellidos}",
        codigo        = codigo
    )

    if not enviado:
        raise HTTPException(
            status_code = status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail      = "No se pudo enviar el código de verificación."
        )

    return {"mensaje": "Se envió un nuevo código de verificación a tu correo."}