# Backend clinica estetica

Este backend esta preparado para trabajar con PostgreSQL remoto, en este proyecto usando Supabase como base de datos de desarrollo y pruebas.

## Estructura

- `accounts/`: autenticacion, roles, usuario personalizado y comando `seed_demo_data`.
- `customers/`: clientes y prospectos.
- `staff/`: especialistas y sus especialidades.
- `catalogs/`: catalogos editables del negocio y catalogos clinicos.
- `operations/`: operaciones, citas y ficha clinica configurable.
- `billing/`: cuotas y pagos con verificacion administrativa.
- `clinical/`: analisis estetico, patologias y alergias.
- `common/`: modelos abstractos compartidos.
- `config/`: configuracion del proyecto Django.

## Variables de entorno

El proyecto carga automaticamente `backend/.env` usando `python-dotenv`.

Usa un `.env` con una conexion PostgreSQL valida para Supabase. Si necesitas una base, puedes copiar `.env.example` y completar las credenciales reales.

## Primer arranque

Desde `D:\proyecto C\backend`:

```powershell
..\env\Scripts\pip.exe install -r requirements.txt
..\env\Scripts\python.exe manage.py migrate
..\env\Scripts\python.exe manage.py seed_demo_data
..\env\Scripts\python.exe manage.py runserver
```

## Vaciar datos y conservar administrador

Si quieres limpiar la base de datos activa pero mantener el administrador:

```powershell
.\scripts\purge_data_keep_admin.ps1 -Force
```

Por defecto preserva `admin`. Si quieres preservar otros usuarios:

```powershell
.\scripts\purge_data_keep_admin.ps1 -Username admin,otro_admin -Force
```

Importante: este script actua sobre la base configurada en `backend/.env`. Si `.env` apunta a Supabase, la limpieza se hace en Supabase.

## Accesos demo

- Admin Django: `admin / admin123456`
- Salud del servicio: `http://127.0.0.1:8000/health/`

## Notas

- El usuario autenticable es `accounts.Usuario`, un modelo personalizado de Django.
- Los datos demo se cargan con `manage.py seed_demo_data`.
- Los catalogos clinicos y muchas opciones del formulario estan pensados para administrarse desde la app web y desde Django admin.
