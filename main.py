# ============================================================
# main.py - SERVICIO DOCTORES
# Ubicación: EcoSistemaSalud/ServicioDoctores/main.py
# ============================================================

import sys
import os
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ── Endpoints clínicos ────────────────────────────────────────────────────────
from Endpoints.post_doctor_diagnostico  import router as router_diagnostico
from Endpoints.post_doctor_orden_medica import router as router_orden
from Endpoints.post_doctor_receta       import router as router_receta
from Endpoints.get_pacientes_atendidos  import router as router_pacientes
from Endpoints.get_consulta_paciente    import router as router_consulta
from Endpoints.get_recetas_paciente     import router as router_recetas
from Endpoints.get_doctores             import router as router_doctores
from Endpoints.get_recetas_por_paciente import router as router_recetas_paciente_publico

# ── Autenticación ─────────────────────────────────────────────────────────────
from Endpoints.post_auth_registro    import router as router_registro
from Endpoints.post_auth_login       import router as router_login
from Endpoints.post_auth_verificar   import router as router_verificar
from Endpoints.post_auth_2fa_externo import router as router_2fa_externo  # NUEVO

# ── Inicializar FastAPI ───────────────────────────────────────────────────────
app = FastAPI(
    title       = "ServicioDoctores - EcoSistemaSalud",
    description = """
    Microservicio de Doctores del Ecosistema de Salud Conectado.

    ## Autenticación Doctor (2FA)
    - **POST /auth/registro**         → Asignar credenciales a un doctor
    - **POST /auth/login**            → PASO 1: verifica credenciales, envía código 2FA
    - **POST /auth/verificar**        → PASO 2: valida código, entrega JWT

    ## 2FA Portal Unificado (paciente/clínica)
    - **POST /auth/2fa/{perfil}/enviar**    → Envía código 2FA a email externo
    - **POST /auth/2fa/{perfil}/verificar** → Verifica código y devuelve token

    ## Endpoints del Doctor
    - POST /doctor/diagnostico
    - POST /doctor/orden-medica
    - POST /doctor/receta
    - GET  /doctor/{id}/pacientes-atendidos
    - GET  /doctor/consulta-paciente
    - GET  /doctor/recetas-paciente
    - GET  /doctores
    - GET  /pacientes/{id}/recetas
    """,
    version = "1.2.0"
)

# ── CORS ──────────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Registrar routers ─────────────────────────────────────────────────────────
app.include_router(router_diagnostico)
app.include_router(router_orden)
app.include_router(router_receta)
app.include_router(router_pacientes)
app.include_router(router_consulta)
app.include_router(router_recetas)
app.include_router(router_doctores)
app.include_router(router_recetas_paciente_publico)

app.include_router(router_registro)
app.include_router(router_login)
app.include_router(router_verificar)
app.include_router(router_2fa_externo)   # POST /auth/2fa/{perfil}/enviar y verificar

# ── Health Check ──────────────────────────────────────────────────────────────
@app.get("/", tags=["ServicioDoctores"])
def raiz():
    return {
        "servicio" : "ServicioDoctores - EcoSistemaSalud",
        "estado"   : "activo",
        "version"  : "1.2.0",
        "endpoints": [
            "POST /auth/registro",
            "POST /auth/login",
            "POST /auth/verificar",
            "POST /auth/2fa/{perfil}/enviar",
            "POST /auth/2fa/{perfil}/verificar",
            "POST /doctor/diagnostico",
            "POST /doctor/orden-medica",
            "POST /doctor/receta",
            "GET  /doctor/{id}/pacientes-atendidos",
            "GET  /doctor/consulta-paciente",
            "GET  /doctor/recetas-paciente",
            "GET  /doctores",
            "GET  /pacientes/{id}/recetas"
        ]
    }

# ── Portales HTML ─────────────────────────────────────────────────────────────
@app.get("/panel", tags=["Panel"], include_in_schema=False)
def panel_doctor():
    """Panel del doctor"""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "panel_doctor.html")
    return FileResponse(path)

@app.get("/login", tags=["Portal"], include_in_schema=False)
def portal_login():
    """Portal unificado de login para los 3 perfiles"""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "login_ecosalud.html")
    return FileResponse(path)

# ── Punto de entrada ──────────────────────────────────────────────────────────
if __name__ == "__main__":
    try:
        print("=" * 55)
        print("[*] ServicioDoctores - EcoSistemaSalud v1.2.0")
        print("[*] Puerto  : 8001")
        print("[*] Docs    : http://localhost:8001/docs")
        print("[*] Panel   : http://localhost:8001/panel")
        print("[*] Login   : http://localhost:8001/login")
        print("=" * 55)
        uvicorn.run(
            "main:app",
            host      = "0.0.0.0",
            port      = 8001,
            reload    = True,
            log_level = "info"
        )
    except KeyboardInterrupt:
        print("\n[!] Interrupción detectada por el usuario.")
    except Exception as e:
        print(f"\n[!] Error inesperado: {e}")
    finally:
        print("[*] Proceso finalizado. Puerto liberado.")
        sys.exit(0)