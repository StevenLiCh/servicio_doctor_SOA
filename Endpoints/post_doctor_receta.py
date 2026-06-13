# ============================================================
# ENDPOINT: POST /doctor/receta
# Servicio: ServicioDoctores
# Acción: El doctor emite una receta médica para un paciente
# Tabla BD: pacientes.recetas
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

class Receta(Base):
    """
    Mapea pacientes.recetas de PostgreSQL
    Aunque la crea el doctor, se guarda en el esquema pacientes
    porque pertenece al historial del paciente
    """
    __tablename__  = "recetas"
    __table_args__ = {"schema": "pacientes", "extend_existing": True}

    id                = Column(Integer,    primary_key=True)
    paciente_id       = Column(Integer,    nullable=False)
    doctor_id         = Column(Integer,    nullable=False)
    orden_medica_id   = Column(Integer)    # Opcional: vincular a una orden médica
    medicamento       = Column(String(150),nullable=False)
    dosis             = Column(String(100))
    duracion          = Column(String(100))
    indicaciones      = Column(Text)
    fecha_emision     = Column(Date,       default=date.today)
    fecha_vencimiento = Column(Date)
    estado            = Column(String(30), default="VIGENTE")
    creado_en         = Column(DateTime,   default=datetime.utcnow)

# ── NUEVO: modelo para verificar que exista un diagnóstico previo ────────────
class Diagnostico(Base):
    __tablename__  = "diagnosticos"
    __table_args__ = {"schema": "doctores", "extend_existing": True}

    id          = Column(Integer, primary_key=True)
    paciente_id = Column(Integer, nullable=False)
    doctor_id   = Column(Integer, nullable=False)

# ── Schemas Pydantic ──────────────────────────────────────────────────────────
class RecetaCreate(BaseModel):
    """CONTRATO DE ENTRADA"""
    paciente_id:       int
    doctor_id:         int
    orden_medica_id:   Optional[int]  = None  # Si viene de una orden médica
    medicamento:       str
    dosis:             Optional[str]  = None   # Ej: 500mg
    duracion:          Optional[str]  = None   # Ej: 7 días
    indicaciones:      Optional[str]  = None   # Ej: Tomar después de comer
    fecha_vencimiento: Optional[date] = None   # Hasta cuándo es válida

class RecetaResponse(BaseModel):
    """CONTRATO DE SALIDA"""
    id:                int
    paciente_id:       int
    doctor_id:         int
    orden_medica_id:   Optional[int]
    medicamento:       str
    dosis:             Optional[str]
    duracion:          Optional[str]
    indicaciones:      Optional[str]
    fecha_emision:     Optional[date]
    fecha_vencimiento: Optional[date]
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
    "/doctor/receta",
    response_model = RecetaResponse,
    status_code    = 201,
    tags           = ["ServicioDoctores"],
    summary        = "Emitir receta médica",
    description    = """
    El doctor emite una receta médica para un paciente.
    Se guarda en pacientes.recetas porque pertenece al historial del paciente.
    Puede vincularse a una orden médica existente mediante orden_medica_id.

    Requiere autenticación: Authorization: Bearer <token>
    """
)
def post_doctor_receta(
    datos: RecetaCreate,
    db:    Session = Depends(get_db),
    # ── NUEVO: exige el JWT y trae los datos del doctor autenticado ───────────
    doctor_actual: dict = Depends(get_doctor_actual)
):
    # ── NUEVO REGLA 0: El doctor del token debe coincidir con doctor_id ───────
    if doctor_actual["doctor_id"] != datos.doctor_id:
        raise HTTPException(
            status_code = 403,
            detail      = "No puedes emitir recetas en nombre de otro doctor"
        )

    # ── REGLA 1: Doctor existe ────────────────────────────────────────────────
    doctor = db.query(Doctor).filter(Doctor.id == datos.doctor_id).first()
    if not doctor:
        raise HTTPException(
            status_code = 404,
            detail      = f"Doctor ID {datos.doctor_id} no encontrado"
        )

    # ── NUEVO REGLA 1.5: Debe existir un diagnóstico previo del paciente ──────
    # Una receta solo se puede emitir si el doctor ya diagnosticó al paciente
    diagnostico_existente = db.query(Diagnostico).filter(
        Diagnostico.paciente_id == datos.paciente_id,
        Diagnostico.doctor_id   == datos.doctor_id
    ).first()

    if not diagnostico_existente:
        raise HTTPException(
            status_code = 400,
            detail      = "No puedes emitir una receta sin un diagnóstico previo "
                          "de este paciente. Registra primero el diagnóstico."
        )

    # ── REGLA 2: Medicamento obligatorio ─────────────────────────────────────
    if not datos.medicamento.strip():
        raise HTTPException(
            status_code = 400,
            detail      = "El nombre del medicamento es obligatorio"
        )

    # ── REGLA 3: Fecha vencimiento futura si se provee ────────────────────────
    if datos.fecha_vencimiento and datos.fecha_vencimiento <= date.today():
        raise HTTPException(
            status_code = 400,
            detail      = "La fecha de vencimiento debe ser posterior a hoy"
        )

    # ── GUARDAR en PostgreSQL (esquema pacientes) ─────────────────────────────
    nueva = Receta(
        paciente_id       = datos.paciente_id,
        doctor_id         = datos.doctor_id,
        orden_medica_id   = datos.orden_medica_id,
        medicamento       = datos.medicamento,
        dosis             = datos.dosis,
        duracion          = datos.duracion,
        indicaciones      = datos.indicaciones,
        fecha_emision     = date.today(),
        fecha_vencimiento = datos.fecha_vencimiento,
        estado            = "VIGENTE"
    )

    db.add(nueva)
    db.commit()
    db.refresh(nueva)

    # ── EVENTO SOA (simulado) ─────────────────────────────────────────────────
    print(f"[EVENTO] RECETA_EMITIDA → "
          f"Dr. {doctor.nombres} {doctor.apellidos} | "
          f"Paciente: {datos.paciente_id} | "
          f"Medicamento: {datos.medicamento} | "
          f"Dosis: {datos.dosis}")

    return nueva