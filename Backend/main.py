import os
import io

import pandas as pd
import sqlalchemy
import qrcode

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware

from google.cloud import storage

from pydantic import BaseModel

from sqlalchemy import text

from reportlab.platypus import (
    SimpleDocTemplate,
    Spacer,
    Paragraph,
    Image,
)

from reportlab.lib.styles import getSampleStyleSheet





app = FastAPI(title="Inventory Cloud API - Better Demo")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

BUCKET_NAME = os.environ.get("BUCKET_NAME", "bucket-asset-auscc")
FILE_NAME = os.environ.get("FILE_NAME", "inventory_data.csv")

DB_USER = os.environ.get("DB_USER", "postgres")
DB_PASSWORD = os.environ.get("DB_PASSWORD") or os.environ.get("DB_PASS") or ""
DB_NAME = os.environ.get("DB_NAME", "inventory_db")
INSTANCE_CONNECTION_NAME = os.environ.get("INSTANCE_CONNECTION_NAME", "")

_engine = None


class AssetCreate(BaseModel):
    nombre: str
    departamento: str
    sede: str | None = None
    estatus: str


class CheckoutRequest(BaseModel):
    checked_out_to: str
    checked_out_by: str
    expected_return_at: str | None = None
    notes: str | None = None


class ScanRequest(BaseModel):
    scanned_by: str
    scan_location: str
    notes: str | None = None


class CheckInRequest(BaseModel):
    checked_in_by: str



class MaintenanceRequestCreate(BaseModel):
    issue_description: str
    priority: str = "Medium"
    requested_by: str | None = None
    assigned_to: str | None = None
    notes: str | None = None


class TransferRequestCreate(BaseModel):
    to_location: str
    requested_by: str | None = None
    approved_by: str | None = None
    notes: str | None = None


def get_engine():
    global _engine

    if _engine is not None:
        return _engine

    if INSTANCE_CONNECTION_NAME:
        db_url = sqlalchemy.URL.create(
            drivername="postgresql+pg8000",
            username=DB_USER,
            password=DB_PASSWORD,
            database=DB_NAME,
            query={
                "unix_sock": f"/cloudsql/{INSTANCE_CONNECTION_NAME}/.s.PGSQL.5432"
            },
        )
    else:
        db_url = f"postgresql+pg8000://{DB_USER}:{DB_PASSWORD}@127.0.0.1:5432/{DB_NAME}"

    _engine = sqlalchemy.create_engine(
        db_url,
        pool_pre_ping=True,
        pool_size=2,
        max_overflow=3,
    )

    return _engine


def ensure_assets_table():
    engine = get_engine()

    create_table_sql = text("""
        CREATE TABLE IF NOT EXISTS assets (
            id SERIAL PRIMARY KEY,
            nombre VARCHAR(255),
            departamento VARCHAR(255),
            sede VARCHAR(255),
            estatus VARCHAR(255)
        )
    """)

    with engine.begin() as conn:
        conn.execute(create_table_sql)


@app.get("/")
def root():
    return {
        "message": "Inventory Cloud API - Better Demo",
        "docs": "/docs",
        "health": "/health",
        "csv_data": "/assets/csv",
        "sql_data": "/assets",
        "create_sql_asset": "POST /assets",
        "setup_sql": "/setup/sql",
    }


@app.get("/health")
def health():
    return {
        "status": "online",
        "framework": "FastAPI",
        "demo": "csv_and_sql",
    }


@app.get("/debug/config")
def debug_config():
    return {
        "bucket_name": BUCKET_NAME,
        "file_name": FILE_NAME,
        "db_user": DB_USER,
        "db_password_set": bool(DB_PASSWORD),
        "db_name": DB_NAME,
        "instance_connection_name": INSTANCE_CONNECTION_NAME,
    }


@app.get("/assets/csv")
def get_csv_data():
    try:
        storage_client = storage.Client()
        bucket = storage_client.bucket(BUCKET_NAME)
        blob = bucket.blob(FILE_NAME)
        content = blob.download_as_bytes()

        df = pd.read_csv(io.BytesIO(content))
        records = df.fillna("").to_dict(orient="records")

        return {
            "source": "cloud_storage_csv",
            "bucket": BUCKET_NAME,
            "file": FILE_NAME,
            "count": len(records),
            "data": records,
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"CSV read failed: {str(e)}")


@app.get("/setup/sql")
def setup_sql():
    try:
        ensure_assets_table()

        return {
            "status": "ok",
            "message": "SQL table checked or created",
            "table": "assets",
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"SQL setup failed: {str(e)}")


@app.get("/assets")
def get_assets():
    try:
        ensure_assets_table()
        engine = get_engine()

        with engine.connect() as conn:
            result = conn.execute(
                text("""
                    SELECT id, nombre, departamento, sede, estatus
                    FROM assets
                    ORDER BY id
                """)
            )

            records = [
                {
                    "id": row.id,
                    "nombre": row.nombre,
                    "departamento": row.departamento,
                    "sede": row.sede,
                    "estatus": row.estatus,
                }
                for row in result
            ]

        return {
            "source": "cloud_sql_postgresql",
            "count": len(records),
            "data": records,
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"SQL read failed: {str(e)}")


@app.post("/assets")
def create_asset(asset: AssetCreate):
    try:
        ensure_assets_table()
        engine = get_engine()

        with engine.begin() as conn:
            result = conn.execute(
                text("""
                    INSERT INTO assets (nombre, departamento, sede, estatus)
                    VALUES (:nombre, :departamento, :sede, :estatus)
                    RETURNING id, nombre, departamento, sede, estatus
                """),
                {
                    "nombre": asset.nombre,
                    "departamento": asset.departamento,
                    "sede": asset.sede,
                    "estatus": asset.estatus,
                },
            )

            row = result.fetchone()

        return {
            "status": "created",
            "source": "cloud_sql_postgresql",
            "asset": {
                "id": row.id,
                "nombre": row.nombre,
                "departamento": row.departamento,
                "sede": row.sede,
                "estatus": row.estatus,
            },
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"SQL insert failed: {str(e)}")

@app.post("/assets/{asset_id}/scan")
def scan_asset(asset_id: int, scan: ScanRequest):
    try:
        engine = get_engine()

        with engine.begin() as conn:

            asset = conn.execute(
                text("""
                    SELECT id
                    FROM assets
                    WHERE id = :asset_id
                """),
                {"asset_id": asset_id},
            ).fetchone()

            if not asset:
                raise HTTPException(status_code=404, detail="Asset not found")

            conn.execute(
                text("""
                    INSERT INTO asset_scans
                    (
                        asset_id,
                        scanned_by,
                        scan_location,
                        notes
                    )
                    VALUES
                    (
                        :asset_id,
                        :scanned_by,
                        :scan_location,
                        :notes
                    )
                """),
                {
                    "asset_id": asset_id,
                    "scanned_by": scan.scanned_by,
                    "scan_location": scan.scan_location,
                    "notes": scan.notes,
                },
            )

        return {
            "status": "success",
            "message": "Asset scanned",
            "asset_id": asset_id,
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/assets/{asset_id}/checkout")
def checkout_asset(asset_id: int, checkout: CheckoutRequest):
    try:
        engine = get_engine()

        with engine.begin() as conn:

            asset = conn.execute(
                text("""
                    SELECT id
                    FROM assets
                    WHERE id = :asset_id
                """),
                {"asset_id": asset_id},
            ).fetchone()

            if not asset:
                raise HTTPException(status_code=404, detail="Asset not found")

            conn.execute(
                text("""
                    INSERT INTO asset_checkouts
                    (
                        asset_id,
                        checked_out_to,
                        checked_out_by,
                        expected_return_at,
                        notes
                    )
                    VALUES
                    (
                        :asset_id,
                        :checked_out_to,
                        :checked_out_by,
                        :expected_return_at,
                        :notes
                    )
                """),
                {
                    "asset_id": asset_id,
                    "checked_out_to": checkout.checked_out_to,
                    "checked_out_by": checkout.checked_out_by,
                    "expected_return_at": checkout.expected_return_at,
                    "notes": checkout.notes,
                },
            )

            conn.execute(
                text("""
                    UPDATE assets
                    SET
                        checked_out = TRUE,
                        checked_out_by = :checked_out_to,
                        checked_out_at = NOW(),
                        expected_return_at = :expected_return_at,
                        estatus = 'Checked Out'
                    WHERE id = :asset_id
                """),
                {
                    "asset_id": asset_id,
                    "checked_out_to": checkout.checked_out_to,
                    "expected_return_at": checkout.expected_return_at,
                },
            )

        return {
            "status": "success",
            "message": "Asset checked out",
            "asset_id": asset_id,
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/assets/{asset_id}/history")
def asset_history(asset_id: int):

    try:

        engine = get_engine()

        with engine.connect() as conn:

            asset = conn.execute(
                text("""
                    SELECT *
                    FROM assets
                    WHERE id = :asset_id
                """),
                {"asset_id": asset_id},
            ).mappings().fetchone()

            if not asset:
                raise HTTPException(
                    status_code=404,
                    detail="Asset not found"
                )

            scans = conn.execute(
                text("""
                    SELECT *
                    FROM asset_scans
                    WHERE asset_id = :asset_id
                    ORDER BY scanned_at DESC
                """),
                {"asset_id": asset_id},
            ).mappings().all()

            checkouts = conn.execute(
                text("""
                    SELECT *
                    FROM asset_checkouts
                    WHERE asset_id = :asset_id
                    ORDER BY checked_out_at DESC
                """),
                {"asset_id": asset_id},
            ).mappings().all()

            return {
                "asset": dict(asset),
                "scans": [dict(x) for x in scans],
                "checkouts": [dict(x) for x in checkouts],
            }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/assets/{asset_id}/checkin")
def checkin_asset(asset_id: int, checkin: CheckInRequest):

    try:

        engine = get_engine()

        with engine.begin() as conn:

            checkout = conn.execute(
                text("""
                    SELECT id
                    FROM asset_checkouts
                    WHERE asset_id = :asset_id
                      AND returned_at IS NULL
                    ORDER BY checked_out_at DESC
                    LIMIT 1
                """),
                {"asset_id": asset_id},
            ).fetchone()

            if not checkout:
                raise HTTPException(
                    status_code=404,
                    detail="No active checkout found"
                )

            conn.execute(
                text("""
                    UPDATE asset_checkouts
                    SET
                        returned_at = NOW(),
                        checked_in_by = :checked_in_by
                    WHERE id = :checkout_id
                """),
                {
                    "checkout_id": checkout.id,
                    "checked_in_by": checkin.checked_in_by,
                },
            )

            conn.execute(
                text("""
                    UPDATE assets
                    SET
                        checked_out = FALSE,
                        checked_out_by = NULL,
                        checked_out_at = NULL,
                        expected_return_at = NULL,
                        estatus = 'In Use'
                    WHERE id = :asset_id
                """),
                {
                    "asset_id": asset_id,
                },
            )

        return {
            "status": "success",
            "message": "Asset checked in",
            "asset_id": asset_id,
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/dashboard/stats")
def dashboard_stats():

    try:

        engine = get_engine()

        with engine.connect() as conn:

            total_assets = conn.execute(
                text("""
                    SELECT COUNT(*)
                    FROM assets
                """)
            ).scalar()

            checked_out = conn.execute(
                text("""
                    SELECT COUNT(*)
                    FROM assets
                    WHERE checked_out = TRUE
                """)
            ).scalar()

            total_scans = conn.execute(
                text("""
                    SELECT COUNT(*)
                    FROM asset_scans
                """)
            ).scalar()

            total_checkouts = conn.execute(
                text("""
                    SELECT COUNT(*)
                    FROM asset_checkouts
                """)
            ).scalar()

            return {
                "total_assets": total_assets,
                "checked_out": checked_out,
                "available": total_assets - checked_out,
                "total_scans": total_scans,
                "total_checkouts": total_checkouts,
            }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/assets/{asset_id}/maintenance")
def create_maintenance_request(asset_id: int, request: MaintenanceRequestCreate):
    try:
        engine = get_engine()

        with engine.begin() as conn:
            asset = conn.execute(
                text("SELECT id FROM assets WHERE id = :asset_id"),
                {"asset_id": asset_id},
            ).fetchone()

            if not asset:
                raise HTTPException(status_code=404, detail="Asset not found")

            result = conn.execute(
                text("""
                    INSERT INTO maintenance_requests
                    (
                        asset_id,
                        ticket_number,
                        issue_description,
                        priority,
                        requested_by,
                        assigned_to,
                        notes
                    )
                    VALUES
                    (
                        :asset_id,
                        'MT-' || :asset_id || '-' || EXTRACT(EPOCH FROM NOW())::BIGINT,
                        :issue_description,
                        :priority,
                        :requested_by,
                        :assigned_to,
                        :notes
                    )
                    RETURNING id, ticket_number
                """),
                {
                    "asset_id": asset_id,
                    "issue_description": request.issue_description,
                    "priority": request.priority,
                    "requested_by": request.requested_by,
                    "assigned_to": request.assigned_to,
                    "notes": request.notes,
                },
            )

            row = result.fetchone()

            conn.execute(
                text("""
                    UPDATE assets
                    SET estatus = 'Maintenance'
                    WHERE id = :asset_id
                """),
                {"asset_id": asset_id},
            )

        return {
            "status": "success",
            "message": "Maintenance request created",
            "asset_id": asset_id,
            "maintenance_request_id": row.id,
            "ticket_number": row.ticket_number,
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/maintenance")
def get_maintenance_requests():
    try:
        engine = get_engine()

        with engine.connect() as conn:
            rows = conn.execute(
                text("""
                    SELECT
                        mr.id,
                        mr.asset_id,
                        a.asset_tag,
                        a.nombre,
                        mr.ticket_number,
                        mr.issue_description,
                        mr.priority,
                        mr.requested_by,
                        mr.assigned_to,
                        mr.status,
                        mr.opened_at,
                        mr.completed_at
                    FROM maintenance_requests mr
                    LEFT JOIN assets a ON a.id = mr.asset_id
                    ORDER BY mr.opened_at DESC
                """)
            ).mappings().all()

        return {
            "count": len(rows),
            "data": [dict(row) for row in rows],
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/assets/{asset_id}/transfer")
def create_asset_transfer(asset_id: int, transfer: TransferRequestCreate):
    try:
        engine = get_engine()

        with engine.begin() as conn:
            asset = conn.execute(
                text("""
                    SELECT id, sede
                    FROM assets
                    WHERE id = :asset_id
                """),
                {"asset_id": asset_id},
            ).fetchone()

            if not asset:
                raise HTTPException(status_code=404, detail="Asset not found")

            result = conn.execute(
                text("""
                    INSERT INTO asset_transfers
                    (
                        asset_id,
                        from_location,
                        to_location,
                        requested_by,
                        approved_by,
                        approved_at,
                        completed_at,
                        status,
                        notes
                    )
                    VALUES
                    (
                        :asset_id,
                        :from_location,
                        :to_location,
                        :requested_by,
                        :approved_by,
                        NOW(),
                        NOW(),
                        'Completed',
                        :notes
                    )
                    RETURNING id
                """),
                {
                    "asset_id": asset_id,
                    "from_location": asset.sede,
                    "to_location": transfer.to_location,
                    "requested_by": transfer.requested_by,
                    "approved_by": transfer.approved_by,
                    "notes": transfer.notes,
                },
            )

            row = result.fetchone()

            conn.execute(
                text("""
                    UPDATE assets
                    SET
                        sede = :to_location,
                        updated_at = NOW()
                    WHERE id = :asset_id
                """),
                {
                    "asset_id": asset_id,
                    "to_location": transfer.to_location,
                },
            )

        return {
            "status": "success",
            "message": "Asset transferred",
            "asset_id": asset_id,
            "transfer_id": row.id,
            "from_location": asset.sede,
            "to_location": transfer.to_location,
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/transfers")
def get_asset_transfers():
    try:
        engine = get_engine()

        with engine.connect() as conn:
            rows = conn.execute(
                text("""
                    SELECT
                        at.id,
                        at.asset_id,
                        a.asset_tag,
                        a.nombre,
                        at.from_location,
                        at.to_location,
                        at.requested_by,
                        at.approved_by,
                        at.status,
                        at.requested_at,
                        at.completed_at,
                        at.notes
                    FROM asset_transfers at
                    LEFT JOIN assets a ON a.id = at.asset_id
                    ORDER BY at.requested_at DESC
                """)
            ).mappings().all()

        return {
            "count": len(rows),
            "data": [dict(row) for row in rows],
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/assets/import-csv-from-storage")
def import_csv_from_storage():
    try:
        storage_client = storage.Client()
        bucket = storage_client.bucket(BUCKET_NAME)
        blob = bucket.blob(FILE_NAME)
        content = blob.download_as_bytes()

        df = pd.read_csv(io.BytesIO(content)).fillna("")

        processed = 0
        inserted = 0
        updated = 0
        skipped = 0
        errors = []

        engine = get_engine()

        for index, row in df.iterrows():
            try:
                asset_tag = str(row.get("asset_tag", "")).strip()

                if not asset_tag:
                    skipped += 1
                    continue

                purchase_date = str(row.get("purchase_date", "")).strip() or None
                price_raw = str(row.get("price", "")).strip()

                try:
                    purchase_price = float(price_raw) if price_raw else None
                except Exception:
                    purchase_price = None

                with engine.begin() as conn:
                    existing = conn.execute(
                        text("SELECT id FROM assets WHERE asset_tag = :asset_tag"),
                        {"asset_tag": asset_tag},
                    ).fetchone()

                    asset_values = {
                        "asset_tag": asset_tag,
                        "serial_number": str(row.get("serial_number", "")).strip() or None,
                        "nombre": str(row.get("description", "")).strip() or "Unnamed Asset",
                        "description": str(row.get("description", "")).strip() or None,
                        "departamento": str(row.get("department", "")).strip() or None,
                        "sede": str(row.get("campus", "")).strip() or None,
                        "estatus": str(row.get("status", "")).strip() or "In Use",
                        "category": str(row.get("category", "")).strip() or None,
                        "purchase_date": purchase_date,
                        "purchase_price": purchase_price,
                    }

                    if existing:
                        conn.execute(
                            text("""
                                UPDATE assets
                                SET
                                    serial_number = :serial_number,
                                    nombre = :nombre,
                                    description = :description,
                                    departamento = :departamento,
                                    sede = :sede,
                                    estatus = :estatus,
                                    category = :category,
                                    purchase_date = :purchase_date,
                                    purchase_price = :purchase_price,
                                    updated_at = NOW()
                                WHERE asset_tag = :asset_tag
                            """),
                            asset_values,
                        )
                    else:
                        conn.execute(
                            text("""
                                INSERT INTO assets
                                (
                                    asset_tag,
                                    serial_number,
                                    nombre,
                                    description,
                                    departamento,
                                    sede,
                                    estatus,
                                    category,
                                    purchase_date,
                                    purchase_price
                                )
                                VALUES
                                (
                                    :asset_tag,
                                    :serial_number,
                                    :nombre,
                                    :description,
                                    :departamento,
                                    :sede,
                                    :estatus,
                                    :category,
                                    :purchase_date,
                                    :purchase_price
                                )
                            """),
                            asset_values,
                        )
                processed += 1

                if existing:
                    updated += 1
                else:
                    inserted += 1

            except Exception as row_error:
                errors.append({
                    "row": int(index),
                    "asset_tag": str(row.get("asset_tag", "")),
                    "error": str(row_error),
                })

        return {
            "status": "completed",
            "source": "cloud_storage_csv",
            "bucket": BUCKET_NAME,
            "file": FILE_NAME,
            "processed": processed,
            "inserted": inserted,
            "updated": updated,
            "skipped": skipped,
            "errors": len(errors),
            "error_samples": errors[:10],
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/reports/summary")
def reports_summary():
    try:
        engine = get_engine()

        with engine.connect() as conn:
            by_location = conn.execute(
                text("""
                    SELECT COALESCE(sede, 'Unknown') AS location, COUNT(*) AS count
                    FROM assets
                    GROUP BY COALESCE(sede, 'Unknown')
                    ORDER BY count DESC
                    LIMIT 20
                """)
            ).mappings().all()

            by_department = conn.execute(
                text("""
                    SELECT COALESCE(departamento, 'Unknown') AS department, COUNT(*) AS count
                    FROM assets
                    GROUP BY COALESCE(departamento, 'Unknown')
                    ORDER BY count DESC
                    LIMIT 20
                """)
            ).mappings().all()

            by_status = conn.execute(
                text("""
                    SELECT COALESCE(estatus, 'Unknown') AS status, COUNT(*) AS count
                    FROM assets
                    GROUP BY COALESCE(estatus, 'Unknown')
                    ORDER BY count DESC
                """)
            ).mappings().all()

            maintenance_count = conn.execute(
                text("SELECT COUNT(*) FROM maintenance_requests")
            ).scalar()

            transfer_count = conn.execute(
                text("SELECT COUNT(*) FROM asset_transfers")
            ).scalar()

        return {
            "assets_by_location": [dict(row) for row in by_location],
            "assets_by_department": [dict(row) for row in by_department],
            "assets_by_status": [dict(row) for row in by_status],
            "maintenance_count": maintenance_count,
            "transfer_count": transfer_count,
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/admin/cleanup-preview")
def cleanup_preview():
    try:
        engine = get_engine()

        with engine.connect() as conn:
            synthetic_count = conn.execute(
                text("""
                    SELECT COUNT(*)
                    FROM assets
                    WHERE asset_tag LIKE 'ASSET-%'
                """)
            ).scalar()

            real_count = conn.execute(
                text("""
                    SELECT COUNT(*)
                    FROM assets
                    WHERE asset_tag NOT LIKE 'ASSET-%'
                """)
            ).scalar()

            synthetic_with_scans = conn.execute(
                text("""
                    SELECT COUNT(DISTINCT a.id)
                    FROM assets a
                    JOIN asset_scans s ON s.asset_id = a.id
                    WHERE a.asset_tag LIKE 'ASSET-%'
                """)
            ).scalar()

            synthetic_with_checkouts = conn.execute(
                text("""
                    SELECT COUNT(DISTINCT a.id)
                    FROM assets a
                    JOIN asset_checkouts c ON c.asset_id = a.id
                    WHERE a.asset_tag LIKE 'ASSET-%'
                """)
            ).scalar()

            synthetic_with_maintenance = conn.execute(
                text("""
                    SELECT COUNT(DISTINCT a.id)
                    FROM assets a
                    JOIN maintenance_requests m ON m.asset_id = a.id
                    WHERE a.asset_tag LIKE 'ASSET-%'
                """)
            ).scalar()

            synthetic_with_transfers = conn.execute(
                text("""
                    SELECT COUNT(DISTINCT a.id)
                    FROM assets a
                    JOIN asset_transfers t ON t.asset_id = a.id
                    WHERE a.asset_tag LIKE 'ASSET-%'
                """)
            ).scalar()

            sample = conn.execute(
                text("""
                    SELECT
                        id,
                        asset_tag,
                        nombre,
                        sede,
                        estatus
                    FROM assets
                    WHERE asset_tag LIKE 'ASSET-%'
                    ORDER BY id
                    LIMIT 20
                """)
            ).mappings().all()

        return {
            "synthetic_assets": synthetic_count,
            "real_csv_assets": real_count,
            "synthetic_with_scans": synthetic_with_scans,
            "synthetic_with_checkouts": synthetic_with_checkouts,
            "synthetic_with_maintenance": synthetic_with_maintenance,
            "synthetic_with_transfers": synthetic_with_transfers,
            "sample_synthetic_assets": [dict(row) for row in sample],
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/admin/cleanup-plan")
def cleanup_plan():
    try:
        engine = get_engine()

        with engine.connect() as conn:
            total = conn.execute(
                text("SELECT COUNT(*) FROM assets WHERE asset_tag LIKE 'ASSET-%'")
            ).scalar()

            with_activity = conn.execute(
                text("""
                    SELECT COUNT(DISTINCT a.id)
                    FROM assets a
                    WHERE a.asset_tag LIKE 'ASSET-%'
                      AND (
                        EXISTS (SELECT 1 FROM asset_scans s WHERE s.asset_id = a.id)
                        OR EXISTS (SELECT 1 FROM asset_checkouts c WHERE c.asset_id = a.id)
                        OR EXISTS (SELECT 1 FROM maintenance_requests m WHERE m.asset_id = a.id)
                        OR EXISTS (SELECT 1 FROM asset_transfers t WHERE t.asset_id = a.id)
                      )
                """)
            ).scalar()

            safe_to_delete = conn.execute(
                text("""
                    SELECT COUNT(*)
                    FROM assets a
                    WHERE a.asset_tag LIKE 'ASSET-%'
                      AND NOT EXISTS (SELECT 1 FROM asset_scans s WHERE s.asset_id = a.id)
                      AND NOT EXISTS (SELECT 1 FROM asset_checkouts c WHERE c.asset_id = a.id)
                      AND NOT EXISTS (SELECT 1 FROM maintenance_requests m WHERE m.asset_id = a.id)
                      AND NOT EXISTS (SELECT 1 FROM asset_transfers t WHERE t.asset_id = a.id)
                """)
            ).scalar()

        return {
            "synthetic_total": total,
            "synthetic_with_activity": with_activity,
            "synthetic_safe_to_delete": safe_to_delete,
            "action": "Review this first. No records deleted by this endpoint.",
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/admin/delete-demo-assets")
def delete_demo_assets():
    try:
        engine = get_engine()

        with engine.begin() as conn:
            result = conn.execute(
                text("""
                    DELETE FROM assets a
                    WHERE a.asset_tag LIKE 'ASSET-%'
                      AND NOT EXISTS (SELECT 1 FROM asset_scans s WHERE s.asset_id = a.id)
                      AND NOT EXISTS (SELECT 1 FROM asset_checkouts c WHERE c.asset_id = a.id)
                      AND NOT EXISTS (SELECT 1 FROM maintenance_requests m WHERE m.asset_id = a.id)
                      AND NOT EXISTS (SELECT 1 FROM asset_transfers t WHERE t.asset_id = a.id)
                """)
            )

        return {
            "status": "success",
            "message": "Deleted synthetic demo assets with no activity only.",
            "deleted": result.rowcount,
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/assets/{asset_id}/label")
def generate_asset_label(asset_id: int):
    engine = get_engine()

    with engine.connect() as conn:
        asset = conn.execute(
            text("""
                SELECT id, asset_tag, nombre, sede
                FROM assets
                WHERE id = :asset_id
            """),
            {"asset_id": asset_id},
        ).mappings().first()

    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")

    qr_url = (
        "https://inventory-frontend-271456327495.northamerica-south1.run.app"
        f"/?asset_id={asset_id}"
    )

    pdf_buffer = io.BytesIO()
    doc = SimpleDocTemplate(pdf_buffer)
    styles = getSampleStyleSheet()

    content = [
        Paragraph(f"<b>{asset['asset_tag']}</b>", styles["Title"]),
        Paragraph(asset["nombre"], styles["Heading2"]),
        Paragraph(f"Location: {asset['sede']}", styles["BodyText"]),
        Spacer(1, 12),
    ]

    qr = qrcode.make(qr_url)
    qr_file = io.BytesIO()
    qr.save(qr_file, format="PNG")
    qr_file.seek(0)

    content.append(Image(qr_file, width=180, height=180))

    doc.build(content)
    pdf_buffer.seek(0)

    return StreamingResponse(
        pdf_buffer,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f"attachment; filename=asset_{asset_id}_label.pdf"
        },
    )


@app.get("/reports/scan-compliance")
def scan_compliance():

    engine = get_engine()

    with engine.connect() as conn:

        total_assets = conn.execute(
            text("SELECT COUNT(*) FROM assets")
        ).scalar()

        scanned_assets = conn.execute(
            text("""
                SELECT COUNT(DISTINCT asset_id)
                FROM asset_scans
            """)
        ).scalar()

        never_scanned = total_assets - scanned_assets

        return {
            "total_assets": total_assets,
            "scanned_assets": scanned_assets,
            "never_scanned": never_scanned,
            "audit_coverage_percent":
                round(
                    (scanned_assets / total_assets) * 100,
                    2
                ) if total_assets else 0,
        }


@app.get("/reports/audit-exceptions")
def audit_exceptions():
    try:
        engine = get_engine()

        with engine.connect() as conn:
            rows = conn.execute(
                text("""
                    SELECT
                        a.id,
                        a.asset_tag,
                        a.nombre,
                        a.departamento,
                        a.sede,
                        a.estatus,
                        a.last_scan_at,
                        a.last_scan_by,
                        a.last_scan_location
                    FROM assets a
                    WHERE NOT EXISTS (
                        SELECT 1
                        FROM asset_scans s
                        WHERE s.asset_id = a.id
                    )
                    ORDER BY a.sede, a.departamento, a.nombre
                    LIMIT 500
                """)
            ).mappings().all()

        return {
            "count": len(rows),
            "data": [dict(row) for row in rows],
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
