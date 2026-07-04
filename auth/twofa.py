# ============================================================
# auth/twofa.py
# Ubicación: ServicioDoctor/auth/twofa.py
# Propósito: Todo lo relacionado a la verificación en dos pasos (2FA)
#   - Modelo ORM de la tabla doctores.codigos_2fa
#   - Generar códigos de 6 dígitos
#   - Guardar el código en la BD
#   - Validar el código que envía el doctor
# ============================================================

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import random
from datetime import datetime, timedelta
from sqlalchemy import Column, Integer, String, Boolean, DateTime
from sqlalchemy.orm import Session
from database import Base

MINUTOS_EXPIRACION = 5


class CodigoVerificacion(Base):
    """Mapea doctores.codigos_2fa — guarda los códigos OTP del 2FA"""
    __tablename__  = "codigos_2fa"
    __table_args__ = {"schema": "doctores", "extend_existing": True}

    id         = Column(Integer, primary_key=True)
    doctor_id  = Column(Integer, nullable=False)
    codigo     = Column(String(6), nullable=False)
    usado      = Column(Boolean, default=False)
    creado_en  = Column(DateTime, default=datetime.utcnow)
    expira_en  = Column(DateTime, nullable=False)


def generar_codigo() -> str:
    """Genera un código numérico de 6 dígitos, ej: '045213'"""
    return f"{random.randint(0, 999999):06d}"


def crear_codigo_para_doctor(db: Session, doctor_id: int) -> str:
    """
    Invalida los códigos anteriores no usados del doctor y crea uno nuevo.
    Retorna el código en texto plano (para enviarlo por correo).
    """
    db.query(CodigoVerificacion).filter(
        CodigoVerificacion.doctor_id == doctor_id,
        CodigoVerificacion.usado == False
    ).update({"usado": True})

    codigo = generar_codigo()
    nuevo = CodigoVerificacion(
        doctor_id = doctor_id,
        codigo    = codigo,
        usado     = False,
        expira_en = datetime.utcnow() + timedelta(minutes=MINUTOS_EXPIRACION)
    )
    db.add(nuevo)
    db.commit()

    return codigo


def validar_codigo(db: Session, doctor_id: int, codigo_ingresado: str) -> bool:
    """
    Revisa si el código ingresado es válido para ese doctor:
    - Debe existir
    - No debe estar usado
    - No debe haber expirado
    """
    registro = db.query(CodigoVerificacion).filter(
        CodigoVerificacion.doctor_id == doctor_id,
        CodigoVerificacion.codigo    == codigo_ingresado,
        CodigoVerificacion.usado     == False
    ).order_by(CodigoVerificacion.id.desc()).first()

    if not registro:
        return False

    if registro.expira_en < datetime.utcnow():
        return False

    registro.usado = True
    db.commit()

    return True