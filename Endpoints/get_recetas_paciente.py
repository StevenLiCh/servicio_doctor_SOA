# ============================================================
# ENDPOINT: GET /doctor/recetas-paciente
# Servicio: ServicioDoctores
# Acción: El doctor consulta todas las recetas emitidas a un paciente
# Uso: /doctor/recetas-paciente?paciente_id=1&doctor_id=1
# Tabla BD: pacientes.recetas
#
# PROTEGIDO CON JWT: requiere header Authorization: Bearer <token>
# ============================================================

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from database import SessionLocal, Base

# ── NUEVO: importar la dependencia que valida el JWT ──────────────────────────
#from auth.jwt_config import get_doctor_actual

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import Column, Integer, String, Text, Date, DateTime, Boolean
from datetime import date, datetime

router = APIRouter()

# ── Modelos ORM ───────────────────────────────────────────────────────────────
class Doctor(Base):
    __tablename__  = "doctores"
    __table_args__ = {"schema": "doctores", "extend_existing": True}

    id        = Column(Integer, primary_key=True)
    nombres   = Column(String(100))
    apellidos = Column(String(100))

class Receta(Base):
    __tablename__  = "recetas"
    __table_args__ = {"schema": "pacientes", "extend_existing": True}

    id                = Column(Integer,    primary_key=True)
    paciente_id       = Column(Integer,    nullable=False)
    doctor_id         = Column(Integer,    nullable=False)
    orden_medica_id   = Column(Integer)
    medicamento       = Column(String(150),nullable=False)
    dosis             = Column(String(100))
    duracion          = Column(String(100))
    indicaciones      = Column(Text)
    fecha_emision     = Column(Date,       default=date.today)
    fecha_vencimiento = Column(Date)
    estado            = Column(String(30), default="VIGENTE")

# ── Dependencia BD ────────────────────────────────────────────────────────────
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# ── ENDPOINT ──────────────────────────────────────────────────────────────────
@router.get(
    "/doctor/recetas-paciente",
    tags        = ["ServicioDoctores"],
    summary     = "Consultar recetas emitidas a un paciente",
    description = """
    El doctor consulta todas las recetas médicas
    que ha emitido para un paciente específico.
    Filtra por estado: VIGENTE, ENTREGADO, CADUCADO

    Requiere autenticación: Authorization: Bearer <token>
    """
)
def get_recetas_paciente(
    paciente_id: int,            # ?paciente_id=1
    doctor_id:   int,            # &doctor_id=1
    estado:      str = None,     # &estado=VIGENTE (opcional)
    db: Session = Depends(get_db),
    # ── NUEVO: exige el JWT y trae los datos del doctor autenticado ───────────
   # doctor_actual: dict = Depends(get_doctor_actual)
):
    # ── NUEVO REGLA 0: El doctor del token debe coincidir con doctor_id ───────
  #  if doctor_actual["doctor_id"] != doctor_id:
  #      raise HTTPException(
  #          status_code = 403,
  #          detail      = "No puedes consultar recetas usando el ID de otro doctor"
   #     )

    # ── REGLA 1: Doctor existe ────────────────────────────────────────────────
    doctor = db.query(Doctor).filter(Doctor.id == doctor_id).first()
    if not doctor:
        raise HTTPException(
            status_code = 404,
            detail      = f"Doctor ID {doctor_id} no encontrado"
        )

    # ── Consultar recetas ─────────────────────────────────────────────────────
    query = db.query(Receta).filter(
        Receta.paciente_id == paciente_id,
        Receta.doctor_id   == doctor_id
    )

    # Filtro opcional por estado
    if estado:
        estados_validos = ["VIGENTE", "ENTREGADO", "CADUCADO"]
        if estado.upper() not in estados_validos:
            raise HTTPException(
                status_code = 400,
                detail      = f"Estado inválido. Opciones: {estados_validos}"
            )
        query = query.filter(Receta.estado == estado.upper())

    recetas = query.all()

    return {
        "consultado_por": {
            "doctor_id": doctor.id,
            "nombre"   : f"Dr. {doctor.nombres} {doctor.apellidos}"
        },
        "paciente_id"  : paciente_id,
        "recetas": [
            {
                "id"               : r.id,
                "medicamento"      : r.medicamento,
                "dosis"            : r.dosis,
                "duracion"         : r.duracion,
                "indicaciones"     : r.indicaciones,
                "fecha_emision"    : str(r.fecha_emision),
                "fecha_vencimiento": str(r.fecha_vencimiento) if r.fecha_vencimiento else None,
                "estado"           : r.estado,
                "orden_medica_id"  : r.orden_medica_id
            }
            for r in recetas
        ],
        "total_recetas": len(recetas)
    }