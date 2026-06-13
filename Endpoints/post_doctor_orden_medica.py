# ============================================================
# ENDPOINT: POST /doctor/orden-medica
# Servicio: ServicioDoctores
# Acción: El doctor genera una orden médica para un paciente
# Tabla BD: doctores.ordenes_medicas
#
# PROTEGIDO CON JWT: requiere header Authorization: Bearer <token>
# ============================================================

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from database import SessionLocal, Base

# ── NUEVO: importar la dependencia que valida el JWT ──────────────────────────
from auth.jwt_config import get_doctor_actual

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import Column, Integer, String, Text, Date, DateTime, Boolean
from pydantic import BaseModel
from typing import Optional
from datetime import date, datetime

router = APIRouter()

# ── Modelos ORM ───────────────────────────────────────────────────────────────
class Doctor(Base):
    __tablename__  = "doctores"
    __table_args__ = {"schema": "doctores", "extend_existing": True}

    id        = Column(Integer, primary_key=True)
    nombres   = Column(String(100))
    apellidos = Column(String(100))
    activo    = Column(Boolean, default=True)

class OrdenMedica(Base):
    __tablename__  = "ordenes_medicas"
    __table_args__ = {"schema": "doctores", "extend_existing": True}

    id                = Column(Integer,    primary_key=True)
    paciente_id       = Column(Integer,    nullable=False)
    doctor_id         = Column(Integer,    nullable=False)
    tipo_orden        = Column(String(50))
    detalle           = Column(Text,       nullable=False)
    fecha_emision     = Column(Date,       default=date.today)
    fecha_vencimiento = Column(Date,       nullable=False)
    estado            = Column(String(30), default="EMITIDA")
    resultado         = Column(Text)
    creado_en         = Column(DateTime,   default=datetime.utcnow)

# ── NUEVO: modelo para verificar que exista un diagnóstico previo ────────────
class Diagnostico(Base):
    __tablename__  = "diagnosticos"
    __table_args__ = {"schema": "doctores", "extend_existing": True}

    id          = Column(Integer, primary_key=True)
    paciente_id = Column(Integer, nullable=False)
    doctor_id   = Column(Integer, nullable=False)

# ── Schemas Pydantic ──────────────────────────────────────────────────────────
class OrdenCreate(BaseModel):
    """CONTRATO DE ENTRADA"""
    paciente_id:       int
    doctor_id:         int
    tipo_orden:        str   # LABORATORIO|IMAGENOLOGIA|ESPECIALISTA|PROCEDIMIENTO
    detalle:           str
    fecha_vencimiento: date  # Formato YYYY-MM-DD

class OrdenResponse(BaseModel):
    """CONTRATO DE SALIDA"""
    id:                int
    paciente_id:       int
    doctor_id:         int
    tipo_orden:        Optional[str]
    detalle:           str
    fecha_emision:     Optional[date]
    fecha_vencimiento: date
    estado:            str
    class Config:
        from_attributes = True

# ── Dependencia BD ────────────────────────────────────────────────────────────
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# ── ENDPOINT ──────────────────────────────────────────────────────────────────
@router.post(
    "/doctor/orden-medica",
    response_model = OrdenResponse,
    status_code    = 201,
    tags           = ["ServicioDoctores"],
    summary        = "Emitir orden médica",
    description    = """
    El doctor genera una orden médica para el paciente.
    Tipos válidos: LABORATORIO, IMAGENOLOGIA, ESPECIALISTA, PROCEDIMIENTO.
    En SOA real publica evento ORDEN_CREADA al Message Broker.

    Requiere autenticación: Authorization: Bearer <token>
    """
)
def post_doctor_orden_medica(
    datos: OrdenCreate,
    db:    Session = Depends(get_db),
    # ── NUEVO: exige el JWT y trae los datos del doctor autenticado ───────────
    doctor_actual: dict = Depends(get_doctor_actual)
):
    # ── NUEVO REGLA 0: El doctor del token debe coincidir con doctor_id ───────
    if doctor_actual["doctor_id"] != datos.doctor_id:
        raise HTTPException(
            status_code = 403,
            detail      = "No puedes emitir órdenes médicas en nombre de otro doctor"
        )

    # ── REGLA 1: Doctor existe ────────────────────────────────────────────────
    doctor = db.query(Doctor).filter(Doctor.id == datos.doctor_id).first()
    if not doctor:
        raise HTTPException(
            status_code = 404,
            detail      = f"Doctor ID {datos.doctor_id} no encontrado"
        )

    # ── NUEVO REGLA 1.5: Debe existir un diagnóstico previo del paciente ──────
    # Una orden médica solo se puede emitir si el doctor ya diagnosticó al paciente
    diagnostico_existente = db.query(Diagnostico).filter(
        Diagnostico.paciente_id == datos.paciente_id,
        Diagnostico.doctor_id   == datos.doctor_id
    ).first()

    if not diagnostico_existente:
        raise HTTPException(
            status_code = 400,
            detail      = "No puedes emitir una orden médica sin un diagnóstico previo "
                          "de este paciente. Registra primero el diagnóstico."
        )

    # ── REGLA 2: Tipo de orden válido ─────────────────────────────────────────
    tipos_validos = ["LABORATORIO", "IMAGENOLOGIA", "ESPECIALISTA", "PROCEDIMIENTO"]
    tipo = datos.tipo_orden.upper()
    if tipo not in tipos_validos:
        raise HTTPException(
            status_code = 400,
            detail      = f"Tipo inválido. Opciones: {tipos_validos}"
        )

    # ── REGLA 3: Fecha de vencimiento futura ──────────────────────────────────
    if datos.fecha_vencimiento <= date.today():
        raise HTTPException(
            status_code = 400,
            detail      = "La fecha de vencimiento debe ser posterior a hoy"
        )

    # ── GUARDAR en PostgreSQL ─────────────────────────────────────────────────
    nueva = OrdenMedica(
        paciente_id       = datos.paciente_id,
        doctor_id         = datos.doctor_id,
        tipo_orden        = tipo,
        detalle           = datos.detalle,
        fecha_emision     = date.today(),
        fecha_vencimiento = datos.fecha_vencimiento,
        estado            = "EMITIDA"
    )

    db.add(nueva)
    db.commit()
    db.refresh(nueva)

    # ── EVENTO SOA (simulado) ─────────────────────────────────────────────────
    print(f"[EVENTO] ORDEN_CREADA → "
          f"Tipo: {tipo} | "
          f"Dr. {doctor.nombres} | "
          f"Paciente: {datos.paciente_id} | "
          f"Vence: {datos.fecha_vencimiento}")

    return nueva